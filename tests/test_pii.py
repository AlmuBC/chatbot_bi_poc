"""
Tests del enmascarado de PII (Paso 4):

- Frente A (core/data_engine.describe_schema): las columnas marcadas como
  pii_sensitive en la capa semántica no exponen valores de ejemplo reales.
- Frente B (core/pii.mask_emails + server.answer_question): un email que
  aparezca en texto libre (pregunta, resultado de ejecución, respuesta final)
  no debe llegar en crudo ni al log (logs/interactions.jsonl) ni al historial
  de conversación reinyectado (core/context.get_recent_history). Desde el
  cambio de diseño, esto incluye la propia pregunta: el LLM NUNCA ve el email
  real, solo el placeholder <EMAIL-PII> (ver llm/base.py, regla 4), así que si
  responder exige identificar a esa persona concreta, el LLM debe responder
  action="refuse". Una pregunta que no dependa del email (agregado por sector,
  canal, etc.) debe seguir funcionando con normalidad.
- Frente B, nombres propios (core/pii.mask_known_pii_names): igual que el
  email, pero data-driven contra los valores reales de las columnas
  pii_sensitive del DataFrame (p. ej. "Almudena Barreiro"), en vez de un
  patrón sintáctico por regex. Mismo punto de aplicación (antes de que la
  pregunta cruce hacia el LLM) y mismo comportamiento esperado del LLM
  (refuse si depende de esa persona concreta).
"""
import json

import pandas as pd
import pytest

from core.pii import mask_emails, mask_known_pii_names, EMAIL_PLACEHOLDER, NAME_PLACEHOLDER
from core.semantic_layer import load_semantic_layer, get_dataframe_variable_map, get_pii_columns
from core.data_engine import load_tables, describe_schema

import config
from observability.logger import pseudonymize_user_email
import observability.logger as logger_module
import core.context as context_module
import server


# --- Frente A: describe_schema no expone valores reales de columnas PII ---


def test_describe_schema_masks_pii_column_examples():
    semantic = load_semantic_layer(config.SEMANTIC_LAYER_PATH)
    table_names = list(get_dataframe_variable_map(semantic).keys())
    dataframes = load_tables(config.EXCEL_PATH, table_names)
    df = next(iter(dataframes.values()))

    real_values = set(df["Responsable"].dropna().astype(str).unique())
    schema_block = describe_schema(df, pii_columns=get_pii_columns(semantic))

    assert "Responsable" in schema_block
    assert not any(v in schema_block for v in real_values)


# --- Frente B: mask_emails (unidad) ---


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("almudena.b@t2o.com", EMAIL_PLACEHOLDER),
        ("contacta con juan.perez+ventas@sub.dominio.co", f"contacta con {EMAIL_PLACEHOLDER}"),
        ("no hay ningún email aquí", "no hay ningún email aquí"),
        (None, None),
    ],
)
def test_mask_emails_basic_cases(raw, expected):
    assert mask_emails(raw) == expected


def test_mask_emails_keeps_rest_of_text_and_masks_multiple():
    text = "Presupuesto de almudena.b@t2o.com y de otro.gestor@t2o.com: 1234.56 EUR"
    masked = mask_emails(text)
    assert "almudena.b@t2o.com" not in masked
    assert "otro.gestor@t2o.com" not in masked
    assert masked.count(EMAIL_PLACEHOLDER) == 2
    assert "1234.56 EUR" in masked


# --- Frente B: mask_known_pii_names (unidad) ---

_FAKE_RESPONSABLE_DF = pd.DataFrame(
    {"Responsable": ["Almudena Barreiro (almudena.b@t2o.com)", "Juan Perez (juan.perez@t2o.com)"]}
)


def test_mask_known_pii_names_is_case_insensitive_and_order_agnostic():
    text = "¿cuánto gestiona almudena barreiro? habla con Barreiro Almudena también"
    masked = mask_known_pii_names(text, _FAKE_RESPONSABLE_DF, ["Responsable"])
    assert "almudena" not in masked.lower()
    assert "barreiro" not in masked.lower()
    assert masked.count(NAME_PLACEHOLDER) == 2


def test_mask_known_pii_names_does_not_touch_unknown_names():
    text = "¿cuánto gestiona Pedro Sánchez?"
    masked = mask_known_pii_names(text, _FAKE_RESPONSABLE_DF, ["Responsable"])
    assert masked == text


def test_mask_known_pii_names_none_and_no_pii_columns():
    assert mask_known_pii_names(None, _FAKE_RESPONSABLE_DF, ["Responsable"]) is None
    text = "¿cuánto gestiona Almudena Barreiro?"
    assert mask_known_pii_names(text, _FAKE_RESPONSABLE_DF, []) == text


# --- Frente B: integración end-to-end vía server.answer_question ---

PDF_QUESTION = (
    "¿me puedes dar un resumen del presupuesto total gestionado por la cuenta "
    "de almudena.b@t2o.com?"
)
LEAKED_EMAIL = "almudena.b@t2o.com"


@pytest.fixture
def isolated_log(tmp_path, monkeypatch):
    """Redirige el log de interacciones a un fichero temporal, tanto en
    observability.logger (quien escribe) como en core.context (quien lee),
    para no ensuciar logs/interactions.jsonl real ni depender de su estado."""
    tmp_log = tmp_path / "interactions.jsonl"
    monkeypatch.setattr(logger_module, "LOG_FILE", tmp_log)
    monkeypatch.setattr(context_module, "LOG_FILE", tmp_log)
    return tmp_log


def test_answer_question_masks_question_before_llm_and_refuses_when_email_needed(monkeypatch, isolated_log):
    """Reproduce la pregunta del PDF. El email NUNCA debe llegar al LLM: solo
    debe ver <EMAIL-PII>. Como responder exige identificar a esa persona
    concreta, el LLM (simulado aquí, siguiendo la regla 4 de llm/base.py)
    responde action="refuse"; comprobamos que ni el log ni el historial
    reinyectado ni la respuesta al usuario contienen el email en crudo."""
    seen_questions = []

    def fake_ask_llm_for_code(system_prompt, question, history=None):
        seen_questions.append(question)
        # El LLM solo puede ver el placeholder, nunca el email real.
        assert LEAKED_EMAIL not in question
        assert EMAIL_PLACEHOLDER in question
        return {
            "action": "refuse",
            "code": "",
            "explanation": (
                "No puedo identificar a esa persona porque ese dato está protegido; "
                "puedo darte agregados por sector, canal, etc. si te sirve."
            ),
        }

    monkeypatch.setattr(server, "ask_llm_for_code", fake_ask_llm_for_code)

    user_email = "tester@example.com"
    space_id = "spaces/test-space"

    final_response = server.answer_question(
        PDF_QUESTION, user_email=user_email, space_id=space_id, thread_id="threads/1"
    )

    # El LLM recibió la pregunta ya enmascarada, nunca el email real.
    assert seen_questions == [
        "¿me puedes dar un resumen del presupuesto total gestionado por la cuenta "
        f"de {EMAIL_PLACEHOLDER}?"
    ]

    # La respuesta al usuario es un refuse con explicación honesta, no un
    # intento de ejecutar código de filtrado por el email.
    assert LEAKED_EMAIL not in final_response
    assert "No puedo darte ese dato en bruto." in final_response
    assert "identificar a esa persona" in final_response

    # El log no debe contener el email en crudo en ninguna de sus líneas.
    log_lines = isolated_log.read_text(encoding="utf-8").strip().splitlines()
    assert log_lines, "Se esperaba al menos una línea en el log"
    for line in log_lines:
        assert LEAKED_EMAIL not in line
        entry = json.loads(line)
        assert LEAKED_EMAIL not in json.dumps(entry, ensure_ascii=False)
    assert EMAIL_PLACEHOLDER in log_lines[-1]

    # El historial reinyectado (lo que se mandaría al LLM en el siguiente turno)
    # tampoco debe contener el email en crudo.
    user_id = pseudonymize_user_email(user_email)
    history = context_module.get_recent_history(user_id, space_id)
    assert history, "Se esperaba historial reconstruido tras la interacción"
    for message in history:
        assert LEAKED_EMAIL not in message["content"]


def test_aggregate_question_without_email_still_executes_normally(monkeypatch, isolated_log):
    """Caso 3 del encargo: una pregunta que NO depende del email (agregado por
    sector) no debe activar ningún refuse ni verse afectada por el
    enmascarado — evita una regresión donde el refuse se dispare de más."""
    question = "¿cuál es el CPA medio de las campañas gestionadas por el sector Retail_Moda?"
    seen_questions = []

    def fake_ask_llm_for_code(system_prompt, question, history=None):
        seen_questions.append(question)
        return {
            "action": "execute_code",
            "code": (
                "subset = df[df['Cliente_Sector'] == 'Retail_Moda']\n"
                "result = subset['Inversion_EUR'].sum() / subset['Conversiones'].sum()"
            ),
            "explanation": "CPA medio de las campañas del sector Retail_Moda.",
        }

    monkeypatch.setattr(server, "ask_llm_for_code", fake_ask_llm_for_code)
    # No se mockea run_generated_code: se ejecuta de verdad sobre los datos
    # reales cargados por server.py, para probar el camino completo.

    final_response = server.answer_question(
        question, user_email="tester@example.com", space_id="spaces/test-space-2", thread_id="threads/2"
    )

    # La pregunta llega intacta al LLM (no contenía ningún email que enmascarar).
    assert seen_questions == [question]

    assert EMAIL_PLACEHOLDER not in final_response
    assert "No puedo darte ese dato en bruto." not in final_response
    assert "Resultado (calculado por código, no por el LLM):" in final_response


def test_named_person_question_is_refused_and_never_reaches_llm_or_log(monkeypatch, isolated_log):
    """Reproduce el incidente de producción: preguntar por el nombre completo de
    un Responsable (sin usar su email) llegaba en crudo al LLM, que generaba
    código de filtro válido y exponía el desglose completo de esa persona.
    Ahora el nombre se enmascara antes de cruzar hacia el LLM (igual que un
    email), así que debe responder refuse y el nombre no debe aparecer en
    ningún campo persistido ni en la respuesta al usuario."""
    question = "¿cuánto presupuesto gestiona Almudena Barreiro?"
    seen_questions = []

    def fake_ask_llm_for_code(system_prompt, question, history=None):
        seen_questions.append(question)
        # El LLM solo puede ver el placeholder, nunca el nombre real.
        assert "Almudena" not in question
        assert "Barreiro" not in question
        assert NAME_PLACEHOLDER in question
        return {
            "action": "refuse",
            "code": "",
            "explanation": (
                "No puedo identificar a esa persona porque ese dato está protegido; "
                "puedo darte agregados por sector, canal, etc. si te sirve."
            ),
        }

    monkeypatch.setattr(server, "ask_llm_for_code", fake_ask_llm_for_code)

    final_response = server.answer_question(
        question, user_email="tester@example.com", space_id="spaces/test-space-3", thread_id="threads/3"
    )

    # El LLM recibió la pregunta ya enmascarada, nunca el nombre real.
    assert seen_questions == [f"¿cuánto presupuesto gestiona {NAME_PLACEHOLDER}?"]

    # La respuesta al usuario es un refuse, no el desglose de esa persona.
    assert "Almudena" not in final_response
    assert "Barreiro" not in final_response
    assert "No puedo darte ese dato en bruto." in final_response

    # Ni generated_code ni execution_result llegan a generarse (refuse corta
    # antes de llamar a run_generated_code), y el log no contiene el nombre.
    log_lines = isolated_log.read_text(encoding="utf-8").strip().splitlines()
    assert log_lines, "Se esperaba al menos una línea en el log"
    entry = json.loads(log_lines[-1])
    assert entry["generated_code"] is None
    assert entry["execution_result"] is None
    for line in log_lines:
        assert "Almudena" not in line
        assert "Barreiro" not in line
    assert NAME_PLACEHOLDER in log_lines[-1]
