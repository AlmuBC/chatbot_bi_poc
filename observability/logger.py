"""
Logging de trazabilidad de cada interacción del chatbot, en JSON Lines
(un objeto JSON por línea) en logs/interactions.jsonl.

Es deliberadamente "best-effort": una interacción real con el usuario nunca debe
fallar porque el logging falle (permisos de disco, disco lleno, etc.).
"""
import hashlib
import hmac
import json
import sys
import threading
import uuid
from datetime import datetime, timezone

import config

LOG_DIR = config.BASE_DIR / "logs"
LOG_FILE = LOG_DIR / "interactions.jsonl"

_lock = threading.Lock()


def pseudonymize_user_email(user_email: str | None) -> str | None:
    """Deriva un identificador determinista y no reversible a partir del email, usando
    HMAC-SHA256 con un secreto (config.LOG_USER_ID_SECRET) que nunca se guarda en el log.

    Determinista: el mismo email siempre produce el mismo identificador, así que se
    pueden agrupar las interacciones de un mismo usuario. No identificable: sin el
    secreto no se puede recuperar ni verificar el email original a partir del log."""
    if not user_email:
        return None
    digest = hmac.new(
        config.LOG_USER_ID_SECRET.encode("utf-8"),
        user_email.strip().lower().encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"u_{digest[:16]}"


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
    model: str | None = None,
    semantic_layer_version: str | None = None,
    space_id: str | None = None,
    thread_id: str | None = None,
    user_profile: str | None = None,       # "tecnico" | "negocio" | None (blocked/error)
    profile_confidence: str | None = None, # "alta" | "media" | "baja" | None
) -> None:
    """Añade una línea JSON con el detalle de la interacción a logs/interactions.jsonl.

    Nunca lanza una excepción: si falla la escritura, se informa por stderr y se
    continúa, para no romper la respuesta al usuario."""
    entry = {
        "interaction_id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "user_id": pseudonymize_user_email(user_email),
        "space_id": space_id,
        "thread_id": thread_id,
        "question": question,
        "llm_action": llm_action,
        "model": model,
        "semantic_layer_version": semantic_layer_version,
        "generated_code": generated_code,
        "execution_result": execution_result,
        "execution_error": execution_error,
        "final_response": final_response,
        "status": status,
        "latency_ms": latency_ms,
        "user_profile": user_profile,
        "profile_confidence": profile_confidence,
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
