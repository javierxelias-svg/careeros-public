#!/usr/bin/env python3
"""
Company-category and not-corporate tests.

    python3 careeros/tests/test_company.py

Added 2026-08-17 when the operator enabled four target company categories.
The penalty side is tested as hard as the bonuses.

Revised 2026-08-24. Hard term 3 ("under ~100 people") was relaxed outright by the
operator: "you can expand employee count, that's fine." The penalty no longer tracks
headcount — it tracks the shape the operator actually rejects: consultancies and body
shops, banks, gig-work platforms, legacy enterprise IT, and mega-tech. Big remote-first
product companies (Coinbase, Databricks, Stripe, Cloudflare, Airbnb...) were released
and are asserted below to score zero, so a future edit cannot quietly re-penalise them.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import company  # noqa: E402
import fit  # noqa: E402
import prefilter  # noqa: E402

# (company, expected sign of points, label that must appear)
CASES = [
    ("Beehiiv", +1, "creator-economy tools"),
    ("Ghost", +1, "creator-economy tools"),
    ("Gumroad", +1, "creator-economy tools"),
    # Hospitality / luxury disabled 2026-10-08 (operator's call): Mews, Cloudbeds and
    # Canary now score 0, checked in HOSPITALITY_OFF below.
    ("Surge AI", +1, "AI evals / red-teaming / model QA"),
    ("Labelbox", +1, "AI evals / red-teaming / model QA"),
    ("Deel", +1, "LATAM / bilingual-premium"),
    ("Oyster", +1, "LATAM / bilingual-premium"),
    # The penalty side.
    ("Google", -1, "large employer"),
    ("Goldman Sachs", -1, "large employer"),
    ("Deloitte", -1, "large employer"),
    ("Accenture", -1, "large employer"),
    ("Toptal", -1, "large employer"),
    ("Optum", -1, "large employer"),
]

# Must score zero — no category, no penalty.
NEUTRAL = ["Hightouch", "MapTiler", "Storyblok", "Jumio", "Harris Farm Markets"]

# Released 2026-08-24 when term 3 was relaxed. Big, but remote-first product companies,
# so size alone must not hold them down. Airbnb is deliberately NOT here: it was also
# added to hospitality_tech (see HOSPITALITY_OFF below).
RELEASED = ["Coinbase", "Databricks", "Stripe", "Cloudflare", "Atlassian", "Twilio"]

# Legal suffixes and casing must not defeat the match.
NORMALIZE = [("Deel Inc", "Deel"), ("MEWS", "Mews"), ("Gumroad, LLC", "Gumroad")]

# Substring collisions the whole-word rule must refuse.
NO_FALSE_MATCH = ["Remotasks", "Kitchen Brains", "Ghostwriter Agency Ltd",
                  "Circleci", "Blockchain Capital"]


def main():
    failures = []

    print("=== company.score() ===")
    for name, sign, label in CASES:
        points, labels = company.score(name)
        ok = (points * sign > 0) and label in labels
        print(f"  [{'PASS' if ok else 'FAIL'}] {name:22s} {points:+3d}  {labels}")
        if not ok:
            failures.append(f"{name}: want sign {sign} and {label!r}, got {points} {labels}")

    print("\n=== neutral companies score exactly zero ===")
    for name in NEUTRAL:
        points, labels = company.score(name)
        ok = points == 0 and not labels
        print(f"  [{'PASS' if ok else 'FAIL'}] {name:26s} {points:+3d} {labels}")
        if not ok:
            failures.append(f"{name}: expected 0/[], got {points}/{labels}")

    print("\n=== suffixes and casing ===")
    for raw, plain in NORMALIZE:
        ok = company.score(raw) == company.score(plain)
        print(f"  [{'PASS' if ok else 'FAIL'}] {raw:20s} == {plain}")
        if not ok:
            failures.append(f"{raw} scored differently from {plain}")

    print("\n=== substring collisions must NOT match ===")
    for name in NO_FALSE_MATCH:
        points, labels = company.score(name)
        ok = points == 0
        print(f"  [{'PASS' if ok else 'FAIL'}] {name:24s} {points:+3d} {labels}")
        if not ok:
            failures.append(f"{name}: false match, got {points} {labels}")

    print("\n=== a small target-category company outranks a corporate ===")
    # Same role, same everything else — only the employer differs.
    small, _ = company.score("Beehiiv")
    big, _ = company.score("Deloitte")
    ok = small > big
    print(f"  [{'PASS' if ok else 'FAIL'}] Beehiiv ({small:+d}) > Deloitte ({big:+d})")
    if not ok:
        failures.append("target-category company did not outrank the large employer")

    print("\n=== released 2026-08-24: size alone is no longer a penalty ===")
    for name in RELEASED:
        points, labels = company.score(name)
        ok = points >= 0 and "large employer" not in labels
        print(f"  [{'PASS' if ok else 'FAIL'}] {name:<12} -> {points:+d} {labels}")
        if not ok:
            failures.append(f"{name}: still penalised after term 3 was relaxed")

    # Hospitality / luxury disabled 2026-10-08, operator's call. Airbnb was its
    # flagship case; now it, Mews, Cloudbeds and Canary all score 0 and are
    # still never treated as large employers.
    print("\n=== hospitality lane off: no bonus, no penalty ===")
    for name in ("Airbnb", "Mews", "Cloudbeds", "Canary Technologies"):
        points, labels = company.score(name)
        ok = points == 0 and "hospitality / luxury tech" not in labels
        print(f"  [{'PASS' if ok else 'FAIL'}] {name} -> {points:+d} {labels}")
        if not ok:
            failures.append(f"{name}: want 0 after hospitality removal, got {points} {labels}")

    print("\n=== broken config must not crash the run ===")
    got = company.score("Beehiiv", path="/nonexistent/companies.json")
    ok = got == (0, [])
    print(f"  [{'PASS' if ok else 'FAIL'}] missing config -> {got}")
    if not ok:
        failures.append(f"missing config returned {got}")

    print("\n=== the four lanes the operator opened are reachable in fit.py ===")
    lane_cases = [
        ("AI Red Team Engineer", fit.LANE_ADJACENT),
        # The bug this ordering exists to prevent: the senior pure-engineering
        # gate matches "Senior <anything> Engineer".
        ("Senior Red Team Engineer", fit.LANE_ADJACENT),
        ("Model Evaluation Engineer", fit.LANE_ADJACENT),
        ("Evals Engineer", fit.LANE_ADJACENT),
        ("Model QA Specialist", fit.LANE_ADJACENT),
        ("AI Safety Engineer", fit.LANE_ADJACENT),
        # Reversed 2026-09-28, deliberately. This asserted off-lane on the
        # reading that "AI Trainer" is a teaching job, which the operator
        # excludes. At the labs and data companies it is not: it is
        # writing and grading model responses, which is evals work wearing the
        # vocabulary of teaching, and it is one of the few lanes that hires
        # with no seniority gate and takes part-time hours. The word really is used both ways, so the carve-out in
        # fit.py requires the `ai` prefix and "Corporate Trainer" stays off.
        ("AI Trainer", fit.LANE_ADJACENT),
        ("Corporate Trainer", fit.LANE_OFF),
        ("Account Executive", fit.LANE_OFF),
        ("Senior Backend Engineer", fit.LANE_OFF),
        # Engineering-heavy titles demoted to adjacent 2026-10-12 (the
        # operator's re-aim); still never off.
        ("Forward Deployed Engineer", fit.LANE_ADJACENT),
        ("Solutions Architect", fit.LANE_ADJACENT),
    ]
    for title, expected in lane_cases:
        lane, label = fit.classify(title)
        ok = lane == expected
        print(f"  [{'PASS' if ok else 'FAIL'}] {title:28s} -> {lane:8s} ({label})")
        if not ok:
            failures.append(f"{title}: want {expected}, got {lane}")

    print("\n=== Spanish is finally scored ===")
    flag_cases = [
        ("Support for our Spanish-speaking customers across LATAM", True),
        ("Bilingual support engineer, English and Spanish", True),
        ("Fluent in Spanish required", True),
        # Must not fire on a country, only on the requirement.
        ("Our office is in Spain and we love spanish food", False),
    ]
    for text, expected in flag_cases:
        green, _ = prefilter.find_flags(text)
        got = "bilingual advantage" in green
        ok = got == expected
        print(f"  [{'PASS' if ok else 'FAIL'}] {text[:50]:52s} -> {got}")
        if not ok:
            failures.append(f"bilingual flag on {text!r}: want {expected}, got {got}")

    print("\n" + "=" * 60)
    if failures:
        print(f"FAILED {len(failures)}")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("ALL COMPANY TESTS PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
