# Enmascarado de PII y guardrails

## Enmascarado de PII

Tres mecanismos deterministas y sin dependencias de NLP/NER, todos en `core/pii.py`
(y `core/data_engine.py` para el primero):

1. **Esquema que ve el LLM (`describe_schema`):** las columnas marcadas
   `pii_sensitive: true` en `semantic_layer.yaml` (hoy solo `Responsable`) nunca
   muestran valores de ejemplo reales en el bloque de esquema del prompt — se
   sustituyen por `<PII - valor no expuesto>`. El LLM sigue viendo que la columna
   existe y su tipo, nunca un dato real. Determinista por código: aunque el LLM
   ignorase la regla del prompt, el dato ni siquiera está ahí.
2. **Emails en texto libre (`mask_emails`):** cualquier email (regex genérico, no
   solo del dominio del dataset) se sustituye por `<EMAIL-PII>`.
3. **Nombres conocidos (`mask_known_pii_names`):** data-driven contra los valores
   reales de las columnas `pii_sensitive` del propio DataFrame — en este dataset,
   los "Responsable" son un conjunto finito y cerrado. Detecta el nombre en
   cualquier orden (`Nombre Apellido` / `Apellido Nombre`) y sin distinguir
   mayúsculas/minúsculas, sustituyéndolo por `<NOMBRE-PII>`.

Los dos enmascarados de texto libre se aplican **en el punto de entrada**, antes
de que la pregunta del usuario cruce hacia el LLM (`server.py::answer_question` /
`chatbot.py::main`) — no solo antes de loguear. Ningún dato PII llega al modelo,
ni siquiera dentro de la pregunta. Como defensa en profundidad, también se aplican
sobre `execution_result`, `final_response` y `generated_code` justo antes de
loguear/responder, por si el código generado expusiera el dato de otra forma (p.
ej. un `.unique()` sobre la columna PII).

`llm/base.py` (regla 4 del prompt de sistema) le dice al LLM cómo comportarse
cuando la pregunta trae `<EMAIL-PII>` o `<NOMBRE-PII>`: si responder exige
identificar a esa persona concreta, debe responder `action: "refuse"` con una
explicación honesta ("no puedo identificar a esa persona porque ese dato está
protegido..."); si la pregunta es un agregado que no depende de ese valor (por
sector, canal, etc.), responde con normalidad.

> **Alcance actual:** esto protege el email (patrón genérico, cualquier dominio) y
> los nombres que YA existen en los datos (`Responsable`). No es un NER general —
> un nombre de persona que no esté en el dataset no se detecta. Ver
> [notas-tecnicas-y-roadmap.md](notas-tecnicas-y-roadmap.md) para el enfoque más
> robusto (tipo Microsoft Presidio) previsto más adelante.

### Tests

`tests/test_pii.py` cubre los tres mecanismos anteriores (unitarios) y dos
escenarios de integración end-to-end contra `server.answer_question` (mockeando el
LLM): una pregunta que exige identificar a una persona por email o por nombre
(debe dar `refuse`, sin que el dato llegue al LLM, al log ni al historial) y una
pregunta agregada que no depende de PII (debe funcionar con normalidad — para
detectar un `refuse` disparándose de más).

---

## Guardrail contra prompt injection y extracción masiva de PII

`core/guardrails.py`: `check_prohibited(question)` se ejecuta justo después del
enmascarado de PII (arriba) y antes de llamar al LLM (`server.py::answer_question`).
Si detecta un motivo de bloqueo, corta ahí mismo — sin gastar ninguna llamada al
LLM — y responde con un mensaje genérico ("No puedo ayudarte con eso. Solo respondo
preguntas sobre las campañas de marketing con los datos disponibles."). El motivo
detallado se registra en el log (`status: "blocked"`, `llm_action: "blocked"`), pero
nunca se expone al usuario, para no revelar qué patrón lo disparó.

Igual que el enmascarado de PII y por el mismo motivo (evitar dependencias nuevas
como Presidio), es un guardrail propio por regex/listas, determinista y sin
llamadas a red ni a ningún modelo:

1. **Cambio de rol / instrucciones (jailbreak, prompt injection):** patrones tipo
   "ignora las reglas anteriores", "ahora eres...", "olvida tu rol", "actúa como",
   "nuevas instrucciones", y sus equivalentes en inglés ("ignore previous
   instructions", "you are now", "pretend you are...").
2. **Extracción masiva de PII sin agregación:** combina una forma de petición
   masiva ("lista todos", "dame todos los nombres/emails/responsables",
   "exporta...") con que la pregunta mencione la columna PII o sus sinónimos
   (reutiliza `semantic_layer.get_pii_columns()`, igual que el enmascarado de PII)
   **sin** ningún término de agregación ("cuánto", "total", "promedio",
   "cuántos"...). Una pregunta como "¿cuántos responsables gestionan campañas de
   Retail?" pasa sin bloqueo porque agrega; "dame todos los nombres de los
   responsables" se bloquea.

Además, `llm/base.py` refuerza la regla 0 del prompt de sistema: si la pregunta no
tiene relación con las campañas de marketing ni con los datos disponibles en `df`
(política, actualidad, opinión personal...), el LLM debe responder `action:
"refuse"` en vez de forzar una traducción a pandas sin sentido.

Como segunda capa, `core/sandbox.py::validate_pii_exfiltration()` revisa el
código pandas ya generado (antes de ejecutarlo) buscando patrones de exfiltración
de la columna PII con código "legítimo" dentro del sandbox: `.unique()` sobre la
columna, asignación de la columna completa sin ningún agregado a `result`, o
`.to_csv()` que referencia esa columna. Es una capa adicional a `validate_code()`
(que bloquea el escape del sandbox: `import`, `os.`, `exec(`...), no un
reemplazo.

> **Alcance actual:** al igual que el enmascarado de PII, es un guardrail basado
> en patrones conocidos, no un clasificador semántico. Se evaluó y descartó NeMo
> Guardrails (requeriría adaptar el cliente OpenCode a la interfaz de LangChain,
> dependencias pesadas — `nemoguardrails` + `langchain*` + embeddings —, un
> lenguaje de configuración nuevo Colang, y llamadas adicionales al LLM por cada
> rail) a favor de reglas propias, coherente con la misma decisión tomada para
> PII/Presidio. Ver [notas-tecnicas-y-roadmap.md](notas-tecnicas-y-roadmap.md).

### Tests

`tests/test_guardrails.py` cubre `check_prohibited()` (intentos de cambio de rol,
preguntas legítimas, extracción masiva sin agregar, extracción agregada
correctamente) y dos escenarios de integración end-to-end contra
`server.answer_question` (LLM mockeado): una pregunta bloqueada nunca llega a
llamar al LLM, y una legítima no se ve afectada.
