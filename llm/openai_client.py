"""
EJEMPLO de archivo de conexión: proveedor "openai" (API oficial de OpenAI,
api.openai.com). NO es el proveedor activo por defecto — sirve de plantilla
de cómo añadir un proveedor nuevo (selecciónalo con LLM_PROVIDER=openai en
.env). Usa sus propias variables OPENAI_* (distintas de las OPENCODE_*),
aunque comparta el mismo SDK `openai` que llm/opencode_client.py.
"""
from openai import OpenAI

from config.providers import openai as provider_config
from llm.base import parse_llm_json

PROVIDER_NAME = "openai"

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        kwargs = {"api_key": provider_config.API_KEY}
        if provider_config.BASE_URL:
            kwargs["base_url"] = provider_config.BASE_URL
        _client = OpenAI(**kwargs)
    return _client


def validate() -> None:
    """Comprueba que este proveedor tiene todo lo necesario para funcionar
    (API key, modelo). Se llama al seleccionarlo desde llm/__init__.py, antes
    de construir el cliente o hacer ninguna llamada."""
    provider_config.validate()


def get_model_name() -> str:
    return provider_config.MODEL


def ask_llm_for_code(system_prompt: str, question: str, history: list[dict] | None = None) -> dict:
    messages = [{"role": "system", "content": system_prompt}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": question})

    response = _get_client().chat.completions.create(
        model=provider_config.MODEL,
        messages=messages,
        temperature=0,
    )
    raw = response.choices[0].message.content.strip()
    return parse_llm_json(raw)
