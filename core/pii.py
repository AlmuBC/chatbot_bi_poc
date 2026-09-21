"""
Enmascarado determinista de PII en texto libre.

A diferencia de core/semantic_layer.py (que sabe qué *columnas* son PII porque
así lo declara data/semantic_layer.yaml), este módulo no sabe nada del
esquema de datos: busca patrones de PII directamente en texto libre (la
pregunta del usuario, el resultado de ejecutar código, la respuesta final),
que es donde un dato sensible puede colarse aunque no venga de una columna
marcada como pii_sensitive (p. ej. el usuario escribe un email en la pregunta,
o el código generado por el LLM lo imprime en el resultado).

mask_emails() es genérico (cualquier email válido, por regex). mask_known_pii_names()
es data-driven: un nombre propio no tiene un patrón sintáctico reconocible por regex
(a diferencia de un email), así que en vez de intentar detectar "parece un nombre" se
enmascara contra la lista CONOCIDA de valores reales de las columnas pii_sensitive del
propio DataFrame (en este dataset, los "Responsable" son un conjunto finito y cerrado).
Esto es intencionadamente estrecho: solo protege nombres que ya existen en los datos,
no cualquier nombre de persona en abstracto (eso exigiría NER, fuera de alcance aquí).

Ambas son deliberadamente basadas en regex/listas, sin dependencias nuevas (nada de
spaCy/Presidio): deterministas, sin llamadas a red ni modelos, adecuadas para
aplicarse en el "hot path" de cada interacción antes de loguear, responder o (en el
caso de los nombres conocidos) antes de que la pregunta cruce hacia el LLM.
"""
import re

EMAIL_PLACEHOLDER = "<EMAIL-PII>"
NAME_PLACEHOLDER = "<NOMBRE-PII>"

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

# Los valores reales de "Responsable" en este dataset tienen forma
# "Nombre Apellido (email@dominio)": el nombre de persona es la parte antes
# del paréntesis (el email ya lo cubre mask_emails() por separado).
_PAREN_SUFFIX_RE = re.compile(r"\s*\([^)]*\)\s*$")


def mask_emails(text: str | None) -> str | None:
    """Sustituye cualquier email presente en `text` por EMAIL_PLACEHOLDER.

    Devuelve `None` si `text` es `None` (para poder aplicarse directamente
    sobre campos opcionales como execution_result sin comprobar antes)."""
    if text is None:
        return None
    return _EMAIL_RE.sub(EMAIL_PLACEHOLDER, text)


def _name_variants(raw_value: str) -> set[str]:
    """A partir de un valor real de una columna PII (p. ej.
    'Almudena Barreiro (almudena.b@t2o.com)'), extrae el nombre de persona sin
    el email entre paréntesis y, si tiene forma 'Nombre Apellido', también la
    variante con el orden invertido ('Apellido Nombre'), para detectar ambos
    órdenes en texto libre."""
    name = _PAREN_SUFFIX_RE.sub("", raw_value).strip()
    if not name:
        return set()
    variants = {name}
    parts = name.split()
    if len(parts) == 2:
        variants.add(f"{parts[1]} {parts[0]}")
    return variants


def get_known_pii_names(df, pii_columns) -> list[str]:
    """Extrae, de los valores reales de las columnas `pii_columns` presentes en
    `df`, la lista de nombres de persona conocidos (y sus variaciones de orden
    nombre/apellido). Genérico: funciona para cualquier columna pii_sensitive
    cuyos valores contengan nombres, no solo 'Responsable', por si se añaden
    más columnas PII con nombres en el futuro. Ordenada de más larga a más
    corta para que, al enmascarar, un nombre completo se detecte antes que un
    substring suyo."""
    names: set[str] = set()
    for col in pii_columns:
        if col not in df.columns:
            continue
        for raw_value in df[col].dropna().astype(str).unique():
            names.update(_name_variants(raw_value))
    return sorted(names, key=len, reverse=True)


def mask_known_pii_names(text: str | None, df, pii_columns: list[str]) -> str | None:
    """Sustituye, en `text`, cualquier ocurrencia de un nombre conocido (los
    valores reales de las columnas `pii_columns` del DataFrame `df`, en
    cualquier orden nombre/apellido) por NAME_PLACEHOLDER. Case-insensitive.

    Devuelve `None` si `text` es `None`. Si no hay nombres conocidos (columnas
    PII vacías o inexistentes), devuelve `text` sin modificar."""
    if text is None:
        return None
    names = get_known_pii_names(df, pii_columns)
    if not names:
        return text
    pattern = re.compile(
        r"\b(?:" + "|".join(re.escape(name) for name in names) + r")\b",
        re.IGNORECASE,
    )
    return pattern.sub(NAME_PLACEHOLDER, text)
