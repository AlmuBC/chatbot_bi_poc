"""
Archivo de conexión con OpenCode (Zen/Go), usando el SDK de OpenAI apuntando
a su endpoint OpenAI-compatible. Es el proveedor activo por defecto (ver
LLM_PROVIDER en .env) y el único probado en producción; los demás archivos en
llm/ son ejemplos de cómo añadir otro proveedor.
"""
import uuid
from openai import OpenAI

from config.providers import opencode as provider_config
from llm.base import parse_llm_json

PROVIDER_NAME = "opencode"

_OPENCODE_SESSION_ID = str(uuid.uuid4())
_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(
            api_key=provider_config.API_KEY,
            base_url=provider_config.BASE_URL,
            default_headers={
                # OpenCode Go exige esta cabecera en cada petición (desde el
                # 5 de septiembre de 2026), o responde 400 MissingSessionID.
                "x-opencode-session": _OPENCODE_SESSION_ID,
                "User-Agent": "chatbot-t2o-poc/0.1",
            },
        )
    return _client


def validate() -> None:
    """Comprueba que este proveedor tiene todo lo necesario para funcionar
    (API key, endpoint, modelo). Se llama al seleccionarlo desde llm/__init__.py,
    antes de construir el cliente o hacer ninguna llamada."""
    provider_config.validate()


def get_model_name() -> str:
    return provider_config.MODEL


def ask_llm_for_code(system_prompt: str, question: str, history: list[dict] | None = None) -> dict:
    """`history` son turnos previos de la misma conversación (ver core/context.py),
    ya en formato {"role": "user"|"assistant", "content": ...}, más recientes al
    final. Se insertan entre el system_prompt y la pregunta actual."""
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
