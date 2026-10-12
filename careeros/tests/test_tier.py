#!/usr/bin/env python3
"""
Tiering invariant tests.

    python3 careeros/tests/test_tier.py

Two caps must hold no matter what else changes, because both are rules the
operator set rather than implementation details:

  1. An off-lane role never exceeds C, whatever it pays. On 2026-08-15 an
     Associate General Counsel posting at $240,000-$300,000 reached S-tier on
     three culture keywords. That must be impossible now.

  2. An estimated or unstated salary never exceeds B. The machine is not
     allowed to sound certain about a number it did not read
     (SESSION-STATE.md:74-81). v2 promotes unpriced listings in RANK; this test
     pins that it did not also promote them in TIER.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import fit  # noqa: E402
import geo  # noqa: E402
import prefilter  # noqa: E402
import salary as salary_mod  # noqa: E402

TIER_RANK = {"S": 0, "A": 1, "B": 2, "C": 3, "U": 4}

PUBLISHED_HIGH = salary_mod.Salary(
    low=240_000.0, high=300_000.0, confidence="published", raw="$240,000–$300,000",
)
PUBLISHED_MID = salary_mod.Salary(
    low=110_000.0, high=140_000.0, confidence="published", raw="$110,000–$140,000",
)
ESTIMATED = salary_mod.Salary(
    low=110_000.0, high=140_000.0, confidence="estimated", raw="estimated from title",
)

PERFECT_GREEN = ["work from anywhere", "async", "founder-led", "unlimited PTO"]


def main():
    failures = []

    print("=== off-lane can never outrank C, whatever it pays ===")
    off_cases = [
        ("General Counsel at $300k, perfect culture, anywhere",
         PUBLISHED_HIGH, PERFECT_GREEN, [], geo.CLASS_ANYWHERE, fit.LANE_OFF),
        ("Senior SWE at $300k, perfect culture, anywhere",
         PUBLISHED_HIGH, PERFECT_GREEN, [], geo.CLASS_ANYWHERE, fit.LANE_OFF),
    ]
    for label, sal, green, red, geo_class, lane in off_cases:
        tier = prefilter.assign_tier(sal, green, red, geo_class, lane)
        ok = TIER_RANK[tier] >= TIER_RANK["C"]
        print(f"  [{'PASS' if ok else 'FAIL'}] {label:52s} -> {tier}")
        if not ok:
            failures.append(f"{label}: off-lane reached {tier}")

    print("\n=== estimated or unstated pay can never outrank B ===")
    pay_cases = [
        ("estimated, perfect culture, anywhere, core lane",
         ESTIMATED, PERFECT_GREEN, geo.CLASS_ANYWHERE, fit.LANE_CORE),
        ("unknown salary, perfect culture, anywhere, core lane",
         salary_mod.UNKNOWN, PERFECT_GREEN, geo.CLASS_ANYWHERE, fit.LANE_CORE),
    ]
    for label, sal, green, geo_class, lane in pay_cases:
        tier = prefilter.assign_tier(sal, green, [], geo_class, lane)
        ok = TIER_RANK[tier] >= TIER_RANK["B"]
        print(f"  [{'PASS' if ok else 'FAIL'}] {label:52s} -> {tier}")
        if not ok:
            failures.append(f"{label}: unverified pay reached {tier}")

    print("\n=== a real match still reaches the top ===")
    tier = prefilter.assign_tier(
        PUBLISHED_MID, PERFECT_GREEN, [], geo.CLASS_ANYWHERE, fit.LANE_CORE
    )
    ok = tier == "S"
    print(f"  [{'PASS' if ok else 'FAIL'}] published + core + anywhere -> {tier}")
    if not ok:
        failures.append(f"legitimate S-tier match downgraded to {tier}")

    print("\n=== the 2026-08-15 regression, end to end ===")
    lane, label = fit.classify("Associate General Counsel, Corporate")
    tier = prefilter.assign_tier(
        PUBLISHED_HIGH, PERFECT_GREEN, [], geo.CLASS_ANYWHERE, lane
    )
    ok = lane == fit.LANE_OFF and tier == "C"
    print(f"  [{'PASS' if ok else 'FAIL'}] the lawyer job -> lane={lane} tier={tier}")
    if not ok:
        failures.append(f"lawyer job still ranks: lane={lane} tier={tier}")

    print("\n" + "=" * 60)
    if failures:
        print(f"FAILED {len(failures)}")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("ALL TIER TESTS PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
