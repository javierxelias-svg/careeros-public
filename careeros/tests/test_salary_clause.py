#!/usr/bin/env python3
"""
Clause-scoped period detection.

    python3 careeros/tests/test_salary_clause.py

The 2026-08-16 digest closed with a Hacker News posting labelled "pay not
stated — ask before applying". Its own first line read:

    ... | Full-Time $80k-$120k + equity, or Contract $50-$150/hr | ...

The parser found the annual band, then read "/hr" from a different pay package
thirty characters later, annualised $80k as an hourly rate, blew through the
plausibility ceiling and returned UNKNOWN. A posting that published its salary
in plain text was delivered as unpriced.

A period word now has to be in the same clause as the number it describes.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import salary  # noqa: E402

ARCFORMA = (
    "Arcforma AI (arcforma.ai) | AI Engineer (Marketing / Construction / "
    "Fashion & Luxury) | REMOTE (US only) or ONSITE NYC | "
    "Full-Time $80k-$120k + equity, or Contract $50-$150/hr | jobs@arcforma.ai"
)

# (label, text, expected confidence, expected low, expected high)
CASES = [
    ("the real HN posting: annual band wins, hourly clause ignored",
     ARCFORMA, "published", 80_000, 120_000),
    ("annual clause alone", "Full-Time $80k-$120k + equity",
     "published", 80_000, 120_000),
    ("hourly clause alone still annualises",
     "Contract $50-$150/hr", "published", 104_000, 312_000),
    ("hourly stated next to its own number",
     "Rate: $60-$90 per hour | benefits included",
     "published", 124_800, 187_200),
    ("single-clause annual, unchanged behaviour",
     "$120,000 - $160,000 per year", "published", 120_000, 160_000),
    ("no figure at all", "Competitive salary, DOE", "unknown", None, None),
]


def main():
    failures = []

    print("=== parse(): period read from the clause, not the blob ===")
    for label, text, want_conf, want_low, want_high in CASES:
        got = salary.parse(text)
        ok = (got.confidence == want_conf
              and got.low == want_low and got.high == want_high)
        print(f"  [{'PASS' if ok else 'FAIL'}] {label:52s} -> {got.display()} ({got.confidence})")
        if not ok:
            failures.append(
                f"{label}: want {want_conf} {want_low}-{want_high}, "
                f"got {got.confidence} {got.low}-{got.high}"
            )

    print("\n=== the regression: this posting is no longer 'pay not stated' ===")
    got = salary.parse(ARCFORMA)
    ok = got.confidence == "published" and salary.clears_bar(got, 70_000)
    print(f"  [{'PASS' if ok else 'FAIL'}] Arcforma AI -> {got.display()} "
          f"({got.confidence}), clears the $70k floor")
    if not ok:
        failures.append("Arcforma posting still parses as unpriced")

    print("\n" + "=" * 60)
    if failures:
        print(f"FAILED {len(failures)}")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("ALL SALARY CLAUSE TESTS PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
