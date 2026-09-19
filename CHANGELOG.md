# Changelog

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/).
Este proyecto es una PoC; las versiones se corresponden con los pasos del
proyecto original, no con semver estricto.

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
