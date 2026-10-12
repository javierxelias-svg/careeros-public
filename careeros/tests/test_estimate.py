#!/usr/bin/env python3
"""
Salary estimator tests.

    python3 careeros/tests/test_estimate.py

The estimator is the component most able to mislead, because it invents
numbers. These tests pin three properties: it never returns "published"
confidence, it refuses unrecognised roles instead of guessing, and seniority
moves the band in the right direction.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import estimate as est  # noqa: E402

# (title, should_estimate, should_clear_70k, label)
CASES = [
    ("Solutions Engineer", True, True, "core lane, clears bar"),
    ("Senior Solutions Engineer", True, True, "senior raises band"),
    ("Forward Deployed Engineer", True, True, "highest band"),
    ("Customer Success Manager", True, True, "mid band midpoint clears — CSM really does pay this"),
    ("Senior Customer Success Manager", True, True, "seniority lifts it over"),
    ("Technical Support Engineer", True, True, "clears on midpoint"),
    ("Software Engineer", True, True, "engineering clears"),
    ("Junior Software Engineer", True, True, "junior still clears"),
    ("Customer Service Representative", True, False, "correctly below bar"),
    ("Data Entry Clerk", True, False, "correctly far below bar"),
    ("Virtual Assistant", True, False, "correctly below bar"),
    ("Product Manager", True, True, "clears"),
    ("Director of Engineering", True, True, "director multiplier"),
    ("Graphic Designer", True, False, "below bar on midpoint"),
    ("Chief Vibes Officer", False, False, "unrecognised role refuses"),
    ("", False, False, "empty title refuses"),
    ("Underwater Basket Weaver", False, False, "nonsense refuses"),
]


def main():
    failures = []
    print("=== estimate() ===")
    for title, should_estimate, should_clear, label in CASES:
        salary, why = est.estimate(title)
        estimated = salary.confidence == "estimated"
        clears = est.clears_bar(salary)

        ok = estimated == should_estimate and clears == should_clear
        # An estimate must never masquerade as a published figure.
        if salary.confidence == "published":
            ok = False
            failures.append(f"{label}: estimator returned 'published' confidence")

        mark = "PASS" if ok else "FAIL"
        shown = salary.display() if estimated else "refused"
        print(f"  [{mark}] {label:38s} {title[:32]:34s} -> {shown}")
        if not ok and salary.confidence != "published":
            failures.append(
                f"{label}: title={title!r} want estimate={should_estimate} "
                f"clear={should_clear}, got estimate={estimated} clear={clears} ({why})"
            )

    print("\n=== ordering: seniority must raise the band ===")
    pairs = [
        ("Junior Software Engineer", "Software Engineer"),
        ("Software Engineer", "Senior Software Engineer"),
        ("Senior Software Engineer", "Director of Engineering"),
    ]
    for lower_title, higher_title in pairs:
        lower, _ = est.estimate(lower_title)
        higher, _ = est.estimate(higher_title)
        ok = (higher.high or 0) > (lower.high or 0)
        mark = "PASS" if ok else "FAIL"
        print(f"  [{mark}] {lower_title} < {higher_title}")
        if not ok:
            failures.append(f"ordering broken: {lower_title} vs {higher_title}")

    print("\n=== estimates always carry the estimated label ===")
    sample, _ = est.estimate("Senior Solutions Engineer")
    ok = sample.display().startswith("~") and sample.confidence == "estimated"
    print(f"  [{'PASS' if ok else 'FAIL'}] display starts with ~ : {sample.display()}")
    if not ok:
        failures.append("estimated salary not visually marked")

    print("\n" + "=" * 60)
    if failures:
        print(f"FAILED {len(failures)}")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("ALL ESTIMATOR TESTS PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
