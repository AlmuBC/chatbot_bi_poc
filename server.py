"""
PoC - Paso 1 (versión Google Chat): servidor webhook que recibe los mensajes
enviados a la Chat App "Chatbot BI" y responde usando el mismo motor que ya
probamos en terminal (chatbot.py): capa semántica -> LLM (proveedor configurado
en LLM_PROVIDER, ver llm/) genera código pandas -> se ejecuta de verdad en
sandbox -> se devuelve el resultado.

Ejecución:
    python server.py
Y en otra terminal, para exponerlo a internet:
    cloudflared tunnel --url http://localhost:8080
"""
import logging
import threading
import time
import traceback
from flask import Flask, request, jsonify

import config
import llm
from core.semantic_layer import (
    load_semantic_layer,
    render_semantic_prompt,
    get_dataframe_variable_map,
    get_semantic_layer_version,
    get_pii_columns,
)
from core.data_engine import load_tables, describe_schema
from llm import build_system_prompt, ask_llm_for_code
from core.context import get_recent_history, get_last_known_profile
from core.sandbox import run_generated_code
from core.pii import mask_emails, mask_known_pii_names
from core.guardrails import check_prohibited
from chatbot import format_result_for_display  # reutilizamos el mismo formateador que en el CLI
from observability.logger import log_interaction, pseudonymize_user_email

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("chatbot_googlechat")

app = Flask(__name__)

# --- Carga única al arrancar el servidor (igual que en chatbot.py) ---
_semantic = load_semantic_layer(config.SEMANTIC_LAYER_PATH)
_table_names = list(get_dataframe_variable_map(_semantic).keys())
_dataframes = load_tables(config.EXCEL_PATH, _table_names)
_pii_columns = get_pii_columns(_semantic)
_reference_df = next(iter(_dataframes.values()))
_schema_block = describe_schema(_reference_df, pii_columns=_pii_columns)
_semantic_block = render_semantic_prompt(_semantic)
_semantic_layer_version = get_semantic_layer_version(_semantic)
_system_prompt = build_system_prompt(_semantic_block, _schema_block)

log.info("Datos cargados: %d filas, tabla(s): %s", len(next(iter(_dataframes.values()))), _table_names)


def verify_google_request(req) -> bool:
    """Verifica que la petición viene realmente de Google Chat (JWT firmado por Google).
    Se puede desactivar con GOOGLE_CHAT_VERIFY_REQUESTS=false mientras se depura,
    pero en cuanto todo funcione conviene dejarlo activado."""
    if not config.GOOGLE_CHAT_VERIFY_REQUESTS:
        return True

    auth_header = req.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        log.warning("Petición rechazada: falta cabecera Authorization Bearer")
        return False
    token = auth_header.split(" ", 1)[1]

    try:
        from google.oauth2 import id_token
        from google.auth.transport import requests as google_requests

        claims = id_token.verify_oauth2_token(
            token, google_requests.Request(), audience=config.GOOGLE_CHAT_WEBHOOK_URL
        )
        if claims.get("iss") not in ("https://accounts.google.com", "accounts.google.com"):
            log.warning("Petición rechazada: emisor del token inesperado (%s)", claims.get("iss"))
            return False
        # Con las "funciones interactivas" habilitadas (Workspace Add-on), Google firma
        # el token con esta cuenta de servicio en vez de chat@system.gserviceaccount.com.
        # Esa forma de email es la MISMA para cualquier Workspace Add-on de cualquier
        # desarrollador (solo cambia el número de proyecto), así que no basta con
        # comprobar que contiene "gcp-sa-gsuiteaddons": hay que exigir coincidencia
        # exacta con nuestro propio GOOGLE_CHAT_PROJECT_NUMBER.
        expected_email = f"service-{config.GOOGLE_CHAT_PROJECT_NUMBER}@gcp-sa-gsuiteaddons.iam.gserviceaccount.com"
        if claims.get("email") != expected_email:
            log.warning("Petición rechazada: email del token inesperado (%s)", claims.get("email"))
            return False
        return True
    except Exception as e:
        log.warning("Petición rechazada: token inválido (%s)", e)
        return False


def _safe_log_interaction(**kwargs) -> None:
    """Defensa adicional en el punto de llamada: aunque logger.py ya no debería
    lanzar, si algo inesperado ocurre aquí no debe afectar a la respuesta ya calculada."""
    try:
        log_interaction(**kwargs)
    except Exception as e:
        log.error("No se pudo registrar la interacción en el log: %s", e)


def _safe_get_history(user_id: str | None, space_id: str | None) -> list[dict]:
    """Igual que _safe_log_interaction pero para la lectura del historial: si algo
    falla leyendo/parseando logs/interactions.jsonl, la pregunta se responde sin
    contexto en vez de romper la respuesta al usuario."""
    try:
        return get_recent_history(user_id, space_id)
    except Exception as e:
        log.error("No se pudo recuperar el historial de conversación: %s", e)
        return []


def _safe_get_last_profile(user_id: str | None, space_id: str | None) -> str | None:
    """Igual que _safe_get_history pero para el perfil (técnico/negocio) del turno
    anterior: si algo falla, se sigue sin pista de perfil previo (el LLM lo infiere
    desde cero, asumiendo "negocio" por defecto) en vez de romper la respuesta."""
    try:
        return get_last_known_profile(user_id, space_id)
    except Exception as e:
        log.error("No se pudo recuperar el perfil de usuario previo: %s", e)
        return None


def answer_question(question: str, user_email: str | None = None, space_id: str | None = None, thread_id: str | None = None) -> str:
    """Ejecuta el mismo flujo que chatbot.py (CLI) pero devuelve el texto ya formateado,
    listo para meter en la respuesta JSON de Google Chat. Registra cada interacción
    (pregunta, código generado, resultado/error y latencia) vía logger.py."""
    start = time.monotonic()
    # PII: se enmascara la pregunta en el punto de entrada, lo antes posible,
    # antes de que cruce cualquier frontera (red hacia el LLM, disco/log,
    # historial). La pregunta real sin enmascarar no sobrevive más allá de
    # esta línea: ningún dato PII debe llegar al modelo bajo ninguna
    # circunstancia, ni siquiera dentro de la pregunta del usuario.
    question = mask_emails(question)
    question = mask_known_pii_names(question, _reference_df, _pii_columns)

    # Guardrail previo al LLM: si la pregunta es un intento de cambio de rol
    # (jailbreak/prompt injection) o de extracción masiva de PII en bruto,
    # se corta aquí mismo, sin gastar ninguna llamada al LLM. El motivo
    # detallado (blocked_reason) solo se registra en el log; el usuario ve
    # un mensaje genérico que no revela qué patrón lo disparó.
    blocked_reason = check_prohibited(question)
    if blocked_reason:
        final_response = "No puedo ayudarte con eso. Solo respondo preguntas sobre las campañas de marketing con los datos disponibles."
        _safe_log_interaction(
            user_email=user_email, question=question, llm_action="blocked",
            generated_code=None, execution_result=None, execution_error=blocked_reason,
            final_response=final_response, status="blocked",
            latency_ms=int((time.monotonic() - start) * 1000),
            model=llm.MODEL_NAME, semantic_layer_version=_semantic_layer_version,
            space_id=space_id, thread_id=thread_id,
        )
        return final_response

    generated_code = None
    execution_result = None
    execution_error = None
    # Se lee en el momento de la llamada (no se asume fijo globalmente).
    model = llm.MODEL_NAME

    # Se pseudonimiza aquí (y no solo al loguear) porque el historial se agrupa
    # por (user_id, space_id) -no por thread_id, ver core/context.py- y user_id
    # es justo ese identificador pseudonimizado tal y como queda en el log.
    user_id = pseudonymize_user_email(user_email)
    history = _safe_get_history(user_id, space_id)
    last_profile = _safe_get_last_profile(user_id, space_id)

    # Pista de perfil: no se añade al `question` que se loguea/persiste (arriba),
    # solo a la variante que ve el LLM, para no ensuciar interactions.jsonl con
    # una nota interna. Si no hay perfil previo (conversación nueva o sin dato),
    # el LLM lo infiere desde cero y asume "negocio" por defecto (ver prompt).
    llm_question = question
    if last_profile:
        llm_question = (
            f"{question}\n\n"
            f"(Nota interna: perfil inferido en el turno anterior = \"{last_profile}\". "
            f"Mantenlo si esta pregunta no aporta señal nueva, o ajústalo si sí la aporta.)"
        )

    try:
        decision = ask_llm_for_code(_system_prompt, llm_question, history=history)
    except Exception as e:
        final_response = f"⚠️ Error consultando al modelo: {e}"
        _safe_log_interaction(
            user_email=user_email, question=question, llm_action="error",
            generated_code=None, execution_result=None, execution_error=str(e),
            final_response=final_response, status="error",
            latency_ms=int((time.monotonic() - start) * 1000),
            model=model, semantic_layer_version=_semantic_layer_version,
            space_id=space_id, thread_id=thread_id,
            user_profile=last_profile, profile_confidence=None,
        )
        return final_response

    llm_action = decision.get("action")
    # Fallback a last_profile (y no directamente a "negocio") si el LLM omite el
    # campo: así una conversación ya perfilada no "olvida" el perfil por un turno
    # en el que la respuesta del modelo venga incompleta.
    user_profile = decision.get("user_profile") or last_profile or "negocio"
    profile_confidence = decision.get("profile_confidence", "baja")

    if llm_action == "ask_clarification":
        final_response = decision.get("clarification_question", "Necesito más detalle para responder.")
        status = "clarification"

    elif llm_action == "refuse":
        final_response = f"No puedo darte ese dato en bruto. {decision.get('explanation', '')}"
        status = "refused"

    elif llm_action == "off_topic":
        final_response = decision.get("explanation", "")
        status = "off_topic"

    elif llm_action == "execute_code":
        generated_code = decision.get("code", "")
        try:
            result = run_generated_code(generated_code, _dataframes, pii_columns=_pii_columns)
            execution_result = format_result_for_display(result)
            status = "success"
            explicacion = decision.get("explanation", "")
            # Formato Markdown-like que Google Chat sí soporta (negrita con *asteriscos*,
            # bloque de código con comillas triples), para que se pueda verificar que la
            # respuesta viene de código ejecutado y no de lenguaje libre.
            final_response = (
                f"{explicacion}\n\n"
                f"*Resultado (calculado por código, no por el LLM):* {execution_result}\n\n"
                f"```\n{generated_code.strip()}\n```"
            )
        except Exception:
            execution_error = traceback.format_exc()
            status = "error"
            # Mensaje genérico al usuario: nunca el traceback interno del sandbox.
            final_response = "No he podido calcular la respuesta a tu pregunta. ¿Puedes reformularla o intentarlo de nuevo?"

    else:
        final_response = f"⚠️ Respuesta inesperada del modelo: {decision}"
        status = "error"

    # Enmascarado de PII (emails y nombres conocidos) en lo que se persiste en
    # el log y en lo que llega al usuario final. `question` ya llegó
    # enmascarada al LLM (ver arriba); execution_result/final_response/
    # generated_code pueden contener un email o un nombre si el código
    # generado por el LLM lo filtra o expone pese a todo (defensa en
    # profundidad — p. ej. un `.unique()` sobre la columna Responsable).
    execution_result = mask_emails(execution_result)
    final_response = mask_emails(final_response)
    generated_code = mask_emails(generated_code)
    execution_result = mask_known_pii_names(execution_result, _reference_df, _pii_columns)
    final_response = mask_known_pii_names(final_response, _reference_df, _pii_columns)
    generated_code = mask_known_pii_names(generated_code, _reference_df, _pii_columns)

    _safe_log_interaction(
        user_email=user_email, question=question, llm_action=llm_action,
        generated_code=generated_code, execution_result=execution_result,
        execution_error=execution_error, final_response=final_response, status=status,
        latency_ms=int((time.monotonic() - start) * 1000),
        model=model, semantic_layer_version=_semantic_layer_version,
        space_id=space_id, thread_id=thread_id,
        user_profile=user_profile, profile_confidence=profile_confidence,
    )
    return final_response


_CHAT_BOT_SCOPES = ["https://www.googleapis.com/auth/chat.bot"]
_chat_service = None
_chat_service_lock = threading.Lock()

# Deduplicación de reintentos de entrega de Google Chat: si el mismo evento
# llega dos veces, no se vuelve a procesar. Un set en memoria basta para este
# PoC (no persiste entre reinicios ni se comparte entre instancias).
_processed_event_ids: set[str] = set()
_processed_event_ids_lock = threading.Lock()


def _get_chat_service():
    """Cliente autenticado de la Chat API (cacheado tras la primera llamada),
    usado para publicar la respuesta final una vez termina answer_question()."""
    global _chat_service
    if _chat_service is None:
        with _chat_service_lock:
            if _chat_service is None:
                from google.oauth2 import service_account
                from googleapiclient.discovery import build

                creds = service_account.Credentials.from_service_account_file(
                    str(config.GOOGLE_CHAT_SERVICE_ACCOUNT_FILE), scopes=_CHAT_BOT_SCOPES
                )
                _chat_service = build("chat", "v1", credentials=creds, cache_discovery=False)
    return _chat_service


def enviar_mensaje_chat(space_name: str, texto: str, thread_name: str | None = None) -> None:
    """Publica un mensaje en un espacio de Chat vía la API (usado para entregar
    la respuesta calculada en background, fuera del ciclo request/response)."""
    body = {"text": texto}
    if thread_name:
        body["thread"] = {"name": thread_name}
    _get_chat_service().spaces().messages().create(parent=space_name, body=body).execute()


class _PendingReply:
    """Estado compartido entre el hilo en background y el handler síncrono
    /googlechat para un mismo evento, usado para decidir de forma atómica
    quién entrega la respuesta real al usuario (ver _process_and_reply y
    googlechat_webhook): `event` señala que la respuesta ya está calculada,
    `lock` + `claimed` arbitran, sin condición de carrera, si esa respuesta
    se entrega de forma síncrona (dentro del JSON del propio request) o
    asíncrona (vía enviar_mensaje_chat), pero nunca las dos."""

    def __init__(self):
        self.lock = threading.Lock()
        self.event = threading.Event()
        self.claimed = False
        self.answer: str | None = None


def _process_and_reply(question: str, user_email: str | None, space_id: str, thread_id: str | None, state: _PendingReply) -> None:
    """Ejecuta answer_question() en background y publica el resultado en Chat.
    Si algo falla, el usuario recibe un mensaje de error en vez de quedarse
    solo con el "Dame un momento..." inicial sin respuesta posterior.

    Si el handler síncrono todavía está esperando (no ha expirado su timeout,
    ver googlechat_webhook), le cede la respuesta a él -reclamando `state`
    antes que él- en vez de mandarla también por la Chat API: evita una
    llamada de red innecesaria y, sobre todo, una doble respuesta al mismo
    evento."""
    try:
        answer = answer_question(question, user_email=user_email, space_id=space_id, thread_id=thread_id)
        state.answer = answer
        with state.lock:
            if state.claimed:
                # El handler síncrono ya expiró su espera y se quedó con el
                # turno (devolvió el placeholder): nos toca a nosotros.
                deliver_async = True
            else:
                # Llegamos primero: reclamamos el turno para el propio
                # handler síncrono, que sigue bloqueado en state.event.wait().
                state.claimed = True
                deliver_async = False
        state.event.set()
        if deliver_async:
            enviar_mensaje_chat(space_id, answer, thread_id)
    except Exception as e:
        log.error("Fallo procesando/publicando la respuesta en background: %s", e, exc_info=True)
        try:
            enviar_mensaje_chat(
                space_id,
                "⚠️ Ha ocurrido un error inesperado calculando la respuesta. Inténtalo de nuevo.",
                thread_id,
            )
        except Exception as e2:
            log.error("No se pudo notificar el error al espacio de Chat: %s", e2, exc_info=True)


def chat_text_response(text: str) -> dict:
    """Envuelve un texto en la estructura de respuesta que espera un
    Workspace Add-on de Chat (hostAppDataAction/chatDataAction/createMessageAction)."""
    return {
        "hostAppDataAction": {
            "chatDataAction": {
                "createMessageAction": {
                    "message": {"text": text}
                }
            }
        }
    }


@app.route("/googlechat", methods=["POST"])
def googlechat_webhook():
    if not verify_google_request(request):
        return jsonify({"error": "unauthorized"}), 401

    event = request.get_json(silent=True) or {}
    chat = event.get("chat", {})

    if "addedToSpacePayload" in chat:
        return jsonify(chat_text_response("¡Hola! Soy Chatbot BI. Pregúntame lo que quieras sobre las campañas de marketing (ROAS, CPA, inversión, etc.)."))

    if "removedFromSpacePayload" in chat:
        return "", 200

    if "messagePayload" in chat:
        message_payload = chat["messagePayload"]
        message = message_payload.get("message", {})
        # argumentText viene sin la @mención al bot; si no está, usamos text tal cual.
        question = (message.get("argumentText") or message.get("text") or "").strip()
        if not question:
            return jsonify(chat_text_response("No he recibido ningún texto en tu mensaje."))

        # Estructura según la documentación de la API de Chat (Message.sender.email,
        # Space.name, Message.thread.name); no verificada contra un payload real
        # capturado en esta sesión, así que si Google no manda alguna de estas claves
        # tal cual, quedan en None sin romper el flujo.
        user_email = message.get("sender", {}).get("email")
        space_id = message_payload.get("space", {}).get("name")
        thread_id = message.get("thread", {}).get("name")

        # Dedup por id del evento entrante: Google Chat puede reintentar la
        # entrega del mismo evento si no ve una respuesta HTTP a tiempo (hasta
        # GOOGLE_CHAT_SYNC_WAIT_SECONDS de espera aquí abajo), por si acaso.
        event_id = message.get("name") or event.get("eventTime")
        if event_id:
            with _processed_event_ids_lock:
                if event_id in _processed_event_ids:
                    log.info("Evento duplicado ignorado: %s", event_id)
                    return "", 200
                _processed_event_ids.add(event_id)

        if not space_id:
            log.error("No se pudo determinar el espacio de origen del mensaje; no se puede responder en background")
            return jsonify(chat_text_response("No he podido procesar tu mensaje. Inténtalo de nuevo."))

        log.info("Pregunta recibida: %s", question)
        state = _PendingReply()
        threading.Thread(
            target=_process_and_reply,
            args=(question, user_email, space_id, thread_id, state),
            daemon=True,
        ).start()

        # Esperamos a que el background termine, con margen bajo el límite real
        # de 30s de Google Chat (ver GOOGLE_CHAT_SYNC_WAIT_SECONDS). El propio
        # `with state.lock` decide de forma atómica, junto con _process_and_reply,
        # quién entrega la respuesta: si seguimos aquí es porque nadie la había
        # reclamado todavía, así que nos la quedamos nosotros.
        state.event.wait(config.GOOGLE_CHAT_SYNC_WAIT_SECONDS)
        with state.lock:
            if state.claimed:
                # El background terminó a tiempo y ya reclamó el turno para
                # nosotros: devolvemos la respuesta real sin pasar por la
                # Chat API.
                return jsonify(chat_text_response(state.answer))
            state.claimed = True
        # No terminó a tiempo (o falló, ver _process_and_reply): devolvemos el
        # placeholder ahora; si más tarde obtiene una respuesta real o un
        # error, los entrega él mismo de forma asíncrona.
        return jsonify(chat_text_response("Dame un momento, lo estoy calculando…"))

    # Cualquier otro tipo de evento: respondemos 200 vacío para que Google no reintente.
    return "", 200


@app.route("/", methods=["GET"])
def health():
    return "Chatbot BI webhook activo.", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=config.PORT)
