"""
Configuración del proveedor "openai" (API oficial de OpenAI, api.openai.com).
EJEMPLO: no es el proveedor activo por defecto — sirve de plantilla de cómo
añadir un proveedor nuevo (ver llm/openai_client.py). Usa sus propias
variables OPENAI_*, distintas de las OPENCODE_* aunque ambas usen el SDK
`openai` por debajo.
"""
import os
from dotenv import load_dotenv

from config.settings import BASE_DIR

load_dotenv(BASE_DIR / ".env")

API_KEY = os.getenv("OPENAI_API_KEY", "")
MODEL = os.getenv("OPENAI_MODEL", "gpt-5.1")
# Opcional: solo si se quiere apuntar a un endpoint OpenAI-compatible distinto
# del oficial (proxy, Azure OpenAI, etc.). Vacío = usa el endpoint por defecto
# del SDK (api.openai.com).
BASE_URL = os.getenv("OPENAI_BASE_URL", "")


def validate() -> None:
    missing = []
    if not API_KEY:
        missing.append("OPENAI_API_KEY")
    if not MODEL:
        missing.append("OPENAI_MODEL")

    if missing:
        raise RuntimeError(
            "Falta configuración para el proveedor de LLM 'openai': "
            + ", ".join(missing)
            + ". Añade esas variables a tu .env "
            "(la API key la obtienes en https://platform.openai.com/api-keys)."
        )
