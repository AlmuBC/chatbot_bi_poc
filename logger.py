"""
Logging de trazabilidad de cada interacción del chatbot, en JSON Lines
(un objeto JSON por línea) en logs/interactions.jsonl.

Es deliberadamente "best-effort": una interacción real con el usuario nunca debe
fallar porque el logging falle (permisos de disco, disco lleno, etc.).
"""
import json
import sys
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent / "logs"
LOG_FILE = LOG_DIR / "interactions.jsonl"

_lock = threading.Lock()


def log_interaction(
    user_email: str,
    question: str,
    llm_action: str,          # "execute_code" | "ask_clarification" | "refuse"
    generated_code: str | None,
    execution_result: str | None,
    execution_error: str | None,
    final_response: str,
    status: str,              # "success" | "error" | "clarification" | "refused"
    latency_ms: int,
    space_id: str | None = None,
    thread_id: str | None = None,
) -> None:
    """Añade una línea JSON con el detalle de la interacción a logs/interactions.jsonl.

    Nunca lanza una excepción: si falla la escritura, se informa por stderr y se
    continúa, para no romper la respuesta al usuario."""
    entry = {
        "interaction_id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "user_email": user_email,
        "space_id": space_id,
        "thread_id": thread_id,
        "question": question,
        "llm_action": llm_action,
        "generated_code": generated_code,
        "execution_result": execution_result,
        "execution_error": execution_error,
        "final_response": final_response,
        "status": status,
        "latency_ms": latency_ms,
    }

    try:
        line = json.dumps(entry, ensure_ascii=False)
    except Exception as e:
        print(f"[logger] No se pudo serializar la interacción a JSON: {e}", file=sys.stderr)
        return

    try:
        with _lock:
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(line + "\n")
    except Exception as e:
        print(f"[logger] No se pudo escribir en {LOG_FILE}: {e}", file=sys.stderr)
