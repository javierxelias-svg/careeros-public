#!/usr/bin/env python3
"""
Curated-page tests, run with plain python3.

    python3 careeros/tests/test_curated.py

These pin the selection defects found on 2026-08-18, when the first generated
list put five country-locked Elastic variants and a $256k five-year Coinbase
role above every door the operator could actually walk through.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import curated  # noqa: E402
import fit  # noqa: E402
import geo  # noqa: E402
import salary as salary_mod  # noqa: E402


class FakeListing:
    def __init__(self, title, company, description="", url="https://example.com/1"):
        self.title = title
        self.company = company
        self.description = description
        self.url = url


class FakeItem:
    def __init__(self, listing, salary, lane=fit.LANE_CORE, freedom=5,
                 geo_class=geo.CLASS_ANYWHERE, green=(), red=()):
        self.listing = listing
        self.salary = salary
        self.fit_lane = lane
        self.freedom = freedom
        self.geo_class = geo_class
        self.green = list(green)
        self.red = list(red)


def item(title, company, description="", low=100_000, high=140_000,
         confidence="published", lane=fit.LANE_CORE, geo_class=geo.CLASS_ANYWHERE):
    return FakeItem(
        FakeListing(title, company, description),
        salary_mod.Salary(low, high, confidence=confidence),
        lane=lane, geo_class=geo_class,
    )


TITLE_CASES = [
    ("Support Engineer", "support", "kept: target family"),
    ("Mid-Market Implementation Specialist, Americas", "implementation", "kept"),
    ("Forward Deployed Engineer", "fde", "kept"),
    ("Solutions Architect", "solutions", "kept"),
    ("Agentic AI Engineer", "ai", "kept"),
    ("Technical Account Manager", "support", "kept despite the word manager"),
    # Infrastructure deployment is not forward deployed. Postgres and database
    # deployment roles are internal engineering, not customer-facing.
    ("Postgres Deployment Engineer (Nix)", None, "dropped: infra, not forward deployed"),
    ("Staff Product Designer", None, "dropped: not a target family"),
]

# The decision, not the regex. Both lists below contain the word "manager"; the
# difference is whether it names a team or a customer relationship. Getting this
# wrong deleted a Technical Customer Success Manager role the operator was
# considering from the list on 2026-08-18.
EXCLUDED_TITLES = [
    ("Support Engineering Manager, Americas", "people management"),
    ("Senior Manager, GTM Sales Engineer", "senior manager slipped a comma anchor once"),
    ("Director of Support Engineering", "director"),
    ("Head of Solutions Architecture", "head of"),
    ("Engineering Manager, AI", "manages engineers"),
]
KEPT_MANAGER_TITLES = [
    ("Technical Account Manager", "account manager is a target title"),
    ("Technical Customer Success Manager - Americas", "IC customer-facing role, not a team"),
    ("Customer Success Manager (Americas)", "customer relationship, not a team"),
    ("Engagement Manager - Americas", "individual contributor delivery role"),
]

LOCKED_TITLES = [
    ("Senior Solution Architect, Mumbai", True, "country in the title"),
    ("Senior Solution Architect - Sydney based", True, "city in the title"),
    ("Senior Solutions Architect (NATO)", True, "alliance clearance"),
    ("Senior Solutions Architect - Federal Civilian", True, "US federal"),
    ("Solutions Architect - SLED", True, "US state and local"),
    ("Partner Solution Architect - LATAM", False, "LATAM is in scope"),
    ("Mid-Market Implementation Specialist, Americas", False, "Americas is in scope"),
]


def main():
    failures = []

    print("=== family_of() ===")
    for title, want, label in TITLE_CASES:
        got = curated.family_of(title)
        ok = got == want
        print(f"  [{'PASS' if ok else 'FAIL'}] {label:48s} {title[:38]:40s} -> {got}")
        if not ok:
            failures.append(f"{label}: want {want}, got {got}")

    print("\n=== is_management() ===")
    for title, label in EXCLUDED_TITLES:
        ok = curated.is_management(title)
        print(f"  [{'PASS' if ok else 'FAIL'}] excluded: {label:44s} {title[:42]}")
        if not ok:
            failures.append(f"should exclude {title!r} ({label})")
    for title, label in KEPT_MANAGER_TITLES:
        ok = not curated.is_management(title)
        print(f"  [{'PASS' if ok else 'FAIL'}] kept:     {label:44s} {title[:42]}")
        if not ok:
            failures.append(f"should keep {title!r} ({label})")

    print("\n=== LOCKED_TITLE ===")
    for title, want, label in LOCKED_TITLES:
        got = bool(curated.LOCKED_TITLE.search(title))
        ok = got == want
        print(f"  [{'PASS' if ok else 'FAIL'}] {label:38s} {title[:40]:42s} -> locked={got}")
        if not ok:
            failures.append(f"{label}: want locked={want}, got {got}")

    print("\n=== build(): ordering and hygiene ===")
    door = item("Support Specialist, Americas", "Acme Robotics", "No years mentioned at all here.",
                75_000, 109_250)
    lottery = item("Forward Deployed Engineer", "Coinbase",
                   "Requires 5+ years of experience in a similar role.", 218_025, 256_500)
    placeholder = item("Full Stack AI Engineer", "Interview Resources",
                       "Great opportunity.", 30_000, 90_000)
    locked = item("Senior Solution Architect, Mumbai", "Elastic", "Distributed team.", 133_800, 178_800)
    roles = curated.build([lottery, placeholder, locked, door], notes={}, target=10, pinned=[])
    keys = [r["key"] for r in roles]

    checks = [
        (len(roles) == 2, f"placeholder band and locked title both dropped (got {len(roles)})"),
        (keys and keys[0].startswith("acme-robotics"),
         "a reachable door outranks a $256k role asking five years"),
        (all("mumbai" not in k for k in keys), "no country-locked title survives"),
        (all("interview-resources" not in k for k in keys), "no $30k floor band survives"),
    ]
    for ok, label in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
        if not ok:
            failures.append(label)

    print("\n=== build(): the wall is reported, never used to filter ===")
    # Restated 2026-09-30 for the new wall scale, and the intent matters more
    # than the number: the DIGEST now filters high walls out, and this pins that
    # the curated PAGE still does not. The page is where the operator goes on
    # purpose to look at the stretch; the digest is what arrives unasked. If a
    # later change makes the page filter too, the stretch is visible nowhere.
    walled = item("Solutions Engineer", "SomeCo",
                  "You will need 8+ years of experience in a similar role.", 120_000, 150_000)
    roles = curated.build([walled], notes={}, target=10, pinned=[])
    ok = (len(roles) == 1 and roles[0]["wall"] == 5
          and roles[0]["wing"]["label"] == "Real stretch")
    print(f"  [{'PASS' if ok else 'FAIL'}] an 8-year role is kept, marked wall 5, labelled a real stretch")
    if not ok:
        failures.append("high-wall role must be kept and labelled, not filtered out")

    print("\n=== notes merge ===")
    notes = {"someco|solutions-engineer": {"reviewed": True, "offer": ["x"], "pros": ["y"],
                                           "cons": ["z"], "angle": "a", "ask": "b"}}
    roles = curated.build([walled], notes=notes, target=10, pinned=[])
    ok = roles[0]["reviewed"] is True and roles[0]["angle"] == "a"
    print(f"  [{'PASS' if ok else 'FAIL'}] hand-written notes survive a rebuild and mark the role reviewed")
    if not ok:
        failures.append("notes did not merge")

    unreviewed = curated.build([walled], notes={}, target=10, pinned=[])[0]
    ok = unreviewed["reviewed"] is False and unreviewed["angle"].startswith("Not reviewed yet")
    print(f"  [{'PASS' if ok else 'FAIL'}] an unreviewed role says so instead of pretending")
    if not ok:
        failures.append("auto entry must be labelled")

    print("\n=== the life test ===")
    # A real band, because the pay test now reads the likely offer rather than the
    # ceiling: $110k-$130k lands at $115,000 on the lower quartile.
    base = {"lo": 110_000, "hi": 130_000, "port": "yes", "variable": False, "wall": 0}
    life_cases = [
        ("unlimited PTO, async team, no on-call", 7, "a posting saying no on-call PASSES the pager test"),
        ("There is no pager duty and no weekend rotation. Flexible hours. Unlimited vacation.",
         7, "negated pager language, stated twice"),
        ("You will join an on-call rotation. Unlimited PTO. Async.", 6, "a real rotation fails"),
        ("Async team. 24/7 coverage required. Unlimited PTO.", 6, "24/7 is a pager by another name"),
        ("Nothing stated about time off or hours.", 5, "silence fails the two it cannot evidence"),
    ]
    for text, want, label in life_cases:
        got = sum(curated.life_test(base, text).values())
        ok = got == want
        print(f"  [{'PASS' if ok else 'FAIL'}] {label:56s} -> {got}/7")
        if not ok:
            failures.append(f"{label}: want {want}/7, got {got}/7")

    poor = curated.life_test({"lo": 60_000, "hi": 80_000, "port": "ask",
                              "variable": True, "wall": 4},
                             "on-call rotation required")
    ok = sum(poor.values()) == 0
    print(f"  [{'PASS' if ok else 'FAIL'}] a role failing everything scores 0/7")
    if not ok:
        failures.append("worst case did not score 0/7")

    print("\n=== base_title(): one role, not fourteen filings ===")
    title_norm = [
        ("Senior Customer Engineer, Majors - NYC", "Senior Customer Engineer - Majors", "city dropped"),
        ("Senior Customer Engineer - Vancouver, BC", "Senior Customer Engineer", "city and province dropped"),
        ("Senior Solutions Engineer | East Coast | Remote", "Senior Solutions Engineer", "coast and remote dropped"),
        ("Solutions Architect - PreSales", "Solutions Architect - PreSales", "PreSales is not a place"),
        ("Forward Deployed Engineer", "Forward Deployed Engineer", "nothing to strip"),
    ]
    for raw, want, label in title_norm:
        got = curated.base_title(raw)
        ok = got == want
        print(f"  [{'PASS' if ok else 'FAIL'}] {label:38s} -> {got}")
        if not ok:
            failures.append(f"{label}: want {want!r}, got {got!r}")
    ok = "americas" in curated.base_title("Implementation Specialist - Americas (East)").lower()
    print(f"  [{'PASS' if ok else 'FAIL'}] Americas survives, because it says who can employ the operator, not a filing detail")
    if not ok:
        failures.append("Americas must not be stripped from a title")

    print("\n=== inverted bands ===")
    upside_down = item("Customer Solutions Engineer II", "Fivetran",
                       "No years mentioned.", 134_000, 111_714)
    roles = curated.build([upside_down], notes={}, target=5, pinned=[])
    ok = roles and roles[0]["lo"] == 111_714 and roles[0]["hi"] == 134_000
    print(f"  [{'PASS' if ok else 'FAIL'}] a band published floor-above-ceiling is put back in order")
    if not ok:
        failures.append("inverted band was not corrected")

    print("\n=== likely_offer(): the ceiling is not the offer ===")
    offer_cases = [
        ({"lo": 75_000, "hi": 109_250}, "", 83_562,
         "a $75k-$109k support band lands at its lower quartile, not its ceiling"),
        ({"lo": 100_000, "hi": 200_000}, "We use geographic ranges and cost of labor data",
         100_000, "a company that adjusts by location pays a cheap location its floor"),
        ({"lo": 85_000, "hi": 110_000}, "This range is location-independent",
         91_250, "location-independent pay still lands low in band, but does not get cut"),
        ({"lo": 0, "hi": 0}, "", 0, "no band published"),
    ]
    for role, text, want, label in offer_cases:
        got, _why = curated.likely_offer(role, text)
        ok = abs(got - want) <= 1
        print(f"  [{'PASS' if ok else 'FAIL'}] {label:64s} -> ${got:,}")
        if not ok:
            failures.append(f"{label}: want {want}, got {got}")

    print("\n=== pinned roles ===")
    pinned = [{"t": "Junior Technical Account Manager", "c": "Example Co", "fam": "support",
               "url": "https://example.com", "lo": 0, "hi": 0, "conf": "unknown",
               "wall": 0, "lane": "core", "freedom": 11, "port": "americas",
               "variable": False, "found": "17 August 2026", "offer": [], "pros": [],
               "cons": [], "angle": "a", "ask": "b"}]
    roles = curated.build([door], notes={}, target=10, pinned=pinned)
    carried = [r for r in roles if r.get("pinned")]
    ok = len(carried) == 1 and carried[0]["found"] == "17 August 2026"
    print(f"  [{'PASS' if ok else 'FAIL'}] a role the live pool no longer returns is carried over with its date")
    if not ok:
        failures.append("pinned role was not carried over")

    live_dupe = [{"t": "Support Specialist, Americas", "c": "Acme Robotics", "lo": 1, "hi": 2,
                  "conf": "unknown", "wall": 0, "lane": "core", "freedom": 1,
                  "port": "ask", "variable": False, "found": "old", "offer": [],
                  "pros": [], "cons": [], "angle": "a", "ask": "b"}]
    roles = curated.build([door], notes={}, target=10, pinned=live_dupe)
    ok = len(roles) == 1 and not roles[0].get("pinned")
    print(f"  [{'PASS' if ok else 'FAIL'}] a pinned role the pool DID return loses to the live one")
    if not ok:
        failures.append("stale pinned entry shadowed a live listing")

    print("\n=== the shipped notes file parses and matches the schema ===")
    try:
        shipped = curated.load_notes()
        ok = len(shipped) > 0 and all(
            all(field in entry for field in ("offer", "pros", "cons", "angle", "ask"))
            for entry in shipped.values())
        print(f"  [{'PASS' if ok else 'FAIL'}] {len(shipped)} hand-written entries, all with the required fields")
        if not ok:
            failures.append("curated-notes.json is missing fields")
    except (OSError, json.JSONDecodeError) as exc:
        print(f"  [FAIL] notes file unreadable: {exc}")
        failures.append("notes file unreadable")

    print("\n" + "=" * 60)
    if failures:
        print(f"FAILED {len(failures)}")
        for f in failures:
            print("  - " + f)
        return 1
    print("ALL CURATED TESTS PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
