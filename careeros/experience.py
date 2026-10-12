"""
The experience wall: how many years a posting demands, and whether the title
itself is a wall even when no number appears.

Measured 2026-08-18 across 747 in-lane listings: 4 in 10 state a number, and
in the core lane 32 of the 42 postings with NO number still carry a seniority
title. So a years filter alone reads the smaller of the two walls. Both are
reported here and both are shown to the operator, because the decision of
whether to apply anyway is the operator's, not the machine's.

Two defects found while building this, both pinned in tests:

  1. "5+ years in a customer-facing role" has no word "experience" in it. An
     early version required one nearby and missed most real walls.
  2. Matching the surrounding context inside the same regex made matches
     non-overlapping, so "travel 4 times a year ... 2+ years of experience"
     lost the second figure to the first match's window. Context is now sliced
     by index after the fact, which cannot swallow a neighbour.
"""

import re

WORD_NUMBERS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}

# Only the figure. Context is read by index afterwards. See defect 2 above.
_YEARS = re.compile(
    r"\b(\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten)"
    r"\s*(?:\+|plus)?\s*(?:[-–]\s*\d{1,2})?\s*(?:\+|plus)?\s*(?:years?|yrs?)\b",
    re.IGNORECASE,
)

# Phrasings where a number of years is not a requirement: company offsites,
# vacation days, roadmaps, ages, and "year over year" growth claims.
_LEAD_NOT_A_WALL = re.compile(
    r"(once|twice|each|every|per|a|the past|the last|last|next|for the|"
    r"up to \d+ times a)\s*$",
    re.IGNORECASE,
)
_TAIL_NOT_A_WALL = re.compile(
    r"^\s*(ago|old|of age|[-–]?over[-–]?year|of vacation|of pto|of paid|"
    r"of unlimited|of tenure)",
    re.IGNORECASE,
)
_CONTEXT = 40  # characters either side that decide whether a figure is a wall

_MIN_YEARS, _MAX_YEARS = 1, 20

# A title that gates on level rather than on a number.
SENIORITY_TITLE = re.compile(
    r"\b(senior|sr\.?|staff|principal|lead|director|head of|manager|"
    r"vp|vice president|chief|architect)\b",
    re.IGNORECASE,
)


def years_required(text):
    """
    (highest_years_demanded, evidence) or (None, "").

    Highest wins across separate requirements: a posting asking 3 years in one
    bullet and 7 in another is a 7 year posting for the purpose of deciding
    whether to bother. Within a single stated range the FLOOR is the bar, since
    "3-5 years" is a posting that will look at three.
    """
    if not isinstance(text, str) or not text:
        return None, ""
    best, evidence = None, ""
    for match in _YEARS.finditer(text):
        lead = text[max(0, match.start() - _CONTEXT):match.start()]
        tail = text[match.end():match.end() + _CONTEXT]
        if _LEAD_NOT_A_WALL.search(lead) or _TAIL_NOT_A_WALL.search(tail):
            continue
        token = match.group(1).lower()
        years = WORD_NUMBERS.get(token)
        if years is None:
            try:
                years = int(token)
            except ValueError:
                continue
        if not (_MIN_YEARS <= years <= _MAX_YEARS):
            continue
        if best is None or years > best:
            best = years
            evidence = " ".join((lead + match.group(0) + tail).split())
    return best, evidence


# Staff, principal and above are a different gap from "senior": senior is a
# claim the operator can argue with artifacts, principal is a claim about scope
# the operator has never had. Reported separately so the page does not flatten the two.
UPPER_TITLE = re.compile(r"\b(staff|principal|distinguished|head of|director|chief|vp)\b", re.IGNORECASE)

# The words the operator actually objected to, and only those. Added 2026-09-30
# on the operator's instruction to block senior-titled roles too.
#
# SENIORITY_TITLE bundles two unlike things: real level markers, and words that
# merely describe the shape of a role. Blocking the whole list would have thrown
# out "Solutions Architect", a PRIMARY TARGET LANE, and "Manager", which is
# frequently an individual-contributor title. The September complaint was
# specific: six of eighteen roles were Senior, Sr. or Staff, for an operator
# early in a new career. Senior, Sr and Staff. Not Architect, not Manager.
#
# "Snr" is here because it is not "Sr" and the `sr\.?` alternative never matched
# it — "Snr Solutions Architect @ Elastic" was reading as an unmarked title.
TRUE_SENIORITY = re.compile(r"\b(senior|sr\.?|snr|lead)\b", re.IGNORECASE)

# "Lead Generation Specialist" is not a senior role, and fit.py already guards
# this one. It matters more here: there it cost points, here it costs the listing.
_LEAD_GEN = re.compile(r"\blead\s+gen(?:eration)?\b", re.IGNORECASE)


def names_seniority(title):
    """True when the title claims a level the operator cannot claim yet."""
    if not title:
        return False
    return bool(TRUE_SENIORITY.search(_LEAD_GEN.sub(" ", title)))


def has_seniority_title(title):
    """True when the title gates on level even if no number is stated."""
    return bool(title) and bool(SENIORITY_TITLE.search(title))


def title_level(title):
    """0 no level named, 1 senior or architect, 2 staff, principal and above."""
    if not title:
        return 0
    if UPPER_TITLE.search(title):
        return 2
    return 1 if SENIORITY_TITLE.search(title) else 0


# An unread page is not a clean page. Added 2026-09-30, and it is the reason a
# years filter could not simply be switched on.
#
# Measured over the 532 cached pages in state/pages: page length is bimodal with
# nothing in between. 187 pages are under 100 characters — Ashby and Greenhouse
# single-page apps answering "You need to enable JavaScript to run this app."
# Every page that carries a real posting is over 4,500. p30 is 95 characters,
# p40 is 4,530.
#
# Those 187 state no years because there is no text, so wall_height read them as
# height 0, clean, nothing in the way. Harmless while the wall was only a label.
# The moment it becomes a gate it inverts: a filter that blocks stated years
# would pass every posting it cannot read and send them as entry level. Unknown
# has to be its own answer.
UNREADABLE = -1
PAGE_MIN_CHARS = 1200  # inside the gap between the two modes, closer to neither


UNREADABLE_WHY = "page did not render without JavaScript, bar unknown"


def page_is_readable(text):
    """
    True when a FETCHED PAGE holds enough text for a requirement to be in it.

    Deliberately a length test and not a JavaScript-shell test. The shells vary
    by vendor and the phrasing will change; what does not change is that a
    posting stating no years in 60 characters has stated nothing at all.

    Called by enrich.py, NOT by wall_height. The first version of this put the
    length test inside wall_height and it was wrong within the hour: curated.py
    passes `listing.description`, which is a board summary and legitimately
    short, so every curated role turned UNREADABLE. Only the stage that fetched
    a page knows whether short text means a failed render or a brief summary.
    """
    return isinstance(text, str) and len(text) >= PAGE_MIN_CHARS


def wall_from_text(title, text):
    """
    wall_height, but UNREADABLE when `text` is too thin to hold a requirement.

    The one function both callers use, because the "absent means clean" inversion
    showed up twice in one afternoon — first when the length test lived inside
    wall_height, then again when prefilter started reading the bar from
    `listing.description` and a feed with no description scored as height 0,
    nothing in the way. Two callers implementing the same guard is two chances to
    get it wrong; there is now one.

    A title the gate blocks is blocked before the length test, not after. Until
    2026-10-01 a Senior or Staff role whose page was a JavaScript shell came back
    UNREADABLE, and admits() lets UNREADABLE through — so "block the senior ones
    too" held only for postings that happened to render.
    """
    if not page_is_readable(text):
        height, why, _ = wall_height(title, "")
        if height in BLOCKED_HEIGHTS:
            return height, why, None
        return UNREADABLE, UNREADABLE_WHY, None
    return wall_height(title, text)


def wall_height(title, text):
    """
    How far above the operator's head the bar is set, plus why.

   -1  the page could not be read, so the bar is unknown  (UNREADABLE)
    0  nothing in the way
    1  a role-shape word (architect, manager), no level claimed, no number
    2  the stated floor is 1 year
    3  the stated floor is 2 to 3 years
    4  staff or principal in the title, no number
    5  the stated floor is 4 or more years
    6  senior, sr, snr or lead in the title, no number

    Heights 2 and 3 were one bucket until 2026-09-30. Splitting them is what
    lets the gate sit at "2 years" without also throwing out the six postings
    that ask for one, and real application forms are why the line falls
    there: some forms require two years outright, one saying "if not, please
    do not apply."

    Staff and principal moved ABOVE the stated-years heights rather than sitting
    at 2 with them. It was never a claim about years. It is a claim about scope
    the operator has not had, and while it shared a bucket with "1–3 years" any gate that
    admitted a two-year posting silently admitted Principal Customer Engineer
    with it — measured on a real Cloudflare posting in the cache.

    Returns (height, why, stated_years). stated_years is None when no figure
    appears, and is the FLOOR of the demand — see years_required. The digest
    prints that number rather than the bucket, because a bucket understates: a
    posting asking "3–5 years of experience" has a floor of 3, which used to
    print as "asks 1–3 years". Caught on a real one, Customer Success Manager @
    Fin, while measuring the cache on 2026-09-30.
    """
    years, evidence = years_required(text)
    level = title_level(title)

    # The TITLE is checked before the years, and that order is the fix for a bug
    # shipped and caught the same day. The first version tested `if years is None`
    # first, so the seniority block only ever ran on postings that stated no
    # number — and "Senior Implementation Specialist @ block", asking 4 years,
    # walked into a verified digest with the word Senior in its title. A gate that
    # any posting can bypass by stating a number is not a gate.
    #
    # `years` is still carried through, so rank_penalty keeps working and
    # wall_label still prints the real figure rather than a level.
    if level == 2:
        return 4, "staff or principal level in the title", years
    if names_seniority(title):
        return 6, "senior in the title", years

    if years is None:
        if level:
            return 1, "a role word, not a level, and no years stated", None
        return 0, "", None
    if years <= 1:
        return 2, evidence, years
    if years <= 3:
        return 3, evidence, years
    return 5, evidence, years


# One short phrase per height, for the digest line. Added 2026-09-29, to answer
# whether titles sound more intimidating than the experience they actually ask for.
#
# Checked against roles in that morning's digest, by fetching the pages:
#
#   Founding Technical Program Manager @ Supabase   no years stated
#   Project Manager @ mongodb                       5+ years
#   Partnerships Manager, Ecosystem @ Supabase      5-10 years
#   Solutions Architect @ databricks                6+ years
#
# So the title is a bad signal in BOTH directions. The most frightening name on
# that list asks for nothing; the plainest asks for five years. Both directions
# are expensive — a title that understates its wall wastes an application, a
# title that overstates it means the operator never applies at all.
#
# Hence wording that names the gap rather than the level. Height 1 is the whole
# reason this exists: the posting sounds senior and never asks for a year.
WALL_LABELS = {
    UNREADABLE: "posting would not load, experience bar unknown",
    0: None,
    1: None,
    4: "staff or principal title",
    6: "senior title, states no experience requirement",
}


def wall_label(height, stated_years=None):
    """
    Short phrase for the digest, or None when nothing is in the way.

    Where a figure was stated the label prints that figure — "asks 3+ years" —
    rather than the bucket it fell in. A bucket can only understate the floor,
    and understating is the expensive direction: it is what sends the operator
    to a form that will reject them on question one.
    """
    if stated_years is not None:
        return f"asks {stated_years}+ years"
    return WALL_LABELS.get(height)


# The gate. Everything above this line reports; this is the only part that
# excludes, and it exists because of the operator's instruction on 2026-09-30,
# after a digest in which 9 of 18 roles demanded four or more years: receive
# only roles tailored to the operator.
#
# That reverses the instruction this module was built under six weeks earlier —
# show the roles the operator would be winging and let them decide. Both
# instructions are the operator's to give. The reversal is recorded rather than quietly applied, because
# the old one is still written three paragraphs up and someone will read it.
#
# MAX_YEARS is the highest stated floor the operator can answer honestly on a form, and
# since 2026-09-30 it RANKS rather than blocks. See BLOCKED_HEIGHTS.
MAX_YEARS = 1


# How far down a stated figure should push a role, 0 to 3. Used as a HIGH sort
# key in digest.rank, not as a score adjustment: the seniority penalty spent six
# weeks in prefilter's `score`, which is the fifth key in that sort, and moved
# nothing visible. A penalty that does not change the order is not a penalty.
def rank_penalty(height, stated_years=None):
    if stated_years is not None:
        if stated_years <= MAX_YEARS:
            return 0
        if stated_years <= 3:
            return 1
        if stated_years <= 5:
            return 2
        return 3
    if height in (1, UNREADABLE):
        return 1
    return 0

# Heights that never reach the digest. TITLES only, as of 2026-09-30.
#
# 4 is staff/principal: a claim about scope the operator has not had, which no
# demo closes.
# 6 is senior/sr/snr/lead, blocked at the operator's request the same day, after
# a digest came back with 8 of 18 roles carrying a level
# and no stated requirement. Height 1 stays out of this list: it is what remains
# once the real level words are removed, namely Architect and Manager, and those
# are a target lane and often an IC title.
#
# STATED YEARS ARE NO LONGER BLOCKED. Height 5 was removed hours after it was
# added, and the reason is the strongest evidence in the project: postings and
# application forms disagree in both directions. One posting stated "No years
# requirement" while its FORM demanded two years and said "if not, please do not
# apply." Another posting read senior while its form had no experience gate at
# all.
#
# The posting is a soft signal. The form is the gate. Blocking on prose discarded
# 2,292 roles a day on the weaker of the two artifacts, including most of the
# implementation lane, which routinely asks 2 to 5 years. Years now sort via
# rank_penalty() and the form gets read on a weekly shortlist of five.
BLOCKED_HEIGHTS = (4, 6)


def admits(height, stated_years=None):
    """
    (True, "") when a posting is one the operator could answer honestly, else (False, why).

    An unreadable page is admitted. That is a choice, not an oversight, and it
    is the opposite of what a strict reading of "only tailored to me" would do.
    187 of 532 cached pages are JavaScript shells, and blocking unknown would
    throw out a third of every board watched on no evidence at all. Admitted and
    labelled, so the digest says the bar is unknown and the operator opens the
    link.
    """
    if height == UNREADABLE:
        return True, ""
    if height in BLOCKED_HEIGHTS:
        return False, WALL_LABELS.get(height) or f"wall {height}"
    return True, ""
