"""
Script temporal para verificar el camino de error de la orquestación de forma
aislada, sin depender de que el LLM real genere código que falle.

Fuerza manualmente una decisión llm_action="execute_code" con código pandas que
referencia una columna inexistente (Columna_Que_No_Existe_XYZ), para comprobar
que:
  - sandbox.py (run_generated_code) lanza la excepción esperada.
  - el flujo de orquestación completo (server.answer_question) la captura y
    devuelve el mensaje genérico al usuario, sin filtrar el traceback interno.
  - log_interaction() registra correctamente status="error" y execution_error.

No borrar hasta decidir si se deja como test de regresión.
"""
import server  # importa y ejecuta la carga de datos/semantic layer real del proyecto
from core.sandbox import run_generated_code  # función real de core/sandbox.py, misma firma que usa server.py

BAD_CODE = "result = df['Columna_Que_No_Existe_XYZ'].sum()"


def _fake_ask_llm_for_code(system_prompt, question, history=None):
    """Sustituye la llamada real al LLM: fuerza execute_code con código que falla."""
    return {
        "action": "execute_code",
        "code": BAD_CODE,
        "explanation": "Prueba forzada del camino de error del sandbox.",
        "clarification_question": "",
    }


def main():
    # Monkeypatch del nombre que usa server.answer_question() internamente.
    server.ask_llm_for_code = _fake_ask_llm_for_code

    # Primero, confirmar que el sandbox por sí solo lanza la excepción esperada.
    try:
        run_generated_code(BAD_CODE, server._dataframes)
        print("[sandbox] ERROR: se esperaba una excepción y no se lanzó ninguna.")
    except Exception as e:
        print(f"[sandbox] Excepción esperada capturada: {type(e).__name__}: {e}")

    # Ahora, el flujo de orquestación completo (incluye log_interaction al final).
    final_response = server.answer_question(
        "¿pregunta de prueba que dispara el código malo?",
        user_email="test@example.com",
        space_id="spaces/TEST",
        thread_id="spaces/TEST/threads/TEST",
    )

    print("\n[orquestación] final_response devuelto al usuario:")
    print(final_response)


if __name__ == "__main__":
    main()
