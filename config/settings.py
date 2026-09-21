"""
Configuración general del proyecto: NO incluye nada específico de un proveedor
de LLM (eso vive en `config/providers/`, un archivo por proveedor). Lee
variables de entorno (desde .env si existe) y expone constantes simples.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Esta configuración vive en config/settings.py, un nivel por debajo de la
# raíz del proyecto: BASE_DIR debe apuntar a la raíz, no a config/.
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

# Qué proveedor de LLM usar: selecciona el archivo de conexión que se carga
# en llm/__init__.py (uno de "opencode", "anthropic", "openai"...). Cada
# proveedor tiene su propio archivo de configuración en config/providers/.
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "opencode")

EXCEL_PATH = BASE_DIR / os.getenv("EXCEL_PATH", "data/marketing_performance_1000_t2o.xlsx")
SEMANTIC_LAYER_PATH = BASE_DIR / os.getenv("SEMANTIC_LAYER_PATH", "data/semantic_layer.yaml")

GOOGLE_CHAT_PROJECT_NUMBER = os.getenv("GOOGLE_CHAT_PROJECT_NUMBER", "")
GOOGLE_CHAT_WEBHOOK_URL = os.getenv("GOOGLE_CHAT_WEBHOOK_URL")
GOOGLE_CHAT_VERIFY_REQUESTS = os.getenv("GOOGLE_CHAT_VERIFY_REQUESTS", "true").lower() == "true"
PORT = int(os.getenv("PORT", "8080"))

# Secreto usado para pseudonimizar user_email en logs/interactions.jsonl (HMAC-SHA256,
# ver observability/logger.py). Debe mantenerse fuera del código y no compartirse con el log.
LOG_USER_ID_SECRET = os.getenv("LOG_USER_ID_SECRET", "")

# Memoria de conversación de corto plazo (ver core/context.py): cuántos turnos previos
# del mismo thread_id se incluyen como historial en la llamada al LLM, y a partir
# de cuántos minutos de inactividad se considera que la conversación "empieza de
# cero" (no se incluye historial).
CONTEXT_MAX_TURNS = int(os.getenv("CONTEXT_MAX_TURNS", "3"))
CONTEXT_INACTIVITY_MINUTES = int(os.getenv("CONTEXT_INACTIVITY_MINUTES", "20"))

if not LOG_USER_ID_SECRET:
    raise RuntimeError(
        "Falta LOG_USER_ID_SECRET. Añade a tu .env una clave secreta aleatoria "
        "(ej. genera una con `python -c \"import secrets; print(secrets.token_hex(32))\"`); "
        "se usa para pseudonimizar el email del usuario en logs/interactions.jsonl."
    )
