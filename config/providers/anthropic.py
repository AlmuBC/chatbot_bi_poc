"""
Configuración del proveedor "anthropic" (API nativa de Anthropic,
api.anthropic.com). EJEMPLO: no es el proveedor activo por defecto — sirve de
plantilla de cómo añadir un proveedor nuevo. Requiere `pip install anthropic`
(ver llm/anthropic_client.py).
"""
import os
from dotenv import load_dotenv

from config.settings import BASE_DIR

load_dotenv(BASE_DIR / ".env")

API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5")
# Anthropic exige max_tokens en cada llamada (a diferencia de OpenCode/OpenAI,
# donde es opcional).
MAX_TOKENS = int(os.getenv("ANTHROPIC_MAX_TOKENS", "4096"))


def validate() -> None:
    missing = []
    if not API_KEY:
        missing.append("ANTHROPIC_API_KEY")
    if not MODEL:
        missing.append("ANTHROPIC_MODEL")

    if missing:
        raise RuntimeError(
            "Falta configuración para el proveedor de LLM 'anthropic': "
            + ", ".join(missing)
            + ". Añade esas variables a tu .env "
            "(la API key la obtienes en https://console.anthropic.com/settings/keys)."
        )
