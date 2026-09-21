# Memoria de conversación y perfilado adaptativo

## Memoria de conversación de corto plazo

Cada pregunta se procesaba de forma aislada: el LLM no tenía memoria de turnos
anteriores, así que si el bot pedía una aclaración ("¿te refieres a conversiones
o a ingresos en euros?"), la respuesta del usuario ("en euros") le llegaba sin
contexto.

`core/context.py` reconstruye ese contexto a partir del propio
`logs/interactions.jsonl` (no hay estado en memoria del proceso): dada la pareja
`(user_id, space_id)`, busca sus últimas `CONTEXT_MAX_TURNS` interacciones y las
convierte en pares de mensajes `{"role": "user", ...}` / `{"role": "assistant",
...}`, que `llm.ask_llm_for_code` inserta entre el `system_prompt` y la pregunta
actual. Si la última interacción de esa conversación supera
`CONTEXT_INACTIVITY_MINUTES` de antigüedad, se trata como conversación nueva y no
se incluye historial. La lectura del log es *best-effort* igual que la escritura:
si falla, se responde sin contexto en vez de romper la respuesta.

> **Por qué `(user_id, space_id)` y no `thread_id`:** en espacios de Google Chat
> sin "threaded history" activado, cada mensaje entrante llega con un `thread_id`
> distinto aunque sea la misma conversación seguida — comportamiento normal de la
> plataforma, no un error de parseo. Agrupar por `thread_id` (como en una versión
> anterior) hacía que nunca se encontrara historial. `thread_id` se sigue
> guardando en el log como metadata de Google Chat, solo dejó de usarse como
> clave de agrupación del historial.

---

## Perfilado adaptativo del usuario (técnico vs. negocio)

El bot ajusta el estilo de sus preguntas de aclaración (y de sus explicaciones)
según el perfil que infiere del usuario, sin preguntárselo nunca de forma
explícita ni gastar una llamada extra al LLM:

- **Técnico:** preguntas de aclaración mínimas, puede nombrar columnas/métricas
  exactas de la capa semántica (CPA, ROAS, CTR, nombres de columna, sintaxis de
  filtro).
- **Negocio:** preguntas más guiadas, en lenguaje llano, evitando jerga técnica —
  ofrece opciones concretas en vez de nombrar columnas.

**Cómo se infiere:** `llm/base.py` (regla 7 del prompt de sistema) le pide al LLM
que, en la misma respuesta JSON que ya genera para decidir `action`, incluya
también `user_profile` (`"tecnico"` | `"negocio"`) y `profile_confidence`
(`"alta"` | `"media"` | `"baja"`), inferidos de la terminología de la pregunta
actual y del historial de la conversación. Señal técnica: terminología exacta de
la capa semántica. Señal de negocio: lenguaje coloquial o vago. Sin señal clara,
se asume `"negocio"` por defecto. Cuando la señal es insuficiente, se aprovecha la
pregunta aclaratoria que el bot ya hace (el bucle de aclaración de arriba) para
capturar más señal con la respuesta del usuario, en vez de añadir una pregunta
dedicada a perfilar.

**Persistencia entre turnos:** el perfil se recalcula en cada turno (no queda
fijado desde el primer mensaje) usando la memoria conversacional ya existente.
`core/context.py::get_last_known_profile()` lee el perfil de la última interacción
de esa `(user_id, space_id)` en `logs/interactions.jsonl`, y
`server.py::answer_question()` lo añade como una nota interna al final de la
pregunta que ve el LLM (nunca a la pregunta que se loguea ni a la que ve el
usuario), para que el modelo lo mantenga si el turno actual no aporta señal
nueva, en vez de resetear a `"negocio"` cada vez.

**Trazabilidad:** `user_profile` y `profile_confidence` quedan registrados en
cada línea de `logs/interactions.jsonl` (ver
[logging-y-trazabilidad.md](logging-y-trazabilidad.md)). Cuando el guardrail
bloquea la pregunta antes de llamar al LLM, ambos valen `null` (no llegó a
inferirse nada). Si falla la llamada al LLM, `user_profile` conserva el último
perfil conocido de esa conversación (si lo había) y `profile_confidence` vale
`null`.
