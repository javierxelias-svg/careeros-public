"""
Geo-class and timezone filtering (plan Section 1b).

The operator is US work-authorised and based in a US jurisdiction
(configurable), and may later work from a far-away timezone (e.g. UTC+7). Two
consequences drive this module:

  - US-only postings are ELIGIBLE, not rejected. This is the largest remote
    pool available, so filtering it out would gut the search.
  - A posting demanding fixed overlap with US business hours is painful from
    UTC+7, because it means working through the night. Timezone is therefore
    a filter, not a vibe score (see the HARD/SOFT split below).
"""

import re

CLASS_ANYWHERE = "A"   # work from anywhere on earth — the target
CLASS_US = "B"         # US-restricted; operator eligible, may require US residence
CLASS_BLOCKED = "C"    # locked to a region the operator cannot work from

ANYWHERE_PATTERNS = [
    r"anywhere in the world",
    r"work from anywhere",
    r"\bwfa\b",
    r"fully (?:distributed|global|remote,? worldwide)",
    r"globally remote",
    r"remote,?\s*(?:global|worldwide|anywhere)",
    r"\bworldwide\b",
    r"any (?:country|location|timezone|time zone)",
    r"no location requirement",
    r"location[:\s]*(?:independent|agnostic)",
]

# "You can work from anywhere within this region" is the opposite of a
# work-from-anywhere offer: it is a company telling you the region is the limit.
# Linear writes exactly that under a "North America" location.
_QUALIFIED_ANYWHERE_RE = re.compile(
    r"(?:work|working|live|based)\s+(?:from\s+)?anywhere\s+"
    r"(?:with)?in\s+(?:this|the|that)\s+"
    r"(?:region|country|area|timezone|time zone|zone)", re.I
)

US_PATTERNS = [
    r"\bremote\s*[-(,]?\s*u\.?s\.?a?\b",
    r"\bus\s*(?:only|based|remote)\b",
    r"\bunited states\b",
    r"\busa\b",
    r"\bu\.s\.\b",
    r"authorized to work in the us",
    # Anchored. Unanchored, this matched "must reside in the UK", and because
    # _US_RE vetoes the blocked-region check below, UK-only postings were
    # classified as US-eligible and shown to the operator.
    r"must (?:reside|be located|live) in the u\.?s\.?a?\b",
    r"\bus[- ]based\b",
]

# Regions the operator cannot legally work from. Presence of these WITHOUT a
# US or anywhere signal means the posting is closed to them.
BLOCKED_PATTERNS = [
    (r"\b(?:eu|europe|european union|emea)\s*(?:only|based|remote)?\b", "EU"),
    (r"\bmust (?:reside|be located|live) in (?:the )?(?:eu|europe|uk)", "EU/UK"),
    (r"\b(?:uk|united kingdom|britain)\s*(?:only|based)\b", "UK"),
    (r"\bcanada\s*(?:only|based)\b", "Canada"),
    (r"\bcanadian residents? only\b", "Canada"),
    (r"\b(?:latam|latin america)\s*only\b", "LATAM"),
    (r"\b(?:apac|australia|new zealand|india|germany|france|spain|netherlands|poland|brazil|mexico|argentina)\s*(?:only|based|residents? only)\b", "region-locked"),
]

# Split into two groups, because they fail for different reasons.
#
# HARD — bad wherever the operator lives. Night shifts, on-call rotations and
# weekend coverage wreck a life in any timezone, so these stay rejections.
# A posting that says "no on-call" is advertising the BEST signal it can give,
# and reading that as a pager duty threw it away. Found 2026-09-30: "No on-call,
# ever. We protect your evenings." was rejected outright by the digest.
#
# curated.py has carried exactly this guard since August — its comment says
# reading "no on-call" as pager duty "inverts the best signal a posting can
# give" — and the guard was never added here. So the curated page was protected
# and the daily digest, which is what actually reaches the operator, was not. Negated mentions
# are REMOVED before the search rather than matched around, same as curated does.
TZ_NEGATED = re.compile(
    r"\b(?:no|without|never any|zero|free from|not?\s+require\w*)\s+"
    r"(?:formal\s+|scheduled\s+|any\s+)?"
    r"(?:on[- ]call|pager(?: duty)?|weekend (?:rotation|coverage)|shift work|"
    r"night shifts?)", re.I)

TIMEZONE_HARD = [
    (r"\bon-?call\b", "on-call rotation"),
    # "weekend rotation required" and "shift work, nights and weekends" both
    # survived the original list: it demanded the word "rotating" before
    # weekends, and never carried a bare "shift work" or "weekend rotation".
    # Measured the same day, and both are hard rejects by the stated terms.
    (r"\bnight shifts?\b|\brotating (?:shifts?|weekends?)\b|"
     r"\bweekend (?:coverage|rotation|shifts?|work)\b|\bshift work\b|"
     r"\bnights and weekends\b|\brotational shifts?\b", "shift work"),
    # Pager duty is on-call wearing a different word. Rejected for the same
    # reason: the operator's stated requirement is that clocking out means
    # actually clocking out, with nothing pending overnight.
    (r"\bpager\s*duty\b|\bpagerduty\b|\bcarry(?:ing)? (?:a |the )?pager\b", "pager duty"),
]

# SOFT — only painful if the operator relocates far from US hours. The move is
# an option kept open, not a booked plan, so these became a score penalty
# and a visible tag rather than a rejection. Rejecting them was throwing away
# roughly ten viable jobs a day for a trip that may not happen this year.
TIMEZONE_SOFT = [
    (r"\b(?:overlap|overlapping)\b[^.]{0,60}\b(?:pt|pst|pdt|et|est|edt|ct|cst|mt|mst|pacific|eastern|central)\b", "requires US-hours overlap"),
    (r"\b(?:pt|pst|pdt|et|est|edt|ct|cst)\b[^.]{0,40}\b(?:hours|time zone|timezone|working hours)\b", "US timezone working hours"),
    (r"\bcore (?:hours|working hours)\b", "fixed core hours"),
    (r"\bmust be (?:available|online)\b[^.]{0,60}\b(?:9|8|10)\s*(?:am|:00)?\s*(?:-|to|–)\s*(?:5|6|17|18)\b", "fixed daily availability window"),
    (r"\bdaily stand-?ups?\b[^.]{0,40}\b(?:\d{1,2}\s*(?:am|pm)|est|pst|et|pt)\b", "fixed-time daily standup"),
    (r"\b(?:\d{1,2})\+?\s*hours? of overlap\b", "mandated overlap hours"),
]

TIMEZONE_BLOCKERS = TIMEZONE_HARD + TIMEZONE_SOFT

TIMEZONE_FRIENDLY = [
    (r"\basync(?:hronous)?(?:[- ]first)?\b", "async"),
    (r"\bno (?:fixed|set|core) (?:hours|schedule)\b", "no fixed hours"),
    (r"\bflexible (?:hours|schedule|working hours)\b", "flexible hours"),
    (r"\bwork when you want\b|\bown your schedule\b|\bset your own hours\b", "own schedule"),
    (r"\bresults[- ]oriented\b|\boutcome[- ]driven\b", "results-oriented"),
    (r"\bany time ?zone\b|\btimezone[- ]agnostic\b", "timezone agnostic"),
    (r"\bno (?:standups?|meetings)\b", "no standups"),
]

# US sub-regions. Named in a title these mean "US-restricted", not "blocked" —
# the operator is a US citizen — but they are never "anywhere in the world".
TITLE_US_REGIONS = [
    (r"\b(?:west|east)\s*coast\b", "a US coast"),
    (r"\bnorth america\b", "North America"),
    (r"\bamericas\b", "the Americas"),
]

# A country named in a TITLE needs no qualifier — that is the whole difference
# between this list and BLOCKED_PATTERNS above. Body text mentions countries for
# a dozen innocent reasons ("our Berlin office", "customers across India"), so
# there a bare country name must never block. A title is different: a company
# that writes "- Thailand" after a role name is telling you where the job is.
#
# Without this, `Regional Director of Customer Success - Thailand` and
# `Technical Account Manager – Payments (APAC)` were classified work-from-
# anywhere and printed to the operator under a 🌍 globe on 2026-08-17. That is
# the same defect class fixed for "Remote in Europe" earlier the same day —
# title_region_lock() had learned region phrases and US coasts, but never
# learned that a country name on its own is a lock.
#
# Anchored to a delimiter so the country has to be a qualifier on the role, not
# a word inside it. The negative lookahead keeps "Customer Success - Singapore
# Clients" out: that names a customer base, not a work location.
_TITLE_COUNTRIES = (
    r"thailand|singapore|india|japan|china|south korea|korea|vietnam|"
    r"philippines|indonesia|malaysia|taiwan|hong kong|australia|new zealand|"
    r"germany|france|spain|italy|netherlands|poland|portugal|ireland|sweden|"
    r"norway|denmark|finland|switzerland|austria|belgium|greece|romania|"
    r"czechia|hungary|ukraine|turkey|israel|uae|dubai|saudi arabia|qatar|"
    r"egypt|nigeria|kenya|ghana|south africa|morocco|"
    r"brazil|argentina|chile|colombia|peru|uruguay|mexico|costa rica|canada"
)
TITLE_REGION_LOCKS = [
    (rf"[-–—,(\[|/]\s*(?:remote[,\s]+)?(?:{_TITLE_COUNTRIES})\b"
     r"(?!\s+(?:clients?|customers?|market|accounts?|users?|portfolio))",
     "a single country"),
    # Region abbreviations. UK and EU were missing until 2026-08-18, when
    # "Staff AI Engineer - 2nd Horizon | UK | Remote" at Grafana Labs scored 81
    # and printed as work-from-anywhere — the operator cannot work in the UK.
    # A bare country name is already handled above; these are the shorthands a
    # company uses when the territory IS the job.
    (r"[-–—,(\[|/]\s*(?:apac|emea|anz|dach|benelux|mena|uk|eu|nordics|iberia)\b"
     r"(?!\s+(?:clients?|customers?|market|accounts?|users?))",
     "a single region"),

    # CITIES outside the Americas. Added 2026-09-30 after a dry run printed "UX
    # Research Programs & Operations (Zurich)" to the digest wearing a
    # work-from-anywhere globe, next to "Premium Support Engineer (Tokyo)". The
    # two rules above match a COUNTRY after a delimiter, and a city is neither.
    #
    # This is the third guard found in one day that curated.py has and geo.py does
    # not — curated.LOCKED_TITLE has locked Mumbai and Sydney since August. The
    # others were the "no on-call" negation and the office requirement. Every time,
    # the page visited deliberately is protected and the digest that arrives
    # unasked is not.
    #
    # Americas cities are deliberately absent. The operator is US-authorised and
    # open to the Americas, so New York, Mexico City and São Paulo are places they
    # can work; only the ones they cannot are listed. Also absent: "based" and "hybrid"
    # phrasings, which belong to office_required() rather than here.
    (r"[-–—,(\[|/]\s*(?:remote[,\s]+)?(?:"
     r"mumbai|bangalore|bengaluru|hyderabad|pune|chennai|delhi|gurgaon|noida|"
     r"sydney|melbourne|brisbane|perth|auckland|wellington|"
     r"singapore|tokyo|osaka|kyoto|seoul|beijing|shanghai|shenzhen|guangzhou|"
     r"hong kong|taipei|manila|cebu|jakarta|bangkok|ho chi minh|hanoi|"
     r"kuala lumpur|dhaka|karachi|lahore|colombo|"
     r"london|manchester|birmingham|bristol|edinburgh|glasgow|belfast|dublin|cork|"
     r"berlin|munich|m[uü]nchen|hamburg|frankfurt|cologne|k[oö]ln|stuttgart|"
     r"paris|lyon|marseille|toulouse|bordeaux|nantes|"
     r"madrid|barcelona|valencia|seville|bilbao|lisbon|porto|"
     r"amsterdam|rotterdam|utrecht|eindhoven|brussels|antwerp|luxembourg|"
     r"zurich|z[uü]rich|geneva|gen[eè]ve|basel|bern|lausanne|"
     r"vienna|wien|prague|praha|warsaw|warszawa|krakow|krak[oó]w|wroclaw|"
     r"budapest|bucharest|sofia|belgrade|zagreb|ljubljana|bratislava|tallinn|"
     r"riga|vilnius|"
     r"stockholm|gothenburg|oslo|bergen|copenhagen|aarhus|helsinki|reykjavik|"
     r"milan|milano|rome|roma|turin|naples|bologna|florence|athens|thessaloniki|"
     r"istanbul|ankara|tel aviv|jerusalem|haifa|"
     r"dubai|abu dhabi|riyadh|jeddah|doha|kuwait city|manama|muscat|cairo|"
     r"lagos|abuja|nairobi|accra|johannesburg|cape town|pretoria|durban|casablanca"
     r")\b"
     r"(?!\s+(?:clients?|customers?|market|accounts?|users?|portfolio|team))",
     "a city the operator cannot work from"),
]

# An explicit remote-scope declaration in the BODY, e.g. WeWorkRemotely postings
# that open with "Headquarters: Remote (North America)". This is the employer
# writing down where the job may be worked, and it has to outrank the feed's
# region field for the same reason title_region_lock() does: WWR stamps
# <region>Anywhere in the World</region> on ~95 of every 100 items because that
# is the CATEGORY being fetched, not a fact about the job.
#
# Found 2026-08-17 on Hightouch's Customer Success Engineer — body said
# "Remote (North America)", feed said "Anywhere in the World", and it printed
# to the operator under a work-from-anywhere globe. Their careers page lists
# three separate CSE roles (North America / New York / Europe), so the scope in
# the body was the real one.
#
# Anchored to an explicit "Remote (...)" or "Headquarters:" construction and to
# the head of the posting, so ordinary prose about markets or customers cannot
# trip it.
BODY_SCOPE_HEAD = 400
_BODY_SCOPE_RE = re.compile(
    r"(?:headquarters\s*:\s*)?remote\s*[\(\[]\s*([^)\]]{2,40}?)\s*[\)\]]",
    re.I,
)
# Scopes a US-authorised operator is eligible for, but which are NOT
# work-from-anywhere.
_SCOPE_US = re.compile(
    # Bare "Canada" is NOT here — no Canadian work authorization is assumed, so
    # "Remote (Canada)" is blocked. "US & Canada" keeps the operator eligible.
    r"\b(?:north america|usa?|u\.s\.|united states|americas|"
    r"us\s*(?:&|and|/)\s*canada)\b",
    re.I,
)
_SCOPE_ANYWHERE = re.compile(
    r"\b(?:anywhere|worldwide|global|any location)\b", re.I
)
# Named scopes the operator cannot work from. An explicit list rather than "anything not
# recognised is blocked", because `remote (...)` also appears in ordinary prose
# — "we serve customers remote (across many markets)" — and this module's own
# rule is that an unrecognised value must never be punished like a known-bad
# one. Unknown scope returns None and the normal region-field path runs.
_SCOPE_BLOCKED = re.compile(
    r"\b(?:europe|emea|eu|uk|united kingdom|britain|ireland|"
    r"apac|asia|asia[- ]pacific|anz|australia|new zealand|india|japan|"
    r"singapore|china|korea|latam|latin america|dach|benelux|mena|"
    r"middle east|africa|germany|france|spain|italy|netherlands|poland|"
    r"portugal|brazil|mexico|argentina|colombia|canada)\b",
    re.I,
)


def body_region_lock(text):
    """
    Return (geo_class, reason) when the posting BODY declares its own remote
    scope, else None. Only the head of the posting is read.
    """
    head = (text or "")[:BODY_SCOPE_HEAD]
    match = _BODY_SCOPE_RE.search(head)
    if not match:
        return None
    scope = match.group(1).strip()
    if _SCOPE_ANYWHERE.search(scope):
        return None
    if _SCOPE_US.search(scope):
        return CLASS_US, f"posting states remote scope: {scope}"
    if _SCOPE_BLOCKED.search(scope):
        return CLASS_BLOCKED, f"posting states remote scope: {scope}"
    return None


_ANYWHERE_RE = re.compile("|".join(ANYWHERE_PATTERNS), re.I)
_US_RE = re.compile("|".join(US_PATTERNS), re.I)
_BLOCKED_RES = [(re.compile(p, re.I), label) for p, label in BLOCKED_PATTERNS]
_TZ_HARD_RES = [(re.compile(p, re.I), label) for p, label in TIMEZONE_HARD]
_TZ_SOFT_RES = [(re.compile(p, re.I), label) for p, label in TIMEZONE_SOFT]
_TZ_FRIENDLY_RES = [(re.compile(p, re.I), label) for p, label in TIMEZONE_FRIENDLY]
_TITLE_US_RES = [(re.compile(p, re.I), label) for p, label in TITLE_US_REGIONS]
_TITLE_LOCK_RES = [(re.compile(p, re.I), label) for p, label in TITLE_REGION_LOCKS]

NOT_REMOTE_RE = re.compile(
    r"\b(?:hybrid|on-?site|in-?office|in[- ]person)\b", re.I
)
REMOTE_RE = re.compile(r"\bremote\b|\bdistributed\b|\bwork from home\b", re.I)

# Any word that shows a posting is talking about remote work at all. Wider than
# REMOTE_RE because this one asks "was it ever mentioned", not "does this line
# say remote".
# "remotely" is spelled out because \bremote\b does not match it, and six Paddle
# postings saying "you can work remotely, from one of our stylish hubs, or even a
# bit of both" were rejected as having no remote signal at all while the rule was
# being measured.
# For a REGION field, where any mention of remote work is about this job.
REMOTE_TOKEN_RE = re.compile(
    r"\bremote(?:ly)?\b|\bwork from home\b|\bwfh\b|\banywhere\b"
    r"|\bhome[- ]based\b|\bdistributed\b", re.I
)

# For a BODY, where the same words mean other things. A posting is only claiming
# to be remote if it describes a working ARRANGEMENT, so the phrase has to say
# so. Measured on the frozen pool of 2026-08-17: accepting the bare word instead
# let 494 employer-board listings through, including "experience with remote
# notebooks", "deployable anywhere", and "distributed systems engineering" —
# the last of which alone kept all eighteen of Scale AI's Forward Deployed
# roles alive, every one of them located in New York, San Francisco, London or
# Doha with the word remote nowhere in the posting.
REMOTE_ARRANGEMENT_RE = re.compile(
    r"\bwork(?:ing)? (?:remotely|from home|from anywhere)\b"
    r"|\bremote[- ](?:first|friendly|position|role|work|team|company|opportunity|eligible)\b"
    r"|\bfully remote\b|\b100% remote\b"
    r"|\bremote,? (?:us|usa|united states|canada|amer|americas|latam|emea|apac|global|worldwide|anywhere)\b"
    r"|\bthis (?:role|position) is remote\b"
    r"|\b(?:fully|globally) distributed\b|\bdistributed (?:team|company|workforce)\b"
    r"|\bwork from anywhere\b|\bhome[- ]based\b|\bno (?:offices?|hq)\b"
    r"|\bhire globally\b|\bremote work\b", re.I
)

# Sentences a company writes when the job has a desk in it. These are PHRASES,
# never bare words: "in-person" alone appears in perfectly remote postings that
# hold in-person offsites twice a year (Canonical, Supabase), and rejecting on
# the bare word would cost real listings.
#
# Measured on the frozen 3,191-listing pool of 2026-08-17: these six patterns
# rejected 165 postings, and a seventh candidate — relocat\w+ (to|support) —
# was dropped after measurement. Alone it rejected 16, of which five were wrong:
# Remote.com's "Benefits Operations Specialist - AMER" carries region
# "Remote-AMER" and only mentions relocation in passing.
ONSITE_PHRASE_RE = re.compile(
    r"this is an in[- ]person role"
    r"|in[- ]person \d+ days? (?:a|per) week"
    r"|\d+ days? (?:a|per) week in (?:the |our )?office"
    r"|in[- ]office (?:on )?(?:mon|tue|wed|thu|fri)"
    r"|\bhybrid role\b"
    r"|\bhybrid position\b", re.I
)


def title_region_lock(title):
    """
    Return (geo_class, reason) when a job TITLE names its own region, else None.

    A company that writes a territory into the job title means it. This outranks
    the structured region field because that field is often a feed CATEGORY, not
    a fact about the job: on 2026-08-16, 95 of 100 WeWorkRemotely items carried
    <region>Anywhere in the World</region>, so four postings whose own titles read
    "Remote in Europe", "Europe/LaTAM", "Canada, Europe" and "West Coast" were all
    printed to the operator under a "work from anywhere" globe.

    A title that says "anywhere" is not a lock and returns None, so the normal
    region-field path still runs.
    """
    text = (title or "").strip()
    if not text or _ANYWHERE_RE.search(text):
        return None

    for pattern, label in _BLOCKED_RES:
        if pattern.search(text) and not _US_RE.search(text):
            return CLASS_BLOCKED, f"title restricts to {label}: {text}"
    for pattern, label in _TITLE_LOCK_RES:
        if pattern.search(text) and not _US_RE.search(text):
            return CLASS_BLOCKED, f"title restricts to {label}: {text}"
    for pattern, label in _TITLE_US_RES:
        if pattern.search(text):
            return CLASS_US, f"title restricts to {label}: {text}"
    if _US_RE.search(text):
        return CLASS_US, f"title restricts to the US: {text}"
    return None


# TERM 1, the operator's first-ranked and hard: fully remote — no office, no
# hybrid, no "come in sometimes". It was never enforced. Measured 2026-09-30,
# every one of these came back CLASS_US — reaching the digest's US-ONLY section rather
# than being rejected:
#
#   "You will be in our office 3 days a week"
#   "Employees are in office at least 25% of the time"   <- a real Anthropic role
#   "Hybrid: 2 days onsite in New York"
#
# The handoff has logged this since 2026-09-28 as "the remote gate trusts prose
# over an explicit in-office percentage" and it stayed open while two days went
# into the years filter, which nobody had asked for.
#
# Negations are stripped first, for the same reason TZ_NEGATED exists: "no office
# days", "no hybrid nonsense" and "fully remote, never in an office" are postings
# advertising exactly what is wanted, and matching the word "office" inside them
# inverts the best signal on the page.
OFFICE_NEGATED = re.compile(
    r"\b(?:no|never|without|zero|free from|not?\s+require\w*)\s+"
    r"(?:any\s+|mandatory\s+|required\s+)?"
    r"(?:hybrid|office|in[- ]office|onsite|on[- ]site|rto|return to office|"
    r"office days?|days? in (?:the )?office)", re.I)

IN_OFFICE = re.compile(
    # an explicit share of time in an office
    r"\bin[- ](?:the\s+)?office\b[^.\n]{0,30}?\d{1,3}\s*%"
    r"|\d{1,3}\s*%[^.\n]{0,30}?\bin[- ](?:the\s+)?office\b"
    # Anthropic's current wording, 2026-10-05: "we expect all staff to be in one
    # of our offices at least 25% of the time".
    r"|\bin\s+(?:one of\s+)?(?:our|an?)\s+offices?\b[^.\n]{0,30}?\d{1,3}\s*%"
    # a number of days a week on site
    r"|\b\d\s*(?:\+)?\s*days?\s*(?:a|per)\s*week\b[^.\n]{0,24}?"
    r"(?:office|onsite|on[- ]site|in person)"
    r"|(?:office|onsite|on[- ]site|in person)[^.\n]{0,24}?"
    r"\b\d\s*(?:\+)?\s*days?\s*(?:a|per)\s*week\b"
    # named as hybrid outright
    r"|\bhybrid\s+(?:role|position|work|schedule|model|setup)\b"
    r"|\bthis (?:role|position) is hybrid\b"
    r"|\bhybrid\b[^.\n]{0,20}?\b\d\s*days?\b"
    # required presence
    r"|\b(?:must|required to|expected to)\s+(?:be\s+)?"
    r"(?:work\s+)?(?:in|at)\s+(?:the\s+)?(?:office|our offices?)\b"
    r"|\breturn[- ]to[- ]office\b|\bRTO policy\b",
    re.I,
)


def office_required(text):
    """(True, evidence) when the posting requires time in an office."""
    blob = OFFICE_NEGATED.sub(" ", text or "")
    hit = IN_OFFICE.search(blob)
    return (True, " ".join(hit.group(0).split())[:60]) if hit else (False, "")


def classify_geo(region_field, text, title=""):
    """
    Return (geo_class, reason).

    `region_field` is the structured location string when a source provides one
    (WeWorkRemotely's "Anywhere in the World", Remotive's "USA"). It is trusted
    over free text, because free text mentions countries for many reasons —
    an office address is not a work restriction.

    The job title outranks both. See title_region_lock().
    """
    region = (region_field or "").strip()
    blob = f"{region}\n{text or ''}"

    locked = title_region_lock(title)
    if locked is not None:
        return locked

    # Term 1 before everything else about location: a hybrid role is not a remote
    # role the operator can take, whatever its region field claims.
    needs_office, evidence = office_required(blob)
    if needs_office:
        return CLASS_BLOCKED, f"requires time in an office: {evidence}"

    # The employer's own scope statement beats the feed's category.
    locked = body_region_lock(text)
    if locked is not None:
        return locked

    if region and _ANYWHERE_RE.search(region):
        return CLASS_ANYWHERE, f"region field: {region}"

    if region:
        for pattern, label in _BLOCKED_RES:
            if pattern.search(region) and not _US_RE.search(region):
                return CLASS_BLOCKED, f"region locked to {label}: {region}"
        if _US_RE.search(region):
            return CLASS_US, f"region field: {region}"
        # A region field naming a US sub-region is a lock too, and it has to be
        # read BEFORE the body. Linear's Customer Success Manager carries
        # region "North America" and the sentence "This role is open to
        # candidates based in North America. You can work from anywhere within
        # this region." — the body phrase matched, and a North-America-only job
        # printed under a work-from-anywhere globe on 2026-08-18.
        for pattern, label in _TITLE_US_RES:
            if pattern.search(region):
                return CLASS_US, f"region field names {label}: {region}"

    match = _ANYWHERE_RE.search(blob)
    if match and not _QUALIFIED_ANYWHERE_RE.search(blob):
        return CLASS_ANYWHERE, "posting states work from anywhere"

    for pattern, label in _BLOCKED_RES:
        if pattern.search(blob) and not _US_RE.search(blob):
            return CLASS_BLOCKED, f"restricted to {label}"

    if _US_RE.search(blob):
        return CLASS_US, "US-restricted (operator eligible as US citizen)"

    # Nothing said either way. Treat as US-class rather than anywhere-class:
    # assuming global when unstated produces false hope, and the digest tags it.
    return CLASS_US, "location unstated, assumed US-scope"


def is_remote(region_field, text, workplace="", source=""):
    """
    False for hybrid/onsite postings that leaked into a remote feed.

    `workplace` is what the ATS itself recorded — "remote", "onsite" or ""
    (unknown) — and `source` is the feed the listing came from. Both default to
    empty so an aggregator listing is judged exactly as it was before.

    Why they were added, 2026-08-17: SIX of the highest-scoring roles in the
    pool were onsite jobs. Reducto ("This is an in person role at our office in
    SF"), Auctor ("in person 5 days per week"), Confido (which offers paid
    relocation to NYC), Arini, PermitFlow (in-office Mon/Wed/Fri) and Retell AI
    — whose Senior Forward Deployed Engineer pays a $300/month COMMUTER
    stipend — all passed this gate scored 10/10 on "fully remote", the
    operator's first hard constraint. Three separate causes:

      1. The gate defaulted to remote when nothing was said. Safe for an
         aggregator, whose feed is remote by construction; wrong for an
         employer board, which carries every job the company has. Same defect
         class as invariant 4 and digest.earns_main_lane().
      2. The disclosure comes late. "in person" sits at character 3,404 in
         Reducto's posting, 2,210 in Arini's, 5,360 in Retell's — all past the
         1,200-character window. Same shape as the pay section sitting below
         the 3,000-character cut.
      3. Confido never writes the word at all. Its posting says "NYC Office"
         in the location field and isRemote: false in the structured data, and
         nowhere in the prose. No amount of text scanning can catch that one —
         only the field can.
    """
    blob = f"{region_field or ''}\n{text or ''}"
    head = blob[:1200]

    # 1. The employer's own structured answer, when there is one, settles it.
    if workplace == "onsite":
        return False, "job board states onsite or hybrid"

    if NOT_REMOTE_RE.search(head) and not REMOTE_RE.search(head):
        return False, "hybrid or onsite"
    if re.search(r"\bhybrid\b", head, re.I):
        return False, "hybrid"

    # 2. An onsite sentence anywhere in the body, not just the first 1,200
    #    characters — but the region field outranks it. Labelbox repeats a
    #    "3 days per week in office" line on postings whose location reads
    #    "Remote, United States"; boilerplate must not beat a stated region.
    if not REMOTE_TOKEN_RE.search(region_field or "") and ONSITE_PHRASE_RE.search(blob):
        return False, "posting says onsite"

    # 3. An employer board that never says the job can be worked from home is
    #    not offering a remote job. The region field may say it in one word; the
    #    body has to say it as a phrase, for the reason above.
    #    Only applied to source="ats": the aggregators
    #    pre-filter to remote and often carry no body text at all, so demanding
    #    a positive signal from them would empty the pool.
    if (source == "ats" and workplace != "remote"
            and not REMOTE_TOKEN_RE.search(region_field or "")
            and not REMOTE_ARRANGEMENT_RE.search(blob)):
        return False, "employer board, no remote signal"

    return True, "remote"


def timezone_verdict(text):
    """
    Return (ok, hard, soft, friendly).

    `ok` is False only for hard blockers — shift work and on-call, which are
    bad from anywhere. Soft blockers (US-hours overlap, core hours) come back
    as a list so the caller can apply a score penalty and tag the listing,
    letting the operator decide rather than deciding for them.
    """
    blob = text or ""
    # Strip the negated mentions first. "No on-call, ever" must not read as
    # on-call — that inverts the strongest positive signal a posting has.
    blob = TZ_NEGATED.sub(" ", blob)
    hard = [label for pattern, label in _TZ_HARD_RES if pattern.search(blob)]
    soft = [label for pattern, label in _TZ_SOFT_RES if pattern.search(blob)]
    friendly = [label for pattern, label in _TZ_FRIENDLY_RES if pattern.search(blob)]

    # Explicit async language outweighs a single incidental soft phrase: plenty
    # of async teams still say "no core hours" near the word "overlap".
    if friendly and len(soft) <= 1:
        soft = []

    return (not hard), hard, soft, friendly


SOFT_TZ_PENALTY = 2


def geo_score(geo_class):
    """
    Class A used to be "the arbitrage target" and earned +3 against 0 for
    US-only. Cut to +1 on 2026-09-28, when the operator settled on a US home
    base and stopped chasing the arbitrage — see freedom.ANYWHERE_POINTS. A
    role requiring US residence is one a US-based operator qualifies for rather
    than one that breaks the plan. The remaining point is for optionality, not
    for a plan being executed.
    """
    return {CLASS_ANYWHERE: 1, CLASS_US: 0, CLASS_BLOCKED: -99}.get(geo_class, 0)


def geo_tag(geo_class, reason=""):
    # No emoji here — the digest adds its own warning marker, and two stacked
    # warning signs read as a bug rather than emphasis.
    #
    # A North America or Americas scope is not a US-residence requirement.
    # Linear's Implementation Manager reads "open to candidates based in North
    # America" and printed as "may require US residence" on 2026-10-01.
    if geo_class == CLASS_US:
        if re.search(r"\bnorth america\b", reason or "", re.I):
            return "North America only, not US-only"
        if re.search(r"\bamericas\b", reason or "", re.I):
            return "the Americas only, not US-only"
    return {
        CLASS_ANYWHERE: "work from anywhere",
        CLASS_US: "US remote · ask about working abroad",
        CLASS_BLOCKED: "region-locked",
    }.get(geo_class, "")
