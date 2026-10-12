"""
Salary estimation for postings that do not publish a range.

Roughly 60% of listings state no pay. Dropping them silently was gutting the
search, so this module estimates a band from the job title, seniority markers,
and employment type.

Three rules govern everything here:

1. An estimate is never presented as a fact. Everything it returns carries
   confidence="estimated", which caps the listing at B-tier forever and prints
   with a "~" and an explicit label.
2. When the role family is unrecognisable, it returns UNKNOWN rather than
   guessing from nothing. A wrong number is worse than no number.
3. The bands below are MY market estimates for US remote roles, not measured
   data. They are written down so they can be argued with and corrected, and
   they should be revisited as real offers come in.
"""

import re

import salary as salary_mod

# US fully-remote annual USD bands, 2026, for a mid-level holder of the role.
# (low, high). Seniority modifiers are applied on top.
ROLE_BANDS = [
    # --- customer-facing technical: the operator's strongest lane ---
    (r"\bsolutions?\s+(?:engineer|architect|consultant)\b", (95_000, 155_000)),
    (r"\bforward[- ]deployed\b", (120_000, 200_000)),
    (r"\bsales\s+engineer\b|\bpre[- ]?sales\b", (95_000, 150_000)),
    (r"\btechnical\s+account\s+manager\b", (85_000, 135_000)),
    (r"\b(?:implementation|onboarding)\s+(?:specialist|manager|consultant|engineer)\b", (65_000, 110_000)),
    (r"\bcustomer\s+success\b", (60_000, 115_000)),
    (r"\bsupport\s+engineer\b|\btechnical\s+support\b", (65_000, 110_000)),
    (r"\bdeveloper\s+(?:advocate|relations)\b|\bdevrel\b", (90_000, 150_000)),
    (r"\bdeveloper\s+experience\b", (95_000, 155_000)),

    # --- engineering ---
    (r"\b(?:machine\s+learning|ml|ai)\s+engineer\b", (110_000, 190_000)),
    (r"\bdata\s+(?:engineer|scientist)\b", (100_000, 175_000)),
    (r"\b(?:software|backend|frontend|full[- ]?stack|platform|infrastructure)\s+engineer\b", (95_000, 175_000)),
    (r"\b(?:devops|site\s+reliability|sre|cloud)\s+engineer\b", (105_000, 180_000)),
    (r"\bsecurity\s+engineer\b", (110_000, 185_000)),
    (r"\bmobile\s+(?:engineer|developer)\b|\bios\b|\bandroid\s+developer\b", (95_000, 170_000)),
    (r"\b(?:web|wordpress|shopify)\s+developer\b", (60_000, 110_000)),
    (r"\bqa\b|\bquality\s+assurance\b|\btest\s+engineer\b", (65_000, 115_000)),
    (r"\bengineer(?:ing)?\b|\bdeveloper\b|\bprogrammer\b", (85_000, 155_000)),

    # --- design ---
    (r"\b(?:product|ux|ui|experience)\s+designer\b", (85_000, 145_000)),
    (r"\bgraphic\s+designer\b|\bvisual\s+designer\b", (45_000, 85_000)),
    (r"\bdesigner\b", (70_000, 125_000)),

    # --- product, project, ops ---
    (r"\bproduct\s+manager\b", (95_000, 165_000)),
    (r"\b(?:project|program|delivery)\s+manager\b", (70_000, 125_000)),
    (r"\b(?:operations|ops|business\s+operations)\b", (65_000, 120_000)),
    (r"\bchief\s+of\s+staff\b", (95_000, 165_000)),

    # --- go-to-market ---
    (r"\b(?:account\s+executive|sales\s+(?:rep|representative|manager))\b", (60_000, 120_000)),
    (r"\b(?:sdr|bdr|business\s+development)\b", (45_000, 85_000)),
    (r"\bgrowth\s+(?:marketer|manager|lead)\b", (75_000, 135_000)),
    (r"\b(?:marketing|demand\s+gen)\b", (60_000, 120_000)),
    (r"\b(?:content|copy)\s*(?:writer|strategist|marketer)?\b", (50_000, 100_000)),
    (r"\b(?:seo|social\s+media)\b", (50_000, 95_000)),

    # --- business functions ---
    (r"\b(?:accountant|accounting|bookkeep)", (55_000, 105_000)),
    (r"\b(?:finance|financial\s+analyst|fp&a)\b", (70_000, 135_000)),
    (r"\b(?:recruiter|talent|people\s+ops|human\s+resources|hr)\b", (60_000, 110_000)),
    (r"\blegal\b|\bparalegal\b|\bcounsel\b", (65_000, 145_000)),

    # --- lower bands: these mostly get filtered out, and should ---
    (r"\bcustomer\s+(?:service|support)\s+(?:rep|representative|agent|associate)\b", (40_000, 70_000)),
    (r"\b(?:virtual\s+assistant|executive\s+assistant|admin)\b", (35_000, 70_000)),
    (r"\b(?:data\s+entry|annotation|transcription|moderator)\b", (25_000, 55_000)),
]

SENIORITY = [
    (r"\b(?:chief|vp|vice\s+president|head\s+of|director)\b", 1.70, "director+"),
    (r"\b(?:staff|principal|lead)\b", 1.40, "staff/lead"),
    (r"\b(?:senior|sr\.?|snr)\b", 1.25, "senior"),
    (r"\b(?:junior|jr\.?|entry[- ]level|associate|assistant|intern|graduate|trainee)\b", 0.75, "junior"),
]

PART_TIME = re.compile(r"\bpart[- ]?time\b|\bcontract\b|\bfreelance\b", re.I)

_ROLE_RES = [(re.compile(p, re.I), band) for p, band in ROLE_BANDS]
_SENIORITY_RES = [(re.compile(p, re.I), mult, label) for p, mult, label in SENIORITY]


MULTI_ROLE_SEPARATORS = re.compile(r",|\band\b|/|\+")


def _is_multi_role(title):
    """
    True when a posting advertises several distinct roles at once.

    Estimating across "Site Lead, Sr Engineers, Security Engineer, PM, Data
    Engineer" averages unrelated bands into a range so wide it means nothing.
    Better to decline and let it fall through to the unpriced bucket.
    """
    matches = sum(1 for pattern, _ in _ROLE_RES if pattern.search(title))
    separators = len(MULTI_ROLE_SEPARATORS.findall(title))
    return matches >= 2 and separators >= 2


def estimate(title, description="", job_type=""):
    """
    Estimate an annual USD band from the title.

    Returns (Salary, explanation). The Salary carries confidence="estimated",
    or is UNKNOWN when no role family matched.
    """
    text = f"{title or ''}"
    if not text.strip():
        return salary_mod.UNKNOWN, "no title"

    if _is_multi_role(text):
        return salary_mod.UNKNOWN, "multiple roles in one posting"

    band = None
    matched = None
    for pattern, role_band in _ROLE_RES:
        if pattern.search(text):
            band = role_band
            matched = pattern.pattern
            break

    if band is None:
        return salary_mod.UNKNOWN, "role family not recognised"

    low, high = band
    multiplier = 1.0
    seniority_label = "mid"
    # Most specific seniority marker wins; the list is ordered senior-first.
    for pattern, mult, label in _SENIORITY_RES:
        if pattern.search(text):
            multiplier = mult
            seniority_label = label
            break

    low = low * multiplier
    high = high * multiplier

    # Part-time and contract postings state a full-time-equivalent rate far
    # less often than they state a reduced one. Widening the band downward
    # keeps the estimate honest rather than optimistic.
    combined = f"{job_type} {description[:500]}"
    if PART_TIME.search(combined) or PART_TIME.search(text):
        low = low * 0.55
        high = high * 0.70
        seniority_label += ", part-time/contract"

    # Report the central portion of the band. The raw band spans the whole
    # spread of a role family; a ~$60k-wide guess is not actionable.
    spread = high - low
    low = low + spread * 0.20
    high = high - spread * 0.20

    estimated = salary_mod.Salary(
        low=round(low, -2), high=round(high, -2),
        currency="USD", period="year",
        confidence="estimated",
        raw=f"estimated from title: {title[:80]}",
    )
    return estimated, f"{seniority_label} band for matched role family"


def clears_bar(estimated, floor=70_000):
    """
    An estimate clears the bar only if its MIDPOINT does.

    Testing the top of an estimated band would let almost anything through —
    a wide guess would always have a high end above the floor. The midpoint is
    the honest test of whether the role typically pays enough.
    """
    if estimated is None or estimated.low is None or estimated.high is None:
        return False
    midpoint = (estimated.low + estimated.high) / 2
    return midpoint >= floor
