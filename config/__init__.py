"""
Configuración central del proyecto, dividida en dos partes:

  - `config.settings`: configuración general, no ligada a ningún proveedor de
    LLM (rutas de datos, Google Chat, logging, memoria de conversación, y el
    selector `LLM_PROVIDER`).
  - `config.providers`: un archivo de configuración por proveedor de LLM
    (OpenCode, Anthropic, OpenAI...), cada uno con su propia validación.

Se reexportan aquí las constantes de `settings` para poder seguir escribiendo
`import config; config.EXCEL_PATH` desde el resto del proyecto.
"""
from config.settings import (
    BASE_DIR,
    LLM_PROVIDER,
    EXCEL_PATH,
    SEMANTIC_LAYER_PATH,
    GOOGLE_CHAT_PROJECT_NUMBER,
    GOOGLE_CHAT_WEBHOOK_URL,
    GOOGLE_CHAT_VERIFY_REQUESTS,
    GOOGLE_CHAT_SERVICE_ACCOUNT_FILE,
    GOOGLE_CHAT_SYNC_WAIT_SECONDS,
    PORT,
    LOG_USER_ID_SECRET,
    CONTEXT_MAX_TURNS,
    CONTEXT_INACTIVITY_MINUTES,
)

__all__ = [
    "BASE_DIR",
    "LLM_PROVIDER",
    "EXCEL_PATH",
    "SEMANTIC_LAYER_PATH",
    "GOOGLE_CHAT_PROJECT_NUMBER",
    "GOOGLE_CHAT_WEBHOOK_URL",
    "GOOGLE_CHAT_VERIFY_REQUESTS",
    "GOOGLE_CHAT_SERVICE_ACCOUNT_FILE",
    "GOOGLE_CHAT_SYNC_WAIT_SECONDS",
    "PORT",
    "LOG_USER_ID_SECRET",
    "CONTEXT_MAX_TURNS",
    "CONTEXT_INACTIVITY_MINUTES",
]
