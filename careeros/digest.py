"""
Ranking and message formatting.

Output obeys plan Section 8. Telegram caps a message at 4096 characters, so a
long digest is split across numbered messages on listing boundaries rather
than truncated. Any listings beyond the cap are still counted in the footer —
never dropped silently.
"""

import re
from collections import Counter
from datetime import datetime

import dedupe
import applied
import experience
import fit
import geo
import netpay
import prefilter
from _shared.paths import SENT_DIR

# Fit lanes in preference order — used only for sorting, never as a gate here.
# The gate lives in prefilter.is_portable().
LANE_ORDER = {
    fit.LANE_CORE: 0,
    fit.LANE_ADJACENT: 1,
    fit.LANE_STRETCH: 2,
    fit.LANE_OFF: 3,
}

# Level, second only to lane. Added 2026-09-28 after the seniority penalty
# failed to do anything visible.
#
# The penalty went into prefilter's `score`, which is the FIFTH key in the sort
# below — behind lane, freedom, ecosystem and salary confidence. So the numbers
# moved and the list did not: a dry run that afternoon still opened with two
# Databricks Sr. roles, which is the exact complaint that started the work.
#
# Ordering on level directly is what the operator actually asked for: senior
# roles were leading a digest for someone changing careers. Sorting, never filtering —
# senior roles still print, at the bottom of their lane.
LEVEL_ORDER = {
    "entry-friendly": 0,
    None: 1,
    "senior-titled": 2,
}
# A published number outranks an invented one at equal freedom and fit. This is
# how the "never sound certain about a number it did not read" rule survives
# unpriced listings being promoted into the main lane.
CONFIDENCE_ORDER = {"published": 0, "estimated": 1, "unknown": 2}

# Inside core, the operator's NAMED first choice outranks the rest of core. Added 2026-09-30
# after widening the implementation patterns moved 901 market roles into core and
# changed the digest by one listing: core was already full, and rank() had nothing
# that told implementation apart from Support Engineer. The operator's notes had
# named "Implementation / Onboarding at a 15-50 person AI company" as the target
# since 2026-09-28 and no code acted on it.
#
# Keyed on fit_label, which classify() already returns, so the priority follows
# the patterns instead of duplicating them.
TARGET_LABELS = (
    # Re-aimed 2026-10-12, operator decision: lead with "AI + people" work,
    # never with roles that screen for coding depth. Three
    # families: AI operations / agent ops, implementation / onboarding, and AI
    # customer-service ops / human-AI design. Forward deployed and deployment
    # engineering were here; they now rank as adjacent (fit.DEMOTED_PATTERNS).
    "AI operations", "AI builder", "AI adoption", "deployment strategist",
    "implementation", "onboarding", "professional services",
    "AI customer-service ops", "conversation design", "model behaviour",
    "AI character", "knowledge / context engineering",
)


# Specialist over Manager inside implementation, 2026-10-01. Read line by line,
# a typical Implementation Manager posting asked for 5+ years, 1,000-user
# rollouts and steering committees. The Specialist and Consultant seats are the
# same work at a level a career-changer can reach.
# Manager stays core and still prints; it just no longer leads.
_MANAGER_TITLE = re.compile(r"\bmanager\b", re.I)
_LEVELLED_LABELS = ("implementation", "onboarding", "professional services")


def target_rank(item):
    """0 when this is the work the operator named as the target, 1 otherwise."""
    label = item.fit_label or ""
    if label not in TARGET_LABELS:
        return 1
    if label in _LEVELLED_LABELS and _MANAGER_TITLE.search(item.listing.title or ""):
        return 1
    return 0

MAX_MAIN = 14
MAX_WILDCARD = 3
MAX_US_ONLY = 4
TELEGRAM_SAFE_CHARS = 3800
# One employer may not own the digest. Reading employer boards directly put 1,764
# postings into the pool, and Payoneer took four consecutive main-lane slots with
# near-identical Customer Success Manager listings. Two is enough to show that a
# company is worth a look; the fifth variation of one role teaches the operator nothing and
# costs a slot a different company could have used.
MAX_PER_COMPANY = 2


def writes_freedom(item):
    """
    True when the posting itself writes async or flexible hours.

    Added 2026-10-05, the operator's words: "just add any single job that could give me
    what I want." Such a job boards ahead of the lane order, whatever its type,
    so a customer-success role that writes "async" is no longer stuck behind
    fourteen core roles that say nothing about the operator's time. Off-lane roles never
    jump: those are the operator's nevers, not a ranking question.
    """
    if fit.is_off_lane(item.fit_lane):
        return False
    reasons = item.freedom_reasons or []
    return "async" in reasons or "flexible hours" in reasons


def rank(items):
    """
    Role fit first, then freedom, then how trustworthy the pay figure is, then
    the figure itself.

    Portability is a GATE, not a sort key — prefilter.is_portable() already
    removed everything that cannot travel, so ranking on it again inside the
    surviving pool just buries the operator's own target roles beneath whatever
    generic remote job happened to say "async". Sorting freedom-first put a
    Front-End WordPress Developer above a Forward Deployed Engineer.

    v1's mistake was leading with tier, which is a proxy for salary. The fix is
    not to lead with freedom — it is to lead with whether this is the operator's job.

    Changed 2026-10-05, the operator's call: "make it freedom first". Freedom now sorts
    straight after the lane and ahead of target_rank. The WordPress failure
    above stays fixed because the lane still comes first, so an off-lane role
    cannot climb past the operator's own work on an "async"; and freedom now scores only
    written evidence (freedom.py), so silence no longer counts as a perk.

    The Anthropic-stack signal is a tiebreaker, not a priority. It ranks below
    freedom on the operator's own calibration: building on Claude is "a plus
    because I can learn more, but not a dealbreaker," whereas a job that wraps
    around the operator's life is the point of the whole search. It sits below fit for the
    same reason a Claude shop hiring a lawyer is still a lawyer job.
    """
    return sorted(
        items,
        key=lambda pair: (
            0 if writes_freedom(pair[1]) else 1,
            # Inside that group freedom decides, not job type.
            -pair[1].freedom if writes_freedom(pair[1]) else 0,
            LANE_ORDER.get(pair[1].fit_lane, 9),
            -pair[1].freedom,
            target_rank(pair[1]),
            LEVEL_ORDER.get(pair[1].level, 1),
            0 if pair[1].ecosystem else 1,
            CONFIDENCE_ORDER.get(pair[1].salary.confidence, 9),
            -pair[1].score,
            # Stated years, demoted here on 2026-09-30 from third in this tuple.
            # Operator decision: apply regardless of a stated years figure. The
            # evidence supports it — the form is the gate, and
            # reading four of them that day found the walls in academic records,
            # Kubernetes and JavaScript, never in a years field. So the figure
            # breaks ties and is printed on every line, and it decides nothing.
            experience.rank_penalty(
                (pair[1].wall or (0, "", None))[0], _wall_years(pair[1])),
            -(pair[1].salary.top or 0),
        ),
    )


def earns_main_lane(item):
    """
    True when a listing has earned a slot the operator will actually read.

    Core and adjacent always qualify — those are the operator's lanes by definition.

    `stretch` has to bring a reason. Invariant 4 says an unrecognised title
    lands in stretch rather than off, so that unknown is never punished like
    known-bad, and that is right: the operator is open to roles that do not
    pattern-match the operator's history. But `stretch` is not a lane, it is the absence
    of a verdict, and the number of things carrying no verdict scales with the
    corpus.

    Measured on 2026-08-17: of 1,502 fresh listings, 10 were in-lane AND
    portable while 62 were portable `stretch`. The main lane took 14, so six
    slots went to whatever unrecognised title ranked highest — which is how
    HR, tax and executive postings reached a digest that had suppressed 682
    off-lane roles on the same run. The cap was never the problem. ELIGIBILITY
    was: anything portable qualified, so the digest went looking for filler.

    Adding employer job boards is what exposed it. An aggregator pre-filters to
    remote tech-ish work, so an unknown title there is usually an unusual tech
    job. A company's own ATS carries every function it employs — Toast alone
    posts 313 roles including tax, facilities and legal — so the same rule that
    was generous on an aggregator became indiscriminate on an ATS.

    The signals accepted here are about the ROLE, never the employer. Company
    category is deliberately excluded: "Strategic People Partner @ Oyster"
    carried the operator's LATAM/bilingual-premium label and was still an HR job.
    """
    if item.fit_lane in (fit.LANE_CORE, fit.LANE_ADJACENT):
        return True
    if fit.is_off_lane(item.fit_lane):
        return False
    # Built on the stack the operator has chosen to grow into, or offering
    # training — both count in a role's favour.
    has_signal = bool(item.ecosystem) or bool(prefilter.training_signals(item.green))
    # ...but both signals are read from the whole posting, so on their own they
    # describe the employer. The title has to independently show the work is
    # near the operator's lane, or an AI company's compliance and sales openings walk in.
    return has_signal and fit.title_shows_relevant_work(item.listing.title)


def _wall_years(item):
    """The stated floor from item.wall, or None. Tolerates the old 2-tuple."""
    wall = getattr(item, "wall", None)
    if not wall or len(wall) < 3:
        return None
    return wall[2]


# Eligibility, and therefore FIRST in every lane loop below.
#
# This is the fourth time ordering has been the bug rather than matching, so it
# is placed the way fit.HARD_BLOCK_PATTERNS is placed: ahead of portability,
# ahead of lane, ahead of score. An experience wall is not a preference to be
# outvoted by a good salary or a core-lane title. It answers whether the form
# will reject the operator on question one, and that comes before whether the operator wants the
# job.
#
# It runs only on enriched listings. item.wall is None until enrich.py has read
# the page, and a listing with no page read is admitted — same reasoning as
# experience.admits() on UNREADABLE. The cap is 200 pages and select() takes 18
# from the top of that same ranking, so in practice everything the operator sees has been
# read.
def clears_experience_wall(item, walled):
    """
    True when the posting's stated experience bar is one the operator can answer.

    Blocked listings are recorded in `walled` rather than dropped, so the digest
    footer can say how many were held back. Nothing is ever silently removed —
    that is how the language rule was debugged in September and it is why the
    off-lane counts exist.

    `walled` is a dict keyed by id(), not a list: select() calls this from three
    lane loops and the first version counted the same blocked role up to three
    times, which would have reported 33 held back on a day when 11 were.
    """
    admitted, reason = admits_item(item)
    if not admitted:
        walled[id(item)] = reason
    return admitted


def admits_item(item):
    """The same verdict without recording it, for counting `eligible`."""
    wall = getattr(item, "wall", None)
    if not wall:
        return True, ""
    return experience.admits(wall[0], _wall_years(item))


def select(items):
    """
    Choose what to send, in three lanes.

    MAIN is work-from-anywhere roles the operator would actually apply to,
    priced and unpriced ranked side by side. WILDCARD catches no-experience
    openings that would otherwise miss the cut. US-ONLY is kept but demoted and
    labelled — income is needed before any move, but these conflict with the
    plan the operator has chosen.

    Off-lane roles never appear. They are counted and reported, never silently
    dropped.
    """
    ranked = rank(items)
    taken = set()
    per_company = Counter()
    walled = {}

    def _company(pair):
        return dedupe.normalize(pair[1].listing.company) or "?"

    main = []
    for pair in ranked:
        if len(main) >= MAX_MAIN:
            break
        if not clears_experience_wall(pair[1], walled):
            continue
        if not prefilter.is_portable(pair[1]):
            continue
        if not earns_main_lane(pair[1]):
            continue
        if per_company[_company(pair)] >= MAX_PER_COMPANY:
            continue
        main.append(pair)
        per_company[_company(pair)] += 1
        taken.add(pair[0])

    # A wildcard still has to be a job the operator could take from anywhere. Without the
    # portability gate this section published "Shop Assistant Cammeray @ Harris
    # Farm Markets" — a retail floor job in a Sydney suburb, freedom 2 — purely
    # because the posting said "will train".
    wildcards = []
    for pair in ranked:
        if pair[0] in taken or len(wildcards) >= MAX_WILDCARD:
            continue
        if not clears_experience_wall(pair[1], walled):
            continue
        # The heading says "no experience required", so a stated floor above
        # MAX_YEARS disqualifies here even though years only rank elsewhere.
        # On 2026-10-01 all three wildcards asked 5+ years.
        years = _wall_years(pair[1])
        if years is not None and years > experience.MAX_YEARS:
            continue
        if prefilter.is_wildcard(pair[1]) and prefilter.is_portable(pair[1]):
            wildcards.append(pair)
            taken.add(pair[0])

    # A US-only role conflicts with the plan the operator has actually chosen, so it has
    # to be worth the conflict: core or adjacent only. Allowing `stretch` here
    # filled the section with a Canadian Armed Forces posting and an empty
    # "talk to us if you can't find a job" listing.
    us_only = []
    for pair in ranked:
        if pair[0] in taken or len(us_only) >= MAX_US_ONLY:
            continue
        if not clears_experience_wall(pair[1], walled):
            continue
        if (pair[1].geo_class == geo.CLASS_US
                and pair[1].fit_lane in (fit.LANE_CORE, fit.LANE_ADJACENT)):
            us_only.append(pair)
            taken.add(pair[0])

    # What "qualified" means in the footer has to be what qualifies for a slot,
    # or the number is just reassurance. This was an OR — portable OR not
    # off-lane — which counted 790 "more qualified, not shown" on a run where
    # only 10 listings could actually have filled a main-lane slot.
    eligible = sum(
        1 for p in ranked
        if admits_item(p[1])[0]
        and prefilter.is_portable(p[1]) and earns_main_lane(p[1])
    )
    suppressed = sum(1 for p in ranked if fit.is_off_lane(p[1].fit_lane))
    # `eligible` now counts main-lane candidates specifically, so only the main
    # lane is subtracted from it — the wildcard and US-only sections are drawn
    # from different pools and were being double-counted out of this figure.
    overflow = max(0, eligible - len(main))

    chosen = main + wildcards + us_only
    return chosen, main, wildcards, us_only, overflow, suppressed, len(walled)


def _entry(item, note=None):
    listing = item.listing
    lines = [f"• {listing.title} @ {listing.company} — {item.salary.display()}"]
    # Take-home, added 2026-09-28. Gross pay is misleading where the income tax
    # rate is high: under the example tax model in netpay.py a $95k offer is
    # worth about $69k. Printed from the TOP of the
    # band, matching how the pay bonus is scored, and only when a number exists
    # — an estimated band already carries its own warning and does not need a
    # second invented figure stacked on top of it.
    if item.salary.confidence == "published" and item.salary.top:
        take_home = netpay.summary(item.salary.top)
        if take_home:
            lines.append(f"  {take_home}")
    if note:
        lines.append(f"  {note}")

    detail = []
    if item.ecosystem:
        detail.append("🤖 " + "/".join(item.ecosystem))
    # Why this company, not just why this role. "large employer" is printed
    # alongside the rest rather than hidden: the operator prefers non-corporate cultures,
    # so when one appears anyway it says so on its own line.
    if item.company_labels:
        detail.append("🏢 " + " · ".join(item.company_labels[:2]))
    # The operator's first requirement, promoted to the front of the line: the
    # posting itself says the employee can live in another country. Only enrich.py can establish
    # this, because it is written on the job page and never in a feed.
    if "works from another country" in item.green:
        detail.append("✈️ works from another country")
    elif "work-abroad weeks" in item.green:
        detail.append("✈️ work-abroad weeks")
    # Promoted to its own tag rather than left inside the green list, where
    # `green[:2]` was truncating it away — the operator asked specifically for roles that
    # do not require deep expertise, so when one appears it has to be visible.
    if prefilter.ACCESSIBLE_LABEL in item.green:
        detail.append("🌱 junior-friendly")
    if item.freedom_reasons:
        # The globe is a claim about LOCATION and nothing else. It used to print
        # on any freedom reason at all, so a retail floor job in a Sydney suburb
        # went out wearing 🌍 because its perk was "no fixed hours".
        #
        # ⏰ is a claim about HOURS, so since 2026-10-05 it prints only when the
        # posting literally writes async or flexible hours. It used to print on
        # "no fixed hours", which meant only that no time-zone clause was found.
        if "work from anywhere" in item.freedom_reasons:
            icon = "🌍 "
        elif ("async" in item.freedom_reasons
              or "flexible hours" in item.freedom_reasons):
            icon = "⏰ "
        else:
            icon = ""
        detail.append(icon + " · ".join(item.freedom_reasons[:2]))
    if item.green:
        detail.append(", ".join(item.green[:2]))
    if detail:
        lines.append(f"  {' · '.join(detail)}")

    form_tag = getattr(item, "form_tag", None)
    if form_tag:
        lines.append(f"  {form_tag}")

    warnings = list(item.notes)
    # The experience wall, read off the page rather than guessed from the title.
    # Added 2026-09-29 after the operator asked whether the titles "want big experience"
    # more than they look like they do. Checking that morning's roles found it
    # runs both ways — "Founding Technical Program Manager" stated no
    # requirement at all while a plain "Project Manager" wanted five years — so
    # the number is reported and the decision stays the operator's. Only enriched listings
    # have it; the rest say nothing rather than guess.
    if item.wall:
        label = experience.wall_label(item.wall[0], _wall_years(item))
        if label:
            warnings.append(label)
    if item.red:
        warnings.append("flags: " + ", ".join(item.red[:2]))
    if warnings:
        lines.append(f"  ⚠️ {' · '.join(warnings[:3])}")

    if listing.url:
        lines.append(f"  {listing.url}")
    return "\n".join(lines)


def split_messages(text, limit=TELEGRAM_SAFE_CHARS):
    """
    Split a digest into Telegram-sized messages on listing boundaries.

    Listings are separated by blank lines, so splitting there never cuts a job
    in half. Parts are numbered so the operator knows none went missing.
    """
    blocks = text.split("\n\n")
    messages, current = [], ""
    for block in blocks:
        candidate = f"{current}\n\n{block}" if current else block
        if len(candidate) > limit and current:
            messages.append(current)
            current = block
        else:
            current = candidate
    if current:
        messages.append(current)

    if len(messages) > 1:
        total = len(messages)
        messages = [f"{m}\n\n({i + 1}/{total})" for i, m in enumerate(messages)]
    return messages


def gap_warning(today=None):
    """
    "No digest for N days" when there is a hole behind us, otherwise None.

    Why this exists, and why it is a line of text rather than a watchdog
    service. Twice now the system has gone quiet and the failure was never the
    code: a Mac with `autorestart 0` stayed off for 27 days in September, and
    GitHub's scheduler fires roughly one slot in five. Both were survivable.
    What made the first one expensive was that nobody NOTICED — the operator
    found out because the operator's phone had been quiet, four weeks late.

    A punctuality guarantee was considered and rejected on 2026-09-29: job
    postings do not expire in hours, so a digest arriving at 7pm instead of 6am
    costs nothing, and a daily watchdog agent would be one more unattended
    thing that can fail silently. The actual gap was never punctuality. It was
    visibility.

    So the digest reports its own absence. `state/sent/` is written only after
    Telegram confirms delivery, which makes its filenames a record of what
    actually arrived rather than what was attempted.
    """
    today = today or datetime.now().date()
    dates = []
    for path in SENT_DIR.glob("*.json"):
        try:
            d = datetime.strptime(path.stem, "%Y-%m-%d").date()
        except ValueError:
            continue
        if d < today:
            dates.append(d)
    if not dates:
        return None
    gap = (today - max(dates)).days
    if gap <= 1:
        return None
    last = max(dates).strftime("%b %-d")
    if gap == 2:
        return f"⚠️ Nothing sent yesterday — last digest was {last}"
    return f"⚠️ No digest for {gap - 1} days — last was {last}"


def build(chosen, main, wildcards, us_only, overflow, suppressed, walled,
          stats, date_label):
    """Assemble the Telegram message."""
    gap = gap_warning()

    if not chosen:
        header = f"🎯 CareerOS Daily — {date_label}"
        if gap:
            header += f"\n{gap}"
        return (
            f"{header}\n\n"
            "No new matches today, still watching.\n\n"
            f"Scanned: {stats['fetched']} · "
            f"Cleared filters: {stats['kept']} · "
            f"Sources live: {stats['sources_live']}/{stats['sources_total']}"
        )

    parts = [f"🎯 CareerOS Daily — {date_label}"]
    # Second line, above the roles. A gap is the one thing in this message that
    # is about the machine rather than the market, and it has to be read before
    # anything else or it is not read at all.
    if gap:
        parts.append(gap)
    # What the OPERATOR has sent, directly under what the machine found. Added 2026-09-30:
    # twenty-one digests had surfaced 314 roles and nothing anywhere recorded a
    # single application. A funnel with no bottom reads like progress.
    pressure = applied.pressure()
    if pressure:
        parts.append(pressure)

    if main:
        # The lane split, said out loud. A section of 14 reads as 14 matches;
        # on 2026-08-17 all 14 were `stretch` — unrecognised titles in the
        # neutral middle lane — and not one was a role the operator is actually chasing.
        # The count was true and the impression it created was false.
        on_lane = sum(
            1 for p in main
            if p[1].fit_lane in (fit.LANE_CORE, fit.LANE_ADJACENT)
        )
        header = f"🏠 REMOTE FROM HOME ({len(main)})"
        if on_lane != len(main):
            header += f" — {on_lane} in your lane, {len(main) - on_lane} adjacent guesses"
        parts.append(header)
        for pair in main:
            parts.append(_entry(pair[1]))

    if wildcards:
        parts.append(f"🌟 WILDCARD — no experience required ({len(wildcards)})")
        for pair in wildcards:
            parts.append(_entry(pair[1]))

    if us_only:
        parts.append(f"🇺🇸 MORE US / NORTH AMERICA REMOTE ({len(us_only)})")
        for pair in us_only:
            parts.append(_entry(pair[1]))

    footer = (
        f"New today: {len(chosen)} · "
        f"Scanned: {stats['fetched']} · "
        f"Sources live: {stats['sources_live']}/{stats['sources_total']}"
    )
    if stats.get("enriched"):
        footer += f" · {stats['enriched']} job pages read"
    if stats.get("beyond_cap"):
        footer += f" · {stats['beyond_cap']} not page-checked"
    if overflow:
        footer += f" · {overflow} more qualified, not shown"
    if suppressed:
        footer += f"\n{suppressed} off-lane roles suppressed (wrong job, not shown)"
    # Said out loud, every day. The operator asked for the wall filter on 2026-09-30 and
    # the risk of granting it is that the digest quietly shrinks and the operator reads
    # the market as empty when it is the filter doing the work. The number makes
    # the filter's cost visible, so the operator can tell me to loosen it.
    if walled:
        # Wording corrected 2026-09-30 the same evening the years block was
        # reverted. The line still said "2+ years demanded, or a staff/principal
        # title" and a dry run printed "878 roles held back — 2+ years demanded",
        # which was simply untrue: years stopped blocking hours earlier and only
        # titles gate now. A footer that misreports its own filter is worse than
        # no footer, because the operator would read it as the market being thinner than it is.
        footer += (f"\n{walled} roles held back — senior, staff, principal, "
                   f"director or VP in the title")
    if stats.get("no_salary"):
        footer += f"\n{stats['no_salary']} listings dropped — no pay stated and role unrecognised"
    parts.append(footer)

    return "\n\n".join(parts)
