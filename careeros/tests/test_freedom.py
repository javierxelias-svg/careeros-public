#!/usr/bin/env python3
"""
Portability scoring tests.

    python3 careeros/tests/test_freedom.py

One property matters above all others here, and it is the whole reason v2
exists: a work-from-anywhere async role must outrank a US-only fixed-hours role
no matter what either one pays. v1 sorted by tier, which is a proxy for salary,
and therefore got this backwards every single morning.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import freedom  # noqa: E402
import geo  # noqa: E402

# (label, geo_class, tz_friendly, tz_soft, green, expected_points)
# Rescored 2026-10-05 when freedom.py became a scorecard of written evidence
# (async +4, work from anywhere +3, not US-locked +2, time off stated +2, set
# hours -3, unlimited PTO with no minimum -1). The absence of a time-zone clause
# no longer earns anything, which is why every case lost its old 2 points.
CASES = [
    ("anywhere + async + real PTO",
     geo.CLASS_ANYWHERE, ["async"], [], ["real time off"], 11),
    ("anywhere + async, no PTO signal",
     geo.CLASS_ANYWHERE, ["async"], [], [], 9),
    ("anywhere, but fixed core hours",
     geo.CLASS_ANYWHERE, [], ["fixed core hours"], [], 2),
    ("US-only, async",
     geo.CLASS_US, ["async"], [], [], 4),
    ("US-only, fixed hours — the worst shape",
     geo.CLASS_US, [], ["requires US-hours overlap"], [], -3),
    ("unlimited PTO, no minimum, costs a point",
     geo.CLASS_ANYWHERE, [], [], ["unlimited PTO"], 4),
]

# (label, text, extra kwargs, expected_points, reason that must appear or None,
#  reason that must NOT appear or None). All US-remote, so geo adds nothing.
WRITTEN = [
    ("silence about hours scores nothing", "Remote role. Apply today.", {},
     0, None, "no fixed hours"),
    ("'not a traditional 9-to-5' is not set hours",
     "This is not a traditional 9-to-5.", {}, 0, None, "set hours"),
    ("'no core hours' is flexibility, not a penalty",
     "There are no core hours here.", {}, 4, "flexible hours", "set hours"),
    ("PTO stated as a number", "You get 5 weeks paid vacation.", {},
     2, "time off stated", None),
    ("meeting-free days", "Tuesdays and Thursdays are meeting-free days.", {},
     3, "few meetings", None),
    ("business hours are set hours", "Available during business hours.", {},
     -3, "set hours", None),
    ("unlimited PTO with a stated minimum is not penalised",
     "Unlimited PTO with a minimum of 3 weeks.", {"green": ["unlimited PTO"]},
     2, "time off stated", "unlimited PTO, no minimum"),
    ("builder role", "", {"fit_label": "AI builder"}, 2, "builder role", None),
    ("large employer", "", {"large_employer": True}, -1, "large employer", None),
]


def main():
    failures = []

    print("=== freedom.score() ===")
    for label, geo_class, friendly, soft, green, expected in CASES:
        points, reasons = freedom.score(geo_class, friendly, soft, green)
        ok = points == expected
        mark = "PASS" if ok else "FAIL"
        print(f"  [{mark}] {label:46s} {points:2d}/{freedom.MAX_SCORE}  {reasons}")
        if not ok:
            failures.append(f"{label}: want {expected}, got {points}")

    print("\n=== freedom.score() reads written evidence ===")
    for label, text, extra, expected, must, must_not in WRITTEN:
        green = extra.pop("green", [])
        points, reasons = freedom.score(geo.CLASS_US, [], [], green, text=text, **extra)
        ok = (points == expected and (must is None or must in reasons)
              and (must_not is None or must_not not in reasons))
        print(f"  [{'PASS' if ok else 'FAIL'}] {label:52s} {points:3d}  {reasons}")
        if not ok:
            failures.append(f"{label}: want {expected}, got {points} {reasons}")

    print("\n=== the invariant: a week the operator controls beats one they do not ===")
    # This used to be called "freedom beats pay, always" and compared a US-only
    # role against an anywhere one. That comparison stopped meaning anything on
    # 2026-09-28: the operator is US-based, so US-only is not the stuck
    # shape any more. What still has to hold is that async and real time off
    # outrank fixed core hours — the part of freedom actually being exercised.
    stuck, _ = freedom.score(geo.CLASS_US, [], ["core hours"], [])
    free, _ = freedom.score(geo.CLASS_US, ["async"], [], ["real time off"])
    ok = free > stuck
    print(f"  [{'PASS' if ok else 'FAIL'}] US-only async+PTO ({free}) "
          f"> US-only fixed hours ({stuck})")
    if not ok:
        failures.append("a controllable week did not outrank a fixed one")

    print("\n=== is_portable() gates the main lane ===")
    gate_cases = [
        ("anywhere, no hard blockers", geo.CLASS_ANYWHERE, [], True),
        ("anywhere but on-call", geo.CLASS_ANYWHERE, ["on-call rotation"], False),
        # Reversed 2026-09-28. The operator is US-based, so "requires US
        # residence" is a condition already met. Holding these out of the main
        # lane demoted most of the market over a constraint that was dropped.
        ("US-only — the operator is US-based", geo.CLASS_US, [], True),
        ("US-only but on-call", geo.CLASS_US, ["on-call rotation"], False),
        ("region-locked", geo.CLASS_BLOCKED, [], False),
    ]
    for label, geo_class, hard, expected in gate_cases:
        got = freedom.is_portable(geo_class, hard)
        ok = got == expected
        print(f"  [{'PASS' if ok else 'FAIL'}] {label:34s} -> {got}")
        if not ok:
            failures.append(f"is_portable({label}): want {expected}, got {got}")

    print("\n" + "=" * 60)
    if failures:
        print(f"FAILED {len(failures)}")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("ALL FREEDOM TESTS PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
