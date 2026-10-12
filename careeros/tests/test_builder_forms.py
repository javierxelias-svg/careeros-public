"""
Builder lanes, Specialist-over-Manager ranking, and the application-form verdict.

Added 2026-10-01. The operator asked for builder roles (a problem handed over,
the solution built their way), for implementation work at a reachable level, and
for a faster way to apply. Every exclusion set earlier must still hold under the
wider lanes.
"""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import digest  # noqa: E402
import fit  # noqa: E402
import forms  # noqa: E402
import geo  # noqa: E402
import prefilter  # noqa: E402
import salary as salary_mod  # noqa: E402
import sources  # noqa: E402


def scored(title, label):
    listing = sources.Listing(title=title, company="Testco", url="https://example.test/x")
    return prefilter.Scored(
        listing=listing, salary=salary_mod.UNKNOWN, geo_class=geo.CLASS_ANYWHERE,
        geo_reason="test", score=3, green=[], red=[], tz_blockers=[],
        tz_friendly=[], tier="U", notes=[], fit_lane=fit.LANE_CORE,
        fit_label=label, freedom=9, freedom_reasons=["work from anywhere"],
        ecosystem=[],
    )


def main():
    failures = []

    def check(label, ok, detail=""):
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}  {detail}")
        if not ok:
            failures.append(label)

    print("=== builder and creative-tech titles are core ===")
    for title, want in (
        ("AI Automation Specialist", "AI builder"),
        ("AI Agent Engineer", "AI builder"),
        ("Workflow Automation Developer", "AI builder"),
        ("Internal Tools Engineer", "AI builder"),
        ("Creative Technologist", "creative technologist"),
        ("Generative AI Artist", "creative technologist"),
    ):
        got = fit.classify(title)
        check(title, got == (fit.LANE_CORE, want), f"-> {got}")

    print("\n=== the operator's exclusions still win over the new lanes ===")
    for title, want in (
        ("AI Automation Sales Representative", "quota sales"),
        ("Senior AI Agent Engineer", "senior pure engineering"),
        ("Creative Director", "creative/design leadership"),
        ("German-speaking AI Automation Specialist", "language the operator does not speak"),
    ):
        got = fit.classify(title)
        check(title, got == (fit.LANE_OFF, want), f"-> {got}")

    print("\n=== Implementation Specialist leads, Manager still prints ===")
    spec = scored("Implementation Specialist", "implementation")
    mgr = scored("Implementation Manager", "implementation")
    builder = scored("AI Automation Specialist", "AI builder")
    check("specialist is priority tier", digest.target_rank(spec) == 0)
    check("manager drops a tier", digest.target_rank(mgr) == 1)
    check("builder is priority tier", digest.target_rank(builder) == 0)
    ordered = [p[1].listing.title for p in digest.rank([(0, mgr), (1, spec)])]
    check("specialist ranks above manager", ordered[0] == "Implementation Specialist",
          f"-> {ordered}")

    print("\n=== forms.verdict(): the form is the gate ===")
    linear = [("Name", True, "other"), ("Email", True, "other"),
              ("Resume", True, "other"), ("Tell us more", True, "essay"),
              ("LinkedIn profile", True, "other"), ("X profile", False, "other"),
              ("What country are you based in?", True, "other")]
    check("a real 6-question form is quick", forms.verdict(linear) ==
          "⚡ quick form: 6 questions, no years asked", f"-> {forms.verdict(linear)!r}")
    walled = linear + [("Do you have 2+ years of SaaS implementation experience?", True, "other")]
    got = forms.verdict(walled)
    check("a required years question is flagged", (got or "").startswith("⛔"), f"-> {got!r}")
    optional_years = linear + [("Years of experience (optional)", False, "other")]
    check("an optional years question is not", forms.verdict(optional_years).startswith("⚡"))
    essays = [(f"Q{i}", True, "essay") for i in range(3)] + linear
    check("three essays is not quick", forms.verdict(essays).startswith("📝"),
          f"-> {forms.verdict(essays)!r}")
    check("unknown form says nothing", forms.verdict(None) is None and forms.verdict([]) is None)

    print("\n=== a form tag prints on its own line ===")
    item = scored("Implementation Specialist", "implementation")
    item.form_tag = "⚡ quick form: 6 questions, no years asked"
    check("entry carries the tag", "\n  ⚡ quick form" in digest._entry(item))

    print("\n=== home-base plan: US-remote in-lane roles reach the main lane ===")
    us_core = scored("Implementation Specialist", "implementation")
    us_core.geo_class = geo.CLASS_US
    check("US-remote core role is main-lane", prefilter.is_portable(us_core))
    us_stretch = scored("Operations Associate", "unrecognised role")
    us_stretch.geo_class = geo.CLASS_US
    us_stretch.fit_lane = fit.LANE_STRETCH
    check("US-remote stretch role is not", not prefilter.is_portable(us_stretch))
    blocked = scored("Implementation Specialist", "implementation")
    blocked.geo_class = geo.CLASS_BLOCKED
    check("region-locked role is still out", not prefilter.is_portable(blocked))

    print("\n=== work-abroad weeks are tagged ===")
    import enrich  # noqa: E402
    for text, want in (("Work from anywhere for up to 4 weeks a year.", True),
                       ("Ask about our workation program.", True),
                       ("Must work from home in the US.", False)):
        check(f"{text!r}", bool(enrich.TEMP_ABROAD.search(text)) == want)
    item = scored("Implementation Specialist", "implementation")
    item.green = ["work-abroad weeks"]
    check("entry shows the tag", "✈️ work-abroad weeks" in digest._entry(item))

    print("\n=== the (example) pay floor tests the top of a published range ===")
    S = salary_mod.Salary if hasattr(salary_mod, "Salary") else None
    if S is not None:
        for lo, hi, want in ((60_000, 80_000, False), (70_000, 100_000, True), (85_000, 85_000, True)):
            sal = salary_mod.parse(f"${lo:,} - ${hi:,}") if hasattr(salary_mod, "parse") else None
            got = salary_mod.clears_bar(sal, prefilter.PAY_FLOOR) if sal is not None else None
            check(f"${lo//1000}k-${hi//1000}k clears $85k: {want}", got == want, f"-> {got}")
    check("example floor is $85k", prefilter.PAY_FLOOR == 85_000)
    check("estimates use an $85k midpoint test too", prefilter.ESTIMATE_FLOOR == 85_000)

    print("\n=== a job that writes async keeps the lower $65k guess floor ===")
    # A strict guess floor was hiding async roles on a title guess alone.
    # "Customer Success Associate" guesses ~$53k-$78k: midpoint between the two.
    def run_one(title, description):
        listing = sources.Listing(
            title=title, company="Testco", url="https://example.test/" + title,
            region="Remote, US", description=description)
        kept, rejections = prefilter.run([listing], logging.getLogger("test"))
        return kept, rejections
    silent_kept, silent_rej = run_one(
        "Customer Success Associate", "Remote role in the US. Join our team.")
    async_kept, _ = run_one(
        "Customer Success Associate",
        "Remote role in the US. We work async and value deep focus.")
    check("silent CSM guessed under $85k is dropped", not silent_kept,
          f"-> {dict(silent_rej)}")
    check("async CSM guessed under $85k comes back", len(async_kept) == 1)
    if async_kept:
        check("...marked ask base pay first",
              any("ASK BASE PAY FIRST" in n for n in async_kept[0].notes),
              f"-> {async_kept[0].notes}")

    print("\n" + "=" * 60)
    if failures:
        print(f"FAILED {len(failures)}")
        for f in failures:
            print("  - " + f)
        return 1
    print("ALL BUILDER/FORMS TESTS PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
