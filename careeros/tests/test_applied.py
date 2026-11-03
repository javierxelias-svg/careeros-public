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

        # 2026-10-13: roles the operator had skipped printed again in the next
        # digest because only sent roles were remembered.
        print("\n=== skipped: the operator's no is remembered and is not an application ===")
        skips = Path(tmp) / "skips.jsonl"
        applied.log("Skipco", "AI Operations Engineer", status="skipped",
                    note="operator's call: culture reviews", ledger=skips)
        check("a skipped role is in current(), so the run drops it",
              applied.key("skipco", " AI Operations Engineer ")
              in applied.current(skips))
        check("a skip alone prints no pressure line",
              applied.pressure(ledger=skips) is None)
        applied.log("Exampleco", "AI Agent Operations Specialist", ledger=skips)
        line = applied.pressure(ledger=skips)
        check("a skip is never counted as out", line and "1 out" in line, f"-> {line}")

    print("\n=== a retitled posting is still the same application ===")
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "applied.jsonl"
        url = "https://jobs.ashbyhq.com/exampleco/0a1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d"
        applied.log("Exampleco", "AI Agent Operations Specialist, Support", url=url,
                    status="rejected", ledger=path)
        state = applied.current(path)
        check("same URL, new title is done (retitled posting, 2026-10-16)",
              applied.is_done("Exampleco", "AI Agent Support Specialist", url, state))
        check("URL match ignores query string and trailing slash",
              applied.is_done("Exampleco", "Anything", url + "/?utm_source=x", state))
        check("a different role at the same company is not done",
              not applied.is_done("Exampleco", "AI Agent Support Specialist",
                                  "https://jobs.ashbyhq.com/exampleco/other", state))
        gh = "https://jobs.greenco.example/jobs?gh_jid=1234567"
        applied.log("Greenco", "Role A", url=gh, ledger=path)
        state = applied.current(path)
        check("Greenhouse job id in the query keeps two roles apart",
              not applied.is_done("Greenco", "Role B",
                                  "https://jobs.greenco.example/jobs?gh_jid=7654321", state))
        check("same Greenhouse job id is done",
              applied.is_done("Greenco", "Role A renamed", gh + "&gh_jid=1234567", state))
        check("title match still works with no URL",
              applied.is_done("exampleco", "ai agent operations specialist, support", "", state))

    print("\n=== same posting ID behind a different URL form ===")
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "applied.jsonl"
        uuid = "0a1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d"
        applied.log("Exampleco", "AI Agent Operations Specialist, Support",
                    url=f"https://jobs.ashbyhq.com/exampleco/{uuid}",
                    status="rejected", ledger=path)
        applied.log("Greenco", "Role A",
                    url="https://boards.greenhouse.io/greenco/jobs/1234567", ledger=path)
        lever = "0b5c3d1e-2f4a-4b6c-8d9e-0a1b2c3d4e5f"
        applied.log("Acme", "Support Engineer",
                    url=f"https://jobs.lever.co/acme/{lever}", ledger=path)
        applied.log("Bigco", "Support Engineer", url=(
            "https://bigco.wd5.myworkdayjobs.com/en-US/External/job/Remote/"
            "Support-Engineer_R12345"), ledger=path)
        state = applied.current(path)
        check("Ashby /application page of the same UUID is done",
              applied.is_done("Exampleco", "AI Agent Support Specialist",
                              f"https://jobs.ashbyhq.com/exampleco/{uuid}/application?src=x",
                              state))
        check("Ashby job on a company domain (?ashby_jid=) is done",
              applied.is_done("Exampleco", "AI Agent Support Specialist",
                              f"https://www.exampleco.com/careers?ashby_jid={uuid}", state))
        check("Greenhouse ?gh_jid= on a custom board matches /jobs/<id>",
              applied.is_done("Greenco", "Role A renamed",
                              "https://jobs.greenco.example/jobs?gh_jid=1234567", state))
        check("Greenhouse new board host, extra query, same id is done",
              applied.is_done("Greenco", "Role A renamed",
                              "https://job-boards.greenhouse.io/greenco/jobs/1234567?gh_src=a1",
                              state))
        check("a different Greenhouse id is not done",
              not applied.is_done("Greenco", "Role B",
                                  "https://jobs.greenco.example/jobs?gh_jid=7654321", state))
        check("Lever /apply page of the same posting is done",
              applied.is_done("Acme", "AI Support Engineer",
                              f"https://jobs.lever.co/acme/{lever}/apply", state))
        check("Workday retitled slug, same R-number is done",
              applied.is_done("Bigco", "AI Support Engineer", (
                  "https://bigco.wd5.myworkdayjobs.com/External/job/Remote-USA/"
                  "AI-Support-Engineer_R12345?source=LinkedIn"), state))
        check("the same R-number at another Workday employer is not done",
              not applied.is_done("Otherco", "Support Engineer", (
                  "https://otherco.wd1.myworkdayjobs.com/External/job/Remote/"
                  "Support-Engineer_R12345"), state))
        check("a different Ashby UUID is not done",
              not applied.is_done("Exampleco", "AI Agent Support Specialist",
                                  "https://jobs.ashbyhq.com/exampleco/"
                                  "11111111-2222-3333-4444-555555555555", state))

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
