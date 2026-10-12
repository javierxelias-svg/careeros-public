"""
Salary parsing and normalization.

Job postings state pay in every format humans invented: "$70,000 - $90,000",
"70k-90k USD", "$45/hour", "€60.000", "Pay per task", or nothing at all. This
module turns that into a comparable annual USD range, or admits it cannot.

Design rule from the plan (Section 1a): a parsed salary and an absent salary
are different things, and the difference must survive downstream. A listing
whose salary we guessed can never outrank one whose salary was published, so
`confidence` travels with the numbers.

Second rule, added 2026-08-18: a published number and a GUARANTEED number are
also different things. PostHog's Technical CSM posting advertises $237,375 —
an 80/20 on-target figure whose last fifth arrives only if customer-retention
targets are met. Read as salary that overstated the job by roughly $20,000 and
put it top of the digest. So `basis` travels with the numbers too, and `top` —
the number every gate and every ranking is tested against — means the
guaranteed base, never the advertised total.
"""

import json
import re
from pathlib import Path

HOURS_PER_YEAR = 2080  # 40h x 52w, the US full-time convention
WEEKS_PER_YEAR = 52
MONTHS_PER_YEAR = 12
DAYS_PER_YEAR = 260  # working days

# Currency symbols and codes we can convert. Rates live in config/fx-rates.json.
CURRENCY_SYMBOLS = {
    "$": "USD",
    "US$": "USD",
    "usd": "USD",
    "€": "EUR",
    "eur": "EUR",
    "£": "GBP",
    "gbp": "GBP",
    "c$": "CAD",
    "cad": "CAD",
    "a$": "AUD",
    "aud": "AUD",
}

# Ordered longest-first so "US$" wins over "$".
_SYMBOL_PATTERN = "|".join(
    re.escape(s) for s in sorted(CURRENCY_SYMBOLS, key=len, reverse=True)
)

# A number that may carry thousands separators and a k/K suffix.
_NUM = r"(\d[\d.,]*\s*[kK]?)"

RANGE_RE = re.compile(
    rf"(?P<cur1>{_SYMBOL_PATTERN})?\s*{_NUM}\s*(?:-|–|—|to|\.\.\.?)\s*"
    rf"(?P<cur2>{_SYMBOL_PATTERN})?\s*{_NUM}",
    re.IGNORECASE,
)
SINGLE_RE = re.compile(rf"(?P<cur>{_SYMBOL_PATTERN})\s*{_NUM}", re.IGNORECASE)

PERIOD_PATTERNS = [
    (re.compile(r"\b(per\s+hour|/\s*h(ou)?r\b|hourly|an hour|/hr)\b", re.I), "hour"),
    (re.compile(r"\b(per\s+day|/\s*day\b|daily|day rate)\b", re.I), "day"),
    (re.compile(r"\b(per\s+week|/\s*w(ee)?k\b|weekly)\b", re.I), "week"),
    (re.compile(r"\b(per\s+month|/\s*mo(nth)?\b|monthly|a month)\b", re.I), "month"),
    (re.compile(r"\b(per\s+year|/\s*y(ea)?r\b|annually|annual|per annum|a year)\b", re.I), "year"),
]

PERIOD_MULTIPLIER = {
    "hour": HOURS_PER_YEAR,
    "day": DAYS_PER_YEAR,
    "week": WEEKS_PER_YEAR,
    "month": MONTHS_PER_YEAR,
    "year": 1,
}

# Strings that look like pay information but carry no number we can use.
UNUSABLE_MARKERS = re.compile(
    r"\b(pay per task|competitive|doe|depending on experience|negotiable|tbd|"
    r"based on experience|market rate|equity only|unpaid|volunteer)\b",
    re.I,
)

# Guards against parsing years, headcounts, and equity percentages as money.
_YEAR_LIKE = re.compile(r"\b(19|20)\d{2}\b")
_MIN_PLAUSIBLE_ANNUAL = 8_000
# Capped well below "technically possible" on purpose. Against a $70k–$100k
# target, a parsed $900k is far more likely to be a misread hourly rate than a
# real offer, and a wrong number that looks exciting is worse than no number.
_MAX_PLAUSIBLE_ANNUAL = 500_000
# A range whose ends differ by more than this is not a range, it is a parse
# accident (two unrelated figures in the same sentence).
_MAX_RANGE_RATIO = 20

# Company money, written the way company money is written. A figure carrying a
# millions or billions suffix is funding, valuation or revenue — never a wage —
# and the suffix letter sits OUTSIDE the number group, so without this the "M"
# is silently discarded and the digits are read on their own.
#
# This published a fabricated salary. LangChain's About Us blurb says "With
# $125M raised at Series B"; SINGLE_RE matched "$125", the M was dropped,
# _infer_period() saw 125 <= 500 and called it hourly, and 125 x 2080 came out
# as $260,000 stamped confidence="published". Nine LangChain postings carried
# that same invented number into the digest on 2026-08-17, including three SDR
# roles with no published pay at all.
_MAGNITUDE_MONEY = re.compile(
    rf"(?:{_SYMBOL_PATTERN})?\s*\d[\d.,]*\s*(?:[MmBb]\b|million|billion)",
    re.IGNORECASE,
)

# Prose about the company, not about the job's pay. RANGE_RE takes its currency
# symbols as optional, so an unguarded sentence like "we grew from 10 to 50
# people" parses as a $104,000 hourly-inferred band. A clause making a claim
# about funding, growth or customers is refused outright rather than mined for
# a number — the same discipline enrich.find_salary() applies to estimate
# language.
_NOT_PAY_CONTEXT = re.compile(
    r"\b(raised|raising|funding|funded|backed by|valuation|valued at|"
    r"series\s+[a-e]\b|seed round|arr\b|revenue|run rate|"
    r"customers|users|downloads|employees|headcount|team of|fortune\s*\d)\b",
    re.IGNORECASE,
)


# --- Base vs on-target earnings ---------------------------------------------
#
# A posting quoting OTE is quoting base + variable. The variable half is
# conditional on hitting targets, so it is not income anyone can plan a life on and
# it must not compete with a guaranteed number on the same axis.

# What a posting says when its figure is a total rather than a base. Deliberately
# narrow: every entry here discounts a real published number, so a false positive
# is expensive. "base + variable" is included because the phrase describes the
# package the quoted range covers, not a base with something extra bolted on.
OTE_MARKER = re.compile(
    r"\b(?:ote|o\.t\.e\.|on[-\s]?target\s+(?:earnings|compensation|comp)|"
    r"total\s+target\s+(?:cash\s+)?comp(?:ensation)?|"
    r"base\s*(?:\+|plus|and)\s*(?:variable|commission|bonus|incentive)|"
    r"salary\s*(?:\+|plus)\s*commission)\b",
    re.IGNORECASE,
)

# "Base salary: $100,000 plus commission" quotes a BASE, not a total — the
# whole $100,000 is guaranteed and discounting it would understate the job by
# as much as reading OTE as base overstates one. A base word standing directly
# in front of the figure therefore wins over any OTE word elsewhere in the text.
#
# The generous vocabulary is not decoration. A posting frozen from
# WeWorkRemotely on 2026-08-19 states both numbers in one sentence — "the base
# wage range for this position is targeted at $137,000-$177,000 and competitive
# On-Target Earnings ... of $210,800-$272,000" — and an anchor list missing
# "wage" discounted the base by 20% on the strength of the OTE clause after it,
# understating a real posting by about $35,000.
_BASE_ANCHOR = re.compile(
    r"\bbase\s+(?:salary|salaries|pay|wage|compensation|comp|rate|range|band|of)\b",
    re.IGNORECASE,
)
_BASE_ANCHOR_WINDOW = 60  # characters of lead-in that count as "directly before"

# The split, when the posting states it: "80/20", "20% variable", "80% base".
_SPLIT_RATIO = re.compile(r"\b(\d{2})\s*/\s*(\d{2})\b")
_VARIABLE_PCT = re.compile(
    r"\b(\d{1,2})\s*%\s*(?:\w+\s+){0,2}?(?:variable|commission|bonus|incentive)\b",
    re.IGNORECASE,
)
_BASE_PCT = re.compile(
    r"\b(\d{1,2})\s*%\s*(?:\w+\s+){0,2}?(?:base|fixed)\b", re.IGNORECASE
)

# When a posting says OTE but not the split. 80/20 is the modal split for the
# customer-facing roles in this search and is what PostHog publishes. It is an
# assumption, it is marked as one in `split_stated`, and the digest prints "ask
# the split" so the number gets confirmed on the first call rather than trusted.
DEFAULT_VARIABLE_SHARE = 0.20
_MIN_VARIABLE_SHARE = 0.05
_MAX_VARIABLE_SHARE = 0.60


def variable_share(text):
    """
    (share_of_total_that_is_variable, stated_by_the_posting).

    Falls back to DEFAULT_VARIABLE_SHARE rather than refusing, because "OTE with
    no split published" is the common case and a discounted estimate is closer
    to the truth than treating the total as guaranteed.
    """
    if isinstance(text, str) and text:
        match = _SPLIT_RATIO.search(text)
        if match:
            first, second = int(match.group(1)), int(match.group(2))
            # Sum-to-100 is the guard that stops a date or a version number
            # ("10/20", "9/11") being read as a compensation split.
            if first + second == 100:
                share = min(first, second) / 100.0
                if _MIN_VARIABLE_SHARE <= share <= _MAX_VARIABLE_SHARE:
                    return share, True

        match = _VARIABLE_PCT.search(text)
        if match:
            share = int(match.group(1)) / 100.0
            if _MIN_VARIABLE_SHARE <= share <= _MAX_VARIABLE_SHARE:
                return share, True

        match = _BASE_PCT.search(text)
        if match:
            share = 1.0 - int(match.group(1)) / 100.0
            if _MIN_VARIABLE_SHARE <= share <= _MAX_VARIABLE_SHARE:
                return share, True

    return DEFAULT_VARIABLE_SHARE, False


def detect_basis(text, figure_start=None):
    """
    Whether a quoted figure is base pay or an on-target total.

    Returns (basis, variable_share, split_stated) where basis is "base" or
    "ote". `figure_start` is the offset of the figure inside `text`; without it
    the base-anchor check reads the whole string, which is what a caller holding
    only a structured pay field (no surrounding prose) wants.
    """
    if not isinstance(text, str) or not text:
        return "base", 0.0, False

    lead = text if figure_start is None else text[max(0, figure_start - _BASE_ANCHOR_WINDOW):figure_start]
    if _BASE_ANCHOR.search(lead):
        return "base", 0.0, False

    if not OTE_MARKER.search(text):
        return "base", 0.0, False

    share, stated = variable_share(text)
    return "ote", share, stated


class Salary:
    """A normalized annual USD salary range."""

    __slots__ = ("low", "high", "currency", "period", "confidence", "raw",
                 "converted", "basis", "variable_share", "split_stated")

    def __init__(self, low, high, currency="USD", period="year",
                 confidence="published", raw="", converted=False,
                 basis="base", variable_share=0.0, split_stated=False):
        self.low = low
        self.high = high
        self.currency = currency
        self.period = period
        self.confidence = confidence  # "published" | "estimated" | "unknown"
        self.raw = raw
        self.converted = converted
        self.basis = basis  # "base" | "ote"
        self.variable_share = variable_share  # fraction of the total that is at risk
        self.split_stated = split_stated  # did the posting publish the split?

    @property
    def is_ote(self):
        return self.basis == "ote" and self.variable_share > 0

    @property
    def advertised_top(self):
        """The top of the range as the posting wrote it, at risk included."""
        return self.high if self.high is not None else self.low

    def _guaranteed(self, value):
        if value is None:
            return None
        return value * (1 - self.variable_share) if self.is_ote else value

    @property
    def base_low(self):
        return self._guaranteed(self.low)

    @property
    def base_high(self):
        return self._guaranteed(self.high)

    @property
    def at_risk(self):
        """Dollars of the advertised top that are conditional, or 0."""
        top = self.advertised_top
        if top is None or not self.is_ote:
            return 0
        return top - self._guaranteed(top)

    @property
    def top(self):
        """
        The number the pay bar is tested against — GUARANTEED base, always.

        Every gate and every ranking reads this property, so defining it as base
        is what makes "rank on base, not OTE" true everywhere at once instead of
        at each call site that remembers to.
        """
        return self._guaranteed(self.advertised_top)

    def as_dict(self):
        return {
            "low": self.low,
            "high": self.high,
            "base_low": self.base_low,
            "base_high": self.base_high,
            "basis": self.basis,
            "variable_share": self.variable_share,
            "split_stated": self.split_stated,
            "currency": self.currency,
            "confidence": self.confidence,
            "converted": self.converted,
            "raw": self.raw[:200],
        }

    @staticmethod
    def _band(low, high, prefix=""):
        if high and low and high != low:
            return f"{prefix}${low:,.0f}–${high:,.0f}"
        return f"{prefix}${(high or low):,.0f}"

    def display(self):
        if self.low is None and self.high is None:
            return "salary not stated"
        prefix = "~" if self.confidence == "estimated" else ""

        if self.is_ote:
            # Base first, because base is the number a life gets planned around, and
            # the advertised total second so the posting is still recognisable.
            split = f"{100 - self.variable_share * 100:.0f}/{self.variable_share * 100:.0f}"
            text = f"~{self._band(self.base_low, self.base_high)} base"
            text += f" ({'' if self.split_stated else 'assumed '}{split}"
            text += f" of {self._band(self.low, self.high)} OTE"
            text += ")" if self.split_stated else " — ask the split)"
        else:
            text = self._band(self.low, self.high, prefix)

        if self.converted:
            text += f" (from {self.currency})"
        return text

    def __repr__(self):
        return f"<Salary {self.display()} {self.confidence}>"


UNKNOWN = Salary(None, None, confidence="unknown")


def _load_fx(fx_path=None):
    """Conversion rates to USD. Missing file means USD-only parsing."""
    if fx_path is None:
        fx_path = Path(__file__).resolve().parent.parent / "config" / "fx-rates.json"
    try:
        data = json.loads(Path(fx_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"USD": 1.0}
    rates = data.get("to_usd")
    if not isinstance(rates, dict):
        return {"USD": 1.0}
    rates["USD"] = 1.0
    return rates


_FX_CACHE = None


def fx_rates():
    global _FX_CACHE
    if _FX_CACHE is None:
        _FX_CACHE = _load_fx()
    return _FX_CACHE


def _to_number(token):
    """'70k' -> 70000, '70,000' -> 70000, '60.000' -> 60000 (European grouping)."""
    if not token:
        return None
    token = token.strip()
    multiplier = 1
    if token[-1] in "kK":
        multiplier = 1000
        token = token[:-1].strip()

    # Distinguish a decimal point from European thousands grouping: '60.000' is
    # sixty thousand, '60.5' is sixty point five.
    if "," in token and "." in token:
        # Whichever separator comes last is the decimal one.
        token = (token.replace(",", "")
                 if token.rfind(".") > token.rfind(",")
                 else token.replace(".", "").replace(",", "."))
    elif "," in token:
        token = token.replace(",", "") if re.search(r",\d{3}\b", token) else token.replace(",", ".")
    elif "." in token:
        if re.search(r"\.\d{3}\b", token):
            token = token.replace(".", "")

    try:
        return float(token) * multiplier
    except ValueError:
        return None


def _detect_period(text):
    for pattern, period in PERIOD_PATTERNS:
        if pattern.search(text):
            return period
    return None


_CLAUSE_BOUNDARY = re.compile(r"[|;\n,]")


def _clause_around(text, start, end):
    """
    The clause containing a matched figure.

    A period word describes the number standing next to it, not every number in
    the blob. A Hacker News post reading "Full-Time $80k-$120k + equity, or
    Contract $50-$150/hr" put "/hr" thirty characters after an ANNUAL band; read
    globally that made it $80k an hour, which blew through the plausibility
    ceiling, so a posting that stated its pay in plain text was delivered to the
    operator as "pay not stated — ask before applying".

    When the text has no clause boundaries this returns the whole string, so
    single-clause parsing is bit-for-bit unchanged.
    """
    head, tail = text[:start], text[end:]
    left = max((m.end() for m in _CLAUSE_BOUNDARY.finditer(head)), default=0)
    boundary = _CLAUSE_BOUNDARY.search(tail)
    right = end + (boundary.start() if boundary else len(tail))
    return text[left:right]


def _detect_currency(*candidates):
    for candidate in candidates:
        if candidate:
            code = CURRENCY_SYMBOLS.get(candidate.strip().lower())
            if code:
                return code
    return None


def _infer_period(low, high, explicit, allow_hourly=True):
    """
    When the posting does not say, infer from magnitude.

    A '45' with no period is an hourly rate; a '90000' is annual. The bands
    below are deliberately wide — a wrong guess here is worse than no guess,
    so anything ambiguous returns None and the caller treats it as unusable.

    `allow_hourly` is False when the text is prose rather than a dedicated pay
    field. Guessing "hourly" from a small number is safe in a salary field and
    reckless in a paragraph, because a paragraph is full of small numbers that
    are not wages. Every fabricated salary found on 2026-08-17 came through
    this branch: 125 ("$125M raised") became $260,000, 148 became $307,840, and
    4 — read out of an HTML class name — became $8,320. The x2080 multiplier
    turns any small integer into a plausible-looking annual salary.

    The annual inference stays on in prose: a number at or above 12,000 next to
    a pay word is a salary in every posting format we have seen.
    """
    if explicit:
        return explicit
    value = high or low
    if value is None:
        return None
    if value <= 500:
        return "hour" if allow_hourly else None
    if value >= 12_000:
        return "year"
    return None  # 500–12,000 is genuinely ambiguous: monthly? weekly? refuse.


def parse(text, currency_hint=None, allow_hourly_inference=True):
    """
    Parse a salary string into an annualized USD Salary, or UNKNOWN.

    `currency_hint` is used when the posting states a currency in a separate
    field rather than inline.
    """
    if not isinstance(text, str) or not text.strip():
        return UNKNOWN

    raw = text.strip()
    cleaned = _YEAR_LIKE.sub(" ", raw)
    # Blank funding and valuation figures before any number is read, so they
    # cannot be mistaken for a wage by a later stage.
    cleaned = _MAGNITUDE_MONEY.sub(" ", cleaned)

    if UNUSABLE_MARKERS.search(cleaned) and not re.search(r"\d", cleaned):
        return Salary(None, None, confidence="unknown", raw=raw)

    currency = None
    low = high = None

    match = RANGE_RE.search(cleaned)
    if match:
        low = _to_number(match.group(2))
        high = _to_number(match.group(4))
        currency = _detect_currency(match.group("cur1"), match.group("cur2"), currency_hint)
    else:
        match = SINGLE_RE.search(cleaned)
        if match:
            low = high = _to_number(match.group(2))
            currency = _detect_currency(match.group("cur"), currency_hint)

    if low is None and high is None:
        return Salary(None, None, confidence="unknown", raw=raw)

    # Read the period from the clause holding the figure, not the whole blob.
    # Where the clause is silent, _infer_period() decides on magnitude, which is
    # safer than borrowing a period word from a different pay package.
    clause = _clause_around(cleaned, match.start(), match.end())
    # A figure sitting in a sentence about the company is not the job's pay.
    if _NOT_PAY_CONTEXT.search(clause):
        return Salary(None, None, confidence="unknown", raw=raw)

    period = _detect_period(clause)

    if low is not None and high is not None and low > high:
        low, high = high, low

    # "$70 - $120,000" and "$160–$220,000" are how humans write "70k to 120k".
    # The low end dropped its thousands marker; restore it rather than reading
    # the posting as paying seventy dollars a year.
    if (low is not None and high is not None and low > 0
            and high / low > 50 and low < 1000):
        low *= 1000

    period = _infer_period(low, high, period, allow_hourly_inference)
    if period is None:
        return Salary(None, None, confidence="unknown", raw=raw)

    multiplier = PERIOD_MULTIPLIER[period]
    low = low * multiplier if low is not None else None
    high = high * multiplier if high is not None else None

    currency = currency or "USD"
    converted = False
    if currency != "USD":
        rate = fx_rates().get(currency)
        if rate is None:
            return Salary(None, None, confidence="unknown", raw=raw)
        low = low * rate if low is not None else None
        high = high * rate if high is not None else None
        converted = True

    top = high if high is not None else low
    if top is None or top < _MIN_PLAUSIBLE_ANNUAL or top > _MAX_PLAUSIBLE_ANNUAL:
        return Salary(None, None, confidence="unknown", raw=raw)

    if low and high and low > 0 and (high / low) > _MAX_RANGE_RATIO:
        return Salary(None, None, confidence="unknown", raw=raw)

    basis, share, split_stated = detect_basis(cleaned, match.start())

    return Salary(
        low=low, high=high, currency=currency, period=period,
        confidence="published", raw=raw, converted=converted,
        basis=basis, variable_share=share, split_stated=split_stated,
    )


# Words a posting uses when it is about to state pay. Used to find the
# compensation section rather than reading a job ad from the top and hoping.
PAY_LABEL = re.compile(
    r"\b(?:salary|compensation|base pay|basepay|pay range|pay band|pay rate|"
    r"remuneration|total comp(?:ensation)?|ote\b|we offer|offers? between)\b",
    re.I,
)
# How much text after a pay word can still belong to the same statement. Kept
# short on purpose: at 400 characters a generic "compensation and benefits
# programs..." boilerplate line reached forward into an unrelated number.
_PAY_WINDOW = 220
# A posting stating pay names a currency. Requiring one here is what stops
# RANGE_RE — whose currency symbols are optional — from reading "100% Medical,
# Dental" or a list of benefits as a salary band.
_HAS_CURRENCY = re.compile(_SYMBOL_PATTERN, re.IGNORECASE)
# Guard against a pathological description; job posts are not books.
_MAX_DESCRIPTION_SCAN = 20_000


def parse_description(text, currency_hint=None):
    """
    Find the posting's own pay statement anywhere in its body.

    Reading `description[:3000]` — which is what prefilter did — gets this
    backwards. The first 3,000 characters of a job ad are the company pitch;
    the pay lives at the bottom, under a "Compensation" heading. LangChain's
    Python OSS Engineer publishes "$160,000- $240,000" at character 3,274, so
    the digest reported it as an ESTIMATE while a real number sat 274
    characters past the cut. The head of the same description is where the
    "$125M raised at Series B" fabrication came from, so the old window was
    simultaneously missing the pay and inventing it.

    Anchors on a pay word and parses the clause after it. parse() still applies
    its own funding and magnitude guards, so a "total compensation" sentence
    that turns out to be about revenue is refused there.
    """
    if not text:
        return UNKNOWN
    body = text[:_MAX_DESCRIPTION_SCAN]
    for match in PAY_LABEL.finditer(body):
        segment = body[match.start():match.start() + _PAY_WINDOW]
        if not _HAS_CURRENCY.search(segment):
            continue
        # Prose: never let a small bare number be guessed into an hourly wage.
        parsed = parse(segment, currency_hint=currency_hint,
                       allow_hourly_inference=False)
        if parsed.confidence == "published":
            return parsed
    return UNKNOWN


def clears_bar(salary, floor=70_000):
    """
    True if the top of the range clears the pay floor.

    Tests the TOP of the range, per Section 1: a $60k–$85k posting is worth
    surfacing because the ceiling clears the bar. `Salary.top` is guaranteed
    base, so an OTE posting has to clear the floor on money it actually pays.
    """
    if salary is None or salary.top is None:
        return False
    return salary.top >= floor
