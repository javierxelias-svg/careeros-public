"""
Canonical paths for CareerOS.

Everything resolves from the repo root, computed from this file's location, so
the code works identically when launched from a shell, from launchd, or from
any working directory. launchd in particular does not set a useful cwd.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

CONFIG_DIR = REPO_ROOT / "config"
STATE_DIR = REPO_ROOT / "state"
LOGS_DIR = REPO_ROOT / "logs"
CONTEXT_DIR = REPO_ROOT / "context"
VERIFICATION_DIR = REPO_ROOT / "verification"

SOURCES_CONFIG = CONFIG_DIR / "sources.json"
FX_RATES = CONFIG_DIR / "fx-rates.json"

SEEN_LEDGER = STATE_DIR / "seen.jsonl"
SENT_DIR = STATE_DIR / "sent"
FEEDBACK_LEDGER = STATE_DIR / "feedback.jsonl"
TELEGRAM_OFFSET = STATE_DIR / "telegram_offset.txt"
RAW_DIR = STATE_DIR / "raw"

CANDIDATE_PROFILE = CONTEXT_DIR / "candidate-profile.md"

WRITABLE_DIRS = (STATE_DIR, LOGS_DIR, SENT_DIR, RAW_DIR)


def ensure_dirs():
    """Create every directory the run writes to. Safe to call repeatedly."""
    for directory in WRITABLE_DIRS:
        directory.mkdir(parents=True, exist_ok=True)
