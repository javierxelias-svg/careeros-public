"""
Dependency checking for CareerOS.

Every external thing the run needs is checked here, before any work starts.
On failure the run logs, alerts, and exits 0 — it never crashes and never
crash-loops, because a launchd agent that exits non-zero repeatedly gets
throttled or respawned in ways that hide the real problem.

A check returns (name, ok, detail). `detail` is safe to log — it never
contains a secret value, only whether one was found.
"""

import json
import urllib.error
import urllib.request

from _shared import secrets
from _shared.paths import SOURCES_CONFIG, WRITABLE_DIRS, ensure_dirs

NETWORK_PROBE_URL = "https://api.telegram.org"
PROBE_TIMEOUT = 15


def _check_writable_dirs():
    try:
        ensure_dirs()
    except OSError as exc:
        return ("writable_dirs", False, f"cannot create directories: {exc}")
    for directory in WRITABLE_DIRS:
        probe = directory / ".preflight-write-test"
        try:
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
        except OSError as exc:
            return ("writable_dirs", False, f"{directory} not writable: {exc}")
    return ("writable_dirs", True, f"{len(WRITABLE_DIRS)} directories writable")


def _check_network():
    try:
        request = urllib.request.Request(NETWORK_PROBE_URL, method="GET")
        with urllib.request.urlopen(request, timeout=PROBE_TIMEOUT) as response:
            response.read(256)
    except urllib.error.HTTPError:
        # Any HTTP response at all proves the network path works.
        return ("network", True, "reachable")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return ("network", False, f"no network: {exc}")
    return ("network", True, "reachable")


def _check_sources_config():
    if not SOURCES_CONFIG.exists():
        return ("sources_config", False, f"missing {SOURCES_CONFIG}")
    try:
        data = json.loads(SOURCES_CONFIG.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return ("sources_config", False, f"unreadable: {exc}")
    if not isinstance(data, dict):
        return ("sources_config", False, "config is not an object")
    sources = data.get("sources")
    if not isinstance(sources, list) or not sources:
        return ("sources_config", False, "no sources defined")
    enabled = [s for s in sources if isinstance(s, dict) and s.get("enabled")]
    if not enabled:
        return ("sources_config", False, "no sources enabled")
    return ("sources_config", True, f"{len(enabled)} of {len(sources)} sources enabled")


def _check_secret_present(name):
    try:
        present = secrets.has_secret(name)
    except Exception as exc:  # Keychain access can fail in unexpected ways
        return (name, False, f"lookup failed: {exc}")
    if not present:
        return (
            name,
            False,
            "not in Keychain or environment — run: "
            f"security add-generic-password -a \"$USER\" -s {name} -w '<value>'",
        )
    return (name, True, "found")


def _check_telegram_credentials_work():
    """
    Prove the bot token is valid, not merely present.

    A previous project's relay held a token that returned 403, so presence alone is not
    evidence. getMe is a read-only call that confirms the token authenticates.
    """
    token = secrets.get_secret("TELEGRAM_BOT_TOKEN")
    if not token:
        return ("telegram_auth", False, "no token to validate")
    url = f"https://api.telegram.org/bot{token}/getMe"
    try:
        with urllib.request.urlopen(url, timeout=PROBE_TIMEOUT) as response:
            body = json.loads(response.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        return ("telegram_auth", False, f"token rejected: HTTP {exc.code}")
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        return ("telegram_auth", False, f"could not validate: {exc}")
    if not isinstance(body, dict) or not body.get("ok"):
        return ("telegram_auth", False, "getMe returned not-ok")
    result = body.get("result")
    username = result.get("username") if isinstance(result, dict) else None
    return ("telegram_auth", True, f"authenticated as @{username}")


def run(require_delivery=True):
    """
    Run all checks.

    Returns (ok, results). `ok` is False if any required check failed.
    `require_delivery=False` skips the Telegram checks — used by build-time
    tooling that must run before the bot exists.
    """
    checks = [
        _check_writable_dirs(),
        _check_sources_config(),
        _check_network(),
    ]
    if require_delivery:
        checks.append(_check_secret_present("TELEGRAM_BOT_TOKEN"))
        checks.append(_check_secret_present("TELEGRAM_CHAT_ID"))
        checks.append(_check_telegram_credentials_work())

    ok = all(passed for _, passed, _ in checks)
    return ok, checks


def format_results(results):
    lines = []
    for name, passed, detail in results:
        mark = "PASS" if passed else "FAIL"
        lines.append(f"  [{mark}] {name}: {detail}")
    return "\n".join(lines)
