#!/usr/bin/env python3
"""
The operator's TERMS, not preferences — the gates that decide whether a job is livable.

    python3 careeros/tests/test_fit_terms.py

Every case here is a real defect found on 2026-09-30, when the operator asked
for the thing this whole file exists for: only right-fit jobs.
Three gates were checked and all three were broken, and 21 passing test files had
never touched any of them.

  1. The travel branch of prefilter.HARD_INCOMPATIBLE could never match. The
     alternation was wrapped in \\b...\\b and that branch ends in "%", which is a
     non-word character, so no boundary existed after it. Caught by reading a
     Vector posting that reached the top of the digest carrying "Able to
     travel up to 50% to customer locations".
  2. geo.timezone_verdict REJECTED "No on-call, ever. We protect your evenings."
     curated.py had guarded that inversion since August; geo.py never did, so the
     page was protected and the digest the operator actually reads was not.
  3. "weekend rotation required" and "shift work, nights and weekends" both passed
     the shift-work gate, which demanded the word "rotating" before "weekends".

The pattern across all three: a gate nobody had ever fed a real posting.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import geo  # noqa: E402
import prefilter  # noqa: E402

# Phrasings lifted from real postings, not invented.
TRAVEL_BLOCKS = [
    "Able to to travel up to 50% to customer locations",   # Vector, verbatim
    "Willing to travel 50% of the time",
    "Expect ~50% travel to customer sites",
    "Travel: 50%",
    "up to 50% travel required",
    "Travelling up to 30% is expected",
    "Travel: 26%",
    "25–40% travel",               # Hippocratic AI Payors shape, 2026-10-16
    "travel 20-40% of the time",   # the TOP of a range decides
    # Anthropic, Community Engagement (Texas), verbatim, 2026-10-05.
    "You will travel regularly within your region, up to 50% of the time",
]
TRAVEL_ALLOWS = [
    # 5% is a couple of trips a year, and the operator accepts work trips.
    "travel up to 5%",
    # Operator term change, 2026-10-15: up to 25% is allowed and flagged, the operator decides.
    "This role requires travel up to 25%",
    "Expect ~20% travel to customer sites",
    "15-25% travel",
    "occasional travel to meet the team",
    "we travel twice a year for offsites",
    "This role has 100% remote flexibility",   # must not read as 100% travel
    "we are 100% distributed",
    "you will travel to our annual summit",
    "we travel twice a year for offsites, and we are 100% distributed",
]

# Pay fields as Ashby writes them. Zapier's Automation Strategist, 2026-10-05.
COMMISSION_BLOCKS = [
    "$158.3K – $263.4K • Offers Commission • Multiple Ranges",
    "$120,000 base plus commission",
    "$90k + commission",
]
COMMISSION_ALLOWS = [
    "$110K – $165K • Offers Equity",
    "$95,000 – $120,000",
    "",
]
OTHER_BLOCKS = [
    "must have a valid drivers license",
    "ability to lift 50 pounds",
    "relocation required",
]

HOURS_REJECT = [
    "You will participate in an on-call rotation",
    "This role includes 24/7 on-call coverage",
    "weekend rotation required",
    "shift work, nights and weekends",
    "Rotating shifts including weekends",
    "participate in the on-call pager rotation",
    "carrying the pager one week in four",
]
HOURS_KEEP = [
    # The inversion. These advertise the best thing a posting can say to the operator.
    "No on-call, ever. We protect your evenings.",
    "There is no on-call rotation for this role",
    # Ashby's Product Support Engineer, rejected for on-call on 2026-10-13.
    "We staff across regions rather than relying on on-call rotations",
    "follow-the-sun coverage instead of on-call",
    "We do not require weekend coverage",
    "fully async, no set hours",
    "Remote, async, flexible hours",
]


# TERM 1, the operator's first-ranked hard term, and it was never enforced. Every
# one of these came back CLASS_US — reaching the digest's US-ONLY section instead
# of being rejected. The 25% case is a real Anthropic role at $230-265k.
OFFICE_REJECT = [
    "This is a remote role. You will be in our office 3 days a week.",
    "Remote-friendly. Employees are in office at least 25% of the time.",
    "Hybrid: 2 days onsite in New York.",
    "This is a hybrid role based in Austin.",
    "You must work in the office on Tuesdays.",
    "We have a return-to-office policy of 3 days.",
    # Anthropic, verbatim, 2026-10-05.
    "Currently, we expect all staff to be in one of our offices at least 25% of the time.",
    # Thatch, verbatim, 2026-10-12. It printed as "fully remote" because the
    # company blurb said "fully distributed".
    "We're hiring a Member Experience Specialist based in our San Francisco office "
    "to support Thatch members.",
]
# And the inversion guard: these advertise exactly what the operator wants and must not be
# rejected for containing the word "office".
OFFICE_KEEP = [
    "Fully remote, work from anywhere.",
    "Remote. No office, no hybrid, ever.",
    "We are 100% remote and have never had an office.",
    "Remote role; we meet in person twice a year for offsites.",
    "Our office in Lisbon is open if you want a desk, but nobody is required to come in.",
    # Ramp, verbatim, 2026-10-13: a benefits list. Eight "Remote (US)" Technical
    # Consultant roles were rejected as hybrid over this line.
    "Parental leave at 100% pay - Pet insurance - In-office perks: lunch, snacks, drinks",
    # Where the COMPANY sits is not where the role sits.
    "Thatch is fully distributed. Our team is based in San Francisco.",
]


def main():
    failures = []

    def check(label, ok, detail=""):
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}{('  ' + detail) if detail else ''}")
        if not ok:
            failures.append(label)

    print("=== travel percentage is a hard reject (the branch that never matched) ===")
    for text in TRAVEL_BLOCKS + OTHER_BLOCKS:
        check(f"blocks: {text[:56]}",
              bool(prefilter.hard_incompatible(text)))

    print("\n=== ...without eating the roles that are fine ===")
    for text in TRAVEL_ALLOWS:
        hit = prefilter.hard_incompatible(text)
        check(f"allows: {text[:56]}", hit is None,
              f"matched {hit.group(0)!r}" if hit else "")

    print("\n=== allowed travel is still flagged, the operator decides ===")
    for text in ("This role requires travel up to 25%", "Expect ~20% travel to customer sites"):
        red = [label for rx, label in prefilter._RED if rx.search(text)]
        check(f"flags: {text[:56]}", "travel 10-25%, operator's call" in red, f"-> {red}")
    check("5% travel is not flagged",
          not any(rx.search("travel up to 5%") for rx, _ in prefilter._RED))

    print("\n=== commission in the pay field is a hard reject ===")
    for text in COMMISSION_BLOCKS:
        check(f"blocks: {text[:56]}", bool(prefilter.COMMISSION_PAY.search(text)))
    for text in COMMISSION_ALLOWS:
        check(f"allows: {text[:56]!r}", prefilter.COMMISSION_PAY.search(text) is None)

    print("\n=== commission stated in the body, two exact phrasings only ===")
    for text in ("Compensation range (mix of salary and commission): $140,000-$170,000 USD.",
                 "Competitive salary + equity + commission",
                 "$72,000 - $95,000 USD base salary + commission"):
        check(f"blocks: {text[:56]}", bool(prefilter.COMMISSION_BODY.search(text)))
    for text in ("a base salary, an equity incentive plan and variable commission "
                 "(for quota-based roles)",
                 "For commissioned roles, the base salary listed does not include variable pay",
                 "Our cash compensation (salary + commission if applicable) range for this role",
                 "regulated by the Securities and Exchange Commission"):
        check(f"allows: {text[:56]!r}", prefilter.COMMISSION_BODY.search(text) is None)

    print("\n=== a learning stipend is a perk, not 'no experience required' ===")
    green = prefilter.find_flags("We offer a $1,500 annual learning stipend.")[0]
    check("learning stipend is labelled as a perk", "learning budget" in green)
    check("...and is not a will-train signal", "will train" not in green)

    print("\n=== on-call and shift work are hard rejects ===")
    for text in HOURS_REJECT:
        ok, hard, _soft, _f = geo.timezone_verdict(text)
        check(f"rejects: {text[:52]}", not ok, f"-> {hard[:1]}")

    print("\n=== a posting PROMISING no on-call is the best signal, not a reject ===")
    for text in HOURS_KEEP:
        ok, hard, _soft, _f = geo.timezone_verdict(text)
        check(f"keeps: {text[:52]}", ok, f"-> {hard[:1]}")

    print("\n=== TERM 1: an office requirement is a hard reject ===")
    for text in OFFICE_REJECT:
        needs, why = geo.office_required(text)
        check(f"rejects: {text[:52]}", needs, f"-> {why}")

    print("\n=== ...and a posting PROMISING no office is not rejected for it ===")
    for text in OFFICE_KEEP:
        needs, why = geo.office_required(text)
        check(f"keeps: {text[:52]}", not needs, f"-> {why}")

    total = (len(TRAVEL_BLOCKS) + len(OTHER_BLOCKS) + len(TRAVEL_ALLOWS)
             + len(HOURS_REJECT) + len(HOURS_KEEP)
             + len(OFFICE_REJECT) + len(OFFICE_KEEP))
    print("\n" + "=" * 60)
    if failures:
        print(f"FAILED {len(failures)}/{total}")
        for failure in failures:
            print("  - " + failure)
        return 1
    print(f"ALL {total} TERM TESTS PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
