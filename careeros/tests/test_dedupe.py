#!/usr/bin/env python3
"""
Territory-suffix dedupe tests.

    python3 careeros/tests/test_dedupe.py

On 2026-08-16 slots 2 and 3 of the digest were "Senior Solutions Architect" and
"Senior Solutions Architect- West Coast", both at Airtable, both showing the
same estimated band. One job, listed once per territory, counted twice.

The opposite failure is worse: collapsing two genuinely different roles means
one of them is silently never shown. The SEPARATE cases below guard that side.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import dedupe  # noqa: E402

# (title, expected stripped title)
STRIP_CASES = [
    ("Senior Solutions Architect- West Coast", "Senior Solutions Architect"),
    ("Deal Operations Manager - Canada, Europe", "Deal Operations Manager"),
    ("AI Operations & Automation Manager - Europe/LaTAM",
     "AI Operations & Automation Manager"),
    ("Customer Success Manager, EMEA", "Customer Success Manager"),
    # Seen live 2026-08-17: one Airtable role listed twice, "- West" and "- East".
    ("Program Manager, Professional Services - West",
     "Program Manager, Professional Services"),
    ("Program Manager, Professional Services - East",
     "Program Manager, Professional Services"),
    ("Location Services Engineer | Maps Platform (Remote in Europe)",
     "Location Services Engineer | Maps Platform"),
    # Untouched: no trailing territory.
    ("Forward Deployed Engineer, Compliance [Office of the CTO]",
     "Forward Deployed Engineer, Compliance [Office of the CTO]"),
    ("Senior Solutions Architect", "Senior Solutions Architect"),
    # A region word mid-title is NOT a suffix and must survive.
    ("Head of Europe Sales", "Head of Europe Sales"),
    ("US Payments Engineer", "US Payments Engineer"),
    # Never strip to nothing.
    ("EMEA", "EMEA"),
]

# Pairs that must collapse to one key.
SAME = [
    ("Airtable", "Senior Solutions Architect",
     "Airtable", "Senior Solutions Architect- West Coast"),
    ("Storyblok", "Deal Operations Manager",
     "Storyblok", "Deal Operations Manager - Canada, Europe"),
    ("Airtable", "Program Manager, Professional Services - West",
     "Airtable", "Program Manager, Professional Services - East"),
]

# Pairs that must stay distinct.
SEPARATE = [
    ("Airtable", "Senior Solutions Architect",
     "Airtable", "Staff Solutions Architect"),
    ("Airtable", "Senior Solutions Architect",
     "Hightouch", "Senior Solutions Architect"),
    ("Storyblok", "Deal Operations Manager",
     "Storyblok", "AI Operations & Automation Manager"),
    ("Acme", "Head of Europe Sales", "Acme", "Head of Sales"),
]



# --------------------------------------------------------------------------
# 2026-08-18: the employer's own board must win a duplicate, whatever order the
# copies arrive in. Braze's "Customer Success Manager II" comes from
# WeWorkRemotely as "Anywhere in the World" and from Braze's Greenhouse board as
# "Remote - Spain" — the operator has no right to work in Spain, and the
# aggregator copy sat at number four on the shortlist for two days.
# --------------------------------------------------------------------------
def test_employer_board_wins_duplicates():
    import sources as _sources

    class _Item:
        def __init__(self, listing):
            self.listing = listing

    class _Quiet:
        def info(self, *a, **k):
            pass

    def _pair(order):
        wwr = _Item(_sources.Listing(title="Customer Success Manager II",
                                     company="Braze", region="Anywhere in the World",
                                     source="weworkremotely_all"))
        ats = _Item(_sources.Listing(title="Customer Success Manager II",
                                     company="Braze", region="Remote - Spain",
                                     source="ats"))
        items = [wwr, ats] if order == "aggregator first" else [ats, wwr]
        kept = dedupe.filter_new(items, set(), _Quiet())
        return kept[0][1].listing.source, len(kept)

    failures = []
    for order in ("aggregator first", "employer first"):
        source, count = _pair(order)
        if source != "ats" or count != 1:
            failures.append(f"{order}: kept {source!r}, {count} item(s)")
    return failures


# _timezone_penalty(): West and East merge to one key, correctly. WHICH copy
# survives is the operator's working hours. On US Eastern or Atlantic time a
# PST/MST seat means a noon-to-9pm day. Before 2026-08-19 the survivor was
# whichever arrived first, and on one Mid-Market Implementation Specialist
# listing that was West.
TZ_CASES = [
    ("Mid-Market Implementation Specialist - Americas (East)", 0),
    ("Program Manager, Professional Services - East", 0),
    ("Solutions Engineer, CST timezone", 0),
    ("Mid-Market Implementation Specialist - Americas (West)", 2),
    ("Senior Solutions Architect- West Coast", 2),
    ("Engineer, PST timezone", 2),
    # Unmarked stays neutral: guessing here silently hides a job.
    ("Product Support Specialist", 1),
    ("Customer Success Manager, EMEA", 1),
]


class _TZItem:
    def __init__(self, title, source="ats"):
        self.listing = type("L", (), {"title": title, "source": source,
                                      "company": "Example Co"})()


def _tz_survivor_is_east():
    """The whole point: given both seats, the East one must be the one kept."""
    west = _TZItem("Mid-Market Implementation Specialist - Americas (West)")
    east = _TZItem("Mid-Market Implementation Specialist - Americas (East)")
    class _Quiet:
        def info(self, *a, **k):
            pass

    for order in ([west, east], [east, west]):
        kept = dedupe.filter_new(order, set(), _Quiet())
        if len(kept) != 1:
            return f"expected 1 survivor, got {len(kept)}"
        if "(East)" not in kept[0][1].listing.title:
            return f"kept {kept[0][1].listing.title!r}, wanted the East seat"
    return None


def main():
    failures = []

    print("=== strip_region_suffix() ===")
    for title, expected in STRIP_CASES:
        got = dedupe.strip_region_suffix(title)
        ok = got == expected
        print(f"  [{'PASS' if ok else 'FAIL'}] {title[:50]:52s} -> {got!r}")
        if not ok:
            failures.append(f"{title!r}: want {expected!r}, got {got!r}")

    print("\n=== same job, two territories -> one key ===")
    for c1, t1, c2, t2 in SAME:
        ok = dedupe.make_key(c1, t1) == dedupe.make_key(c2, t2)
        print(f"  [{'PASS' if ok else 'FAIL'}] {t1[:32]:34s} == {t2[:38]}")
        if not ok:
            failures.append(f"did not merge: {t1!r} / {t2!r}")

    print("\n=== _timezone_penalty() — which seat survives the merge ===")
    for title, want in TZ_CASES:
        got = dedupe._timezone_penalty(_TZItem(title))
        ok = got == want
        print(f"  [{'PASS' if ok else 'FAIL'}] {title[:50]:52s} -> {got}")
        if not ok:
            failures.append(f"{title!r}: want penalty {want}, got {got}")

    print("\n=== West/East merge keeps the seat on the operator's clock ===")
    err = _tz_survivor_is_east()
    print(f"  [{'PASS' if err is None else 'FAIL'}] East seat survives regardless of arrival order")
    if err:
        failures.append(err)

    print("\n=== different jobs -> different keys (the dangerous direction) ===")
    for c1, t1, c2, t2 in SEPARATE:
        ok = dedupe.make_key(c1, t1) != dedupe.make_key(c2, t2)
        print(f"  [{'PASS' if ok else 'FAIL'}] {c1}/{t1[:26]:28s} != {c2}/{t2[:26]}")
        if not ok:
            failures.append(f"wrongly merged: {c1}/{t1!r} and {c2}/{t2!r}")

    dup = test_employer_board_wins_duplicates()
    ok = not dup
    print(f"\n  [{'PASS' if ok else 'FAIL'}] employer board wins a duplicate, either arrival order")
    failures.extend(dup)

    print("\n" + "=" * 60)
    if failures:
        print(f"FAILED {len(failures)}")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("ALL DEDUPE TESTS PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
