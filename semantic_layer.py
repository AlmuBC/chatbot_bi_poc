"""
Carga la capa semántica (YAML) y la convierte en un bloque de texto
que se inyecta en el prompt del LLM, para que sepa:
  - qué columnas existen y qué sinónimos coloquiales usa la gente para nombrarlas
  - qué métricas calculadas existen y su fórmula exacta
  - qué columnas son PII (dato sensible)

No inventa nada: es una traducción literal del YAML a texto para el prompt.
"""
import yaml
from pathlib import Path


def load_semantic_layer(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_pii_columns(semantic: dict) -> list[str]:
    cols = []
    for table in semantic.get("tables", []):
        for col in table.get("columns", []):
            if col.get("pii_sensitive"):
                cols.append(col["name"])
    return cols


def get_dataframe_variable_map(semantic: dict) -> dict[str, str]:
    """Mapea nombre_de_tabla -> nombre de variable pandas usada en el sandbox."""
    return {table["name"]: "df" for table in semantic.get("tables", [])}


def render_semantic_prompt(semantic: dict) -> str:
    """Convierte la capa semántica en texto legible para el system prompt del LLM."""
    lines = []
    for table in semantic.get("tables", []):
        lines.append(f"Tabla: {table['name']} (variable pandas disponible: df)")
        if table.get("description"):
            lines.append(f"  Descripción: {table['description']}")
        lines.append("  Columnas:")
        for col in table.get("columns", []):
            syns = ", ".join(str(s) for s in col.get("synonyms", []))
            pii = "  [PII - NUNCA muestres el valor crudo, solo agregados/contadores]" if col.get("pii_sensitive") else ""
            lines.append(f"    - {col['name']}: {col.get('description', '')} (sinónimos: {syns}){pii}")

        metrics = table.get("calculated_metrics", [])
        if metrics:
            lines.append("  Métricas calculadas (usa SIEMPRE esta fórmula exacta, no la inventes de otra forma):")
            for m in metrics:
                syns = ", ".join(str(s) for s in m.get("synonyms", []))
                lines.append(f"    - {m['name']}: formula = {m['formula']} (sinónimos: {syns})")
    return "\n".join(lines)
