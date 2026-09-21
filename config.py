"""
Configuración central del PoC.
Lee variables de entorno (desde .env si existe) y expone constantes simples.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()  # carga el archivo .env si está presente

BASE_DIR = Path(__file__).resolve().parent

OPENCODE_API_KEY = os.getenv("OPENCODE_API_KEY", "")
OPENCODE_BASE_URL = os.getenv("OPENCODE_BASE_URL", "https://opencode.ai/zen/go/v1")
OPENCODE_MODEL = os.getenv("OPENCODE_MODEL", "glm-5.2")

EXCEL_PATH = BASE_DIR / os.getenv("EXCEL_PATH", "data/marketing_performance_1000_t2o.xlsx")
SEMANTIC_LAYER_PATH = BASE_DIR / os.getenv("SEMANTIC_LAYER_PATH", "data/semantic_layer.yaml")

GOOGLE_CHAT_PROJECT_NUMBER = os.getenv("GOOGLE_CHAT_PROJECT_NUMBER", "")
GOOGLE_CHAT_WEBHOOK_URL = os.getenv("GOOGLE_CHAT_WEBHOOK_URL")
GOOGLE_CHAT_VERIFY_REQUESTS = os.getenv("GOOGLE_CHAT_VERIFY_REQUESTS", "true").lower() == "true"
PORT = int(os.getenv("PORT", "8080"))

# Secreto usado para pseudonimizar user_email en logs/interactions.jsonl (HMAC-SHA256,
# ver logger.py). Debe mantenerse fuera del código y no compartirse con el log.
LOG_USER_ID_SECRET = os.getenv("LOG_USER_ID_SECRET", "")

# Memoria de conversación de corto plazo (ver context.py): cuántos turnos previos
# del mismo thread_id se incluyen como historial en la llamada al LLM, y a partir
# de cuántos minutos de inactividad se considera que la conversación "empieza de
# cero" (no se incluye historial).
CONTEXT_MAX_TURNS = int(os.getenv("CONTEXT_MAX_TURNS", "3"))
CONTEXT_INACTIVITY_MINUTES = int(os.getenv("CONTEXT_INACTIVITY_MINUTES", "20"))

if not OPENCODE_API_KEY:
    raise RuntimeError(
        "Falta OPENCODE_API_KEY. Copia .env.example a .env y añade tu API key "
        "(la obtienes en https://opencode.ai/auth)."
    )

if not LOG_USER_ID_SECRET:
    raise RuntimeError(
        "Falta LOG_USER_ID_SECRET. Añade a tu .env una clave secreta aleatoria "
        "(ej. genera una con `python -c \"import secrets; print(secrets.token_hex(32))\"`); "
        "se usa para pseudonimizar el email del usuario en logs/interactions.jsonl."
    )
