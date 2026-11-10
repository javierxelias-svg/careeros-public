"""
The terms gate (second filter), 2026-10-30.

FAILS: sentences from real postings that an audit confirmed as a written no
against the operator's terms (quotes machine-checked against the postings).
Each must fail the rule it broke. CLEAN: sentences that look close but are not
a no, so the gate never hides a good role by accident.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import terms_gate  # noqa: E402

FAILS = json.loads((Path(__file__).parent / "fixtures" / "terms_gate_fails.json")
                   .read_text(encoding="utf-8"))
FAILS += [
    {"rule": "F6", "text": "This is a quota-carrying role."},
    {"rule": "F6", "text": "Own retention and expansion strategy across your portfolio."},
    {"rule": "F10", "text": "We offer gender-affirming hormone therapy."},
    {"rule": "F11", "text": "Host monthly webinars for customers."},
    {"rule": "F7", "text": "5+ years of experience managing audits for a technology company."},
    {"rule": "F7", "text": "A minimum of four years in customer support."},
    # Misses found reading finalists, 2026-10-30.
    {"rule": "F7", "text": "4+ years in software engineering, platform/infrastructure engineering, or a similarly technical role."},
    {"rule": "F7", "text": "- 5+ years of engineering experience, with proven work shipping AI/ML systems into production."},
    {"rule": "F7", "text": "- 5 to 10 years of experience in management consulting or equivalent roles."},
    {"rule": "F7", "text": "Minimum requirements 7+ years of experience in a technical sales role 3+ years of product experience Preferred qualifications Experience with embedded finance"},
    {"rule": "F7", "text": "As an ideal candidate, you will have: 5 to 8\xa0 years of related industry experience"},
    {"rule": "F7", "text": "Must-Have Experience - 4–8+ years of Solutions Engineering, Sales Engineering, or technical consulting"},
    {"rule": "F7", "text": "As an ideal candidate, you will have: 5 to 8 years of related industry experience, ideally in a customer facing role"},
    {"rule": "F7", "text": "MUST-HAVES - 5-7 years at a leading management consulting firm"},
    {"rule": "F7", "text": "ABOUT YOU: - 10+ years designing and delivering complex software systems"},
    {"rule": "F1", "text": "This role balances deep technical expertise with hands-on, onsite engagement."},
    {"rule": "F1", "text": "Location: This role is remote or hybrid based out of São Paulo, Brazil."},
    {"rule": "F1", "text": "Our ideal weekly schedule is 4 days in-office and 1 day working remotely."},
    {"rule": "F7", "text": "4 plus years building and shipping production software"},
    {"rule": "F6", "text": "a Partner Solutions Architect to play a critical role in driving revenue through enterprise deals"},
    {"rule": "F1", "text": "The nature of this role requires candidates to be based in the San Francisco Bay metro area, though there isn't an in-office requirement."},
    {"rule": "F11", "text": "- Host one of our bi-weekly demo stream, for a live audience of customers and prospects."},
    # Leaks in the first gated digest, 2026-10-31 (Lyra Health).
    {"rule": "F6", "text": "- Be measured on what the motion produces: reply and meeting rates, pipeline and revenue, cost per account worked."},
    {"rule": "F6", "text": "You will be measured on pipeline generated and closed revenue."},
    {"rule": "F16", "text": "This is a 1099 independent contractor engagement."},
    {"rule": "F16", "text": "We're hiring a 1099 Physician to provide regulatory APP supervision."},
    {"rule": "F16", "text": "This 1099 Contractor role offers the opportunity to help redefine healthcare."},
    {"rule": "F11", "text": "You will present at conferences and run customer webinars every month."},
    {"rule": "F3", "text": "This role requires flexibility to work evenings, weekends, and holidays as part of our regular coverage schedule."},
    {"rule": "F3", "text": "You must be able to work the following shift(s): Tuesday - Saturday 9:30am - 6pm PST"},
    {"rule": "F3", "text": "Must be able to work one of the following shifts: Sunday - Thursday 11:30am - 8pm PT"},
    {"rule": "F3", "text": "You must be able to work the following shift(s):\nTuesday - Saturday 9:30am - 6pm PST (10:30am - 7pm MT)\nSunday - Thursday 9:30am - 6pm PT"},
]
CLEAN = [
    "Sales owns renewals and expansion; you own the technical relationship.",
    "There is no on-call rotation and no weekend work.",
    "Acme powers hybrid search over billions of vectors.",
    "This is a unique hybrid role.",
    "Base salary + commission (for quota-based roles) + equity.",
    "For sales roles, the range provided is the role's On Target Earnings (OTE).",
    "Minimum of 2 years of experience in a Customer Success or quota-carrying role.",
    "You will occasionally present your work in our weekly demo.",
    "Represent us at conferences when needed.",
    "Exampleco runs training, simulation, synthetic data and inference workloads.",
    "We help small business owners get their nights and weekends back.",
    "Experience with prior on-call rotation experience is a plus.",
    "Fully remote, async-first, take real vacation.",
    "3-5 years of experience in technical support.",
    "5+ years of experience is a plus, not required.",
    "We have 10 years of runway and 4 offices.",
    "- 3–5+ years in systems administration, business systems engineering, or customer support platform work.",
    "You must be based in the United States.",
    "Data streams from billions of devices flow through our platform.",
    "Own the ingestion layer that processes event streams from customers.",
    "Preferred: 5+ years of experience with Kubernetes.",
    "This role is fully remote, based out of the United States.",
    # False fails seen in the 2026-10-30 dry run, fixed the same day.
    "Exclusive Events: Engage with your colleagues through exclusive in-person and virtual events.",
    "This is a non-exclusive engagement.",
    "❌ Running yawn-worthy webinars and bombarding users with invitations to attend.",
    "Contributions to open-source security projects, published research, conference talks.",
    "You have real experience producing video, with hands-on camera, audio, and editing.",
    "Gender affirming benefits",
    "Manage GTM headcount planning, including ratios such as quota-carrying reps to sales support.",
    "We're always on the search for amazing people.",
    "Experience managing a high-volume book of business at scale.",
    "We will use this information to evaluate your application for employment or an independent contractor role, as applicable.",
    "Our support team is available Monday - Sunday so customers are never stuck.",
    "Shifts are Monday - Friday, 9am - 5pm ET.",
    "We measure success by customer outcomes, not revenue.",
    "You will be measured on system uptime and data quality.",
    # False removals found in the 2026-10-31 run log.
    "Contribute to our large-scale tax and regulatory reporting systems, including US IRS information returns (the 1099 family of forms).",
    "Own W9 collection and assist year-end 1099 preparation and submission.",
    "Whether this engagement is structured as W2 employment or a 1099 independent contractor relationship will be determined by location.",
    "We'll discuss opportunities for you to present at conferences, attend and give training, plan and run meetups.",
    "Build and tune capacity alerting so headroom, quota, and reservation issues surface months out.",
    "The above for non-commission based roles or the below for commission based…",
    "USA Pacific OTE (CA, WA, NY, NJ, CT): $X - $X",
    "The pay range listed represents the expected base salary range for non-commissionable roles or on-target earnings for commissionable roles.",
]
BRIDGE_CLEAN = [
    "Confirm each expert's availability, work authorization, and exclusivity, and surface any red flags.",
    "Projects vary in scope and duration, with typical commitments ranging from 15-30 hours per week.",
    "This is a non-exclusive engagement.",
]
BRIDGE_FAILS = [
    ("B5", "40 hours per week."),
    ("B4", "Contractors must work exclusively for us during the project."),
]

failures = []
for case in FAILS:
    got = [r for r, _, _ in terms_gate.check(case["text"], min_chars=0).fails]
    if case["rule"] not in got:
        failures.append(f"{case['rule']} missed: {case['text'][:90]!r} (got {got})")
for text in CLEAN:
    got = [(r, l) for r, l, _ in terms_gate.check(text, min_chars=0).fails]
    if got:
        failures.append(f"false fail {got}: {text!r}")

for text in BRIDGE_CLEAN:
    got = [r for r, _, _ in terms_gate.check(text, min_chars=0, bridge=True).fails]
    if got:
        failures.append(f"bridge false fail {got}: {text!r}")
for rule, text in BRIDGE_FAILS:
    got = [r for r, _, _ in terms_gate.check(text, min_chars=0, bridge=True).fails]
    if rule not in got:
        failures.append(f"bridge {rule} missed: {text!r}")

# Title and pay rules, operator decisions on 2026-10-30.
v = terms_gate.check("x" * 500, "Senior Solutions Engineer")
if not any(r == "F8" for r, _, _ in v.fails):
    failures.append("senior title passed")
for title in ("Manager, Solutions Engineering", "Support Engineering Manager",
              "Fraud Analyst - Sat-Wed Shift"):
    if terms_gate.check("x" * 500, title).passed:
        failures.append(f"title passed: {title}")
for title in ("Implementation Manager", "Customer Success Manager", "Product Manager"):
    if not terms_gate.check("x" * 500, title).passed:
        failures.append(f"IC manager title failed: {title}")
for title in ("Ubuntu Enablement Engineer", "Ubuntu Linux Kernel Engineer - Silicon Enablement"):
    if not terms_gate.check("x" * 500, title).passed:
        failures.append(f"hardware enablement title failed: {title}")
for title in ("Sales Enablement Manager", "GTM Enablement - Partner Program",
              "Technical GTM Enablement Manager"):
    if terms_gate.check("x" * 500, title).passed:
        failures.append(f"enablement title passed: {title}")
if terms_gate.check("x" * 500, "Consultant", company="Veeva Systems").passed:
    failures.append("pharma vendor passed")
v = terms_gate.check("x" * 500, "Developer Advocate")
if not any(r == "F11" for r, _, _ in v.fails):
    failures.append("developer advocate title passed")
# The (example) top floor is $85k.
if terms_gate.check("x" * 500, "Support Engineer", pay_top=80_000, pay_published=True).passed:
    failures.append("$80k top passed, floor is $85k")
if not terms_gate.check("x" * 500, "Support Engineer", pay_top=85_000, pay_published=True).passed:
    failures.append("$85k top failed")
if not terms_gate.check("x" * 500, "Support Engineer", pay_top=None).passed:
    failures.append("unposted pay failed; it is an ask, not a no")
if terms_gate.check("too short", "Support Engineer").passed:
    failures.append("an unread posting passed")

# Lever keeps duties in "lists" and benefits in "additional"; the gate must
# read them (Olo's on-call line leaked into the 2026-10-31 digest).
import ats  # noqa: E402
row = ats._lever([{"text": "Software Engineer", "hostedUrl": "https://jobs.lever.co/x/1",
                   "descriptionPlain": "We build things. " * 30,
                   "lists": [{"text": "What you'll do",
                              "content": "<li>Join the on-call rotation.</li>"}],
                   "additionalPlain": "Unlimited snacks."}], "Co")[0]
if terms_gate.check(row["description"], row["title"]).passed:
    failures.append("Lever lists not read: on-call in duties passed")
row = ats._lever([{"text": "Partner", "description": "<p>" + "We help clients. " * 30 + "</p>",
                   "descriptionPlain": ""}], "Co")[0]
if len(row["description"]) < 400:
    failures.append("Lever HTML description dropped when descriptionPlain is empty")

# 2026-11-10: a long posting with few periods made the boilerplate regex
# quadratic and stalled the run past its time limit (11-07..11-09).
import time  # noqa: E402
_t = time.time()
terms_gate.check("word " * 40000, title="Support Engineer")
if time.time() - _t > 10:
    failures.append(f"long posting took {time.time() - _t:.0f}s (quadratic regex is back)")

print(f"  terms gate: {len(FAILS)} fail cases, {len(CLEAN)} clean cases")
if failures:
    for f in failures:
        print("  FAIL", f)
    sys.exit(1)
print("ALL TERMS GATE TESTS PASS")
