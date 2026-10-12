"""
Portability scoring — how well a job wraps around a life.

The operator's own framing: this search optimises for how a job fits a life,
not for career maximisation. v1 ranked by tier and salary, which inverted
that: a $186k role demanding US-hours overlap outranked a $110k async role that
could be done from anywhere.

Measured on the 2026-08-15 archive, the work-from-anywhere pool was both larger
(133 vs 101 listings) and better paid (median published ceiling $63,500 vs
$50,024) than the US-only pool. Portability is not a tax on income here — it is
the thing worth optimising, so it becomes the primary sort key.

Deliberately a small integer, not a weighted model. Each plus point is a phrase
the posting actually wrote; nothing is inferred from what it leaves out.
"""

import re

import geo

# Rebuilt 2026-10-05 as a scorecard of WRITTEN evidence, freedom first, on the
# operator's instruction. The old score paid 2 points for the
# ABSENCE of a time-zone clause and printed it as "no fixed hours", so silence
# read as a promise. Nothing here scores silence any more: every plus point is
# a phrase the posting actually wrote.
#
# The operator's order, from the same session: remote from home, then async or flexible
# hours, then work-abroad weeks, then judged on results, then real PTO, then a
# small company. The weights follow that order.
ASYNC_POINTS = 4
FLEXIBLE_HOURS_POINTS = 4
FEW_MEETINGS_POINTS = 3
ANYWHERE_POINTS = 3
FOUR_DAY_WEEK_POINTS = 3
PTO_STATED_POINTS = 2
RESULTS_POINTS = 2
BUILDER_POINTS = 2
NOT_US_LOCKED_POINTS = 2
FULLY_REMOTE_POINTS = 1

SET_HOURS_PENALTY = -3
ALWAYS_ON_PENALTY = -2
WEEKENDS_PENALTY = -2
UNLIMITED_PTO_PENALTY = -1   # unlimited with no stated minimum often means less
LARGE_EMPLOYER_PENALTY = -1

MAX_SCORE = (ASYNC_POINTS + FLEXIBLE_HOURS_POINTS + FEW_MEETINGS_POINTS
             + ANYWHERE_POINTS + FOUR_DAY_WEEK_POINTS + PTO_STATED_POINTS
             + RESULTS_POINTS + BUILDER_POINTS + NOT_US_LOCKED_POINTS
             + FULLY_REMOTE_POINTS)

# Labels geo.TIMEZONE_FRIENDLY and prefilter.GREEN_FLAGS already extract. Matched
# by label so the modules cannot drift apart on wording.
FLEXIBLE_LABELS = ("no fixed hours", "flexible hours", "own schedule")
BUILDER_LABELS = ("AI builder", "creative technologist")

_ASYNC = re.compile(r"\basync(?:hronous)?\b", re.I)
_FLEXIBLE = re.compile(
    r"\bflexible (?:working )?(?:hours|schedules?)\b|\bset your own (?:hours|schedule)\b|"
    r"\bown your schedule\b|\bno (?:fixed|set|core) (?:hours|schedule)\b|"
    r"\bwork when you want\b", re.I)
_FEW_MEETINGS = re.compile(
    r"\b(?:no|few|fewer|minimal) meetings\b|\bmeeting[- ]free\b|\bno (?:daily )?stand-?ups?\b",
    re.I)
_ANYWHERE = re.compile(
    r"\bwork from anywhere\b|\bwork(?:ing)? from abroad\b|\bworkation\b|"
    r"\bwork from (?:any|another) country\b", re.I)
_PTO_STATED = re.compile(
    r"\b(?:\d{1,2}|two|three|four|five|six)\+?\s*(?:weeks?|days?)\s+(?:of\s+)?"
    r"(?:paid\s+)?(?:pto|vacation|time off|holidays?|leave)\b|"
    r"\b(?:pto|vacation|time off)\b[^.]{0,30}\b\d{1,2}\s*(?:weeks|days)\b", re.I)
_RESULTS = re.compile(r"\bresults[- ]oriented\b|\boutcome[- ]driven\b", re.I)
_FULLY_REMOTE = re.compile(r"\bfully (?:remote|distributed)\b|\bremote[- ]first\b|\ball[- ]remote\b", re.I)
_SET_HOURS = re.compile(
    r"\bcore (?:working )?hours\b|\bbusiness hours\b|"
    r"\bworking (?:in )?(?:the )?(?:est|edt|pst|pdt|et|pt|cst|eastern|pacific|central)\b|"
    r"\b9\s*(?:am)?\s*(?:-|–|to)\s*5\s*(?:pm)?\b|\bnine[- ]to[- ]five\b", re.I)
_ALWAYS_ON = re.compile(r"\balways[- ]on\b|\bhustle\b", re.I)
_WEEKENDS = re.compile(r"\bweekends?\b|\bovertime\b", re.I)
# "not a traditional 9-to-5" and "no core hours" are freedom, not its opposite.
_NEGATION = re.compile(r"\b(?:not|no|never|isn'?t|without|beyond)\b[^.]{0,20}$", re.I)


def _says(pattern, text):
    """True when the posting writes the phrase, not when it writes it negated."""
    for match in pattern.finditer(text or ""):
        if not _NEGATION.search(text[max(0, match.start() - 30):match.start()]):
            return True
    return False


def score(geo_class, tz_friendly, tz_soft, green, text="",
          fit_label="", large_employer=False):
    """
    Return (points, reasons).

    `reasons` is the human-readable breakdown the digest prints, strongest
    first, so the operator can see why one job ranked above another rather than
    trusting a number. Minus reasons are printed too: a posting that writes
    "business hours" should say so on its line.
    """
    points = 0
    reasons = []

    def add(value, label):
        nonlocal points
        points += value
        reasons.append(label)

    if "async" in tz_friendly or "async" in green or _says(_ASYNC, text):
        add(ASYNC_POINTS, "async")
    if (any(label in tz_friendly or label in green for label in FLEXIBLE_LABELS)
            or _says(_FLEXIBLE, text)):
        add(FLEXIBLE_HOURS_POINTS, "flexible hours")
    if "no standups" in tz_friendly or _says(_FEW_MEETINGS, text):
        add(FEW_MEETINGS_POINTS, "few meetings")
    if geo_class == geo.CLASS_ANYWHERE or _says(_ANYWHERE, text):
        add(ANYWHERE_POINTS, "work from anywhere")
    if "4-day week" in green:
        add(FOUR_DAY_WEEK_POINTS, "4-day week")
    pto_stated = "real time off" in green or _says(_PTO_STATED, text)
    if pto_stated:
        add(PTO_STATED_POINTS, "time off stated")
    if ("results-oriented" in green or "results-oriented" in tz_friendly
            or _says(_RESULTS, text)):
        add(RESULTS_POINTS, "results-oriented")
    if fit_label in BUILDER_LABELS:
        add(BUILDER_POINTS, "builder role")
    if geo_class == geo.CLASS_ANYWHERE:
        add(NOT_US_LOCKED_POINTS, "not US-locked")
    if "fully distributed" in green or _says(_FULLY_REMOTE, text):
        add(FULLY_REMOTE_POINTS, "fully remote")

    if tz_soft or _says(_SET_HOURS, text):
        add(SET_HOURS_PENALTY, "set hours")
    if _says(_ALWAYS_ON, text):
        add(ALWAYS_ON_PENALTY, "always-on")
    if _says(_WEEKENDS, text):
        add(WEEKENDS_PENALTY, "weekends or overtime")
    if "unlimited PTO" in green and not pto_stated:
        add(UNLIMITED_PTO_PENALTY, "unlimited PTO, no minimum")
    if large_employer:
        add(LARGE_EMPLOYER_PENALTY, "large employer")

    return points, reasons


def is_portable(geo_class, tz_hard):
    """
    The hard gate for the main digest lane.

    Rewritten 2026-09-28. It used to read:

        return geo_class == geo.CLASS_ANYWHERE and not tz_hard

    with a note holding US-only roles out of the main lane, because the
    operator's plan at the time was to live outside the US, where a role
    requiring US residence would break it.

    The plan changed: the operator is now US-based, so "requires US residence"
    is a requirement simply met. The gate was quietly demoting most of the
    market over a constraint that had been dropped.

    Region-locked roles are still rejected upstream and shift work and on-call
    are still hard exclusions — those were never about the move. What remains is
    only: can the operator legally do this job, and does it wreck their week.
    """
    return geo_class in (geo.CLASS_ANYWHERE, geo.CLASS_US) and not tz_hard
