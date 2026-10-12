"""
Regressions for the 2026-08-17 lean pass.

Every case here printed to the operator, or was measured on the live pool the
same day. Each one is a real defect with a receipt, not a hypothetical.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import digest  # noqa: E402
import fit  # noqa: E402
import geo  # noqa: E402
import prefilter  # noqa: E402
import salary  # noqa: E402
import sources  # noqa: E402


FAILURES = []


def check(label, got, want):
    if got != want:
        FAILURES.append(f"{label}: got {got!r}, want {want!r}")


# --------------------------------------------------------------------------
# salary: a funding figure is not a wage
#
# "With $125M raised at Series B" -> SINGLE_RE matched "$125", the M sat outside
# the number group and was discarded, _infer_period() saw 125 <= 500 and called
# it hourly, and 125 x 2080 = $260,000 went out stamped confidence="published".
# Nine LangChain postings carried that invented number on 2026-08-17, three of
# them SDR roles that publish no salary at all.
# --------------------------------------------------------------------------
def test_funding_is_not_salary():
    check("$125M raised",
          salary.parse("With $125M raised at Series B from IVP, Sequoia").confidence,
          "unknown")
    check("100M downloads",
          salary.parse("We have 100M+ monthly open source downloads").confidence,
          "unknown")
    check("headcount range",
          salary.parse("we grew from 10 to 50 employees").confidence,
          "unknown")
    check("valuation",
          salary.parse("now valued at $3B after the round").confidence,
          "unknown")
    check("customer count",
          salary.parse("6,000+ active LangSmith customers").confidence,
          "unknown")


def test_real_pay_still_parses():
    """The guard must not cost a single genuine band."""
    published = [
        ("Compensation - Annual salary range: $160,000- $240,000", 240000.0),
        ("$70,000 - $90,000 per year", 90000.0),
        ("70k-90k USD", 90000.0),
        ("$45/hour", 93600.0),
        ("$208,000—$312,000 USD", 312000.0),
        ("Salary: $93,600 - $104,000", 104000.0),
        ("$216,300", 216300.0),
    ]
    for text, top in published:
        parsed = salary.parse(text)
        check(f"published {text[:28]}", parsed.confidence, "published")
        check(f"top {text[:28]}", parsed.top, top)


# --------------------------------------------------------------------------
# geo: a country in a TITLE is a lock, with no qualifier needed
#
# BLOCKED_PATTERNS requires "Canada only" / "India based" because body text
# names countries innocently. A title does not. Both of these printed under a
# work-from-anywhere globe on 2026-08-17.
# --------------------------------------------------------------------------
def test_country_in_title_is_a_lock():
    locked = [
        "Regional Director of Customer Success - Thailand",
        "Technical Account Manager – Payments (APAC)",
        "Manager - India Tax & Operations",
        "Solutions Engineer, EMEA",
        "AI Engineer (Remote, Canada)",
        "Solutions Engineer - Mexico",
    ]
    for title in locked:
        result = geo.title_region_lock(title)
        check(f"locked {title[:34]}", result and result[0], geo.CLASS_BLOCKED)


def test_country_lock_does_not_overreach():
    """A customer base is not a work location, and Indiana is not India."""
    free = [
        "Customer Success - Singapore Clients",
        "Account Manager - Enterprise Accounts",
        "Senior Solutions Consultant - Global Payroll, AMER",
        "Forward Deployed Engineer",
        "Junior Technical Account Manager",
        "Indiana Support Engineer",
    ]
    for title in free:
        check(f"free {title[:34]}", geo.title_region_lock(title), None)


# --------------------------------------------------------------------------
# fit: off-lane families that reached the main lane on 2026-08-17
# --------------------------------------------------------------------------
def test_off_lane_leaks_closed():
    off = [
        "Sales Development Representative",           # quota sales, a hard no
        "Sales Development Representative (French Speaking)",
        "GTM Lead",
        "Strategic People Partner",                   # HR
        "Regional HR & People Operations Specialist",
        "Manager - India Tax & Operations",
        "Senior Director, Data Platform and AI",
        "Regional Director of Customer Success",
        "Creative Director",
        "Manager, Account Development",
    ]
    for title in off:
        check(f"off {title[:38]}", fit.classify(title)[0], fit.LANE_OFF)


def test_operator_lane_survives():
    """The blocklist additions must not touch a role the operator is chasing."""
    expected = {
        "Junior Technical Account Manager": fit.LANE_CORE,
        "Senior Solutions Engineer": fit.LANE_ADJACENT,  # demoted 2026-10-12
        "Director of Solutions Engineering": fit.LANE_ADJACENT,  # demoted 2026-10-12
        "Forward Deployed Engineer": fit.LANE_ADJACENT,  # demoted 2026-10-12
        "Technical Support Engineer": fit.LANE_ADJACENT,  # demoted 2026-10-12
        "Senior AI Engineer - Agentic Systems": fit.LANE_ADJACENT,  # demoted 2026-10-12
        "Customer Success Manager": fit.LANE_ADJACENT,
        "Customer Success Engineer": fit.LANE_ADJACENT,
        "Senior Red Team Engineer": fit.LANE_ADJACENT,
        "Solutions Consultant": fit.LANE_ADJACENT,
        "Developer Advocate": fit.LANE_ADJACENT,
        "GTM Engineer": fit.LANE_STRETCH,
    }
    for title, lane in expected.items():
        check(f"lane {title[:38]}", fit.classify(title)[0], lane)


# --------------------------------------------------------------------------
# digest: a stretch listing has to earn its slot
#
# 2026-08-17: 10 listings were in-lane AND portable, the main lane took 14, so
# six slots went to the highest-ranked unrecognised titles — HR, tax and
# executive roles, on a run that suppressed 682 off-lane listings.
# --------------------------------------------------------------------------
class _Listing:
    def __init__(self, title):
        self.title = title


class _Item:
    def __init__(self, lane, ecosystem=(), green=(), title="Agent Platform Engineer"):
        self.fit_lane = lane
        self.ecosystem = list(ecosystem)
        self.green = list(green)
        self.listing = _Listing(title)


def test_stretch_must_earn_its_slot():
    check("core always", digest.earns_main_lane(_Item(fit.LANE_CORE)), True)
    check("adjacent always", digest.earns_main_lane(_Item(fit.LANE_ADJACENT)), True)
    check("off never", digest.earns_main_lane(_Item(fit.LANE_OFF)), False)
    check("bare stretch", digest.earns_main_lane(_Item(fit.LANE_STRETCH)), False)
    check("stretch + ecosystem",
          digest.earns_main_lane(_Item(fit.LANE_STRETCH, ecosystem=["Claude"])), True)
    check("stretch + training",
          digest.earns_main_lane(
              _Item(fit.LANE_STRETCH, green=["training provided"])), True)


def test_company_category_alone_does_not_earn_a_slot():
    """
    Employer signal is not role signal. "Strategic People Partner @ Oyster"
    carried a LATAM/bilingual-premium company label and was still an HR job.
    """
    item = _Item(fit.LANE_STRETCH, green=["fully distributed", "async"])
    check("company/culture only", digest.earns_main_lane(item), False)


def test_employer_ai_signal_does_not_carry_an_unrelated_title():
    """
    ecosystem and training are matched against the whole posting, so an AI
    company's compliance and sales openings inherit them. "GRC Analyst @
    Vercel" and "Manager, Account Development @ Justworks" both took main-lane
    slots that way before the title had to agree.
    """
    for title in ("GRC Analyst", "Manager, Account Development",
                  "Office Coordinator", "Payroll Specialist"):
        item = _Item(fit.LANE_STRETCH, ecosystem=["Claude"], title=title)
        check(f"employer-signal only {title[:30]}",
              digest.earns_main_lane(item), False)

    # ...while a genuinely unusual AI role still gets through. This one is real:
    # Vercel, $208,000-$312,000, published.
    for title in ("Member of the Technical Staff, Internal Agent Platform",
                  "CX AI & Automation Lead"):
        item = _Item(fit.LANE_STRETCH, ecosystem=["Claude"], title=title)
        check(f"relevant stretch {title[:30]}",
              digest.earns_main_lane(item), True)


# --------------------------------------------------------------------------
# prefilter: the accessible-role signal asked for on 2026-08-17
# --------------------------------------------------------------------------
def test_accessible_titles():
    accessible = [
        "Junior Technical Account Manager",
        "Associate Solutions Engineer",
        "Entry-Level Support Engineer",
        "Graduate AI Engineer",
        "Associate Product Manager",
        "AI Engineer Intern",
    ]
    for title in accessible:
        check(f"accessible {title[:32]}", prefilter.accessible_title(title), True)

    not_accessible = [
        "Senior Associate, Business Ops",   # "Senior Associate" is not junior
        "Senior AI Engineer",
        "Solutions Engineer",
        "Associate Director of Customer Success",
        "Lead Apprentice Program Manager",
    ]
    for title in not_accessible:
        check(f"not accessible {title[:32]}", prefilter.accessible_title(title), False)


def test_pay_lives_at_the_bottom_of_a_posting():
    """
    prefilter read description[:3000]. The first 3,000 characters of a job ad
    are the company pitch; pay sits underneath a "Compensation" heading.
    LangChain publishes $160,000-$240,000 at character 3,274, so the digest
    called it an estimate while a real number sat 274 characters past the cut —
    and the fabricated $260,000 came out of the pitch at the top of the very
    same description.
    """
    pitch = "ABOUT US We raised $125M at Series B and serve 6,000+ customers. "
    body = pitch + ("x" * 3000)
    posting = body + " Compensation - Annual salary range: $160,000- $240,000"

    check("head-only misses it", salary.parse(posting[:3000]).confidence, "unknown")
    parsed = salary.parse_description(posting)
    check("found at the bottom", parsed.confidence, "published")
    check("and it is the right number", parsed.top, 240000.0)


def test_prose_never_invents_an_hourly_wage():
    """
    Every fabricated salary traced to one branch: a small bare number inferred
    as hourly and multiplied by 2,080. 125 -> $260,000, 148 -> $307,840, and a
    4 read out of an HTML class name -> $8,320.
    """
    check("bare small number in prose",
          salary.parse_description(
              "Our compensation philosophy rewards the top 148 performers"
          ).confidence,
          "unknown")
    # An EXPLICIT hourly rate is still read, and still annualized.
    hourly = salary.parse_description(
        "COMPENSATION & BENEFITS - Hourly Compensation: $5-$15 per hour"
    )
    check("explicit hourly survives", hourly.confidence, "published")
    check("explicit hourly annualized", hourly.top, 31200.0)


def test_encoded_markup_never_reaches_the_parser():
    """
    clean_text() stripped tags BEFORE unescaping entities, so `&lt;span
    class="...id-1691622878"&gt;` survived the strip and was then decoded into a
    live tag. Digits out of a CSS class name published a Product Manager role
    at $8,320-$18,720.
    """
    encoded = ('&lt;p&gt;Compensation&lt;/p&gt; &lt;span class="block-id-1691622878"&gt;'
               'Salary: $120,000 - $150,000&lt;/span&gt;')
    cleaned = sources.clean_text(encoded)
    check("no tags survive", "<span" in cleaned or "<p>" in cleaned, False)
    check("no class attribute survives", "1691622878" in cleaned, False)
    parsed = salary.parse_description(cleaned)
    check("real band still read", parsed.confidence, "published")
    check("real band correct", parsed.top, 150000.0)


def test_body_scope_beats_the_feed_category():
    """
    WeWorkRemotely stamps <region>Anywhere in the World</region> on ~95 of every
    100 items because that is the CATEGORY being fetched. Hightouch's Customer
    Success Engineer opens its body with "Headquarters: Remote (North America)"
    and printed to the operator under a work-from-anywhere globe on 2026-08-17.
    Their careers page lists three separate CSE roles — North America, New York,
    Europe — so the body was right and the feed was naming a bucket.
    """
    check("north america -> US",
          geo.body_region_lock("Headquarters: Remote (North America) About us")[0],
          geo.CLASS_US)
    check("europe -> blocked",
          geo.body_region_lock("Headquarters: Remote (Europe) About us")[0],
          geo.CLASS_BLOCKED)
    check("canada -> blocked (no work authorization)",
          geo.body_region_lock("Headquarters: Remote (Canada)")[0],
          geo.CLASS_BLOCKED)
    check("us & canada -> US (operator is eligible)",
          geo.body_region_lock("Headquarters: Remote (US & Canada)")[0],
          geo.CLASS_US)
    # and it overrides the feed end to end
    cls, _ = geo.classify_geo("Anywhere in the World",
                              "Headquarters: Remote (North America) About Hightouch")
    check("feed category overridden", cls, geo.CLASS_US)


def test_body_scope_does_not_fire_on_prose():
    """An unrecognised scope returns None rather than blocking — same rule the
    rest of this module follows: unknown must not be punished like known-bad."""
    for text in ("We serve customers remote (across many markets)",
                 "Headquarters: Remote (Anywhere in the World)",
                 "Headquarters: San Francisco, CA",
                 "Remote (Worldwide) - Senior Engineer"):
        check(f"no lock {text[:34]}", geo.body_region_lock(text), None)


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    if FAILURES:
        print(f"FAIL test_lean.py ({len(FAILURES)})")
        for failure in FAILURES:
            print("   ", failure)
        return 1
    print("PASS test_lean.py")
    return 0


if __name__ == "__main__":
    sys.exit(run())
