#!/usr/bin/env python3
"""
Ashby compensation-tier tests.

    python3 careeros/tests/test_ashby_tiers.py

Ashby prices the same role per location and the board shows a blended headline.
Reading the headline credits a remote candidate with a San Francisco salary.
Every case below is copied from a live posting on 2026-08-18.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ats  # noqa: E402

CASES = [
    ("Product Support Specialist",
     {"compensationTierSummary": "$75,000 – $109,250 • Offers Equity • Multiple Ranges",
      "compensationTiers": [
          {"title": "San Francisco, New York City", "tierSummary": "$86,250 – $109,250 • Offers Equity"},
          {"title": "United States", "tierSummary": "$75,000 – $95,000 • Offers Equity"},
          {"title": "Canada", "tierSummary": "CA$75,000 – CA$95,000 • Offers Equity"}]},
     "$75,000 – $95,000 • Offers Equity",
     "the national tier, not the metro tier and not the blend"),

    ("Mid-Market Implementation Specialist",
     {"compensationTierSummary": "$120K – $159K • Offers Equity • Multiple Ranges",
      "compensationTiers": [
          {"title": "San Francisco - Remote Base Salary", "tierSummary": "$140,000 – $159,000 • Offers Equity"},
          {"title": "US Average - Remote Base Salary", "tierSummary": "$120,000 – $140,000 • Offers Equity"},
          {"title": "Canada - Remote Base Salary", "tierSummary": "CA$120,000 – CA$138,750 • Offers Equity"}]},
     "$120,000 – $140,000 • Offers Equity",
     "US Average wins over San Francisco"),

    ("Support Operations Specialist",
     {"compensationTierSummary": "$75K – $107K • Offers Equity • Multiple Ranges",
      "compensationTiers": [
          {"title": "Remote - US", "tierSummary": "$75K – $94K • Offers Equity"},
          {"title": "NYC, San Francisco", "tierSummary": "$86K – $107K • Offers Equity"}]},
     "$75K – $94K • Offers Equity",
     "Remote - US wins even when it is listed first"),

    ("no tiers published", {"compensationTierSummary": "$100K – $130K"}, "",
     "falls back to the published summary rather than inventing one"),

    ("tiers with no national row",
     {"compensationTierSummary": "$150K – $200K",
      "compensationTiers": [{"title": "San Francisco", "tierSummary": "$150K – $200K"}]},
     "", "a metro-only posting must not be read as a national band"),

    ("Canada must not be mistaken for the US",
     {"compensationTiers": [{"title": "Canada - Remote", "tierSummary": "CA$120,000 – CA$138,750"}]},
     "", "the word Canada contains no standalone 'us'"),
]


# _tier_fallback(): what is used when no national tier matched. Ashby's blended
# compensationTierSummary drops the "On Target Earnings" prefix the tier row
# carries, which recorded PermitFlow's commission package as guaranteed base and
# ranked it 3rd overall on 2026-08-19.
FALLBACK_CASES = [
    ("lone OTE tier keeps its label",
     {"compensationTiers": [{"title": None, "tierSummary": "On Target Earnings $175K – $225K • Offers Equity"}],
      "compensationTierSummary": "$175K – $225K • Offers Equity"},
     "On Target Earnings $175K – $225K • Offers Equity"),
    ("several tiers: a lost OTE label is carried back onto the blend",
     {"compensationTiers": [{"title": "SF", "tierSummary": "OTE $200K – $240K"},
                            {"title": "US", "tierSummary": "OTE $175K – $225K"}],
      "compensationTierSummary": "$175K – $240K"},
     "OTE $175K – $240K"),
    ("blend that already says OTE is left alone",
     {"compensationTiers": [{"title": "SF", "tierSummary": "OTE $200K – $240K"},
                            {"title": "US", "tierSummary": "OTE $175K – $225K"}],
      "compensationTierSummary": "OTE $175K – $240K"},
     "OTE $175K – $240K"),
    ("a lone base tier is passed straight through",
     {"compensationTiers": [{"title": None, "tierSummary": "Base Salary $120,000 – $140,000"}],
      "compensationTierSummary": "$120,000 – $140,000"},
     "Base Salary $120,000 – $140,000"),
    ("no tiers at all: the blend is all there is",
     {"compensationTierSummary": "$90K – $110K"}, "$90K – $110K"),
]

# _ashby() workplace: Ashby returns isRemote AND workplaceType, and they
# contradict each other. workplaceType is its own answer and must win.
WORKPLACE_CASES = [
    ("hybrid wins over isRemote: true", True, "Hybrid", "onsite"),
    ("onsite wins over isRemote: true", True, "Onsite", "onsite"),
    ("remote workplaceType passes", True, "Remote", "remote"),
    ("no workplaceType falls back to isRemote true", True, "", "remote"),
    ("no workplaceType falls back to isRemote false", False, "", "onsite"),
    ("neither field stated is unknown, not remote", None, "", ""),
]


def main():
    failures = []
    print("=== _national_tier() ===")
    for label, comp, want, why in CASES:
        got = ats._national_tier(comp)
        ok = got == want
        print(f"  [{'PASS' if ok else 'FAIL'}] {label:36s} -> {got or '(fallback)'}")
        print(f"          {why}")
        if not ok:
            failures.append(f"{label}: want {want!r}, got {got!r}")

    print("\n=== _tier_fallback() — the OTE label must survive ===")
    for label, comp, want in FALLBACK_CASES:
        got = ats._tier_fallback(comp)
        ok = got == want
        print(f"  [{'PASS' if ok else 'FAIL'}] {label:52s} -> {got!r}")
        if not ok:
            failures.append(f"{label}: want {want!r}, got {got!r}")

    print("\n=== _ashby() workplace — workplaceType beats isRemote ===")
    for label, is_remote, wtype, want in WORKPLACE_CASES:
        job = {"title": "T", "location": "Somewhere", "workplaceType": wtype}
        if is_remote is not None:
            job["isRemote"] = is_remote
        got = ats._ashby({"jobs": [job]}, "Co")[0]["workplace"]
        ok = got == want
        print(f"  [{'PASS' if ok else 'FAIL'}] {label:52s} -> {got!r}")
        if not ok:
            failures.append(f"{label}: want {want!r}, got {got!r}")

    total = len(CASES) + len(FALLBACK_CASES) + len(WORKPLACE_CASES)
    print("\n" + "=" * 60)
    if failures:
        print(f"FAILED {len(failures)}/{total}")
        for f in failures:
            print("  - " + f)
        return 1
    print(f"ALL {total} ASHBY TIER TESTS PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
