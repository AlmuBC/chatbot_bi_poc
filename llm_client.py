"""
Cliente para OpenCode (Zen/Go), usando el SDK de OpenAI apuntando a su endpoint
OpenAI-compatible. El LLM NUNCA calcula la métrica "de memoria": su único trabajo
es traducir la pregunta coloquial en código pandas, usando la capa semántica como
diccionario. El cálculo real lo hace pandas en sandbox.py.
"""
import json
import uuid
from openai import OpenAI
import config

_OPENCODE_SESSION_ID = str(uuid.uuid4())

_client = OpenAI(
    api_key=config.OPENCODE_API_KEY,
    base_url=config.OPENCODE_BASE_URL,
    default_headers={
        "x-opencode-session": _OPENCODE_SESSION_ID,
        "User-Agent": "chatbot-t2o-poc/0.1",
    },
)

SYSTEM_PROMPT_TEMPLATE = """Eres el motor de traducción de un chatbot de analítica de marketing.
Tu ÚNICA función es convertir la pregunta del usuario en código Python/pandas que calcule
la respuesta exacta a partir de los datos reales. NUNCA respondas con el número directamente
en lenguaje natural, y NUNCA inventes cifras: todo dato numérico debe salir de ejecutar código
sobre el DataFrame `df`.

CAPA SEMÁNTICA (columnas, sinónimos y fórmulas oficiales —úsalas literalmente, no inventes otras):
{semantic_block}

ESQUEMA REAL DE LOS DATOS (df), con tipos y ejemplos de valores:
{schema_block}

REGLAS:
1. Si la pregunta es lo bastante clara para calcularse con las columnas/fórmulas de arriba,
   responde con action="execute_code" y escribe código pandas que deje el resultado final
   en una variable llamada `result` (puede ser un número, una Serie, un dict o un DataFrame
   pequeño ya agregado). Usa siempre las fórmulas oficiales de la capa semántica para las
   métricas calculadas (CTR, CPA, ROAS...), nunca una fórmula distinta.
2. Si la pregunta es ambigua (por ejemplo, no se especifica si se quiere en euros o en
   conversiones, o no se indica el alcance: toda la agencia vs. un sector concreto),
   responde con action="ask_clarification" y NO generes código.
3. Si la pregunta pide directamente datos personales/identificativos marcados como PII
   (nombres, emails, "quién es responsable de..."), responde con action="execute_code" pero
   el código debe trabajar solo con AGREGADOS (sumas, medias, conteos) y nunca debe incluir
   la columna PII cruda en el `result`. Si la pregunta busca exclusivamente exponer el dato
   PII en bruto sin ningún agregado posible, responde action="refuse".
4. Nunca uses import, ni acceso a archivos, red o sistema. Solo pandas (pd), numpy (np) y
   el DataFrame `df` ya cargado en memoria.
5. Responde EXCLUSIVAMENTE con un JSON válido, sin texto adicional, sin markdown, con esta forma:
{{
  "action": "execute_code" | "ask_clarification" | "refuse",
  "code": "código pandas si action=execute_code, si no cadena vacía",
  "explanation": "una frase breve en español describiendo qué calcula el código, o el motivo del refuse",
  "clarification_question": "pregunta al usuario si action=ask_clarification, si no cadena vacía"
}}
"""


def build_system_prompt(semantic_block: str, schema_block: str) -> str:
    return SYSTEM_PROMPT_TEMPLATE.format(semantic_block=semantic_block, schema_block=schema_block)


def ask_llm_for_code(system_prompt: str, question: str) -> dict:
    response = _client.chat.completions.create(
        model=config.OPENCODE_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": question},
        ],
        temperature=0,
    )
    raw = response.choices[0].message.content.strip()

    # Algunos modelos envuelven el JSON en ```json ... ``` pese a las instrucciones; lo limpiamos.
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"El modelo no devolvió un JSON válido. Respuesta cruda:\n{raw}") from e
