"""
Telegram delivery for CareerOS, with a local-file fallback.

Two rules this module exists to enforce:

1. A send is successful only when Telegram returns a message_id. Reaching the
   end of the function proves nothing. Callers use the returned id as the
   receipt that delivery actually happened.
2. If Telegram itself is unreachable, the message is never lost — it is written
   to state/ALERT-<timestamp>.txt so the next successful run can report the
   backlog.
"""

import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from _shared.paths import STATE_DIR, ensure_dirs
from _shared.secrets import get_secret

API_BASE = "https://api.telegram.org"
SEND_TIMEOUT = 30
TELEGRAM_MAX_CHARS = 4096


class DeliveryFailed(RuntimeError):
    """Raised when a message could not be delivered and was written to fallback."""


def _write_fallback(text, reason):
    """Persist an undeliverable message so it is never silently lost."""
    ensure_dirs()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = STATE_DIR / f"ALERT-{stamp}.txt"
    try:
        path.write_text(
            f"CareerOS undelivered message\nreason: {reason}\n\n{text}\n",
            encoding="utf-8",
        )
    except OSError:
        # Disk problems are beyond what this layer can fix. The caller still
        # gets a failure signal from the return value.
        return None
    return path


def _post(method, payload, token):
    url = f"{API_BASE}/bot{token}/{method}"
    data = urllib.parse.urlencode(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, method="POST")
    with urllib.request.urlopen(request, timeout=SEND_TIMEOUT) as response:
        body = response.read().decode("utf-8", errors="replace")
    return json.loads(body)


def send(text, disable_preview=True):
    """
    Send `text` to the configured chat.

    Returns the Telegram message_id on confirmed delivery, or None on failure
    (in which case the message has been written to the fallback file).
    """
    token = get_secret("TELEGRAM_BOT_TOKEN")
    chat_id = get_secret("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        _write_fallback(text, "TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID unavailable")
        return None

    if len(text) > TELEGRAM_MAX_CHARS:
        text = text[: TELEGRAM_MAX_CHARS - 20].rstrip() + "\n… (truncated)"

    payload = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": "true" if disable_preview else "false",
    }

    try:
        result = _post("sendMessage", payload, token)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        _write_fallback(text, f"HTTP {exc.code}: {detail}")
        return None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        _write_fallback(text, f"network error: {exc}")
        return None
    except json.JSONDecodeError as exc:
        _write_fallback(text, f"unparseable response: {exc}")
        return None

    # The Telegram API returns 200 with ok:false for application-level errors,
    # so a successful HTTP status is not proof of delivery.
    if not isinstance(result, dict) or not result.get("ok"):
        _write_fallback(text, f"api rejected: {str(result)[:400]}")
        return None

    message = result.get("result")
    if not isinstance(message, dict):
        _write_fallback(text, f"unexpected result shape: {str(result)[:400]}")
        return None

    message_id = message.get("message_id")
    if message_id is None:
        _write_fallback(text, "no message_id in response")
        return None

    return message_id


def alert(text):
    """
    Send an operational alert (preflight failure, crash traceback).

    Prefixed so alerts are visually distinct from the daily digest. Always
    falls back to a local file, never raises.
    """
    return send(f"🚨 CareerOS ALERT\n\n{text}")


def pending_alerts():
    """Return any fallback files written by previous failed sends."""
    if not STATE_DIR.exists():
        return []
    return sorted(STATE_DIR.glob("ALERT-*.txt"))
