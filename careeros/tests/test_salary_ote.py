#!/usr/bin/env python3
"""
Base vs on-target-earnings tests, run with plain python3 (no pytest).

    python3 careeros/tests/test_salary_ote.py

The defect these pin: PostHog's Technical CSM posting advertises $237,375, an
80/20 figure whose last fifth is paid only on hitting retention targets. Read
as salary it overstated the role by about $20,000 and ranked it top of the
digest. `Salary.top` — what every gate and every ranking reads — must be the
guaranteed base, and the advertised total must survive separately so the
posting is still recognisable in the digest.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import salary as salary_mod  # noqa: E402

# (input, expected_basis, expected_variable_share, expected_top, label)
BASIS_CASES = [
    # --- OTE detected, split not stated: the 80/20 assumption applies ---
    ("$237,375 OTE", "ote", 0.20, 189_900, "bare OTE, split assumed"),
    ("On-target earnings: $150,000", "ote", 0.20, 120_000, "spelled out"),
    ("On target compensation $120,000", "ote", 0.20, 96_000, "no hyphen"),
    ("Total target compensation $200,000", "ote", 0.20, 160_000, "TTC wording"),
    ("$120,000 - $150,000 base + variable", "ote", 0.20, 120_000, "base + variable package"),
    ("$100,000 - $130,000 salary + commission", "ote", 0.20, 104_000, "salary + commission"),

    # --- OTE with the split published: use what the posting says ---
    ("OTE $94,427 - $104,426, 80/20 split", "ote", 0.20, 83_540.8, "80/20 stated"),
    ("$150,000 OTE (70/30)", "ote", 0.30, 105_000, "70/30 stated"),
    ("$100,000 OTE with 30% variable", "ote", 0.30, 70_000, "variable percentage"),
    ("$200,000 OTE, 60% base", "ote", 0.40, 120_000, "base percentage"),
    ("$120,000 OTE, 10% commission", "ote", 0.10, 108_000, "commission percentage"),

    # --- base wins: the whole number is guaranteed ---
    ("$110,000 - $130,000", "base", 0.0, 130_000, "plain range untouched"),
    ("Base salary: $100,000 - $120,000, plus uncapped commission",
     "base", 0.0, 120_000, "base anchor beats the commission word"),
    ("Base pay range $95,000-$115,000. OTE varies by territory.",
     "base", 0.0, 115_000, "base anchor beats a later OTE word"),
    ("Salary $80,000 per year", "base", 0.0, 80_000, "no variable language at all"),
    # Frozen from WeWorkRemotely 2026-08-19 — states BOTH numbers in one
    # sentence, and the base is the one the parser anchors on.
    ("the base wage range for this position is targeted at $137,000-$177,000 and "
     "competitive On-Target Earnings, inclusive of incentive compensation, of "
     "$210,800-$272,000", "base", 0.0, 177_000, "base wage range beside an OTE clause"),

    # --- guards: numbers that look like a split and are not ---
    ("$150,000 OTE — interviews start 10/20", "ote", 0.20, 120_000,
     "date does not sum to 100, assumption stands"),
    ("$90,000 - $110,000, team grew 40/60 across regions", "base", 0.0, 110_000,
     "no OTE word means no discount, whatever the ratio"),
]

# (input, expected_advertised_top, expected_at_risk, label)
ADVERTISED_CASES = [
    ("$237,375 OTE", 237_375, 47_475, "advertised total survives the discount"),
    ("$110,000 - $130,000", 130_000, 0, "base range risks nothing"),
]

# (input, expected_clears_70k, label)
BAR_CASES = [
    ("$85,000 OTE", False, "OTE clears the floor, base does not — refused"),
    ("$85,000", True, "same number as base clears"),
    ("$95,000 OTE", True, "base of $76,000 still clears"),
    ("$237,375 OTE", True, "PostHog's advertised figure clears on base too"),
]

# (input, must_contain, label)
DISPLAY_CASES = [
    ("$237,375 OTE", ["base", "$237,375", "OTE", "ask the split"],
     "assumed split says so in the digest line"),
    ("OTE $94,427 - $104,426, 80/20 split", ["base", "80/20", "OTE"],
     "stated split is quoted, not queried"),
    ("$110,000 - $130,000", ["$110,000–$130,000"], "base line unchanged"),
]

# (description, expected_basis, expected_top, label) — parse_description() is
# the path most postings actually take, so the split has to survive it too.
DESCRIPTION_CASES = [
    ("About us. " + "x" * 3200 + " Compensation. In the United States, the OTE "
     "compensation range for this role is $120,000 - $150,000, split 70/30 "
     "between base and variable.", "ote", 105_000, "OTE below the old 3,000-char cut"),
    ("Compensation: The on-target earnings range for this role is $180,000 - "
     "$220,000, inclusive of incentive compensation.", "ote", 176_000,
     "on-target earnings section"),
    ("Salary range: $110,000 - $140,000 base salary. Equity and benefits on top.",
     "base", 140_000, "base section untouched"),
]

# (text, expected_basis, label) — structured ATS fields carry no prose.
STRUCTURED_CASES = [
    ("$120,000 OTE", "ote", "raw field naming OTE"),
    ("Account Executive, OTE", "ote", "title naming OTE"),
    ("$120,000 - $140,000", "base", "plain structured field"),
    ("", "base", "empty field defaults to base"),
    (None, "base", "None field defaults to base"),
]


def approx(a, b, tolerance=1.0):
    if a is None or b is None:
        return a is b
    return abs(a - b) <= tolerance


def main():
    failures = []

    print("=== basis, split, and guaranteed top ===")
    for text, want_basis, want_share, want_top, label in BASIS_CASES:
        result = salary_mod.parse(text)
        ok = (result.basis == want_basis
              and approx(result.variable_share, want_share, 0.001)
              and approx(result.top, want_top))
        mark = "PASS" if ok else "FAIL"
        print(f"  [{mark}] {label:48s} {text[:34]:36s} -> {result.basis} top={result.top}")
        if not ok:
            failures.append(
                f"{label}: input={text!r} want basis={want_basis} share={want_share} "
                f"top={want_top}, got basis={result.basis} "
                f"share={result.variable_share} top={result.top}"
            )

    print("\n=== advertised total and money at risk ===")
    for text, want_advertised, want_risk, label in ADVERTISED_CASES:
        result = salary_mod.parse(text)
        ok = approx(result.advertised_top, want_advertised) and approx(result.at_risk, want_risk)
        mark = "PASS" if ok else "FAIL"
        print(f"  [{mark}] {label:48s} advertised={result.advertised_top} at_risk={result.at_risk}")
        if not ok:
            failures.append(
                f"{label}: input={text!r} want advertised={want_advertised} "
                f"risk={want_risk}, got advertised={result.advertised_top} "
                f"risk={result.at_risk}"
            )

    print("\n=== clears_bar(floor=70000) reads base ===")
    for text, want, label in BAR_CASES:
        got = salary_mod.clears_bar(salary_mod.parse(text))
        ok = got == want
        mark = "PASS" if ok else "FAIL"
        print(f"  [{mark}] {label:48s} {text:22s} -> {got}")
        if not ok:
            failures.append(f"{label}: input={text!r} want={want} got={got}")

    print("\n=== display() ===")
    for text, needles, label in DISPLAY_CASES:
        shown = salary_mod.parse(text).display()
        missing = [n for n in needles if n not in shown]
        ok = not missing
        mark = "PASS" if ok else "FAIL"
        print(f"  [{mark}] {label:48s} -> {shown}")
        if not ok:
            failures.append(f"{label}: display={shown!r} missing {missing}")

    print("\n=== parse_description() ===")
    for desc, want_basis, want_top, label in DESCRIPTION_CASES:
        result = salary_mod.parse_description(desc)
        ok = result.basis == want_basis and approx(result.top, want_top)
        mark = "PASS" if ok else "FAIL"
        print(f"  [{mark}] {label:48s} -> {result.basis} top={result.top}")
        if not ok:
            failures.append(
                f"{label}: want basis={want_basis} top={want_top}, "
                f"got basis={result.basis} top={result.top}"
            )

    print("\n=== detect_basis() on structured fields ===")
    for text, want_basis, label in STRUCTURED_CASES:
        basis, _share, _stated = salary_mod.detect_basis(text)
        ok = basis == want_basis
        mark = "PASS" if ok else "FAIL"
        print(f"  [{mark}] {label:48s} {str(text)[:24]:26s} -> {basis}")
        if not ok:
            failures.append(f"{label}: input={text!r} want={want_basis} got={basis}")

    print("\n" + "=" * 60)
    total = (len(BASIS_CASES) + len(ADVERTISED_CASES) + len(BAR_CASES)
             + len(DISPLAY_CASES) + len(DESCRIPTION_CASES) + len(STRUCTURED_CASES))
    if failures:
        print(f"FAILED {len(failures)}/{total}")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print(f"ALL {total} BASE-VS-OTE TESTS PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
