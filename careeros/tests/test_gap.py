#!/usr/bin/env python3
"""
The digest reporting its own absence.

This is the lesson from two separate failures, and it is not about either
failure. In September a Mac with `autorestart 0` stayed off for 27 days; in
the same week GitHub's scheduler was measured firing one slot in five. Both
were survivable. What made the first expensive was that the gap was invisible
until the operator noticed the phone had been quiet, four weeks late.

So these tests are about one question: if the machine goes quiet again, does
the next message say so?
"""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import digest  # noqa: E402


class FakeSentDir:
    """Stands in for state/sent/, holding whatever dates a case needs."""

    def __init__(self, stems):
        self._stems = stems

    def glob(self, _pattern):
        return [Path(f"{stem}.json") for stem in self._stems]


def main():
    failures = []
    real = digest.SENT_DIR
    today = date(2026, 9, 29)

    cases = [
        # (delivered dates, expected substring or None, why it matters)
        (["2026-09-28"], None,
         "delivered yesterday — normal, say nothing"),
        (["2026-09-28", "2026-09-27"], None,
         "a healthy streak stays silent"),
        (["2026-09-27"], "Nothing sent yesterday",
         "one missed day is named, not shrugged off"),
        (["2026-09-26"], "No digest for 2 days",
         "two missed days"),
        (["2026-08-31"], "No digest for 28 days",
         "the September outage: 27 silent days, reported on the 28th"),
        ([], None,
         "first ever run — nothing behind it, so no false alarm"),
        (["2026-09-29"], None,
         "only today's own file present: not a gap"),
        (["2026-09-29", "2026-09-26"], "No digest for 2 days",
         "today's file must not mask the hole behind it"),
        (["not-a-date", "2026-09-28"], None,
         "a junk filename is skipped, not crashed on"),
    ]

    print("=== gap_warning() ===")
    for stems, expected, why in cases:
        digest.SENT_DIR = FakeSentDir(stems)
        try:
            got = digest.gap_warning(today=today)
        except Exception as exc:  # noqa: BLE001
            got = f"RAISED {exc!r}"
        if expected is None:
            ok = got is None
        else:
            ok = got is not None and expected in got
        shown = got if got is not None else "(silent)"
        print(f"  [{'PASS' if ok else 'FAIL'}] {why}")
        print(f"          -> {shown}")
        if not ok:
            failures.append(f"{why}: got {got!r}, wanted {expected!r}")

    digest.SENT_DIR = real

    print("\n=== the line reaches the message the operator reads ===")
    # A warning that gap_warning() computes but build() never prints is worth
    # nothing. Both shapes of digest have to carry it: the normal one and the
    # empty one.
    digest.SENT_DIR = FakeSentDir(["2026-08-31"])
    stats = {"fetched": 10_000, "kept": 2_000, "sources_live": 8,
             "sources_total": 8, "suppressed": 0}
    empty = digest.build([], [], [], [], 0, {}, 0, stats, "Sep 29, 2026")
    ok = "No digest for" in empty
    print(f"  [{'PASS' if ok else 'FAIL'}] empty digest carries the warning")
    if not ok:
        failures.append("empty digest dropped the gap warning")
    digest.SENT_DIR = real

    print("\n" + "=" * 60)
    if failures:
        print(f"FAILED {len(failures)}")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("ALL GAP TESTS PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
