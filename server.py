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
)
from core.data_engine import load_tables, describe_schema
from llm import build_system_prompt, ask_llm_for_code
from core.context import get_recent_history
from core.sandbox import run_generated_code
from chatbot import format_result_for_display  # reutilizamos el mismo formateador que en el CLI
from observability.logger import log_interaction, pseudonymize_user_email

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("chatbot_googlechat")

app = Flask(__name__)

# --- Carga única al arrancar el servidor (igual que en chatbot.py) ---
_semantic = load_semantic_layer(config.SEMANTIC_LAYER_PATH)
_table_names = list(get_dataframe_variable_map(_semantic).keys())
_dataframes = load_tables(config.EXCEL_PATH, _table_names)
_schema_block = describe_schema(next(iter(_dataframes.values())))
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


def answer_question(question: str, user_email: str | None = None, space_id: str | None = None, thread_id: str | None = None) -> str:
    """Ejecuta el mismo flujo que chatbot.py (CLI) pero devuelve el texto ya formateado,
    listo para meter en la respuesta JSON de Google Chat. Registra cada interacción
    (pregunta, código generado, resultado/error y latencia) vía logger.py."""
    start = time.monotonic()
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

    try:
        decision = ask_llm_for_code(_system_prompt, question, history=history)
    except Exception as e:
        final_response = f"⚠️ Error consultando al modelo: {e}"
        _safe_log_interaction(
            user_email=user_email, question=question, llm_action="error",
            generated_code=None, execution_result=None, execution_error=str(e),
            final_response=final_response, status="error",
            latency_ms=int((time.monotonic() - start) * 1000),
            model=model, semantic_layer_version=_semantic_layer_version,
            space_id=space_id, thread_id=thread_id,
        )
        return final_response

    llm_action = decision.get("action")

    if llm_action == "ask_clarification":
        final_response = decision.get("clarification_question", "Necesito más detalle para responder.")
        status = "clarification"

    elif llm_action == "refuse":
        final_response = f"No puedo darte ese dato en bruto. {decision.get('explanation', '')}"
        status = "refused"

    elif llm_action == "execute_code":
        generated_code = decision.get("code", "")
        try:
            result = run_generated_code(generated_code, _dataframes)
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

    _safe_log_interaction(
        user_email=user_email, question=question, llm_action=llm_action,
        generated_code=generated_code, execution_result=execution_result,
        execution_error=execution_error, final_response=final_response, status=status,
        latency_ms=int((time.monotonic() - start) * 1000),
        model=model, semantic_layer_version=_semantic_layer_version,
        space_id=space_id, thread_id=thread_id,
    )
    return final_response


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

        log.info("Pregunta recibida: %s", question)
        answer = answer_question(question, user_email=user_email, space_id=space_id, thread_id=thread_id)
        return jsonify(chat_text_response(answer))

    # Cualquier otro tipo de evento: respondemos 200 vacío para que Google no reintente.
    return "", 200


@app.route("/", methods=["GET"])
def health():
    return "Chatbot BI webhook activo.", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=config.PORT)
