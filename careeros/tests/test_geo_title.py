#!/usr/bin/env python3
"""
Title-versus-region tests.

    python3 careeros/tests/test_geo_title.py

Every case below is a real line from the digest delivered on 2026-08-16
(message_ids 9-10). WeWorkRemotely stamped <region>Anywhere in the World</region>
on 95 of 100 items that morning because that is its feed CATEGORY, so four
postings that named their own territory in their own titles went out to the
operator wearing a "work from anywhere" globe.

The rule under test: when a title names a region, the title wins.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import geo  # noqa: E402

WWR_FEED_REGION = "Anywhere in the World"

# (label, title, region_field, expected_class)
CASES = [
    # Cities, added 2026-09-30. A dry run put "UX Research Programs & Operations
    # (Zurich)" into the digest wearing a work-from-anywhere globe, beside "Premium
    # Support Engineer (Tokyo)". The two existing rules match a COUNTRY or a region
    # abbreviation after a delimiter, and a city is neither.
    #
    # curated.LOCKED_TITLE has locked Mumbai and Sydney since August. This was the
    # third guard found in a single day that the curated page has and the digest
    # does not — the others were the "no on-call" negation and the office
    # requirement. Each time the page opened deliberately was protected and the
    # message that arrives unasked was not.
    ("Zurich in the title", "UX Research Programs & Operations (Zurich)",
     WWR_FEED_REGION, geo.CLASS_BLOCKED),
    ("Tokyo in the title", "Premium Support Engineer (Tokyo)",
     WWR_FEED_REGION, geo.CLASS_BLOCKED),
    ("London in the title", "Solutions Engineer (London)",
     WWR_FEED_REGION, geo.CLASS_BLOCKED),
    ("Munich after a dash", "Solutions Architect - Munich",
     WWR_FEED_REGION, geo.CLASS_BLOCKED),
    ("Amsterdam after a pipe", "Customer Engineer | Amsterdam",
     WWR_FEED_REGION, geo.CLASS_BLOCKED),
    # Americas cities are NOT locked: the operator is US-authorised and open to
    # the Americas, so these are places they can work.
    ("New York is in the Americas", "Implementation Manager (New York, NY)",
     WWR_FEED_REGION, geo.CLASS_ANYWHERE),
    ("Toronto is in the Americas", "Solutions Engineer (Toronto)",
     WWR_FEED_REGION, geo.CLASS_ANYWHERE),
    # A city named as a MARKET is not a location requirement. The lookahead that
    # protects "LATAM clients" protects this too.
    ("London clients is a market, not a seat", "Support Engineer - London clients",
     WWR_FEED_REGION, geo.CLASS_ANYWHERE),

    # The four that shipped wrong on 2026-08-16.
    ("MapTiler, Europe in the title",
     "Location Services Engineer | Maps Platform (Remote in Europe)",
     WWR_FEED_REGION, geo.CLASS_BLOCKED),
    ("Storyblok, Europe/LaTAM",
     "AI Operations & Automation Manager - Europe/LaTAM",
     WWR_FEED_REGION, geo.CLASS_BLOCKED),
    ("Storyblok, Canada + Europe",
     "Deal Operations Manager - Canada, Europe",
     WWR_FEED_REGION, geo.CLASS_BLOCKED),
    ("Airtable, a US coast is US-class, not blocked",
     "Senior Solutions Architect- West Coast",
     WWR_FEED_REGION, geo.CLASS_US),

    # Must still pass through untouched.
    ("no region in the title, feed says anywhere",
     "Forward Deployed Engineer, Compliance [Office of the CTO]",
     WWR_FEED_REGION, geo.CLASS_ANYWHERE),
    ("plain title, plain feed",
     "Senior Solutions Architect", WWR_FEED_REGION, geo.CLASS_ANYWHERE),
    ("title says anywhere — not a lock",
     "Support Engineer (Work From Anywhere)", WWR_FEED_REGION, geo.CLASS_ANYWHERE),
    ("US in the title stays eligible — the operator is US-authorised",
     "AI Engineer (US Only)", "", geo.CLASS_US),
    ("no title at all, old two-arg behaviour",
     "", WWR_FEED_REGION, geo.CLASS_ANYWHERE),
]


def main():
    failures = []

    print("=== classify_geo(): title outranks feed region ===")
    for label, title, region, expected in CASES:
        got, reason = geo.classify_geo(region, "", title)
        ok = got == expected
        print(f"  [{'PASS' if ok else 'FAIL'}] {label:48s} -> {got}  ({reason[:52]})")
        if not ok:
            failures.append(f"{label}: want {expected}, got {got}")

    print("\n=== the globe must never appear on a region-locked job ===")
    for label, title, region, expected in CASES[:4]:
        got, _ = geo.classify_geo(region, "", title)
        ok = got != geo.CLASS_ANYWHERE
        print(f"  [{'PASS' if ok else 'FAIL'}] {title[:56]:58s} -> {got}")
        if not ok:
            failures.append(f"{label}: still classed work-from-anywhere")

    # ---------------------------------------------------------------------
    # 2026-08-18: a region FIELD naming a US sub-region, and a body sentence
    # that says "anywhere" while meaning the opposite.
    # ---------------------------------------------------------------------
    linear = ("Linear is a remote-first company, with optional co-working offices "
              "in San Francisco, New York, and London. This role is open to "
              "candidates based in North America. You can work from anywhere "
              "within this region.")
    print("\nregion field and qualified 'anywhere':")
    checks = [
        ("Linear CSM, North America", ("North America", linear, "Customer Success Manager"),
         geo.CLASS_US),
        ("qualified anywhere, no region", ("", linear, "Solutions Engineer"),
         geo.CLASS_US),
        ("genuine anywhere survives",
         ("Remote", "We hire globally. There are no offices, work from anywhere.",
          "Developer Relations Engineer"), geo.CLASS_ANYWHERE),
        ("stated anywhere region survives",
         ("Anywhere in the World", "work from anywhere", "Customer Success Manager"),
         geo.CLASS_ANYWHERE),
    ]
    for label, args, want in checks:
        got, why = geo.classify_geo(*args)
        ok = got == want
        print(f"  [{'PASS' if ok else 'FAIL'}] {label:38s} -> {got} ({why[:44]})")
        if not ok:
            failures.append(f"{label}: got {got}, want {want}")

    print("\n" + "=" * 60)
    if failures:
        print(f"FAILED {len(failures)}")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("ALL GEO TITLE TESTS PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
