"""
What the operator actually sent, and what came back.

Why this exists. On 2026-09-30, twenty-one digests in, the pipeline had surfaced
314 roles and the last hand-written send pack was dated August 24. There was no
`applied` state anywhere in the codebase — no reply ledger, no follow-up date,
nothing. `state/sent/` records what the MACHINE sent to the operator. Nothing
recorded what the OPERATOR sent to anyone, which means the one number that says whether any of this
works did not exist.

A search that only ever widens its funnel is a search that never closes one. The
counter-pressure is a single line in the digest: applications out, replies in,
oldest one still silent. That is the same trick gap_warning() plays on the
schedule — make the absence visible, and let the operator decide.

Deliberately a JSONL append log, same shape as state/seen.jsonl:

  - The GitHub Actions runner is stateless, so this has to be tracked in the repo
    or it does not exist. Append-only means two writers never destroy each other's
    lines, which matters because both the operator and a run can add to it.
  - One line per EVENT, not per application. A status change appends; it never
    rewrites. The history of an application is worth more than its current state,
    because "applied, then silence for 40 days" is the fact that matters.

Statuses are deliberately few. `sent` and `rejected` are facts. `replied` and
`interviewing` are facts. There is no `maybe` and no score: this file records what
happened, and every judgement lives elsewhere.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

STATE_DIR = Path(__file__).resolve().parent.parent / "state"
LEDGER = STATE_DIR / "applied.jsonl"

# A form gate found by READING THE FORM, which is the only artifact that decides.
# A hand-written note once read "No years requirement" off a posting whose form
# demanded two years and said "if not, please do not apply"; another posting
# read senior and its form asked nothing. Recorded per application so the pattern
# becomes visible across employers instead of being re-learned each time.
STATUSES = ("sent", "replied", "interviewing", "offer", "rejected", "withdrawn",
            "blocked_by_form")


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def key(company, title):
    """Stable identity for one application, matching dedupe's normalisation."""
    return f"{(company or '').strip().lower()}|{(title or '').strip().lower()}"


def log(company, title, url="", status="sent", note="", form_gate="",
        ledger=None):
    """
    Append one event. Returns the record written.

    Never rewrites and never deduplicates: a second `sent` for the same role is
    either a genuine re-application or a mistake worth seeing, and silently
    swallowing it would hide both.
    """
    if status not in STATUSES:
        raise ValueError(f"unknown status {status!r}, expected one of {STATUSES}")
    path = Path(ledger) if ledger else LEDGER
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "at": _now(),
        "key": key(company, title),
        "company": company,
        "title": title,
        "url": url,
        "status": status,
        # What the FORM asked, in plain words, e.g. "2 years required, said
        # do not apply if you lack them". Empty when the form was not read.
        "form_gate": form_gate,
        "note": note,
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def load(ledger=None):
    """Every event, oldest first. A corrupt line is skipped, never fatal."""
    path = Path(ledger) if ledger else LEDGER
    if not path.exists():
        return []
    events = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events


def current(ledger=None):
    """
    Latest state per application: {key: last_event}.

    Last write wins, which is correct for an append log ordered by time.
    """
    state = {}
    for event in load(ledger):
        if isinstance(event, dict) and event.get("key"):
            state[event["key"]] = event
    return state


def pressure(today=None, ledger=None):
    """
    One line for the digest, or None when nothing has been sent yet.

    Returns None rather than "0 applications out" on purpose. A zero is a
    reproach, not information. The line appears once there is something true
    to report.
    """
    state = current(ledger)
    if not state:
        return None
    today = today or datetime.now(timezone.utc)
    out, answered, oldest_days, oldest_name = 0, 0, None, ""
    for event in state.values():
        status = event.get("status")
        if status in ("replied", "interviewing", "offer"):
            answered += 1
        if status != "sent":
            continue
        out += 1
        try:
            at = datetime.fromisoformat(str(event["at"]))
        except (ValueError, KeyError):
            continue
        age = (today - at).days
        if oldest_days is None or age > oldest_days:
            oldest_days, oldest_name = age, event.get("company", "?")
    parts = [f"{out} out"] if out else []
    if answered:
        parts.append(f"{answered} answered")
    if oldest_days is not None and oldest_days >= 7:
        parts.append(f"oldest {oldest_days}d silent ({oldest_name})")
    return "📮 " + " · ".join(parts) if parts else None
