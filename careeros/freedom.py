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
# Added 2026-10-12, operator decision. Two of the operator's hard terms had no
# written-evidence score at all. A stated vacation MINIMUM is the good kind of
# time off under the operator's own rule, so it outranks a bare "time off
# stated". Health that actually covers the employee is another term. And an employer whose
# own public handbook or benefits page proves several terms in writing (config
# category "terms-proven employer", each entry audited with quotes and URLs)
# gets credit even when one posting is silent about them.
PTO_MINIMUM_POINTS = 3
HEALTH_COVERED_POINTS = 2
TERMS_PROVEN_POINTS = 3
TERMS_PROVEN_LABEL = "terms-proven employer"

SET_HOURS_PENALTY = -3
ALWAYS_ON_PENALTY = -2
WEEKENDS_PENALTY = -2
UNLIMITED_PTO_PENALTY = -1   # unlimited with no stated minimum often means less
LARGE_EMPLOYER_PENALTY = -1

MAX_SCORE = (ASYNC_POINTS + FLEXIBLE_HOURS_POINTS + FEW_MEETINGS_POINTS
             + ANYWHERE_POINTS + FOUR_DAY_WEEK_POINTS + PTO_STATED_POINTS
             + RESULTS_POINTS + BUILDER_POINTS + NOT_US_LOCKED_POINTS
             + FULLY_REMOTE_POINTS + PTO_MINIMUM_POINTS + HEALTH_COVERED_POINTS
             + TERMS_PROVEN_POINTS)

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
    r"\bwork from (?:any|another) country\b|\banywhere in the world\b", re.I)

# Work-abroad stays: weeks a year working from another country while the job
# stays home-based. Operator term change (2026-10-15): a ranking BONUS, never a gate.
# Tagged separately so the digest says which of the two the posting offers.
_NOMAD = re.compile(
    r"\bdigital nomads?\b|\bnomad[- ]friendly\b|"
    r"\bwork(?:ing)? (?:remotely )?(?:from )?abroad\b|"
    r"\bwork from (?:other|different) countries\b", re.I)
_PTO_STATED = re.compile(
    r"\b(?:\d{1,2}|two|three|four|five|six)\+?\s*(?:weeks?|days?)\s+(?:of\s+)?"
    r"(?:paid\s+)?(?:pto|vacation|time off|holidays?|leave)\b|"
    r"\b(?:pto|vacation|time off)\b[^.]{0,30}\b\d{1,2}\s*(?:weeks|days)\b", re.I)
# "Unlimited PTO with a three-week minimum" (ReadMe) matched nothing here before
# 2026-10-12 and was charged the unlimited-PTO penalty instead.
_NUM = r"(?:\d{1,2}|one|two|three|four|five|six|ten|fifteen|twenty)"
_PTO_MINIMUM = re.compile(
    r"\b" + _NUM + r"[- ](?:weeks?|days?)\s+minimum\b|"
    r"\bminimum (?:of )?" + _NUM + r"[- ]?(?:weeks?|days?)\b|"
    r"\b(?:required|mandatory) (?:minimum )?(?:pto|vacation|time off)\b", re.I)
# A minimum only counts when it is about time off. The first version matched
# "minimum of 16 weeks of parental leave" (Elastic, 404 postings) and "a minimum
# of 3 days a week in office" (Braze) — the opposite of what it means here.
_TIME_OFF_WORD = re.compile(r"\b(?:pto|vacation|time off|holidays?|days off)\b", re.I)
_NOT_TIME_OFF = re.compile(
    r"\b(?:parental|maternity|paternity|family) leave\b|\boffice\b|\bon-?site\b|"
    r"\bin-office\b|\bper week\b|\ba week\b|/week\b|\binternship\b", re.I)


def _says_pto_minimum(text):
    for match in _PTO_MINIMUM.finditer(text or ""):
        window = text[max(0, match.start() - 50):match.end() + 70]
        if _NEGATION.search(text[max(0, match.start() - 30):match.start()]):
            continue
        if _TIME_OFF_WORD.search(window) and not _NOT_TIME_OFF.search(window):
            return True
    return False


_HEALTH_COVERED = re.compile(
    r"\b100\s?% (?:of )?(?:your |employee |the )?(?:health|medical|healthcare|insurance)\b|"
    r"\b100\s?% of [^.]{0,30}\bpremiums?\b|\bcovers? 100\s?%|"
    # Ashby: "all premiums covered by us". Customer.io: "100% coverage of
    # medical, dental, vision, mental health, and supplemental insurance premiums".
    r"\ball (?:of )?(?:the )?premiums (?:are )?(?:covered|paid)\b|"
    r"\b100\s?% coverage of [^.]{0,90}\bpremiums?\b|"
    r"\bfully (?:covered|paid) (?:medical|health)|"
    # FleetWorks wrote "vision benefits - Fully covered lunches and dinners".
    r"\b(?:medical|health)[^.]{0,40}\bfully (?:covered|paid)\b"
    r"(?! (?:lunch|dinner|meal|breakfast|snack))", re.I)
_RESULTS = re.compile(r"\bresults[- ]oriented\b|\boutcome[- ]driven\b", re.I)
_FULLY_REMOTE = re.compile(r"\bfully (?:remote|distributed)\b|\bremote[- ]first\b|\ball[- ]remote\b", re.I)
_SET_HOURS = re.compile(
    r"\bcore (?:working )?hours\b|\bbusiness hours\b|"
    r"\bworking (?:in )?(?:the )?(?:est|edt|pst|pdt|et|pt|cst|eastern|pacific|central)\b|"
    r"\b9\s*(?:am)?\s*(?:-|–|to)\s*5\s*(?:pm)?\b|\bnine[- ]to[- ]five\b", re.I)
_ALWAYS_ON = re.compile(r"\balways[- ]on\b|\bhustle\b", re.I)
_WEEKENDS = re.compile(r"\bweekends?\b|\bovertime\b", re.I)
# "not a traditional 9-to-5" and "no core hours" are freedom, not its opposite.
_NEGATION = re.compile(r"\b(?:not|no|never|isn'?t|cannot|can'?t|unable to|without|beyond)\b[^.]{0,20}$", re.I)


def _says(pattern, text):
    """True when the posting writes the phrase, not when it writes it negated."""
    for match in pattern.finditer(text or ""):
        if not _NEGATION.search(text[max(0, match.start() - 30):match.start()]):
            return True
    return False


def score(geo_class, tz_friendly, tz_soft, green, text="",
          fit_label="", large_employer=False, terms_proven=False):
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
    elif _says(_NOMAD, text):
        add(ANYWHERE_POINTS, "nomad-friendly")
    if "4-day week" in green:
        add(FOUR_DAY_WEEK_POINTS, "4-day week")
    pto_minimum = _says_pto_minimum(text)
    pto_stated = pto_minimum or "real time off" in green or _says(_PTO_STATED, text)
    if pto_minimum:
        add(PTO_MINIMUM_POINTS, "time off minimum")
    elif pto_stated:
        add(PTO_STATED_POINTS, "time off stated")
    if _says(_HEALTH_COVERED, text):
        add(HEALTH_COVERED_POINTS, "health fully covered")
    if terms_proven:
        add(TERMS_PROVEN_POINTS, TERMS_PROVEN_LABEL)
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
