"""
Detección de intenciones prohibidas en la pregunta del usuario: intentos de
cambio de rol/instrucciones (jailbreak / prompt injection) y peticiones de
extracción masiva de datos PII en bruto (listar/exportar responsables sin
ningún agregado).

Mismo criterio de diseño que core/pii.py: reglas propias por regex/listas,
deterministas, sin llamadas a red ni a ningún modelo, pensadas para cortar el
flujo ANTES de gastar una llamada al LLM (ver server.py::answer_question, que
llama a check_prohibited() justo después de enmascarar PII y antes de
ask_llm_for_code()). No es un clasificador semántico: es una lista de
patrones conocidos y ampliable, igual que mask_known_pii_names() es
intencionadamente estrecho y no pretende ser NER.
"""
import re

import config
from core.semantic_layer import load_semantic_layer, get_pii_columns

# --- Cambio de rol / instrucciones (jailbreak, prompt injection) ---
# Cada patrón cubre una forma habitual de pedirle al modelo que descarte su
# rol o las reglas del system prompt. Se usa un hueco corto ".{0,N}?" entre
# el verbo y el objeto para tolerar variantes ("ignora TODAS LAS reglas
# anteriores" además de "ignora las reglas anteriores"), sin abrir tanto el
# patrón como para disparar con frases inocuas. Español e inglés,
# case-insensitive (ver _ROLE_CHANGE_RE más abajo).
_ROLE_CHANGE_PATTERNS = [
    r"ignora(?:r|d)?\b.{0,25}?(?:instrucciones|reglas)\s+anteriores",
    r"olvida(?:r)?\b.{0,15}?(?:todo\s+lo\s+anterior|tu\s+rol)",
    r"ahora\s+eres\b",
    r"act[uú]a\s+como\b",
    r"system\s+prompt",
    r"nuevas\s+instrucciones",
    r"disregard\b.{0,15}?(?:the\s+)?(?:above|previous)",
    r"you\s+are\s+now\b",
    r"pretend\s+(?:you\s+are|to\s+be)\b",
    r"ignore\b.{0,25}?(?:previous|above)\s+instructions",
    r"forget\b.{0,15}?(?:your\s+role|everything\s+above)",
]
_ROLE_CHANGE_RE = re.compile("|".join(_ROLE_CHANGE_PATTERNS), re.IGNORECASE)

# --- Extracción masiva de PII en bruto ---
# Formas habituales de pedir un volcado completo (no un cálculo agregado).
_BULK_REQUEST_PATTERNS = [
    r"lista(?:me)?\s+(?:todos|todas)",
    r"dame\s+(?:todos|todas)\s+los?\s+(?:nombres|emails|responsables)",
    r"exporta(?:r|me)?",
    r"todos\s+los\s+datos\s+de",
    r"list\s+all",
    r"export\s+all",
]
_BULK_REQUEST_RE = re.compile("|".join(_BULK_REQUEST_PATTERNS), re.IGNORECASE)

# Si la pregunta contiene alguno de estos términos de agregación, no se
# considera extracción en bruto aunque mencione la columna PII (p. ej.
# "cuántos responsables gestionan campañas de Retail" es un conteo agregado
# legítimo, no un volcado de nombres/emails).
_AGGREGATION_TERMS = [
    "cuánto", "cuanto", "cuántos", "cuantos", "cuántas", "cuantas",
    "promedio", "media", "total", "suma", "count", "average",
]
_AGGREGATION_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(t) for t in _AGGREGATION_TERMS) + r")\b",
    re.IGNORECASE,
)


def _pii_terms(semantic: dict, pii_columns: list[str]) -> list[str]:
    """Nombre de columna + sinónimos declarados en data/semantic_layer.yaml
    para cada columna pii_sensitive (p. ej. "Responsable", "gestor",
    "cuenta", "email", "persona a cargo"). Permite detectar que la pregunta
    se refiere a la columna PII sin depender de un nombre de persona
    concreto (eso ya lo cubre core/pii.py::mask_known_pii_names, que actúa
    sobre valores reales, no sobre el nombre de la columna)."""
    terms: list[str] = []
    for table in semantic.get("tables", []):
        for col in table.get("columns", []):
            if col["name"] in pii_columns:
                terms.append(col["name"])
                terms.extend(str(s) for s in col.get("synonyms", []))
    return terms


def _pii_terms_regex(terms: list[str]) -> re.Pattern | None:
    """Compila los términos PII en un único patrón, permitiendo un plural
    simple en español ("responsable" -> "responsables", "gestor" ->
    "gestores"). Devuelve None si no hay términos (capa semántica sin
    columnas PII), para poder comprobarlo con un simple `is not None`."""
    if not terms:
        return None
    return re.compile(
        r"\b(?:" + "|".join(re.escape(t) for t in terms) + r")(?:es|s)?\b",
        re.IGNORECASE,
    )


# Cargada una sola vez al importar el módulo (igual que server.py carga la
# capa semántica al arrancar): los términos PII no cambian durante la vida
# del proceso.
_semantic = load_semantic_layer(config.SEMANTIC_LAYER_PATH)
_pii_columns = get_pii_columns(_semantic)
_PII_TERMS_RE = _pii_terms_regex(_pii_terms(_semantic, _pii_columns))


def check_prohibited(question: str) -> str | None:
    """Comprueba si `question` debe bloquearse ANTES de llegar al LLM.

    Devuelve `None` si la pregunta puede seguir su curso normal, o un string
    breve (en español, para logging interno) con el motivo de bloqueo si no.
    El mensaje que ve el usuario final es genérico y se construye en el
    punto de llamada (server.py), no aquí, para no revelar qué patrón
    concreto disparó el bloqueo."""
    if not question:
        return None

    if _ROLE_CHANGE_RE.search(question):
        return "intento de cambio de rol/instrucciones (posible prompt injection)"

    if (
        _BULK_REQUEST_RE.search(question)
        and _PII_TERMS_RE is not None
        and _PII_TERMS_RE.search(question)
        and not _AGGREGATION_RE.search(question)
    ):
        return "extracción masiva de datos PII sin agregación"

    return None
