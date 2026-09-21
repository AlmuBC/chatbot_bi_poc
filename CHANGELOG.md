# Changelog

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/).
Este proyecto es una PoC; las versiones se corresponden con los pasos del
proyecto original, no con semver estricto.

## [0.2.4] — Saneado del proyecto: eliminados scripts de diagnóstico y residuo de entorno — 2026-09-21

### Eliminado
- `test_opencode.py`: script de prueba manual de la conexión con el proveedor de LLM
  activo. No formaba parte del flujo de ejecución del proyecto (ni CLI ni servidor lo
  importaban).
- `test_error_path.py`: script de prueba manual del camino de error de la
  orquestación. Traía una nota pendiente ("no borrar hasta decidir si se deja como
  test de regresión") desde el paso 2; se resuelve eliminándolo por no formar parte
  del flujo de ejecución.
- `get-pip.py`: instalador oficial de pip, residuo de la instalación del entorno, sin
  relación con la lógica del chatbot.
- `README.md` y `.gitignore` actualizados para quitar las referencias a estos tres
  archivos.

### Conservado (no son tests, son herramientas de diagnóstico documentadas)
- `requests.http`: peticiones de prueba para los endpoints del servidor.
- `relanzar-chatbot-bi.md`: runbook operativo para relanzar el servidor tras un parón.

## [0.2.3] — Fix: agrupación de la memoria de conversación por (user_id, space_id) — 2026-09-21

### Corregido
- **Bug confirmado con logs reales**: en espacios de Google Chat sin "threaded
  history" activado, cada mensaje entrante llega con un `thread_id` (`message.thread.name`)
  distinto aunque sea la misma conversación seguida (mismo `user_id` y `space_id`, tres
  `thread_id` distintos en 77 segundos) — comportamiento normal de la plataforma en ese
  tipo de espacio, no un error de parseo del payload. Como `get_recent_history()` agrupaba
  por `thread_id`, nunca encontraba historial previo y la memoria de conversación de corto
  plazo (0.2.2) no funcionaba en la práctica.
- `context.py`: `get_recent_history()` ahora recibe `(user_id, space_id)` en vez de
  `thread_id` y filtra el log por esa combinación. El resto de la lógica no cambia
  (ventana de `CONTEXT_MAX_TURNS` turnos, expiración por `CONTEXT_INACTIVITY_MINUTES`).
  `thread_id` se sigue guardando en el log como metadata de Google Chat, simplemente deja
  de usarse como clave de agrupación del historial.
- `server.py`: `answer_question()` pseudonimiza el email (`pseudonymize_user_email()`) antes
  de leer el historial, ya que ahora `_safe_get_history()`/`get_recent_history()` necesitan
  ese `user_id` (mismo valor que se termina guardando en el log) en vez de `thread_id`.

### Caso límite confirmado
- Un mismo usuario hablando en dos espacios distintos a la vez sigue tratándose como dos
  conversaciones separadas (la clave incluye `space_id`, no solo `user_id`).

## [0.2.2] — Memoria de conversación de corto plazo — 2026-09-21

### Añadido
- `context.py` (nuevo): `get_recent_history(thread_id)` reconstruye el historial
  reciente de una conversación a partir de `logs/interactions.jsonl` (sin estado en
  memoria del proceso ni cambios en el formato del log). Lee solo la cola del fichero
  (últimas ~500 líneas, en bloques desde el final) en vez de todo desde el principio,
  filtra por `thread_id`, y devuelve las últimas `CONTEXT_MAX_TURNS` interacciones como
  pares de mensajes `user`/`assistant` — usando `final_response` para el turno del
  asistente en todos los estados (incluida la `clarification_question`, que ya queda
  copiada ahí por `server.py`). Si la última interacción del thread supera
  `CONTEXT_INACTIVITY_MINUTES` de antigüedad, devuelve historial vacío (conversación
  nueva). Nunca lanza excepción por fichero ausente, vacío o con líneas corruptas.
- `config.py`, `.env`, `.env.example`: nuevas variables `CONTEXT_MAX_TURNS` (por
  defecto `3`) y `CONTEXT_INACTIVITY_MINUTES` (por defecto `20`).
- `llm_client.py`: `ask_llm_for_code()` acepta ahora un parámetro `history` opcional y
  construye `messages` como `[system_prompt] + history + [pregunta actual]` en vez de
  solo `[system_prompt] + [pregunta actual]`.
- `server.py`: `answer_question()` recupera el historial vía `_safe_get_history()`
  (mismo patrón *best-effort* que `_safe_log_interaction`) antes de llamar al LLM.

### Contexto
- Hasta ahora cada pregunta se procesaba de forma aislada: si el bot pedía una
  aclaración ("¿conversiones o ingresos en euros?"), la respuesta del usuario ("en
  euros") le llegaba al LLM sin ningún contexto de la pregunta original.
- Este cambio no toca el formato ni el contenido de lo que ya se escribía en
  `logs/interactions.jsonl` — reutiliza el log existente como única fuente del
  historial, sin añadir un almacén de conversación aparte.

## [0.2.1] — Pseudonimización de PII y versionado de la capa semántica en logs — 2026-09-21

### Añadido
- `logger.py`: `pseudonymize_user_email()` deriva un `user_id` determinista y no
  reversible (HMAC-SHA256 con la nueva clave `LOG_USER_ID_SECRET`) a partir del email
  del usuario. `log_interaction()` ya no escribe el email en claro en
  `logs/interactions.jsonl`, solo este `user_id`.
- `logger.py` / `server.py`: cada entrada del log incluye ahora también `model` (el
  modelo de OpenCode usado en esa llamada, leído en el momento de la petición) y
  `semantic_layer_version`, para poder trazar con qué definición de métricas se generó
  cada respuesta.
- `data/semantic_layer.yaml`: nueva clave raíz `version: "1.0.0"`.
- `semantic_layer.py`: `get_semantic_layer_version()` para leer esa versión.
- `config.py`, `.env.example`: nueva variable obligatoria `LOG_USER_ID_SECRET` (el
  servidor no arranca sin ella, igual que ya ocurría con `OPENCODE_API_KEY`).

### Cambiado
- **Formato de `logs/interactions.jsonl`**: el campo `user_email` se sustituye por
  `user_id` (pseudonimizado), y se añaden los campos `model` y
  `semantic_layer_version`. No es retrocompatible con líneas ya escritas por la
  versión anterior del logger.

## [0.2.0] — Paso 2: Logging de trazabilidad — 2026-09-19

### Añadido
- `logger.py`: función `log_interaction()` que registra cada interacción (pregunta,
  decisión del LLM, código generado, resultado/error de ejecución, respuesta final,
  estado y latencia) como una línea JSON en `logs/interactions.jsonl` (JSONL,
  `ensure_ascii=False`). Escritura protegida con un lock a nivel de módulo para
  evitar líneas intercaladas si Flask corre en modo threaded. Es *best-effort*:
  nunca lanza una excepción hacia arriba; si falla la escritura, se informa por
  stderr sin afectar a la respuesta al usuario.
- `server.py`: `answer_question()` ahora mide la latencia total de la interacción,
  captura `execution_error` con el traceback real cuando el sandbox falla, y llama a
  `log_interaction()` al final de cada camino (éxito, aclaración, rehúso, error),
  con una defensa adicional (`_safe_log_interaction`) en el propio punto de llamada.
  Se extraen `user_email`, `space_id` y `thread_id` del payload de Google Chat
  (`message.sender.email`, `messagePayload.space.name`, `message.thread.name`) para
  incluirlos en el log.
- `test_error_path.py`: script para verificar de forma aislada el camino de error
  completo (sandbox → orquestación → log), forzando un código pandas que referencia
  una columna inexistente, sin depender de que el LLM real genere código inválido.
- `logs/` añadido a `.gitignore` (contenido generado en runtime, no versionado).

### Cambiado
- **Comportamiento visible para el usuario**: si el código generado falla al
  ejecutarse en el sandbox, ahora se responde siempre con un mensaje genérico
  ("No he podido calcular la respuesta a tu pregunta. ¿Puedes reformularla o
  intentarlo de nuevo?"), en vez del mensaje anterior que podía filtrar el error
  crudo del sandbox o del intérprete. El detalle técnico real (traceback completo)
  se conserva únicamente en `execution_error` dentro del log.
- Eliminado el manejo diferenciado de `UnsafeCodeError` en `server.py`: ahora
  cualquier excepción del sandbox (código bloqueado o fallo en ejecución) se trata
  de forma unificada — mismo mensaje genérico al usuario, detalle solo en el log.

### Pendiente (deuda técnica conocida, no bloqueante)
- Aún no verificado contra un payload real de Google Chat si `sender.email`,
  `space.name` y `thread.name` llegan tal cual se asume (basado en la documentación
  de la API de Chat, no en tráfico capturado en esta sesión).
- Sin rotación ni límite de tamaño de `logs/interactions.jsonl` (crece indefinidamente).
- `test_error_path.py` queda pendiente de decidir si se conserva como test de
  regresión permanente o se elimina.

## [0.1.0] — Paso 1: Chatbot conversacional funcionando de punta a punta — 2026-09-19

### Añadido
- Capa semántica (`semantic_layer.yaml`) que traduce lenguaje coloquial a columnas,
  sinónimos y fórmulas oficiales (CTR, CPA, ROAS) sobre el dataset de 1,000 campañas
  (`marketing_performance_1000_t2o.xlsx`).
- `llm_client.py`: cliente OpenCode (SDK de OpenAI apuntando a su endpoint Go) cuya
  única función es traducir la pregunta del usuario en código pandas — nunca calcula
  la métrica directamente.
- `sandbox.py`: ejecución acotada del código generado (bloqueo de `import`, `open(`,
  `os.`, `eval(`, etc.), para que el resultado siempre salga de ejecutar código real
  contra los datos, nunca de una respuesta "inventada" por el LLM.
- `chatbot.py`: interfaz de chat en terminal (CLI) para probar el motor sin depender
  de Google Chat.
- `server.py`: servidor Flask que expone el mismo motor como Chat App de Google Chat
  (verificación de peticiones, parseo de eventos, formato de respuesta).
- `test_opencode.py`: script aislado para probar la conexión con OpenCode sin tocar
  Flask ni Google Chat.
- `requests.http`: peticiones de prueba para los endpoints del servidor (health check
  y los distintos tipos de evento del webhook), sin depender de Google Chat real.
- Chat App de Google Chat ("Chatbot BI") creada y configurada íntegramente con una
  cuenta de Gmail personal, expuesta a internet vía VS Code Port Forwarding (dev tunnels).

### Corregido durante la implementación
- **400 `MissingSessionID` de OpenCode Go**: el endpoint exige desde el 5 de
  septiembre de 2026 una cabecera `x-opencode-session` estable por proceso. Añadida
  en `llm_client.py` junto con un `User-Agent` identificable.
- **405 en `POST /`**: la "URL del extremo HTTP" configurada en Google Cloud Console
  no incluía el sufijo `/googlechat`.
- **401 "The requests library is not installed"**: `google-auth` necesita la
  librería `requests` para verificar tokens; añadida a `requirements.txt`.
- **401 "Token used too early"**: reloj del sistema (Windows) desincronizado;
  solucionado sincronizando la hora del equipo, no es un bug de código.
- **401 "Token has wrong audience"**: la Chat App usa el modo de autenticación por
  URL de endpoint (`audienceType: app-url`), no por número de proyecto. Añadida la
  variable `GOOGLE_CHAT_WEBHOOK_URL` y cambiada la verificación para usarla como
  `audience` en vez de `GOOGLE_CHAT_PROJECT_NUMBER`.
- **401 "email del token inesperado"**: con "funciones interactivas" habilitadas
  (estilo Workspace Add-on), Google firma el token con
  `service-<projectNumber>@gcp-sa-gsuiteaddons.iam.gserviceaccount.com`, no con
  `chat@system.gserviceaccount.com`. Esa forma de email es compartida por cualquier
  Workspace Add-on, así que la verificación exige coincidencia exacta con el propio
  `GOOGLE_CHAT_PROJECT_NUMBER`, no solo que contenga `gcp-sa-gsuiteaddons`.
- **Bot silencioso pese a devolver 200**: el payload de entrada de Google Chat no usa
  el formato "clásico" (`{"type": "MESSAGE", ...}`) sino el de complemento de
  Workspace (`chat.messagePayload` / `chat.addedToSpacePayload` /
  `chat.removedFromSpacePayload`), y el formato de respuesta debe envolverse en
  `hostAppDataAction.chatDataAction.createMessageAction.message` — un `{"text": ...}`
  a secas se descarta en silencio. Corregido el parseo de eventos y añadida la función
  `chat_text_response()` en `server.py`.
- **Túnel devolviendo la pantalla de login de GitHub en vez del servidor**: la
  visibilidad del puerto en VS Code había vuelto a "Private"; corregido re-marcándolo
  como "Public" y verificando con un GET externo antes de dar el paso por bueno.

### Hallazgo relevante (fuera de lo documentado por Google)
- La documentación oficial de Google Chat afirma que "la plataforma de desarrollo de
  Chat apps solo está disponible para cuentas de Google Workspace" y que no se puede
  desarrollar ni probar con `@gmail.com`. Este proyecto demuestra en la práctica que
  sí es posible crear, configurar, instalar y usar una Chat App completa con una
  cuenta de Gmail personal, de principio a fin.

### Pendiente (deuda técnica conocida, no bloqueante)
- La URL del túnel cambia en cada reinicio de VS Code/dev tunnels, requiriendo
  actualizar `GOOGLE_CHAT_WEBHOOK_URL` y la configuración de Google Cloud Console.
- `server.py` corre con el servidor de desarrollo de Flask (no apto para producción).
- Sin logging persistente de preguntas/código/respuestas (Paso 2).
- Sin Gateway intermedio tipo LiteLLM (Paso 3).
- Sin enmascarado real de PII, más allá de una regla en el prompt del LLM (Paso 4).
- Sin guardarraíles activos contra prompt injection (Paso 5).
- Sin perfiles de usuario según nivel técnico (Paso 6).
