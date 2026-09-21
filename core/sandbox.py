"""
Ejecuta el código Python/pandas que genera el LLM, de forma acotada.

IMPORTANTE (honestidad sobre el alcance de este PoC):
Esto es una sandbox "básica" pensada para el Paso 1 (demostrar que el bot responde
mediante código real y no mediante texto inventado). NO es un aislamiento de
seguridad de nivel producción (proceso aislado, límites de recursos). El Paso 5
añadió una defensa básica contra dos frentes: validate_code() bloquea el escape
del sandbox (import, os., exec...) y validate_pii_exfiltration() bloquea la
exposición de la columna PII en bruto dentro de código "legítimo" (ver
core/guardrails.py para el guardrail previo a la llamada al LLM, que es la
primera línea de defensa).
"""
import re
import pandas as pd
import numpy as np

# Patrones que nunca deben aparecer en el código generado por el LLM.
FORBIDDEN_PATTERNS = [
    r"\bimport\b", r"\b__\w+__\b", r"\bopen\s*\(", r"\bexec\s*\(", r"\beval\s*\(",
    r"\bos\.", r"\bsys\.", r"\bsubprocess\b", r"\bsocket\b", r"\bshutil\b",
    r"\bglobals\s*\(", r"\blocals\s*\(", r"\bgetattr\s*\(", r"\bcompile\s*\(",
]


class UnsafeCodeError(Exception):
    pass


def validate_code(code: str) -> None:
    for pattern in FORBIDDEN_PATTERNS:
        if re.search(pattern, code):
            raise UnsafeCodeError(f"Código rechazado por el sandbox (patrón no permitido: {pattern})")


def validate_pii_exfiltration(code: str, pii_columns: list[str]) -> None:
    """Bloquea patrones habituales de exfiltración de una columna PII en
    bruto en el código generado por el LLM. Es una capa adicional a
    validate_code(): esa función bloquea el ESCAPE del sandbox (import, os.,
    exec...); esta bloquea la EXPOSICIÓN de datos sensibles con código
    "legítimo" dentro del sandbox (p. ej. imprimir todos los responsables sin
    agregar). Reutiliza la misma lista de columnas PII que core/pii.py y
    core/semantic_layer.py::get_pii_columns. Deliberadamente basada en regex,
    sin dependencias nuevas, mismo criterio que el resto del proyecto: no
    pretende detectar cualquier forma posible de exfiltración, solo las más
    habituales."""
    for col in pii_columns:
        esc = re.escape(col)

        # .unique() aplicado directamente sobre la columna PII: expone la
        # lista completa de valores distintos (nombres/emails) en bruto.
        if re.search(rf"\[\s*['\"]{esc}['\"]\s*\]\s*\.unique\s*\(", code):
            raise UnsafeCodeError(
                f"Código rechazado por el sandbox (PII): .unique() sobre la columna '{col}'"
            )

        # `result` queda asignado a la columna PII completa (con o sin
        # .copy()) sin ningún agregado encadenado: la variable que se
        # devuelve al usuario contendría los valores en bruto.
        if re.search(
            rf"result\s*=\s*[\w.\[\]'\" ]*\[\s*['\"]{esc}['\"]\s*\]\s*(?:\.copy\(\))?\s*$",
            code,
            re.MULTILINE,
        ):
            raise UnsafeCodeError(
                f"Código rechazado por el sandbox (PII): exposición en bruto de la columna '{col}' sin agregación"
            )

        # .to_csv() en código que además referencia la columna PII: intento
        # de volcar/exportar datos que incluyen esa columna.
        if re.search(r"\.to_csv\s*\(", code) and re.search(rf"['\"]{esc}['\"]", code):
            raise UnsafeCodeError(
                f"Código rechazado por el sandbox (PII): exportación (.to_csv) que referencia la columna '{col}'"
            )


def run_generated_code(code: str, dataframes: dict[str, pd.DataFrame], pii_columns: list[str] | None = None):
    """
    Ejecuta `code` con:
      - las tablas disponibles como variables (ej. df si hay una sola tabla)
      - pandas (pd) y numpy (np) disponibles
      - builtins reducidos a lo mínimo necesario para cálculos
    El código DEBE dejar el resultado final en una variable llamada `result`.
    Devuelve el valor de `result`.

    `pii_columns` (opcional): columnas marcadas pii_sensitive en la capa
    semántica, para el check adicional de validate_pii_exfiltration().
    """
    validate_code(code)
    validate_pii_exfiltration(code, pii_columns or [])

    safe_builtins = {
        "len": len, "sum": sum, "min": min, "max": max, "round": round,
        "sorted": sorted, "abs": abs, "float": float, "int": int, "str": str,
        "list": list, "dict": dict, "enumerate": enumerate, "range": range,
        "zip": zip, "True": True, "False": False, "None": None,
    }

    local_env = {name: df.copy() for name, df in dataframes.items()}
    # Si solo hay una tabla, exponla también como `df` (atajo cómodo para el LLM)
    if len(dataframes) == 1:
        local_env["df"] = next(iter(dataframes.values())).copy()

    global_env = {"__builtins__": safe_builtins, "pd": pd, "np": np}

    exec(code, global_env, local_env)

    if "result" not in local_env:
        raise ValueError("El código generado no definió la variable `result` con la respuesta.")

    return local_env["result"]
