"""
Configuración del proveedor "opencode": el que está activo por defecto y en
producción (ver llm/opencode_client.py). Endpoint OpenAI-compatible de
OpenCode Zen/Go.
"""
import os
from dotenv import load_dotenv

from config.settings import BASE_DIR

load_dotenv(BASE_DIR / ".env")

API_KEY = os.getenv("OPENCODE_API_KEY", "")
BASE_URL = os.getenv("OPENCODE_BASE_URL", "https://opencode.ai/zen/go/v1")
MODEL = os.getenv("OPENCODE_MODEL", "glm-5.2")


def validate() -> None:
    missing = []
    if not API_KEY:
        missing.append("OPENCODE_API_KEY")
    if not BASE_URL:
        missing.append("OPENCODE_BASE_URL")
    if not MODEL:
        missing.append("OPENCODE_MODEL")

    if missing:
        raise RuntimeError(
            "Falta configuración para el proveedor de LLM 'opencode': "
            + ", ".join(missing)
            + ". Copia .env.example a .env y rellena esas variables "
            "(la API key la obtienes en https://opencode.ai/auth)."
        )
