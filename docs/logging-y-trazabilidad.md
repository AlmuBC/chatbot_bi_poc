# Logging de trazabilidad

Cada interacción (pregunta, decisión del LLM, código generado, resultado o error de
ejecución, respuesta final, estado, modelo, versión de la capa semántica, perfil de
usuario inferido con su confianza y latencia) se registra en `logs/interactions.jsonl`
(una línea JSON por interacción, formato JSONL), vía `observability/logger.py`.

Campos por línea: `interaction_id`, `timestamp`, `user_id` (pseudonimizado, ver
abajo), `space_id`, `thread_id`, `question`, `llm_action`, `generated_code`,
`execution_result`, `execution_error`, `final_response`, `status`, `latency_ms`,
`user_profile`, `profile_confidence`.

El logging es *best-effort*: si falla la escritura en disco, se avisa por stderr
pero nunca rompe la respuesta al usuario. `logs/` está excluido de git
(`.gitignore`).

## Pseudonimización del email

El email del usuario **nunca se guarda en claro**: se pseudonimiza con
HMAC-SHA256 (`logger.pseudonymize_user_email`, clave `LOG_USER_ID_SECRET`) antes
de escribirse como `user_id`. Es determinista (el mismo email siempre da el mismo
`user_id`, así se pueden agrupar interacciones de un mismo usuario) pero no
reversible sin el secreto.

## Errores de ejecución

Si el código generado falla en el sandbox, el usuario recibe siempre un mensaje
genérico ("No he podido calcular la respuesta a tu pregunta...") — el traceback
real solo queda en `execution_error` dentro del log, nunca se expone en el chat.

## Usos de este log fuera de auditoría

`logs/interactions.jsonl` no es solo un log de auditoría: es también la fuente de
datos de dos funcionalidades del bot, ambas descritas en
[memoria-y-perfilado.md](memoria-y-perfilado.md):

- **Memoria de conversación de corto plazo** (`core/context.py`): reconstruye el
  historial de una conversación leyendo las últimas entradas de este archivo para
  `(user_id, space_id)`.
- **Perfilado adaptativo** (`user_profile` / `profile_confidence`): se lee la
  última entrada conocida para mantener el perfil entre turnos.

## Tests

```bash
pip install -r requirements.txt  # incluye pytest
pytest tests/ -v
```
