"""
Orquestador de proveedores de LLM: decide, en un único sitio, qué archivo de
conexión se usa (LLM_PROVIDER en .env, por defecto "opencode") y expone hacia
el resto del proyecto (chatbot.py, server.py) una interfaz única e
independiente del proveedor: `build_system_prompt()` y `ask_llm_for_code()`.

Al seleccionar un proveedor se llama a su `validate()` (definida en su propio
archivo de conexión, que a su vez delega en config/providers/<proveedor>.py):
si le falta algo para funcionar (API key, modelo...), la ejecución se detiene
aquí mismo con un RuntimeError explicando exactamente qué falta, antes de
cargar datos o abrir el servidor.

Para añadir un proveedor nuevo: crea config/providers/<nombre>.py (config +
validate()) y llm/<nombre>_client.py (con validate(), get_model_name() y
ask_llm_for_code(), ver llm/anthropic_client.py u llm/openai_client.py como
plantilla) y añádelo a _PROVIDER_MODULES.
"""
import importlib

from config.settings import LLM_PROVIDER
from llm.base import build_system_prompt

_PROVIDER_MODULES = {
    "opencode": "llm.opencode_client",
    "anthropic": "llm.anthropic_client",
    "openai": "llm.openai_client",
}


def _load_provider(name: str):
    module_path = _PROVIDER_MODULES.get(name)
    if module_path is None:
        raise RuntimeError(
            f"Proveedor de LLM desconocido: '{name}'. Proveedores disponibles: "
            f"{', '.join(sorted(_PROVIDER_MODULES))}. Revisa LLM_PROVIDER en tu .env."
        )
    module = importlib.import_module(module_path)
    module.validate()
    return module


_provider = _load_provider(LLM_PROVIDER)

PROVIDER_NAME = LLM_PROVIDER
MODEL_NAME = _provider.get_model_name()


def ask_llm_for_code(system_prompt: str, question: str, history: list[dict] | None = None) -> dict:
    return _provider.ask_llm_for_code(system_prompt, question, history=history)


__all__ = ["build_system_prompt", "ask_llm_for_code", "PROVIDER_NAME", "MODEL_NAME"]
