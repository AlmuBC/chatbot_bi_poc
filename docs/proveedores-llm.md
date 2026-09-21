# Cambiar de proveedor de LLM

Todo el código específico de cada proveedor vive en dos sitios, compartimentados
por proveedor y por responsabilidad:

- `config/providers/<proveedor>.py`: lee las variables de entorno del proveedor y
  expone `validate()`, que comprueba que están todas (API key, modelo...) y, si
  falta algo, lanza `RuntimeError` diciendo exactamente qué falta.
- `llm/<proveedor>_client.py`: el "archivo de conexión" — construye el cliente
  del SDK correspondiente y expone `ask_llm_for_code()` con la misma firma para
  todos.

`llm/__init__.py` es el orquestador: lee `LLM_PROVIDER` de `.env`, carga el
archivo de conexión correspondiente y llama a su `validate()` **antes** de cargar
datos o levantar el servidor — si falta configuración, la ejecución se detiene
ahí mismo con el error concreto, en vez de fallar más tarde a mitad de una
conversación.

Hoy solo `opencode` está probado en producción. `anthropic` y `openai` son
plantillas de ejemplo listas para usar (cambia `LLM_PROVIDER` en `.env` y rellena
sus variables); para `anthropic` hace falta además `pip install anthropic`. Para
añadir un proveedor nuevo: copia uno de los ejemplos en ambas carpetas y
regístralo en `llm/__init__.py::_PROVIDER_MODULES`.

## Notas técnicas descubiertas durante la implementación (OpenCode / Google Chat)

Particularidades reales con las que nos encontramos (no están en la
documentación "de libro" de Google/OpenCode, o están dispersas):

- **OpenCode Go exige la cabecera `x-opencode-session`** en cada petición (desde
  el 5 de septiembre de 2026), o responde 400 `MissingSessionID`. Ya está
  implementado en `llm/opencode_client.py` con un UUID estable por proceso.
- **El formato de eventos de Google Chat no es el "clásico"**
  (`{"type": "MESSAGE", ...}`). Con "funciones interactivas" habilitadas, Google
  manda el formato de **complemento de Workspace**: el tipo de evento se deduce
  de qué clave hay dentro de `chat` (`messagePayload` / `addedToSpacePayload` /
  `removedFromSpacePayload`), y el texto está en
  `chat.messagePayload.message.argumentText` / `.text`.
- **El formato de respuesta también cambia**: hay que envolver el texto en
  `{"hostAppDataAction": {"chatDataAction": {"createMessageAction": {"message":
  {"text": ...}}}}}`. Un `{"text": ...}` a secas se descarta en silencio (Google
  responde 200 pero no muestra nada en el chat).
- **El token JWT de verificación** viene firmado por
  `service-<GOOGLE_CHAT_PROJECT_NUMBER>@gcp-sa-gsuiteaddons.iam.gserviceaccount.com`
  (no por `chat@system.gserviceaccount.com`, que es el emisor de las apps
  "clásicas"), y su `audience` es la URL completa del webhook, no el número de
  proyecto — de ahí las dos variables `GOOGLE_CHAT_PROJECT_NUMBER` y
  `GOOGLE_CHAT_WEBHOOK_URL` en `config/settings.py`.
- **El reloj del sistema debe estar sincronizado**: la verificación del JWT falla
  con "Token used too early" si el reloj de Windows está desajustado unos
  segundos.
