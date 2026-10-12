#!/usr/bin/env python3
"""
Salary parser tests, run with plain python3 (no pytest dependency).

    python3 careeros/tests/test_salary.py

Cases are drawn from formats actually seen in the verified source feeds plus
the failure modes that would quietly corrupt the pay filter: years parsed as
money, hourly rates read as annual, European decimal grouping.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import salary as salary_mod  # noqa: E402

# (input, expected_confidence, expected_top_or_None, label)
CASES = [
    # --- published, straightforward ---
    ("$70,000 - $90,000", "published", 90_000, "USD range with separators"),
    ("$70,000-$90,000 per year", "published", 90_000, "explicit annual"),
    ("70k - 90k USD", "published", 90_000, "k-suffix range"),
    ("$120,000", "published", 120_000, "single value"),
    ("USD 80,000 to 100,000", "published", 100_000, "'to' separator"),
    ("$85,000–$110,000", "published", 110_000, "en-dash"),

    # --- period conversion ---
    ("$45/hour", "published", 45 * 2080, "hourly to annual"),
    ("$50 - $60 per hour", "published", 60 * 2080, "hourly range"),
    ("$8,000 per month", "published", 96_000, "monthly to annual"),
    ("$40/hr", "published", 40 * 2080, "abbreviated hourly"),

    # --- currency conversion ---
    ("€60,000 - €80,000", "published", 80_000 * 1.09, "EUR converted"),
    ("£70,000", "published", 70_000 * 1.27, "GBP converted"),

    # --- correctly refused ---
    ("Pay per task", "unknown", None, "no number at all"),
    ("Competitive salary", "unknown", None, "marketing filler"),
    ("DOE", "unknown", None, "depends on experience"),
    ("", "unknown", None, "empty string"),
    (None, "unknown", None, "None input"),
    ("Founded in 2019, we are hiring", "unknown", None, "year must not parse as money"),
    ("$5,000", "unknown", None, "below plausible annual floor"),
    ("0.5% equity", "unknown", None, "equity percentage is not salary"),
    ("$2,500", "unknown", None, "ambiguous magnitude, refuses to guess"),
]

BAR_CASES = [
    ("$70,000 - $90,000", True, "top clears bar"),
    ("$60,000 - $85,000", True, "ceiling clears even though floor does not"),
    ("$50,000 - $65,000", False, "whole range below bar"),
    ("$69,999", False, "just under the bar"),
    ("$70,000", True, "exactly at the bar"),
    ("Pay per task", False, "unparseable cannot clear the bar"),
]


def approx(a, b, tolerance=1.0):
    if a is None or b is None:
        return a is b
    return abs(a - b) <= tolerance


def main():
    failures = []
    print("=== parse() ===")
    for text, want_conf, want_top, label in CASES:
        result = salary_mod.parse(text)
        got_conf = result.confidence
        got_top = result.top
        ok = got_conf == want_conf and (
            want_top is None if got_top is None else approx(got_top, want_top)
        )
        if want_top is None and got_top is not None:
            ok = False
        mark = "PASS" if ok else "FAIL"
        display = result.display() if ok else f"{result.confidence}/{got_top}"
        print(f"  [{mark}] {label:45s} {str(text)[:28]:30s} -> {display}")
        if not ok:
            failures.append(
                f"{label}: input={text!r} want conf={want_conf} top={want_top}, "
                f"got conf={got_conf} top={got_top}"
            )

    print("\n=== clears_bar(floor=70000) ===")
    for text, want, label in BAR_CASES:
        parsed = salary_mod.parse(text)
        got = salary_mod.clears_bar(parsed)
        ok = got == want
        mark = "PASS" if ok else "FAIL"
        print(f"  [{mark}] {label:45s} {text:22s} -> {got}")
        if not ok:
            failures.append(f"{label}: input={text!r} want={want} got={got}")

    print("\n" + "=" * 60)
    total = len(CASES) + len(BAR_CASES)
    if failures:
        print(f"FAILED {len(failures)}/{total}")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print(f"ALL {total} SALARY TESTS PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
