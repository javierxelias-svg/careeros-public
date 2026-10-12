#!/usr/bin/env python3
"""
Page-enrichment tests.

    python3 careeros/tests/test_enrich.py

Fixtures are the real defects found on 2026-08-17 by fetching the eight listings
the pipeline had selected and comparing them against the live pages
(verification/2026-08-17-pool-spotcheck.md):

  MailerLite   digest ~$109,000-$151,000 estimated | page "USD 48,000 - 65,000",
               "Based in EMEA"
  Vercel       digest "salary not stated"          | page $208,000 - $312,000
  Coinbase     digest "salary not stated"          | page $216,300
  Customer.io  digest "salary not stated"          | page "Rate: $45-$50" hourly

No network here. page_text() is the only thing that talks to the internet and it
is tested for failure behaviour, not for fetching.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import enrich  # noqa: E402
import experience  # noqa: E402
import fit  # noqa: E402
import geo  # noqa: E402
import prefilter  # noqa: E402
import salary as salary_mod  # noqa: E402
import sources  # noqa: E402

MAILERLITE = (
    "Technical Product Manager. We are a remote-first company and our people "
    "work from all over the globe. Requirements: 5 years experience. "
    "Based in EMEA. What we offer: Yearly gross salary range: USD 48,000 - "
    "65,000. Remote-first culture and unlimited books."
)
VERCEL = (
    "Member of the Technical Staff, Internal Agent. About the role: you will "
    "build agents. The base pay range for this role is $208,000 - $312,000. "
    "This role is eligible for equity."
)
COINBASE = (
    "Creative Director. Coinbase is a remote-first company. "
    "Target annual base salary range (excluding equity and bonus): $216,300. "
    "You must be authorized to work in the US."
)
CUSTOMER_IO = (
    "Contract IT Specialist. We are fully distributed. Rate: $45-$50 per hour "
    "depending on experience. We hire globally through an employer of record."
)
NOMAD_FRIENDLY = (
    "Solutions Engineer. We hire globally and you can work from any country. "
    "Base salary range: $120,000 - $150,000. Any timezone is fine."
)


def scored(title, company, geo_class=geo.CLASS_ANYWHERE, salary=None,
           notes=(), green=(), lane=fit.LANE_CORE,
           source="weworkremotely_all"):
    listing = sources.Listing(title=title, company=company,
                              url="https://example.test/job", source=source)
    return prefilter.Scored(
        listing=listing, salary=salary or salary_mod.UNKNOWN, geo_class=geo_class,
        geo_reason="feed", score=5, green=list(green), red=[], tz_blockers=[],
        tz_friendly=[], tier="U", notes=list(notes), fit_lane=lane,
        fit_label="test", freedom=6, freedom_reasons=["work from anywhere"],
        ecosystem=[], company_labels=[],
    )


def main():
    failures = []

    def check(label, ok, detail=""):
        suffix = f"  {detail}" if detail else ""
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}{suffix}")
        if not ok:
            failures.append(label)

    print("=== find_salary(): the real number off the page ===")
    cases = [
        ("MailerLite $48k-$65k", MAILERLITE, 48_000, 65_000),
        ("Vercel $208k-$312k", VERCEL, 208_000, 312_000),
        ("Coinbase $216,300 single", COINBASE, 216_300, 216_300),
        ("Customer.io $45-$50/hr annualised", CUSTOMER_IO, 93_600, 104_000),
        ("no figure at all", "We offer a competitive salary.", None, None),
    ]
    for label, text, low, high in cases:
        got = enrich.find_salary(text)
        ok = (got.low == low and got.high == high) if low else got.confidence == "unknown"
        check(label, ok, f"-> {got.display()} ({got.confidence})")

    print("\n=== the 2.3x overshoot is corrected, not merely warned about ===")
    estimated = salary_mod.Salary(109_000, 151_000, confidence="estimated")
    item = scored("Technical Product Manager", "MailerLite", salary=estimated,
                  notes=["salary ESTIMATED from title, not published"])
    changes = enrich.reconsider(item, MAILERLITE)
    check("pay replaced with the published band",
          item.salary.confidence == "published" and item.salary.high == 65_000,
          f"-> {item.salary.display()}")
    check("the ESTIMATED warning is gone",
          not any("ESTIMATED" in n for n in item.notes), f"notes={item.notes}")
    check("the overshoot is logged",
          any("too high" in c for c in changes),
          [c for c in changes if "too high" in c][:1])

    print("\n=== 'Based in EMEA' in the body demotes a work-from-anywhere claim ===")
    check("geo A -> C", item.geo_class == geo.CLASS_BLOCKED, f"-> {item.geo_class}")
    check("globe reason removed",
          "work from anywhere" not in item.freedom_reasons,
          f"-> {item.freedom_reasons}")

    print("\n=== hidden pay is surfaced and re-tiered ===")
    vercel = scored("Member of the Technical Staff", "Vercel",
                    notes=["pay not stated — ask before applying"])
    enrich.reconsider(vercel, VERCEL)
    check("pay found", vercel.salary.high == 312_000, f"-> {vercel.salary.display()}")
    check("no longer 'pay not stated'",
          not any("not stated" in n for n in vercel.notes), f"notes={vercel.notes}")
    check("tier is now a real letter, not U",
          vercel.tier in ("S", "A", "B", "C"), f"-> {vercel.tier}")

    print("\n=== abroad_verdict(): the operator's first requirement ===")
    verdicts = [
        ("hires globally via EOR", CUSTOMER_IO, True),
        ("work from any country", NOMAD_FRIENDLY, True),
        ("US work authorisation required", COINBASE, False),
        ("must reside in the US", "Remote role. You must reside in the US.", False),
        ("EMEA residency required", "You must be located in Europe.", False),
        ("silence is not permission", VERCEL, None),
    ]
    for label, text, expected in verdicts:
        got, reasons = enrich.abroad_verdict(text)
        check(label, got is expected, f"-> {got} {reasons[:1]}")

    print("\n=== another company's job on the same page must not be read ===")
    # Shape of the real Jobicy page that published PolicyMe's CAD band as
    # ecosio's salary on 2026-08-17.
    aggregator = (
        "E-invoicing Integration Engineer at ecosio. Compensation: USD 90,000 - "
        "110,000 per year. About ecosio: we do B2B integration. "
        "Related jobs Compensation CAD 221,800-300,100/year PolicyMe "
        "Compensation GBP 85k-105k/year Jobber"
    )
    got = enrich.find_salary(aggregator)
    check("takes ecosio's own band, not PolicyMe's",
          got.low == 90_000 and got.high == 110_000, f"-> {got.display()}")
    check("the sidebar is cut off entirely",
          "PolicyMe" not in enrich.posting_only(aggregator))

    print("\n=== a site's own estimate is never 'published' ===")
    injected = (
        "Integration Engineer at ecosio. The estimated US market range for this "
        "role is USD 105,000 to USD 150,000 based on our data."
    )
    got = enrich.find_salary(injected)
    check("estimate language refused", got.confidence == "unknown",
          f"-> {got.display()} ({got.confidence})")
    check("a real range beside an estimate still wins",
          enrich.find_salary(
              "Base salary: $120,000 - $140,000. Glassdoor estimate: $200,000."
          ).high == 140_000)

    print("\n=== page salary is only trusted from single-posting sources ===")
    aggregated = scored("Integration Engineer", "ecosio", source="jobicy",
                        notes=["pay not stated — ask before applying"])
    enrich.reconsider(aggregated, VERCEL)   # a page with a real-looking band
    check("an aggregator page cannot set the salary",
          aggregated.salary.confidence == "unknown",
          f"-> {aggregated.salary.display()} ({aggregated.salary.confidence})")
    single = scored("Member of the Technical Staff", "Vercel",
                    source="weworkremotely_all",
                    notes=["pay not stated — ask before applying"])
    enrich.reconsider(single, VERCEL)
    check("a single-posting page can", single.salary.high == 312_000,
          f"-> {single.salary.display()}")
    check("WWR nav 'All Other Jobs' no longer truncates the posting",
          "Vercel" in enrich.posting_only(
              "Full-Time Contract All Other Jobs Top 100 Remote Companies "
              "Blog Vercel base pay range for this role is $208,000 - $312,000."))

    print("\n=== board chrome must not read as an employer commitment ===")
    # Verbatim from RemoteOK's navigation menu. For one run this tagged a coffee
    # roaster and a retail "Team Member" as roles workable from another continent.
    chrome = ("Top remote companies Highest paying remote jobs State of remote "
              "work new Become a digital nomad Web3 Jobs Photo AI Interior AI "
              "Build your resume Health insurance Post a job Log in")
    got, reasons = enrich.abroad_verdict(chrome)
    check("RemoteOK nav is not permission", got is None, f"-> {got} {reasons}")
    got, reasons = enrich.abroad_verdict(
        "Shop Assistant Cammeray. " + chrome + " Join our team on the floor.")
    check("retail job + nav chrome is not permission", got is None, f"-> {got} {reasons}")

    print("\n=== a residency requirement beats a work-from-anywhere claim ===")
    conflicted = "Work from anywhere in the world! Note: you must reside in the US."
    got, reasons = enrich.abroad_verdict(conflicted)
    check("fine print wins", got is False, f"-> {got} {reasons}")

    cb = scored("Creative Director", "Coinbase")
    enrich.reconsider(cb, COINBASE)
    check("US-only page demotes geo A -> B", cb.geo_class == geo.CLASS_US,
          f"-> {cb.geo_class}")
    check("and says so in the digest",
          any("cannot work abroad" in n for n in cb.notes), f"notes={cb.notes}")

    print("\n=== a genuinely portable role is tagged ===")
    good = scored("Solutions Engineer", "Somestartup")
    enrich.reconsider(good, NOMAD_FRIENDLY)
    check("green flag set",
          "works from another country" in good.green, f"-> {good.green}")
    check("still geo A", good.geo_class == geo.CLASS_ANYWHERE)
    check("pay read", good.salary.high == 150_000, f"-> {good.salary.display()}")

    print("\n=== the wall falls back to the ATS description ===")
    # Measured 2026-09-30: Ashby and Greenhouse serve JavaScript shells, but 951 of
    # 952 listings from those boards carry a full description from the API. The
    # first cut of the gate read only the page and marked all of them "bar
    # unknown", which let every one of them through.
    JS_SHELL = ("Solutions Engineer @ Bretton AI You need to enable JavaScript "
                "to run this app.")
    ashby = scored("Solutions Engineer", "Shellco")
    ashby.listing.description = (
        "About the role. " * 90
        + "What we look for: 5+ years of experience in a customer-facing role. "
        + "More filler. " * 60
    )
    enrich.reconsider(ashby, JS_SHELL)
    check("a JS shell no longer reads as unknown",
          ashby.wall[0] != experience.UNREADABLE, f"-> height {ashby.wall[0]}")
    check("the five-year bar is found in the description",
          ashby.wall[2] == 5, f"-> years {ashby.wall[2]}")

    # And when neither source has text, unknown is still honestly unknown.
    blind = scored("Solutions Engineer", "Blindco")
    enrich.reconsider(blind, JS_SHELL)
    check("no page and no description stays UNREADABLE",
          blind.wall[0] == experience.UNREADABLE, f"-> height {blind.wall[0]}")

    # The fallback must not leak into the stages tuned on page text.
    narrow = scored("Solutions Engineer", "Narrowco")
    narrow.listing.description = "We pay $500,000 and you may live anywhere on Earth."
    enrich.reconsider(narrow, JS_SHELL)
    check("salary is NOT read from the description fallback",
          narrow.salary.high != 500_000, f"-> {narrow.salary.display()}")

    print("\n=== failure isolation: the stage must degrade, never crash ===")
    quiet = scored("Anything", "Anyco")
    check("empty page is a no-op", enrich.reconsider(quiet, "") == [])
    check("None page is a no-op", enrich.reconsider(quiet, None) == [])
    check("non-http url returns None",
          enrich.page_text("ftp://nope/x", "ua") is None)
    check("garbage url returns None", enrich.page_text(None, "ua") is None)
    check("unresolvable host returns None",
          enrich.page_text("https://this-host-does-not-exist-careeros.invalid/x",
                           "ua", sleep=False) is None)

    print("\n" + "=" * 60)
    if failures:
        print(f"FAILED {len(failures)}")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("ALL ENRICH TESTS PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
