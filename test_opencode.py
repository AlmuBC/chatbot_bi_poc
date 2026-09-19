"""
Prueba aislada: ¿responde OpenCode correctamente? No toca Flask ni Google Chat.
Ejecuta: py .\\test_opencode.py
"""
import config
from semantic_layer import load_semantic_layer, render_semantic_prompt, get_dataframe_variable_map
from data_engine import load_tables, describe_schema
from llm_client import build_system_prompt, ask_llm_for_code

print(f"Usando modelo: {config.OPENCODE_MODEL}")
print(f"Endpoint: {config.OPENCODE_BASE_URL}")
print(f"API key cargada: {'sí' if config.OPENCODE_API_KEY else 'NO -> revisa tu .env'}\n")

semantic = load_semantic_layer(config.SEMANTIC_LAYER_PATH)
table_names = list(get_dataframe_variable_map(semantic).keys())
dataframes = load_tables(config.EXCEL_PATH, table_names)
schema_block = describe_schema(next(iter(dataframes.values())))
system_prompt = build_system_prompt(render_semantic_prompt(semantic), schema_block)

pregunta = "¿Cuál ha sido el ROAS de las campañas de Search (SEM)?"
print(f"Pregunta de prueba: {pregunta}\n")

try:
    decision = ask_llm_for_code(system_prompt, pregunta)
    print("✅ OpenCode respondió correctamente:")
    print(decision)
except Exception as e:
    print("❌ Falló la llamada a OpenCode:")
    print(repr(e))
