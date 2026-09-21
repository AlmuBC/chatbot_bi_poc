"""
Prueba aislada: ¿responde el proveedor de LLM configurado (LLM_PROVIDER, por
defecto "opencode") correctamente? No toca Flask ni Google Chat.
Ejecuta: py .\\test_opencode.py
"""
import config
import llm
from config.providers import opencode as opencode_config
from core.semantic_layer import load_semantic_layer, render_semantic_prompt, get_dataframe_variable_map
from core.data_engine import load_tables, describe_schema
from llm import build_system_prompt, ask_llm_for_code

print(f"Proveedor: {llm.PROVIDER_NAME}")
print(f"Modelo: {llm.MODEL_NAME}")
if llm.PROVIDER_NAME == "opencode":
    print(f"Endpoint: {opencode_config.BASE_URL}")
    print(f"API key cargada: {'sí' if opencode_config.API_KEY else 'NO -> revisa tu .env'}\n")

semantic = load_semantic_layer(config.SEMANTIC_LAYER_PATH)
table_names = list(get_dataframe_variable_map(semantic).keys())
dataframes = load_tables(config.EXCEL_PATH, table_names)
schema_block = describe_schema(next(iter(dataframes.values())))
system_prompt = build_system_prompt(render_semantic_prompt(semantic), schema_block)

pregunta = "¿Cuál ha sido el ROAS de las campañas de Search (SEM)?"
print(f"Pregunta de prueba: {pregunta}\n")

try:
    decision = ask_llm_for_code(system_prompt, pregunta)
    print(f"✅ {llm.PROVIDER_NAME} respondió correctamente:")
    print(decision)
except Exception as e:
    print(f"❌ Falló la llamada a {llm.PROVIDER_NAME}:")
    print(repr(e))
