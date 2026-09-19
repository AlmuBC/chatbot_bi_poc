"""
Ejecuta el código Python/pandas que genera el LLM, de forma acotada.

IMPORTANTE (honestidad sobre el alcance de este PoC):
Esto es una sandbox "básica" pensada para el Paso 1 (demostrar que el bot responde
mediante código real y no mediante texto inventado). NO es un aislamiento de
seguridad de nivel producción. El endurecimiento serio (proceso aislado, límites de
recursos, defensa activa contra prompt injection) es precisamente el Paso 5 del
proyecto, que abordaremos más adelante.
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


def run_generated_code(code: str, dataframes: dict[str, pd.DataFrame]):
    """
    Ejecuta `code` con:
      - las tablas disponibles como variables (ej. df si hay una sola tabla)
      - pandas (pd) y numpy (np) disponibles
      - builtins reducidos a lo mínimo necesario para cálculos
    El código DEBE dejar el resultado final en una variable llamada `result`.
    Devuelve el valor de `result`.
    """
    validate_code(code)

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
