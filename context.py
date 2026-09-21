"""
Memoria de conversación de corto plazo: reconstruye el historial reciente de un
thread_id a partir de logs/interactions.jsonl (sin tocar el formato ni el
contenido de lo que logger.py ya escribe ahí), para poder incluirlo en el
array `messages` que se envía al LLM y así resolver bucles de aclaración
("¿ingresos o conversiones?" -> "en euros").
"""
import json
from datetime import datetime, timedelta, timezone

import config
from logger import LOG_FILE

# Cuántas líneas finales del log se inspeccionan como máximo al buscar
# interacciones de un thread_id. No es una solución de índices "de producción":
# para el volumen de una demo, leer solo la cola del fichero (en vez de todo
# desde el principio) ya evita el caso realmente costoso.
_TAIL_SCAN_LINES = 500
_TAIL_CHUNK_BYTES = 8192


def _tail_lines(path, max_lines: int) -> list[str]:
    """Devuelve hasta las últimas `max_lines` líneas no vacías de un fichero de
    texto, leyendo desde el final en bloques en vez de cargar todo el fichero."""
    with open(path, "rb") as f:
        f.seek(0, 2)
        pos = f.tell()
        buffer = b""
        while pos > 0 and buffer.count(b"\n") <= max_lines:
            read_size = min(_TAIL_CHUNK_BYTES, pos)
            pos -= read_size
            f.seek(pos)
            buffer = f.read(read_size) + buffer

    raw_lines = buffer.split(b"\n")
    if pos > 0:
        # La primera línea leída puede estar cortada a mitad si no llegamos al
        # principio del fichero: se descarta.
        raw_lines = raw_lines[1:]

    text_lines = [ln.decode("utf-8", errors="replace") for ln in raw_lines if ln.strip()]
    return text_lines[-max_lines:]


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def get_recent_history(thread_id: str | None) -> list[dict]:
    """Reconstruye el historial reciente de un thread_id, listo para insertarse
    en `messages` entre el system_prompt y la pregunta actual.

    Devuelve lista vacía (conversación nueva) si: no hay thread_id, el fichero
    de log no existe/está vacío, no hay interacciones previas de ese thread, o
    la última interacción de ese thread supera CONTEXT_INACTIVITY_MINUTES de
    antigüedad. Nunca lanza excepción por fichero ausente o líneas corruptas."""
    if not thread_id or not LOG_FILE.exists():
        return []

    try:
        raw_lines = _tail_lines(LOG_FILE, _TAIL_SCAN_LINES)
    except OSError:
        return []

    entries = []
    for line in raw_lines:
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if entry.get("thread_id") == thread_id:
            entries.append(entry)

    if not entries:
        return []

    entries.sort(key=lambda e: e.get("timestamp") or "")

    last_ts = _parse_timestamp(entries[-1].get("timestamp"))
    if last_ts is None:
        return []

    now = datetime.now(timezone.utc)
    if now - last_ts > timedelta(minutes=config.CONTEXT_INACTIVITY_MINUTES):
        return []

    recent = entries[-config.CONTEXT_MAX_TURNS:]

    messages: list[dict] = []
    for entry in recent:
        question = entry.get("question")
        # final_response ya contiene lo que el bot dijo en cada caso, incluida
        # la clarification_question cuando status == "clarification" (server.py
        # la copia ahí antes de loguear), así que basta un único campo para
        # representar el turno del asistente en cualquier status.
        final_response = entry.get("final_response")
        if not question or not final_response:
            continue
        messages.append({"role": "user", "content": question})
        messages.append({"role": "assistant", "content": final_response})

    return messages
