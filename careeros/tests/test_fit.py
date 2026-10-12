#!/usr/bin/env python3
"""
Role-fit tests.

    python3 careeros/tests/test_fit.py

This module decides which jobs the operator ever sees, so the tests pin both
directions: every one of the operator's target titles must land in `core`, and
every role that reached the 2026-08-15 digest despite being unreachable or
unwanted must land in `off`.

The third property matters as much as the other two: an unrecognised title must
land in `stretch`, never in `off`. The operator is explicitly open to roles
that do not pattern-match their history, and punishing unknown like known-bad would close
that door.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import fit  # noqa: E402

# The operator's target titles.
CORE_TITLES = [
    "Implementation Specialist",
    "Implementation Engineer",
    "Onboarding Engineer",
    # Added 2026-09-30 after the operator noticed no implementation roles in the
    # digest. 901 implementation-shaped roles were live that day, 155
    # cleared the experience gate, and 7 had reached the digest in twenty-one runs.
    # The gate was not the bottleneck — CORE_PATTERNS required an exact noun
    # straight after "implementation" or "onboarding", so every one of these
    # fell through to stretch.
    "Implementation Manager",
    "Implementation Lead",
    "Implementation Analyst",
    "Implementation Consultant",
    "Cloud Professional Services Manager",
    "Professional Services - Technical Architect",
    "Customer Onboarding Manager",
    "Enterprise Onboarding Manager",
    "SMB Onboarding Lead",
    "Onboarding Project Manager",
    "Deployment Strategist",
    # (A premium member-experience lane was core from 2026-09-30 to 2026-10-08;
    # removed with the hospitality lane, see below.)
    "Technical Account Manager",
    "Automation Engineer",
    # Seniority must not knock a role out of the operator's own lane.
]

# Every one of these was delivered on 2026-08-15 and should never have been.
OFF_TITLES = [
    "Associate General Counsel, Corporate",
    "Director, FinOps",
    "Principal Business Intelligence Analyst",
    "Staff Brand Designer",
    "Senior Software Engineer, Frontend (Consumer - Payments)",
    "Senior Software Engineer (EAA)",
    "Lead Software Engineer",
    "Tech Lead Full-Stack Rails Engineer",
    "Senior Full-Stack Engineer (Elixir + React)",
    "Group Product Manager, Finance Technology",
    "Account Executive, Enterprise",
    "Senior Recruiter",
    "Curriculum Developer",
    # Any C-level title is out of reach and out of lane, nonsense or not.
    "Chief Vibes Officer",
    # Both reached the live digest on 2026-08-16.
    "Shop Assistant Cammeray",
    "Campaign Manager - SEO & AI Content",
]

ADJACENT_TITLES = [
    "Sales Engineer",
    "Developer Advocate",
    "Customer Success Manager",
    "Solutions Consultant",
]

# Must NOT be punished. Unknown is not the same as unwanted.
STRETCH_TITLES = [
    # The three traps in the widened implementation lane, all real titles from
    # the 2026-09-30 audit. "Onboarding" without a customer on the other end is
    # a different job: KYC onboarding is compliance, sales-enablement onboarding
    # is internal training, and employee onboarding is HR. All three matched
    # core on the first cut of the wider pattern.
    # A call-centre title is not the premium-member lane and must not dilute it.
    "Customer Service Representative",
    "KYC/B Onboarding Analyst",
    "Sales Enablement & Onboarding Manager",
    "Employee Onboarding Coordinator",
    "Onboarding Manager",
    "Software Engineer",
    "Founding Software Engineer",
    "Fullstack Engineer",
    "Underwater Basket Weaver",
    "Product Manager",
    "",
]


def _check(titles, want, failures):
    for title in titles:
        lane, label = fit.classify(title)
        ok = lane == want
        mark = "PASS" if ok else "FAIL"
        shown = title if title else "(empty)"
        print(f"  [{mark}] {shown[:52]:54s} -> {lane} ({label})")
        if not ok:
            failures.append(f"{shown!r}: want {want}, got {lane} ({label})")


def main():
    failures = []

    print("=== core: the operator's own target titles ===")
    _check(CORE_TITLES, fit.LANE_CORE, failures)

    print("\n=== off: delivered on 2026-08-15, should not have been ===")
    _check(OFF_TITLES, fit.LANE_OFF, failures)

    print("\n=== adjacent: same lane, different vocabulary ===")
    _check(ADJACENT_TITLES, fit.LANE_ADJACENT, failures)

    # 2026-10-08: AI Operations promoted to core, one of the operator's three target
    # families. Business Systems counts only with an AI/automation word.
    print("\n=== AI operations: core since 2026-10-08 ===")
    _check(["AI Operations Engineer", "AI Ops Specialist",
            "Applied AI Operations Lead", "AI Business Systems Analyst",
            "Business Systems Engineer (Automation)"], fit.LANE_CORE, failures)
    _check(["Business Systems Analyst"], fit.LANE_STRETCH, failures)
    _check(["AI Automation Sales Representative"], fit.LANE_OFF, failures)

    # 2026-10-08: AI customer-service ops lane.
    print("\n=== AI customer-service ops: core since 2026-10-08 ===")
    _check(["Support Operations Specialist", "CX Operations Manager",
            "Customer Experience Operations Analyst", "Chatbot Specialist",
            "AI Support Specialist", "Knowledge Base Specialist"],
           fit.LANE_CORE, failures)
    _check(["Contact Center Operations Manager", "Sales Operations Specialist"],
           fit.LANE_STRETCH, failures)

    # 2026-10-08: hospitality / luxury lane removed by the operator. Concierge and
    # luxury titles must no longer reach core; software-company premium
    # support stays adjacent.
    print("\n=== hospitality removed 2026-10-08: never core ===")
    for t in ("Concierge Specialist", "Luxury Travel Advisor", "Guest Relations Manager",
              "Centurion Member Services Manager", "Lifestyle Manager", "Concierge Manager"):
        lane, label = fit.classify(t)
        ok = lane != fit.LANE_CORE
        print(f"  [{'PASS' if ok else 'FAIL'}] {t:<40} -> {lane} ({label})")
        if not ok:
            failures.append(f"{t!r} still core after hospitality removal")
    _check(["VIP Support Specialist"], fit.LANE_ADJACENT, failures)

    # 2026-10-08: human-AI design, knowledge engineering and AI adoption
    # promoted to core.
    print("\n=== human-AI design lanes: core since 2026-10-08 ===")
    _check(["Conversation Designer", "Model Behavior Specialist",
            "AI Personality Designer", "Prompt Designer", "Knowledge Engineer",
            "Context Engineer", "AI Transformation Lead", "AI Champion"],
           fit.LANE_CORE, failures)
    _check(["AI Character Writer", "Creator Success Manager", "Character Designer"],
           fit.LANE_ADJACENT, failures)
    _check(["Copywriter", "Content Writer"], fit.LANE_OFF, failures)

    # 2026-10-12: engineering-heavy titles demoted, never dropped.
    print("\n=== engineering-heavy: adjacent since 2026-10-12 ===")
    _check(['Solutions Engineer', 'Solutions Architect', 'Forward Deployed Engineer', 'Customer Engineer', 'Technical Support Engineer', 'Support Engineer', 'AI Engineer', 'Integrations Engineer', 'Senior Solutions Engineer', 'Staff Forward Deployed Engineer', 'Director of Solutions Engineering', 'Deployment Engineer', 'Postgres Deployment Engineer'], fit.LANE_ADJACENT, failures)

    print("\n=== stretch: unknown must not be punished like known-bad ===")
    _check(STRETCH_TITLES, fit.LANE_STRETCH, failures)

    print("\n=== scoring order: core > adjacent > stretch > off ===")
    order = [
        fit.LANE_SCORE[fit.LANE_CORE],
        fit.LANE_SCORE[fit.LANE_ADJACENT],
        fit.LANE_SCORE[fit.LANE_STRETCH],
        fit.LANE_SCORE[fit.LANE_OFF],
    ]
    ok = order == sorted(order, reverse=True)
    print(f"  [{'PASS' if ok else 'FAIL'}] {order}")
    if not ok:
        failures.append(f"lane scores out of order: {order}")

    # --- Derived lanes, opened 2026-09-28 -------------------------------
    # Each of these is a real title that used to land off-lane or in stretch.
    # The first three are the collisions: they share a word with an off pattern
    # written for a completely different job.
    print("\n=== derived lanes reach adjacent, not off ===")
    derived_cases = [
        ("Chief of Staff", "collides with the `chief` executive rule"),
        ("Technical Writer", "collides with the `writer` editorial rule"),
        ("AI Trainer", "collides with the `trainer` teaching rule"),
        ("Executive Business Partner", "from prior premium-service work"),
        ("VIP Support Specialist", "from prior premium-service work"),
        ("Trust & Safety Analyst", "from prior regulated support work"),
        ("Content Policy Specialist", "from prior regulated support work"),
        ("Product Designer", "from a design education"),
        ("UX Researcher", "from a design education"),
        ("Localization Manager", "from being bilingual"),
        ("Customer Success Manager, LATAM", "from being bilingual"),
        ("Model Behavior Researcher", "from a psychology background"),
        ("AI Character Designer", "from a psychology background"),
        ("Conversation Designer", "from a psychology background"),
        ("Behavioral Scientist", "from a psychology background"),
        # The health & safety block added 2026-09-29 must not catch these:
        # different domains that happen to share the word.
        ("Trust & Safety Analyst", "safety block must not catch trust & safety"),
        ("AI Safety Engineer", "safety block must not catch AI safety"),
        # Outside software and AI entirely.
        ("Business Operations Manager", "encoding judgment into process"),
        ("Revenue Operations Analyst", "encoding judgment into process"),
        ("Technical Program Manager", "stakeholder management"),
        ("Project Coordinator", "stakeholder management"),
        ("Partner Success Manager", "post-sale relationship work"),
        ("Community Manager", "direct contact, beyond the script"),
        ("QA Analyst", "the resilience discipline, entry-accessible"),
        ("Test Engineer", "the resilience discipline, entry-accessible"),
        ("Global Mobility Specialist", "EOR companies are remote-first"),
        ("Relocation Consultant", "EOR companies are remote-first"),
        ("Patient Advocate", "from prior support work"),
        ("Care Navigator", "from prior support work"),
    ]
    for title, why in derived_cases:
        lane, label = fit.classify(title)
        ok = lane in (fit.LANE_CORE, fit.LANE_ADJACENT)
        print(f"  [{'PASS' if ok else 'FAIL'}] {title:<34} -> {lane}/{label}  ({why})")
        if not ok:
            failures.append(f"{title!r} landed {lane}, expected core or adjacent")

    # The carve-outs must stay narrow. These are the jobs the off rules were
    # actually written for and they must still be blocked.
    print("\n=== carve-outs stayed narrow ===")
    still_off = [
        ("Copywriter", "editorial, not documentation"),
        ("Content Creator", "editorial, not documentation"),
        ("Corporate Trainer", "teaching delivery — excluded by preference"),
        ("Curriculum Developer", "teaching delivery"),
        ("Brand Designer", "physical/brand design, not product design"),
        ("Graphic Designer", "physical/brand design, not product design"),
        ("Chief Technology Officer", "executive hiring"),
        ("Account Executive", "quota sales — a hard exclusion"),
        # Guards on the lanes opened 2026-09-28. Each shares a word with a new
        # pattern and must still be blocked.
        ("Registered Nurse", "clinical — patient advocacy must not open nursing"),
        ("Recruiting Coordinator", "HR — program management must not open recruiting"),
        ("Marketing Manager", "marketing — community must not open campaigns"),
        ("Sales Development Representative", "quota — partnerships must not open closing"),
        # Regression, 2026-09-28. "Channel Account Executive, LATAM @ Asana"
        # reached the main digest because the derived group ran BEFORE the off
        # list, so the LATAM pattern matched first and returned adjacent. A
        # pattern meant to surface Spanish-speaking roles was laundering every
        # off-lane role that mentioned the region — including quota sales, a
        # hard exclusion. A lane may be widened, never at the cost
        # of an exclusion.
        ("Channel Account Executive, LATAM", "the Asana bug: region must not rescue quota sales"),
        ("Account Executive, LATAM", "same, without the Channel prefix"),
        ("Sales Manager LATAM", "same, different closing title"),
        ("Recruiter, Latin America", "region must not rescue HR either"),
        ("Marketing Manager, LATAM", "region must not rescue marketing either"),
        # Both reached the 2026-09-29 digest and were caught by reading it.
        ("Accounting Specialist - LATAM", "the rule knew `accountant`, not `accounting`"),
        ("Health & Safety Program Manager", "program management must not open occupational safety"),
        ("EHS Manager", "same domain, the abbreviation boards actually use"),
        ("Safety Coordinator", "same domain, no Program Manager in the title"),
        # The operator speaks Spanish and English. Both of these reached the 2026-09-29
        # digest asking for neither, through two different doors: the AI-training
        # carve-out and the core sales-engineer rule. Eligibility now outranks
        # lane, so the check runs before core and before the collisions.
        ("Amharic Language Specialist - Freelance AI Trainer Project",
         "came in through the AI Trainer carve-out"),
        ("Presales Engineer (German speaker)", "came in through the core rule"),
        ("Japanese AI Trainer", "same carve-out, different language"),
        ("Senior Solutions Engineer, French Market", "a language wall inside a target lane"),
        ("Grupo QuintoAndar | Vaga afirmativa para PcD - Analista de Business Operations",
         "Portuguese posting: unreadable to the operator, and PcD is a reserved position"),
        ("Desenvolvedor Full Stack", "Portuguese by vocabulary, not by accent"),
        ("Gerente de Operações", "Portuguese by accent alone"),
    ]

    # The languages the operator DOES speak must survive that block, or the fix
    # costs the exact roles it was built to surface.
    print("\n=== Spanish and English still rank, never blocked ===")
    spanish_cases = [
        "Spanish-speaking Support Engineer",
        "Bilingual Implementation Specialist (Spanish/English)",
        "Customer Success Manager, LATAM",
        "Solutions Engineer - Spanish required",
    ]

    for title in spanish_cases:
        lane, label = fit.classify(title)
        ok = lane in (fit.LANE_CORE, fit.LANE_ADJACENT)
        print(f"  [{'PASS' if ok else 'FAIL'}] {title:<46} -> {lane}/{label}")
        if not ok:
            failures.append(f"{title!r} was blocked; Spanish must never be a wall")

    # Spanish shares most of its vocabulary with Portuguese, so the Portuguese
    # block must discriminate on what Spanish does NOT have. These are Spanish
    # job titles: unrecognised, so `stretch` is the right answer — but they must
    # never be BLOCKED, which is what the accent rule could do if it were lazy.
    print("\n=== Spanish-language titles are not mistaken for Portuguese ===")
    for title in ("Analista de Operaciones, Mexico (Remoto)",
                  "Especialista en Soporte Tecnico",
                  "Gerente de Exito del Cliente"):
        lane, label = fit.classify(title)
        ok = lane != fit.LANE_OFF
        print(f"  [{'PASS' if ok else 'FAIL'}] {title:<46} -> {lane}/{label}")
        if not ok:
            failures.append(f"{title!r} blocked as Portuguese; it is Spanish")
    for title, why in still_off:
        lane, label = fit.classify(title)
        ok = lane == fit.LANE_OFF
        print(f"  [{'PASS' if ok else 'FAIL'}] {title:<34} -> {lane}/{label}  ({why})")
        if not ok:
            failures.append(f"{title!r} landed {lane}, expected off")

    # --- Seniority axis -------------------------------------------------
    print("\n=== seniority: level is scored apart from lane ===")
    level_cases = [
        ("Senior Solutions Engineer", "senior-titled"),
        ("Sr. Forward Deployed Engineer", "senior-titled"),
        ("Staff AI Engineer", "senior-titled"),
        ("Principal Solutions Architect", "senior-titled"),
        ("Solutions Engineer", None),
        ("Technical Support Engineer", None),
        ("Junior Solutions Engineer", "entry-friendly"),
        ("Associate Customer Engineer", "entry-friendly"),
        ("Support Engineer, New Grad", "entry-friendly"),
        ("Lead Generation Specialist", None),
    ]
    for title, expected in level_cases:
        _, tag = fit.seniority(title)
        ok = tag == expected
        print(f"  [{'PASS' if ok else 'FAIL'}] {title:<34} -> {tag!r} (want {expected!r})")
        if not ok:
            failures.append(f"{title!r} tagged {tag!r}, expected {expected!r}")

    # The point of the whole change: a senior title in a target lane must now
    # rank below the same role without the word.
    print("\n=== a senior core role ranks below the plain one ===")
    plain, _, _ = fit.score("Solutions Engineer")
    senior, _, _ = fit.score("Senior Solutions Engineer")
    junior, _, _ = fit.score("Junior Solutions Engineer")
    ok = junior > plain > senior
    print(f"  [{'PASS' if ok else 'FAIL'}] junior={junior} > plain={plain} > senior={senior}")
    if not ok:
        failures.append(f"level ordering wrong: {junior}/{plain}/{senior}")

    # Both stay in the lane. Downranked, never blocked — a Senior Solutions
    # Engineer at a fifteen-person startup is still a real shot.
    lane_senior, _ = fit.classify("Senior Implementation Manager")
    ok = lane_senior == fit.LANE_CORE
    print(f"  [{'PASS' if ok else 'FAIL'}] senior core role stayed core, not blocked")
    if not ok:
        failures.append("senior core role was blocked, should only be downranked")

    # An off-lane role is not rescued by being junior.
    off_points, off_lane, _ = fit.score("Junior Account Executive")
    ok = off_lane == fit.LANE_OFF and off_points == fit.LANE_SCORE[fit.LANE_OFF]
    print(f"  [{'PASS' if ok else 'FAIL'}] junior quota sales stayed off at {off_points}")
    if not ok:
        failures.append(f"junior off-lane role scored {off_points} in {off_lane}")

    print("\n" + "=" * 60)
    if failures:
        print(f"FAILED {len(failures)}")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("ALL FIT TESTS PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
