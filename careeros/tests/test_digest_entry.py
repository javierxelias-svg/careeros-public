#!/usr/bin/env python3
"""
Digest formatting and lane-membership tests.

    python3 careeros/tests/test_digest_entry.py

Two defects from the 2026-08-16 delivery:

  1. The globe printed on any freedom reason at all, so "Shop Assistant
     Cammeray @ Harris Farm Markets" — a retail floor job in a Sydney suburb,
     freedom 2, geo B — went out marked 🌍 because the posting said "no fixed
     hours". The globe is a claim about LOCATION and nothing else.

  2. That same listing occupied the WILDCARD section, which had no portability
     gate. A job the operator cannot do from anywhere is not a wildcard, it is noise.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import digest  # noqa: E402
import experience  # noqa: E402
import fit  # noqa: E402
import geo  # noqa: E402
import prefilter  # noqa: E402
import salary as salary_mod  # noqa: E402
import sources  # noqa: E402


def scored(title, company, geo_class, freedom, freedom_reasons, green,
           fit_lane=fit.LANE_STRETCH, region=""):
    listing = sources.Listing(
        title=title, company=company, url="https://example.test/x", region=region
    )
    return prefilter.Scored(
        listing=listing, salary=salary_mod.UNKNOWN, geo_class=geo_class,
        geo_reason="test", score=3, green=green, red=[], tz_blockers=[],
        tz_friendly=[], tier="U", notes=[], fit_lane=fit_lane,
        fit_label="unrecognised role", freedom=freedom,
        freedom_reasons=freedom_reasons, ecosystem=[],
    )


SHOP_ASSISTANT = scored(
    "Shop Assistant Cammeray", "Harris Farm Markets", geo.CLASS_US, 2,
    ["no fixed hours"], ["meaningful domain", "will train"], region="Cammeray,",
)
REAL_WILDCARD = scored(
    "Junior Support Engineer", "Globalco", geo.CLASS_ANYWHERE, 9,
    ["work from anywhere", "async"], ["will train"], fit_lane=fit.LANE_ADJACENT,
)


def with_wall(item, height, years=None):
    """Attach an enrichment verdict the way enrich.reconsider would."""
    item.wall = (height, "test", years)
    return item


# A role that is perfect on every axis the digest ranks on and asks for five
# years. It exists because the gate has to beat lane, freedom and pay, not sit
# downstream of them — the mistake that made the seniority penalty invisible for
# six weeks when it was the fifth key in a sort.
FIVE_YEAR_CORE = with_wall(
    scored("Solutions Engineer", "Perfectco", geo.CLASS_ANYWHERE, 9,
           ["work from anywhere", "async"], ["customer-facing technical"],
           fit_lane=fit.LANE_CORE),
    5, 5,
)
CLEAN_CORE = with_wall(
    scored("Solutions Engineer", "Cleanco", geo.CLASS_ANYWHERE, 9,
           ["work from anywhere", "async"], ["customer-facing technical"],
           fit_lane=fit.LANE_CORE),
    0,
)
# Blocked AND wildcard-shaped AND US-only-shaped, so it is offered to all three
# lane loops. Pins that `walled` counts it once: the first version used a list
# and would have reported 3.
# A staff TITLE, which is still a gate. Offered to all three lane loops, so it
# also pins that `walled` counts it once — the first version used a list and
# would have reported 3.
BLOCKED_EVERYWHERE = with_wall(
    scored("Staff Support Engineer", "Wallco", geo.CLASS_ANYWHERE, 9,
           ["work from anywhere"], ["will train"], fit_lane=fit.LANE_CORE),
    4,
)


def main():
    failures = []

    def check(label, ok, detail=""):
        suffix = f"  {detail}" if detail else ""
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}{suffix}")
        if not ok:
            failures.append(label)

    print("=== the globe means location, nothing else ===")
    # ⏰ narrowed 2026-10-05: it is a claim about hours, so it prints only when
    # the posting writes async or flexible hours. "no fixed hours" used to earn
    # it, and that label meant only that no time-zone clause had been found.
    async_us = scored("Support Specialist", "Asyncco", geo.CLASS_US, 4,
                      ["async"], [])
    checks = [
        ("shop assistant, silence about hours", SHOP_ASSISTANT, None, ("🌍", "⏰")),
        ("genuinely work-from-anywhere", REAL_WILDCARD, "🌍", ("⏰",)),
        ("US-remote that writes async", async_us, "⏰", ("🌍",)),
    ]
    for label, item, want, forbid in checks:
        text = digest._entry(item)
        ok = (want is None or want in text) and not any(f in text for f in forbid)
        print(f"  [{'PASS' if ok else 'FAIL'}] {label:44s} -> {want}")
        if not ok:
            failures.append(f"{label}: wanted {want}, forbade {forbid}\n{text}")

    print("\n=== WILDCARD requires portability ===")
    gate = [
        ("shop assistant is not a wildcard", SHOP_ASSISTANT, False),
        ("portable no-experience role is", REAL_WILDCARD, True),
    ]
    for label, item, expected in gate:
        got = prefilter.is_wildcard(item) and prefilter.is_portable(item)
        ok = got == expected
        print(f"  [{'PASS' if ok else 'FAIL'}] {label:44s} -> {got}")
        if not ok:
            failures.append(f"{label}: want {expected}, got {got}")

    print("\n=== WILDCARD means no experience required ===")
    # 2026-10-01: all three wildcards under that heading asked 5+ years.
    five_year_trainee = with_wall(
        scored("Learning Manager", "Yearsco", geo.CLASS_ANYWHERE, 9,
               ["work from anywhere"], ["will train"]), 5, 5)
    no_years_trainee = with_wall(
        scored("Learning Coordinator", "Freshco", geo.CLASS_ANYWHERE, 9,
               ["work from anywhere"], ["will train"]), 0)
    _, _, wild, _, _, _, _ = digest.select(
        [(0, five_year_trainee), (1, no_years_trainee)])
    names = [p[1].listing.company for p in wild]
    check("5+ years is not a wildcard, none-stated is",
          names == ["Freshco"], f"-> {names}")

    print("\n=== geo_tag(): North America is not US-only ===")
    for reason, want in (
        ("region field names North America: North America",
         "North America only, not US-only"),
        ("region field names the Americas: Americas",
         "the Americas only, not US-only"),
        ("posting states remote scope: US & Canada", "US remote · ask about working abroad"),
    ):
        got = geo.geo_tag(geo.CLASS_US, reason)
        check(f"{reason[:40]}", got == want, f"-> {got!r}")

    print("\n=== rank(): years sink a role, they no longer delete it ===")
    # Reversed 2026-09-30, hours after the block went in. The posting is a soft
    # signal and the application form is the gate — a hand-written note once read
    # "No years requirement" off a posting whose form demanded two. So a five-year role is
    # still sent, and it is sent BELOW an identical clean one.
    chosen, main_lane, _, _, _, _, walled = digest.select(
        [(0, FIVE_YEAR_CORE), (1, CLEAN_CORE)]
    )
    order = [p[1].listing.company for p in main_lane]
    check("both are sent", len(order) == 2, f"main={order}")
    check("the clean role comes FIRST, the five-year role second",
          order == ["Cleanco", "Perfectco"], f"order={order}")
    check("nothing was held back for years alone", walled == 0, f"walled={walled}")

    print("\n=== select(): a senior TITLE is still blocked ===")
    _, main_senior, _, _, _, _, walled_senior = digest.select(
        [(0, BLOCKED_EVERYWHERE)])
    check("staff/senior titles remain a gate, not a penalty",
          len(main_senior) == 0 and walled_senior == 1,
          f"main={len(main_senior)} walled={walled_senior}")

    print("\n=== rank(): freedom first, then implementation, inside a lane ===")
    # The operator named implementation, and until 2026-09-30 nothing acted on it:
    # widening the lane patterns moved 901 market roles into core and changed
    # the digest by one listing, because core was already full and nothing told
    # implementation apart from Support Engineer.
    #
    # Reversed 2026-10-05, operator decision: freedom first. A freer core role
    # now leads; implementation still wins when freedom is equal.
    impl = with_wall(
        scored("Implementation Specialist", "Implco", geo.CLASS_ANYWHERE, 6,
               ["work from anywhere"], [], fit_lane=fit.LANE_CORE), 0)
    impl.fit_label = "implementation"
    other = with_wall(
        scored("Support Engineer", "Otherco", geo.CLASS_ANYWHERE, 9,
               ["work from anywhere", "async"], [], fit_lane=fit.LANE_CORE), 0)
    other.fit_label = "support engineer"
    _, main_t, _, _, _, _, _ = digest.select([(0, other), (1, impl)])
    got = [p[1].listing.company for p in main_t]
    check("the freer core role leads, even over implementation",
          got and got[0] == "Otherco", f"order={got}")
    other.freedom, other.freedom_reasons = impl.freedom, impl.freedom_reasons
    _, main_t, _, _, _, _, _ = digest.select([(0, other), (1, impl)])
    got = [p[1].listing.company for p in main_t]
    check("at equal freedom, implementation leads",
          got and got[0] == "Implco", f"order={got}")

    print("\n=== rank(): a job that writes freedom boards first, any lane ===")
    # 2026-10-05, operator decision: any job that writes the freedom terms should
    # surface. An async CSM role (adjacent) had sat behind 14 silent core roles.
    silent_core = with_wall(
        scored("Solutions Engineer", "Silentco", geo.CLASS_US, 2,
               ["builder role"], [], fit_lane=fit.LANE_CORE), 0)
    async_adjacent = with_wall(
        scored("Customer Success Manager", "Asyncco", geo.CLASS_US, 9,
               ["async", "time off stated"], [], fit_lane=fit.LANE_ADJACENT), 0)
    async_off = with_wall(
        scored("Sales Development Rep", "Quotaco", geo.CLASS_US, 9,
               ["async"], [], fit_lane=fit.LANE_OFF), 0)
    order = [p[1].listing.company
             for p in digest.rank([(0, silent_core), (1, async_adjacent), (2, async_off)])]
    check("async customer success beats a silent core role",
          order.index("Asyncco") < order.index("Silentco"), f"order={order}")
    async_core = with_wall(
        scored("AI Engineer", "Thinco", geo.CLASS_US, 4,
               ["async"], [], fit_lane=fit.LANE_CORE), 0)
    order = [p[1].listing.company
             for p in digest.rank([(0, async_core), (1, async_adjacent)])]
    check("among jobs that write freedom, more freedom wins over job type",
          order == ["Asyncco", "Thinco"], f"order={order}")
    _, main_f, _, _, _, _, _ = digest.select(
        [(0, silent_core), (1, async_adjacent), (2, async_off)])
    got = [p[1].listing.company for p in main_f]
    check("an off-lane job never reaches the operator, async or not",
          "Quotaco" not in got and got[:1] == ["Asyncco"], f"main={got}")

    print("\n=== select(): an unreadable page is admitted, not blocked ===")
    unknown = with_wall(
        scored("Solutions Engineer", "Shellco", geo.CLASS_ANYWHERE, 9,
               ["work from anywhere", "async"], ["customer-facing technical"],
               fit_lane=fit.LANE_CORE),
        experience.UNREADABLE,
    )
    _, main_unknown, _, _, _, _, walled_unknown = digest.select([(0, unknown)])
    check("an Ashby JavaScript shell still reaches the operator, labelled",
          len(main_unknown) == 1 and walled_unknown == 0,
          f"main={len(main_unknown)} walled={walled_unknown}")

    print("\n=== select(): the retail job never reaches the digest ===")
    chosen, main_lane, wildcards, us_only, _, _, _ = digest.select(
        [("k1", SHOP_ASSISTANT), ("k2", REAL_WILDCARD)]
    )
    titles = [pair[1].listing.title for pair in chosen]
    ok = "Shop Assistant Cammeray" not in titles
    print(f"  [{'PASS' if ok else 'FAIL'}] chosen = {titles}")
    if not ok:
        failures.append("Shop Assistant still selected")

    print("\n=== no single employer may own the digest ===")
    # Reading employer boards directly put 1,764 postings in the pool and Payoneer
    # took four consecutive main-lane slots with near-identical CSM listings.
    flood = [
        (f"k{i}", scored(f"Customer Success Manager {i}", "Payoneer",
                        geo.CLASS_ANYWHERE, 9, ["work from anywhere", "async"],
                        ["autonomy"], fit_lane=fit.LANE_ADJACENT))
        for i in range(6)
    ]
    others = [
        (f"o{i}", scored(f"Solutions Engineer {i}", f"Smallco{i}",
                        geo.CLASS_ANYWHERE, 9, ["work from anywhere", "async"],
                        ["autonomy"], fit_lane=fit.LANE_ADJACENT))
        for i in range(4)
    ]
    _, main_lane, _, _, _, _, _ = digest.select(flood + others)
    payoneer = sum(1 for p in main_lane
                   if p[1].listing.company.lower() == "payoneer")
    check(f"Payoneer capped at {digest.MAX_PER_COMPANY}",
          payoneer == digest.MAX_PER_COMPANY, f"-> {payoneer} slots")
    companies = {p[1].listing.company for p in main_lane}
    check("the freed slots went to other companies", len(companies) >= 5,
          f"-> {sorted(companies)}")

    print("\n=== orphan variation selector stripped from titles ===")
    mangled = "️ Location Services Engineer | Maps Platform"
    cleaned = sources.clean_text(mangled)
    ok = cleaned.startswith("Location Services Engineer")
    print(f"  [{'PASS' if ok else 'FAIL'}] {mangled!r} -> {cleaned!r}")
    if not ok:
        failures.append(f"clean_text left the orphan modifier: {cleaned!r}")

    print("\n" + "=" * 60)
    if failures:
        print(f"FAILED {len(failures)}")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("ALL DIGEST ENTRY TESTS PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
