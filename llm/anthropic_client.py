"""
EJEMPLO de archivo de conexión: proveedor "anthropic" (API nativa de
Anthropic, api.anthropic.com). NO es el proveedor activo por defecto — sirve
de plantilla de cómo añadir un proveedor nuevo (selecciónalo con
LLM_PROVIDER=anthropic en .env). Requiere `pip install anthropic`.

Diferencias con el cliente de OpenCode/OpenAI que conviene tener en cuenta:
  - El system prompt se pasa como parámetro `system=...` aparte, no como un
    mensaje más con role="system" dentro de `messages`.
  - `max_tokens` es obligatorio en cada llamada (en OpenAI es opcional).
  - La respuesta se lee de `response.content[0].text`, no de
    `response.choices[0].message.content`.
"""
from config.providers import anthropic as provider_config
from llm.base import parse_llm_json

PROVIDER_NAME = "anthropic"

_client = None


def _get_client():
    global _client
    if _client is None:
        try:
            import anthropic
        except ImportError as e:
            raise RuntimeError(
                "El proveedor 'anthropic' requiere el paquete 'anthropic' "
                "(pip install anthropic), que no está instalado."
            ) from e
        _client = anthropic.Anthropic(api_key=provider_config.API_KEY)
    return _client


def validate() -> None:
    """Comprueba que este proveedor tiene todo lo necesario para funcionar
    (API key, modelo). Se llama al seleccionarlo desde llm/__init__.py, antes
    de construir el cliente o hacer ninguna llamada."""
    provider_config.validate()


def get_model_name() -> str:
    return provider_config.MODEL


def ask_llm_for_code(system_prompt: str, question: str, history: list[dict] | None = None) -> dict:
    messages: list[dict] = list(history) if history else []
    messages.append({"role": "user", "content": question})

    response = _get_client().messages.create(
        model=provider_config.MODEL,
        max_tokens=provider_config.MAX_TOKENS,
        system=system_prompt,
        messages=messages,
        temperature=0,
    )
    raw = response.content[0].text.strip()
    return parse_llm_json(raw)
