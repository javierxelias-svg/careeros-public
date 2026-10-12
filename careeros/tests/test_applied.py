#!/usr/bin/env python3
"""
Applied-ledger tests.

    python3 careeros/tests/test_applied.py

No network and no shared state: every case writes to a temp file. The ledger is
the one file in the project that records the OPERATOR'S actions rather than the machine's, so
the thing under test is mostly that it never loses a line and never lies about a
count.
"""

import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import applied  # noqa: E402


def main():
    failures = []

    def check(label, ok, detail=""):
        suffix = f"  {detail}" if detail else ""
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}{suffix}")
        if not ok:
            failures.append(label)

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "applied.jsonl"

        print("=== append and read back ===")
        applied.log("Acme Robotics", "Support Engineer (AMER)",
                    url="https://example.test/1", ledger=path,
                    form_gate="no experience question on the form")
        applied.log("Example Co", "Mid-Market Implementation Specialist",
                    status="blocked_by_form", ledger=path,
                    form_gate="2 years required, says do not apply without them")
        events = applied.load(path)
        check("both events present", len(events) == 2, f"-> {len(events)}")
        check("the form gate is recorded, not just the posting",
              "do not apply" in events[1]["form_gate"])

        print("\n=== a status change appends, it never rewrites ===")
        applied.log("Acme Robotics", "Support Engineer (AMER)", status="rejected",
                    ledger=path)
        check("history is kept", len(applied.load(path)) == 3)
        state = applied.current(path)
        check("current state is the latest event",
              state[applied.key("Acme Robotics", "Support Engineer (AMER)")]["status"]
              == "rejected")
        check("one entry per application, not per event", len(state) == 2,
              f"-> {len(state)}")

        print("\n=== an unknown status is refused, loudly ===")
        try:
            applied.log("X", "Y", status="probably_maybe", ledger=path)
            check("bad status raises", False)
        except ValueError:
            check("bad status raises", True)

        print("\n=== a corrupt line is skipped, never fatal ===")
        with path.open("a", encoding="utf-8") as handle:
            handle.write("{not json at all\n\n")
        check("load survives garbage", len(applied.load(path)) == 3)

        print("\n=== pressure(): the line that makes inaction visible ===")
        empty = Path(tmp) / "empty.jsonl"
        check("nothing sent yet says NOTHING, not '0 out'",
              applied.pressure(ledger=empty) is None,
              "a zero is a reproach; see the docstring")

        fresh = Path(tmp) / "fresh.jsonl"
        applied.log("Cloudbeds", "Onboarding Project Manager", ledger=fresh)
        line = applied.pressure(ledger=fresh)
        check("one sent shows as out", line and "1 out" in line, f"-> {line}")
        check("a fresh application is not nagged about",
              line and "silent" not in line, f"-> {line}")

        # Age the record by hand: the point of the line is the silence, and the
        # silence only matters once it has lasted.
        old = Path(tmp) / "old.jsonl"
        applied.log("Globex", "Solution Engineer", ledger=old)
        stale = datetime.now(timezone.utc) + timedelta(days=21)
        line = applied.pressure(today=stale, ledger=old)
        check("three weeks of silence is reported, with the company",
              line and "21d silent" in line and "Globex" in line, f"-> {line}")

        answered = Path(tmp) / "answered.jsonl"
        applied.log("Initech", "Resident Solution Architect", ledger=answered)
        applied.log("Initech", "Resident Solution Architect", status="replied",
                    ledger=answered)
        line = applied.pressure(ledger=answered)
        check("a reply moves out of 'out' and into 'answered'",
              line and "answered" in line and "1 out" not in line, f"-> {line}")

    print("\n" + "=" * 60)
    if failures:
        print(f"FAILED {len(failures)}")
        for failure in failures:
            print("  - " + failure)
        return 1
    print("ALL APPLIED-LEDGER TESTS PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
