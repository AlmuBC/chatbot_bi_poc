"""
Carga el Excel de negocio en un dict {nombre_tabla: DataFrame}.
Solo lectura: nunca se modifica ni se sobreescribe el fichero original.
"""
import pandas as pd
from pathlib import Path


def load_tables(excel_path: Path, table_names: list[str]) -> dict[str, pd.DataFrame]:
    xls = pd.ExcelFile(excel_path)
    tables = {}
    for name in table_names:
        if name not in xls.sheet_names:
            raise ValueError(
                f"La hoja '{name}' definida en la capa semántica no existe en el Excel. "
                f"Hojas disponibles: {xls.sheet_names}"
            )
        tables[name] = pd.read_excel(xls, sheet_name=name)
    return tables


def describe_schema(df: pd.DataFrame, n_examples: int = 3) -> str:
    """Genera un resumen de columnas + tipos + un par de valores de ejemplo,
    para dar contexto real al LLM (sin volcar los 1000 registros)."""
    lines = []
    for col in df.columns:
        dtype = str(df[col].dtype)
        sample_vals = df[col].dropna().unique()[:n_examples]
        sample_str = ", ".join(str(v) for v in sample_vals)
        lines.append(f"    - {col} (tipo: {dtype}) — ejemplos: {sample_str}")
    return "\n".join(lines)
