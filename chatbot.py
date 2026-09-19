"""
PoC - Paso 1: Chatbot de consultas de negocio en terminal.

Flujo por cada pregunta:
  1. El LLM (vía OpenCode) traduce la pregunta a código pandas usando la capa semántica.
  2. El código se ejecuta de verdad sobre los datos (sandbox.py) -> nunca se "inventa" un número.
  3. Se muestra el código ejecutado (para poder verificar que la respuesta viene de código,
     no de lenguaje) y el resultado calculado.

Ejecución:
    python chatbot.py
"""
import sys
import pandas as pd

import config
from semantic_layer import load_semantic_layer, render_semantic_prompt, get_dataframe_variable_map
from data_engine import load_tables, describe_schema
from llm_client import build_system_prompt, ask_llm_for_code
from sandbox import run_generated_code, UnsafeCodeError

BANNER = """
==================================================================
  Chatbot de Analítica de Marketing (PoC) - respuestas vía código
  Escribe tu pregunta en lenguaje natural. Ctrl+C o "salir" para terminar.
==================================================================
"""


def format_result_for_display(result) -> str:
    if isinstance(result, pd.DataFrame):
        return "\n" + result.to_string(index=False)
    if isinstance(result, pd.Series):
        return "\n" + result.to_string()
    if isinstance(result, float):
        return f"{result:,.2f}"
    return str(result)


def main():
    print(BANNER)
    print(f"Modelo LLM configurado: {config.OPENCODE_MODEL} (vía {config.OPENCODE_BASE_URL})")

    semantic = load_semantic_layer(config.SEMANTIC_LAYER_PATH)
    table_names = list(get_dataframe_variable_map(semantic).keys())
    dataframes = load_tables(config.EXCEL_PATH, table_names)

    only_df = next(iter(dataframes.values()))
    schema_block = describe_schema(only_df)
    semantic_block = render_semantic_prompt(semantic)
    system_prompt = build_system_prompt(semantic_block, schema_block)

    print(f"Datos cargados: {len(only_df)} registros, tabla(s): {', '.join(table_names)}\n")

    while True:
        try:
            question = input("Tú: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nHasta luego.")
            sys.exit(0)

        if not question:
            continue
        if question.lower() in {"salir", "exit", "quit"}:
            print("Hasta luego.")
            break

        try:
            decision = ask_llm_for_code(system_prompt, question)
        except Exception as e:
            print(f"Bot: ⚠️ Error consultando al modelo: {e}\n")
            continue

        action = decision.get("action")

        if action == "ask_clarification":
            print(f"Bot: {decision.get('clarification_question', 'Necesito más detalle para responder.')}\n")
            continue

        if action == "refuse":
            print(f"Bot: No puedo darte ese dato en bruto. {decision.get('explanation', '')}\n")
            continue

        if action == "execute_code":
            code = decision.get("code", "")
            print(f"[código generado y ejecutado]\n{code}\n")
            try:
                result = run_generated_code(code, dataframes)
            except UnsafeCodeError as e:
                print(f"Bot: ⚠️ Código bloqueado por el sandbox: {e}\n")
                continue
            except Exception as e:
                print(f"Bot: ⚠️ El código generado falló al ejecutarse: {e}\n")
                continue

            print(f"Bot: {decision.get('explanation', '')}")
            print(f"     Resultado (calculado por código, no por el LLM): {format_result_for_display(result)}\n")
            continue

        print(f"Bot: ⚠️ Respuesta inesperada del modelo: {decision}\n")


if __name__ == "__main__":
    main()
