"""
Stage 1: deterministic filtering and rule-based tiering.

Pure code, no LLM, no network. Applies the hard gates from plan Sections 1,
1a and 1b, then scores what survives on keyword flags from Section 3.

Unpriced postings are estimated by estimate.py from the job title rather than
discarded — about 60% of listings state no pay. Estimates are capped at B-tier
and labelled, so the machine never sounds certain about a number it invented.
"""

import re
from collections import Counter

import company as company_mod
import estimate
import experience
import fit
import freedom
import geo
import salary as salary_mod

# EXAMPLE operator setting — set your own floor.
# It applies to the TOP of a published range, so $70k-$100k still shows: $85k+ is
# inside it and negotiable.
PAY_FLOOR = 85_000
# EXAMPLE operator setting — set your own floor.
# A band guessed from the title must have its MIDPOINT at the floor too, so a
# guess like ~$66k-$99k cannot slip in under it. Roles with no guess at all
# still show as "ask".
ESTIMATE_FLOOR = 85_000
# EXAMPLE operator setting — set your own floor.
# ...except a job whose posting WRITES async or flexible hours. A strict guess
# floor was hiding exactly the freedom matches this search exists to find, on a
# title guess alone. Freedom comes first, so those stay down to this lower
# guess, marked to ask pay first. Below it nothing comes back.
FREEDOM_ESTIMATE_FLOOR = 65_000
# Listings at or above these marks score higher and therefore surface first.
STRONG_PAY = 95_000
GREAT_PAY = 120_000

# Paid to the intersection of entry-level and STRONG_PAY, on top of whatever
# each half already earns. Sized at 4 so it outranks the +3 a senior role picks
# up from GREAT_PAY alone: a $130k Staff Engineer the operator cannot get must
# not outrank a $100k Associate Solutions Engineer they can.
ENTRY_AND_PAID_BONUS = 4

# Spanish, paid properly. Added 2026-09-29 for an operator who is fully
# bilingual Spanish/English.
#
# It was already SCORED - "bilingual advantage" is one of forty-odd green flags,
# each worth a flat +1 - which is the same weight as a posting saying "async".
# That is not what this is, and the reason is structural rather than
# sentimental: a role requiring native Spanish AND US work authorisation AND
# US-hours overlap is one most applicants cannot take at all. A bilingual
# candidate competes against dozens instead of thousands.
#
# +3, matching ECOSYSTEM_BONUS and TRAINING_BONUS. Paid on top of the flat green
# point, so a Spanish-requiring role clears an otherwise identical English one
# by four.
BILINGUAL_LABEL = "bilingual advantage"
BILINGUAL_BONUS = 3

# Brazil is Latin America and it is not Spanish. Added 2026-09-29 after
# "Grupo QuintoAndar | Vaga afirmativa para PcD - Analista de Business
# Operations (Remoto)" reached the main lane carrying "bilingual advantage" and
# the note that Spanish made the operator rare there. The posting is in Portuguese, and
# "vaga afirmativa para PcD" means a position reserved for candidates with
# disabilities - so the bonus was wrong twice over on the same listing.
#
# The green flag matches "latin america" and "latam", which are geographies.
# The asset is a LANGUAGE. Where a posting is plainly Portuguese-market and
# never mentions Spanish, the bonus is withdrawn: Brazil is the largest
# employer market in the region and would otherwise dominate a signal the
# operator cannot actually use.
PORTUGUESE_MARKET = re.compile(
    r"\bbrazil(?:ian)?\b|\bbrasil\b|\bportugu[eê]s\b|\bportuguese\b|"
    r"\bs[aã]o paulo\b|\brio de janeiro\b|\bvaga\b|\bremoto\b",
    re.I,
)
SPANISH_SIGNAL = re.compile(
    r"\bspanish\b|\bespa[nñ]ol\b|\bcastellano\b|\bhispanohablante\b|"
    r"\bmexico\b|\bm[eé]xico\b|\bcolombia\b|\bargentina\b|\bchile\b|"
    r"\bper[uú]\b|\bspain\b|\bespa[nñ]a\b",
    re.I,
)


def spanish_actually_applies(blob):
    """
    True when the bilingual signal is about Spanish rather than about the
    region. Portuguese-market postings that never mention Spanish do not count.
    """
    if SPANISH_SIGNAL.search(blob):
        return True
    return not PORTUGUESE_MARKET.search(blob)
TARGET_CEILING = 200_000

# Tier for listings with no published salary. Kept out of the lettered tiers
# entirely so an unpriced job can never be presented as if it cleared the bar.
TIER_UNPRICED = "U"
MIN_GREEN_FOR_UNPRICED = 2

GREEN_FLAGS = [
    (r"\basync(?:hronous)?\b", "async"),
    (r"\bflexible (?:hours|schedule)\b", "flexible hours"),
    # "work from anywhere" deliberately absent: geo.classify_geo already scores
    # that phrase (+3) and freedom.py scores it again as the primary sort key.
    # Rewarding it a third time here made every WFA listing outrank its own tier.
    (r"\bresults[- ]oriented\b|\boutcome[- ]driven\b", "results-oriented"),
    (r"\bno fixed schedule\b|\bset your own hours\b", "own schedule"),
    (r"\b(?:claude|chatgpt|openai|anthropic|copilot|llm|genai)\b", "AI-native"),
    (r"\bai[- ](?:first|native|forward|powered)\b", "AI-forward"),
    (r"\bsmall team\b|\bsmall,? (?:remote )?team\b", "small team"),
    (r"\bflat (?:structure|hierarchy)\b|\bno managers\b", "flat structure"),
    (r"\bfounder(?:s)?\b", "founder-visible"),
    (r"\bfour[- ]day (?:work )?week\b|\b4[- ]day week\b", "4-day week"),
    (r"\bunlimited (?:pto|vacation|time off)\b", "unlimited PTO"),
    (r"\bno (?:prior )?experience (?:is )?(?:required|necessary)\b", "no experience required"),
    (r"\btraining provided\b|\bwe(?:'| wi)ll train you\b", "training provided"),
    (r"\bfully (?:distributed|remote)\b", "fully distributed"),
    # Autonomy weighs heavily for this operator — freedom of method is
    # load-bearing rather than a perk.
    (r"\bautonomy\b|\bautonomous(?:ly)?\b|\bown(?:s|ing)? (?:your|the) (?:work|roadmap|outcomes)\b", "autonomy"),
    (r"\bno micromanag|\btrust(?:ed)? (?:you|our team)\b|\bhigh trust\b", "high trust"),
    (r"\bself[- ]direct(?:ed|ion)\b|\bfigure (?:it|things) out\b", "self-directed"),
    # Deliberately NOT treating "wear many hats" as variety. The operator wants
    # breadth, but in a job posting that phrase reliably signals understaffing,
    # and over-giving before pushing back is a known risk. It stays a red flag.
    # A product that visibly helps people is a real signal for this operator,
    # not a soft preference.
    (r"\bmission[- ]driven\b|\bsocial impact\b|\bnonprofit\b|\bb[- ]corp\b", "mission-driven"),
    (r"\bhelp(?:ing)? (?:people|customers|others) (?:to )?(?:succeed|thrive|grow|learn)\b", "helping people"),
    (r"\b(?:education|healthcare access|climate|accessibility|mental health)\b", "meaningful domain"),
    # The operator's strongest lane: can build the thing and explain it to a
    # non-technical buyer. Highest pay ceiling of the operator's lanes.
    (r"\b(?:solutions?|forward[- ]deployed|implementation|onboarding|"
     r"technical account|customer success|developer (?:advocate|relations|experience))\b", "customer-facing technical"),
    (r"\btranslat(?:e|ing) (?:technical|complex)\b|\bnon-?technical (?:users?|customers?|audience)\b", "translation role"),
    # Culture signals the operator named directly: a founder-led team that
    # treats people as teammates, takes health seriously, and is full of people
    # building and creating on the side.
    (r"\bteam(?:mates)? not employees\b|\blike a (?:family|team), not\b|\bpeople[- ]first\b", "team-not-employees"),
    (r"\bfounder[- ]led\b|\bfounder[- ]owned\b|\bwork directly with (?:the )?founders?\b", "founder-led"),
    (r"\b(?:run club|gym|wellness|health) (?:stipend|budget|benefit|club)\b|"
     r"\bwe (?:value|prioriti[sz]e) (?:health|wellbeing|well-being|rest)\b", "health culture"),
    (r"\bbuild(?:ing)? in public\b|\bside project(?:s)?\b|\bcreator\b|"
     r"\bencourage(?:d)? to (?:write|create|share|post)\b", "creator-friendly"),
    (r"\bwe(?:'| wi)ll teach you\b|\bno experience necessary\b|\blearn on the job\b|"
     r"\b(?:learning|growth) (?:budget|stipend)\b", "will train"),
    (r"\bsabbatical\b|\bgenerous (?:pto|vacation|time off|leave)\b|"
     r"\bminimum (?:pto|vacation)\b", "real time off"),
    (r"\bwork[- ]life balance\b|\bsustainable pace\b|\bno crunch\b|\b40 hours?\b", "sustainable pace"),
    # Cash up front matters on a short planning horizon, so a signing bonus is
    # worth more to this operator than equity.
    (r"\bsign(?:ing|-on)?\s+bonus\b|\bjoining bonus\b|\brelocation bonus\b", "signing bonus"),
    # Remote-first with an optional hub is the ideal shape — free to live
    # anywhere, with somewhere to visit the team when wanted.
    (r"\bremote[- ]first\b", "remote-first"),
    (r"\boptional office\b|\boffice is optional\b|\bhub(?:s)? (?:in|around)\b|"
     r"\b(?:annual|yearly|quarterly) (?:retreat|offsite|meetup)\b", "optional hub / retreats"),
    # Ambitious but humane — the operator wants people fighting for something
    # big, without the team being burned to get there.
    (r"\bambitious\b|\bbig (?:goals|ambitions|bets)\b", "ambitious"),
    (r"\bprofitable\b|\bbootstrapped\b|\bdefault alive\b", "financially stable"),
    # Posting the range up front is both a fairness signal and saves the
    # operator from discovering the pay after three interview rounds.
    (r"\bsalary range\b|\bcompensation range\b|\btransparent (?:pay|salary|compensation)\b", "pay transparency"),
    # Fully bilingual Spanish/English, spoken and written: LATAM-facing roles
    # pay a premium with less competition, and nothing in the pipeline scored
    # it until 2026-08-17.
    # Matches the requirement, not the country: "Spanish-speaking customers" is
    # an asset, "office in Spain" is not, so bare "spanish" never fires.
    (r"\bbilingual\b|\bspanish[- ](?:speaking|language|fluent|proficien\w+)\b|"
     r"\bfluent in spanish\b|\bspanish\s*(?:/|and|&)\s*english\b|"
     r"\benglish\s*(?:/|and|&)\s*spanish\b|"
     r"\b(?:latam|latin america|hispanic market)\b", "bilingual advantage"),
    # Paid apprenticeship. The operator explicitly wants a job that teaches how
    # to run a business later — being paid to learn is part of the return, so
    # training and mentorship signals count as compensation, not as a caveat.
    (r"\bmentor(?:ship|ed|ing)?\b|\byou(?:'| wi)ll be mentored\b", "mentorship"),
    (r"\bhire for potential\b|\bgrow into (?:the|this) role\b|\bwe invest in (?:you|our people)\b", "hires for potential"),
    (r"\bapprentice(?:ship)?\b|\bpaid training\b|\bstructured onboarding\b", "apprenticeship"),
    (r"\byou(?:'| wi)ll learn\b|\blearning[- ](?:focused|culture)\b|\bsteep learning curve\b", "learning culture"),
    # Roles that expose the whole business rather than one narrow function —
    # the fastest way to learn how a company actually runs.
    (r"\bsee (?:the )?(?:whole|entire) business\b|\bwork across (?:the )?(?:business|company)\b|"
     r"\bclose to (?:the )?(?:founder|ceo)\b|\bfirst (?:business|gtm|technical) hire\b", "whole-business exposure"),
]

# The operator's stated direction (2026-08-15): AI-first employers are good,
# employers building on Claude are best.
#
# GREEN_FLAGS already carries a generic "AI-native" pattern worth +1, which
# fires on any posting that says LLM or ChatGPT. This is deliberately narrower
# and worth more: companies building ON Anthropic's stack, where the year of
# work doubles as paid apprenticeship in the stack the operator is betting on.
#
# Note "mcp" is spelled out rather than matched as a bare acronym — it collides
# with Microsoft Certified Professional and managed care provider.
ECOSYSTEM_SIGNALS = [
    (r"\banthropic\b", "Anthropic"),
    (r"\bclaude(?:\s+code)?\b", "Claude"),
    (r"\bmodel context protocol\b|\bmcp servers?\b", "MCP"),
]
_ECOSYSTEM = [(re.compile(p, re.I), label) for p, label in ECOSYSTEM_SIGNALS]
# Large enough to outrank the +3 geo bonus and the +3 top-pay bonus, small
# enough that it cannot lift an off-lane role — those cap at C-tier regardless.
ECOSYSTEM_BONUS = 3

# Being paid to be trained. Stated preference (2026-08-17): a role that trains
# the operator as an engineer is better, not worse.
#
# This is not a perk, it is the return. The operator's gap is team experience —
# work reviewed, a codebase inherited, a decision defended to a colleague. A
# role that trains closes that gap, so it is worth more than any single culture
# keyword.
#
# These labels already existed in GREEN_FLAGS and were each worth +1, the same as
# "ambitious". Counting them again here, once, promotes a role that will teach
# above one that merely sounds pleasant. Once, not per label: a posting that
# says mentorship AND apprenticeship AND learning culture is one good sign
# written three ways, not three good signs.
TRAINING_LABELS = (
    "no experience required", "training provided", "will train",
    "mentorship", "apprenticeship", "hires for potential",
    "learning culture", "whole-business exposure",
)
TRAINING_BONUS = 3

# Roles that do not demand deep expertise but still pay well, asked for
# directly on 2026-08-17.
#
# Matched on the TITLE only, for the reason fit.py gives: a description says
# "junior" about the team, the reporting line, or who you will mentor. The
# seniority veto runs second because boards write "Senior Associate", which is
# not a junior role.
#
# This is deliberately a label rather than a gate or a large bonus. It enters
# `green`, which is worth +1 in the score and prints in the digest, so it breaks
# a tie between two otherwise equal roles and shows which door is open —
# without letting an accessible title outrank role fit or portability.
ACCESSIBLE_TITLE = re.compile(
    r"\b(?:junior|jr\.?|entry[- ]level|graduate|apprentice|trainee|"
    r"associate|assistant|intern)\b", re.I
)
# Only true seniority markers veto. "Manager" and "architect" are role nouns,
# not experience levels — "Junior Technical Account Manager" is exactly the kind
# of open door this is meant to find, and an earlier version of this veto threw
# it away.
ACCESSIBLE_VETO = re.compile(
    r"\b(?:senior|sr\.?|staff|principal|lead|director|head|chief|vp|expert)\b",
    re.I
)
ACCESSIBLE_LABEL = "junior-friendly"


def accessible_title(title):
    """True when the title itself says deep experience is not the bar."""
    text = title or ""
    return bool(ACCESSIBLE_TITLE.search(text)) and not ACCESSIBLE_VETO.search(text)


def training_signals(green):
    """Which paid-apprenticeship labels fired. Bonus applies once, not per label."""
    return [label for label in TRAINING_LABELS if label in green]

# Not a red flag, but a negative signal: the operator can teach and does not
# want to. Roles whose core job is delivering training rank lower.
NEGATIVE_SIGNALS = [
    (r"\b(?:deliver|conduct|facilitate|lead)\s+(?:training|workshops?|classes|courses)\b", "teaching-heavy"),
    (r"\b(?:instructor|trainer|teacher|curriculum developer|tutor)\b", "teaching role"),
]

RED_FLAGS = [
    (r"\bsynergy\b|\bstakeholder alignment\b|\bcross-functional stakeholder\b", "corporate jargon"),
    (r"\bfast[- ]paced\b", "fast-paced"),
    (r"\bwear(?:s|ing)? many hats\b", "wear many hats"),
    (r"\bhustle\b|\bgrind\b|\bwork hard,? play hard\b", "hustle culture"),
    (r"\bownership mentality\b|\bextreme ownership\b", "ownership-mentality"),
    (r"\bhigh[- ]growth\b", "high-growth"),
    (r"\b(?:resolve|handle|close)\s+\d+\+?\s*(?:tickets?|calls?|chats?)\b", "ticket quota"),
    (r"\bsla\b|\bservice level agreement\b", "SLA metrics"),
    (r"\bcall volume\b|\bhigh volume of calls\b", "call volume"),
    (r"\bon-?call\b", "on-call"),
    (r"\bnight shift\b|\brotating (?:shifts?|weekends?)\b", "shift work"),
    # The operator's clearest stated condition, 2026-08-15: when the shift
    # ends, the work ends. Work that follows you home is the thing this search
    # exists to avoid, so it is scored, not ignored. These
    # stay red flags rather than hard rejections because "24/7" in particular
    # often describes the product, not the job.
    (r"\b24/?7\b|\baround the clock\b", "24/7 coverage"),
    (r"\bafter[- ]hours\b|\boutside (?:of )?(?:normal |regular )?business hours\b",
     "after-hours work"),
    (r"\b(?:evenings?|nights?) and weekends\b|\bweekend (?:work|availability)\b",
     "nights and weekends"),
    (r"\balways[- ]on\b|\bfirefighting\b|\bconstant context[- ]switching\b",
     "always-on culture"),
    (r"\b(?:insurance claims?|debt collection|medical billing|telecom)\b", "complaint-heavy industry"),
    # Weighted from the operator's stated terms, not from general taste: these
    # rank as hard flags rather than preferences.
    (r"\b(?:quota|commission[- ]only|uncapped commission|cold call(?:ing|s)?)\b", "quota/commission pressure"),
    (r"\b(?:hit|exceed|smash)\s+(?:your\s+)?(?:targets?|numbers?|quotas?)\b", "targets language"),
    (r"\b(?:aggressive|relentless)\s+(?:sales|growth|outreach)\b", "aggressive sales culture"),
    (r"\b(?:payday loan|mlm|multi-?level marketing|gambling|casino|sportsbook|"
     r"timeshare|forex signals|dropship(?:ping)?)\b", "low-integrity product"),
    (r"\bmicromanag|\bclosely (?:monitored|supervised)\b|\bactivity tracking\b|"
     r"\bscreen(?:shot)? monitoring\b", "surveillance/micromanagement"),
    (r"\bfortune 500\b|\bglobal leader in\b|\bindustry[- ]leading enterprise\b", "enterprise vibe"),
    (r"\brockstar\b|\bninja\b|\bguru\b", "rockstar language"),
    # Corporate CULTURE, the operator's four signals, 2026-10-08. Headcount
    # stopped mattering that day (company size is fine; corporate culture is
    # not), so culture is read from the posting's own words instead.
    # Plain "reports to the VP" is left out: startups have VPs too (PermitFlow's
    # implementation manager reports to one). Layers above VP are the signal.
    (r"\breports? (?:directly )?to (?:the |an? )?(?:svp|evp|senior vice president|"
     r"executive vice president)\b|\bmatrix(?:ed)? (?:organi[sz]ation|"
     r"environment|reporting)\b|\bchain of command\b|\bescalation matrix\b",
     "rigid hierarchy"),
    (r"\bcore (?:working )?hours\b|\bmust be (?:online|available) (?:from|between)\b|"
     r"\b(?:cameras?|webcams?) on\b|\bdaily stand-?ups?\b|\bback-to-back meetings\b",
     "meetings / face time"),
    # "corporate tone" is NOT a single regex: see CORPORATE_TONE below.
    (r"\bremote[- ]friendly\b|\bhub[- ]based\b|\bnear (?:one of )?our (?:hubs?|offices?)\b|"
     r"\bwithin commut(?:ing|able) distance\b|\breturn[- ]to[- ]office\b|"
     r"\bin[- ]person (?:weeks?|days) (?:each|per|every)\b|\bquarterly (?:in[- ]person|onsite)\b",
     "office pressure"),
]

_GREEN = [(re.compile(p, re.I), label) for p, label in GREEN_FLAGS]
_RED = [(re.compile(p, re.I), label) for p, label in RED_FLAGS]
_NEGATIVE = [(re.compile(p, re.I), label) for p, label in NEGATIVE_SIGNALS]
NEGATIVE_PENALTY = 2

# Roles that are structurally incompatible with living abroad, regardless of
# how the posting is worded.
# The travel alternative was DEAD from the day it was written, and every real
# phrasing missed. Found 2026-09-30 by reading a Vector posting that reached the
# top of the sendable list carrying "Able to travel up to 50% to customer
# locations" — 50% travel to distribution centres, against a north star of "a life
# I don't need to escape from".
#
# Cause: the whole alternation was wrapped in \b...\b and the travel branch ends
# in "%". A percent sign is a non-word character, so there is no word boundary
# after it and the branch could never match. The other three branches end in a
# word or a digit, so they worked, and the failure was invisible. Same class as the
# 2026-09-29 backspace-byte regex: it compiled, and it silently never matched.
#
# Now anchored per-branch instead of around the group, and the phrasings come from
# real postings rather than from imagination: "up to 50% travel", "travel 50% of
# the time", "Travel: 50%", "~50% travel".
#
# The threshold stays at two digits on purpose. 5% travel is a couple of trips a
# year and work trips are fine; 25% and up is a different job.
HARD_INCOMPATIBLE = re.compile(
    r"must have a valid driver'?s? licen[cs]e"
    r"|ability to lift \d+"
    r"|relocat(?:e|ion) (?:required|assistance)"
    # "travel up to 50%", "travel at least 25%", "travel 50% of the time"
    r"|travel(?:ling|ing)?[^.\n]{0,24}?\b\d{2,}\s*%"
    # Added 2026-10-05: "travel regularly within your region, up to 50% of the
    # time" (Anthropic, Community Engagement, Texas) sat past the 24-character
    # window. Reaching further only with "up to", which cannot describe remote
    # work: a wider bare window would read "we travel twice a year, and we are
    # 100% distributed" as 100% travel.
    r"|travel(?:ling|ing)?[^.\n]{0,60}?\bup to \d{2,}\s*%"
    # "up to 50% travel", "~50% travel to customer sites", "50% travel required"
    r"|\b\d{2,}\s*%[^.\n]{0,24}?travel",
    re.I,
)


# Commission pay is on the operator's never list (no quota or commission sales).
# Ashby writes it into the pay field itself, e.g. "$158.3K – $263.4K • Offers
# Commission", which is how Zapier's Automation Strategist reached the digest
# on 2026-10-05. Read from the pay field only: "commission" in body text is too
# often a regulator or an unrelated mention.
COMMISSION_PAY = re.compile(r"\boffers commission\b|\bplus commission\b|\+\s*commission\b", re.I)


class Scored:
    """A listing that survived the hard gates, with its score attached."""

    __slots__ = ("listing", "salary", "geo_class", "geo_reason", "score",
                 "green", "red", "tz_blockers", "tz_friendly", "tier", "notes",
                 "fit_lane", "fit_label", "freedom", "freedom_reasons",
                 "ecosystem", "company_labels", "level", "wall", "form_tag")

    def __init__(self, listing, salary, geo_class, geo_reason, score,
                 green, red, tz_blockers, tz_friendly, tier, notes,
                 fit_lane, fit_label, freedom, freedom_reasons, ecosystem,
                 company_labels=(), level=None, wall=None, form_tag=None):
        self.listing = listing
        # One line from forms.verdict(), set only for roles that reach the digest.
        self.form_tag = form_tag
        self.salary = salary
        self.geo_class = geo_class
        self.geo_reason = geo_reason
        self.score = score
        self.green = green
        self.red = red
        self.tz_blockers = tz_blockers
        self.tz_friendly = tz_friendly
        self.tier = tier
        self.notes = notes
        self.fit_lane = fit_lane
        self.fit_label = fit_label
        self.freedom = freedom
        self.freedom_reasons = freedom_reasons
        self.ecosystem = ecosystem
        self.company_labels = list(company_labels)
        # "entry-friendly", "senior-titled", or None. Carried so digest.rank()
        # can order on it: the seniority penalty lives in `score`, and score is
        # the fifth key in that sort, which made the penalty nearly invisible
        # in the list the operator actually reads.
        self.level = level
        # (height, why) from experience.wall_height, or None until enrich.py
        # has read the page. Only a real posting can answer this: 6 in 10 state
        # no years at all, so the title alone cannot.
        self.wall = wall

    def __repr__(self):
        return (f"<Scored {self.tier} f{self.freedom} {self.fit_lane} "
                f"{self.score} {self.listing.title!r}>")


# Corporate tone is a density signal, not a word. Measured 2026-10-08 on 10,820
# employer postings: "world-class" alone appeared in 1,275 and "best-in-class"
# in 688, well-liked startups included, so a one-word flag hit 21% of the kept
# pool. Three or more DIFFERENT buzzwords in one posting is the tone meant.
CORPORATE_TONE = [re.compile(p, re.I) for p in (
    r"\bworld[- ]class\b", r"\bbest[- ]in[- ]class\b", r"\bthought leadership\b",
    r"\bvalue[- ]add(?:ed)?\b", r"\bdrive alignment\b", r"\bsynerg",
    r"\bstakeholder alignment\b", r"\bparadigm\b", r"\bresults[- ]driven\b",
    r"\bself[- ]starter\b", r"\bdynamic (?:environment|organi[sz]ation)\b",
    r"\bindustry[- ]leading\b", r"\bcore competenc", r"\bmove the needle\b",
)]
CORPORATE_TONE_MIN = 3


def find_flags(text):
    green = [label for pattern, label in _GREEN if pattern.search(text)]
    red = [label for pattern, label in _RED if pattern.search(text)]
    if sum(1 for pattern in CORPORATE_TONE if pattern.search(text)) >= CORPORATE_TONE_MIN:
        red.append("corporate tone")
    return green, red


def find_negatives(text):
    return [label for pattern, label in _NEGATIVE if pattern.search(text)]


def find_ecosystem(text):
    """Anthropic-stack signals, returned as labels so the digest can show why."""
    return [label for pattern, label in _ECOSYSTEM if pattern.search(text)]


def assign_tier(salary, green, red, geo_class, fit_lane=fit.LANE_STRETCH):
    """
    Phase 1 tiering — rules only, no model.

    Two caps, both deliberate:

    - An off-lane role caps at C whatever it pays. This is the rule that stops
      a $240k Associate General Counsel posting reaching S-tier on three
      culture keywords, which is exactly what v1 did on 2026-08-15.
    - Estimated or unstated pay caps at B forever (plan Section 1a): the machine
      is never allowed to sound certain about a number it did not read.
    """
    if fit.is_off_lane(fit_lane):
        return "C"
    if salary.confidence != "published":
        return "B"
    if len(green) >= 3 and not red and geo_class == geo.CLASS_ANYWHERE:
        return "S"
    if len(green) >= 3 and not red:
        return "A"
    if len(green) >= 1 and len(red) <= 1:
        return "A" if geo_class == geo.CLASS_ANYWHERE else "B"
    if red and len(red) > len(green):
        return "C"
    return "B"


def run(listings, logger, pay_floor=PAY_FLOOR):
    """
    Apply every hard gate, then score survivors.

    Returns (kept, rejections) where rejections is a Counter of reasons — the
    counts matter as much as the results, because they show what the machine
    is throwing away and why.
    """
    kept = []
    rejections = Counter()

    for listing in listings:
        blob = listing.searchable

        remote_ok, remote_reason = geo.is_remote(
            listing.region, blob,
            workplace=getattr(listing, "workplace", ""), source=listing.source)
        if not remote_ok:
            rejections[f"not remote ({remote_reason})"] += 1
            continue

        geo_class, geo_reason = geo.classify_geo(listing.region, blob, listing.title)
        if geo_class == geo.CLASS_BLOCKED:
            rejections["region-locked, operator ineligible"] += 1
            continue

        tz_ok, tz_hard, tz_soft, tz_friendly = geo.timezone_verdict(blob)
        if not tz_ok:
            rejections[f"shift work / on-call: {tz_hard[0]}"] += 1
            continue

        if HARD_INCOMPATIBLE.search(blob):
            rejections["requires physical presence or travel"] += 1
            continue

        if COMMISSION_PAY.search(listing.salary_raw or ""):
            rejections["commission pay"] += 1
            continue

        # Structured salary fields beat inline text when a source provides them.
        if listing.salary_min or listing.salary_max:
            low = listing.salary_min or listing.salary_max
            high = listing.salary_max or listing.salary_min
            # A structured field carries no prose, so the OTE wording — when
            # there is any — lives in the raw string and the title beside it.
            # Without this, every OTE posting that also fills its ATS pay fields
            # bypasses the base/OTE split entirely.
            basis, share, split_stated = salary_mod.detect_basis(
                f"{listing.salary_raw or ''} {listing.title}"
            )
            parsed = salary_mod.Salary(
                low=float(low), high=float(high),
                confidence="published", raw=listing.salary_raw or "structured field",
                basis=basis, variable_share=share, split_stated=split_stated,
            )
        else:
            parsed = salary_mod.parse(listing.salary_raw or "")
            if parsed.confidence != "published":
                # Fall back to the description — but anchored on the posting's
                # own compensation section, not on its opening pitch. See
                # salary.parse_description().
                parsed = salary_mod.parse_description(listing.description)

        green, red = find_flags(blob)
        if accessible_title(listing.title):
            green.append(ACCESSIBLE_LABEL)
        # estimate.py computes this to haircut its bands, then throws the label
        # away. Contract terms change take-home materially — a 1099 role carries
        # 15.3% self-employment tax a salaried one does not — so it gets said.
        is_contract = bool(estimate.PART_TIME.search(
            f"{listing.title} {listing.job_type} {listing.description[:500]}"
        ))
        fit_points, fit_lane, fit_label = fit.score(listing.title)
        _, level_tag = fit.seniority(listing.title)
        ecosystem = find_ecosystem(blob)
        company_points, company_labels = company_mod.score(listing.company)
        freedom_score, freedom_reasons = freedom.score(
            geo_class, tz_friendly, tz_soft, green, text=blob,
            fit_label=fit_label,
            large_employer="large employer" in company_labels,
        )

        estimated_from_title = False
        ask_pay_first = False
        if parsed.confidence != "published":
            # Nothing published. Try to estimate a band from the title before
            # giving up — this is the difference between a digest of ~10
            # listings and one that ignores 60% of the market.
            guess, why = estimate.estimate(
                listing.title, listing.description, listing.job_type
            )
            if guess.confidence == "estimated":
                if not estimate.clears_bar(guess, ESTIMATE_FLOOR):
                    writes_freedom = ("async" in freedom_reasons
                                      or "flexible hours" in freedom_reasons)
                    if not (writes_freedom and estimate.clears_bar(
                            guess, FREEDOM_ESTIMATE_FLOOR)):
                        rejections[f"estimated below ${ESTIMATE_FLOOR // 1000}k ({why})"] += 1
                        continue
                    ask_pay_first = True
                parsed = guess
                estimated_from_title = True
            else:
                # Title tells us nothing either. 85% of listings never state
                # pay, so discarding these blinds the search to most of its own
                # market. Keep the ones worth a manual look — strong culture
                # signals OR a title in the operator's lane — and label them
                # honestly as unpriced rather than inventing a number.
                worth_a_look = (
                    len(green) >= MIN_GREEN_FOR_UNPRICED
                    or fit_lane in (fit.LANE_CORE, fit.LANE_ADJACENT)
                )
                if worth_a_look and not red:
                    kept.append(Scored(
                        listing=listing, salary=parsed, geo_class=geo_class,
                        geo_reason=geo_reason,
                        score=(len(green) + geo.geo_score(geo_class) + fit_points
                               + (ECOSYSTEM_BONUS if ecosystem else 0)
                               + (TRAINING_BONUS if training_signals(green) else 0)
                               + company_points),
                        green=green, red=red, tz_blockers=tz_soft,
                        tz_friendly=tz_friendly, tier=TIER_UNPRICED,
                        notes=["pay not stated — ask before applying"],
                        fit_lane=fit_lane, fit_label=fit_label,
                        freedom=freedom_score, freedom_reasons=freedom_reasons,
                        ecosystem=ecosystem, company_labels=company_labels,
                        level=level_tag,
                        # Same reason as the priced branch below. Both paths must
                        # carry it or the gate has a hole shaped like "unpriced".
                        wall=experience.wall_from_text(
                            listing.title, listing.description),
                    ))
                else:
                    # Only count it as a rejection when it actually was one.
                    # v1 incremented this on every unpriced listing including
                    # the ones it kept, which corrupted the footer stats.
                    rejections["no salary stated and role family unrecognised"] += 1
                continue

        if not estimated_from_title and not salary_mod.clears_bar(parsed, pay_floor):
            rejections[f"published salary below ${pay_floor // 1000}k"] += 1
            continue

        negatives = find_negatives(blob)
        pay_bonus = 0
        if parsed.top:
            if parsed.top >= GREAT_PAY:
                pay_bonus = 3
            elif parsed.top >= STRONG_PAY:
                pay_bonus = 2

        # The combination asked for on 2026-09-28: an operator re-entering the
        # market at entry level wants entry-level roles that pay very well.
        #
        # Both halves were already scored, separately and additively, which is
        # not the same thing. Entry-level roles are common and mostly pay
        # badly; well-paid roles are common and mostly want five years. The
        # rare and valuable listing is the one that is BOTH, and an additive
        # score buries it under a senior role that merely pays more. This makes
        # the intersection worth more than its parts.
        entry_and_paid = (
            level_tag == "entry-friendly"
            and parsed.top
            and parsed.top >= STRONG_PAY
        )
        score = (len(green) - len(red) + geo.geo_score(geo_class)
                 + pay_bonus + fit_points
                 + (ENTRY_AND_PAID_BONUS if entry_and_paid else 0)
                 + (BILINGUAL_BONUS
                    if BILINGUAL_LABEL in green and spanish_actually_applies(blob)
                    else 0)
                 + (ECOSYSTEM_BONUS if ecosystem else 0)
                 + (TRAINING_BONUS if training_signals(green) else 0)
                 + company_points
                 - (geo.SOFT_TZ_PENALTY if tz_soft else 0)
                 - NEGATIVE_PENALTY * len(negatives))
        tier = assign_tier(parsed, green, red, geo_class, fit_lane)

        notes = []
        if is_contract:
            # Part-time stopped being a caveat on 2026-09-28: well-paid
            # part-time work became a real option for the operator, judged by
            # monthly income.
            #
            # So it is reported in that unit. The caveat
            # that remains is real and specific: salary.py annualises a
            # published hourly rate at HOURS_PER_YEAR (2080, full-time), with
            # no part-time haircut — estimate.py haircuts its own bands, but a
            # PUBLISHED rate never passes through it. A 20-hour week at $75/hr
            # therefore displays as $156k when it pays $78k. Naming the monthly
            # figure and the assumption beats printing a number that is wrong
            # by a factor of two.
            if parsed.top:
                monthly = parsed.top / 12
                notes.append(
                    f"part-time/contract — about ${monthly:,.0f}/month at the "
                    f"top of band, IF full-time hours; confirm the hours"
                )
            else:
                notes.append("part-time/contract — confirm hours and terms")
        # Say the level out loud. A digest of Senior and Staff titles left the
        # reader to work out alone why none of them felt reachable.
        if BILINGUAL_LABEL in green and spanish_actually_applies(blob):
            notes.append("Spanish is an asset here — far fewer applicants qualify")
        if entry_and_paid:
            notes.append("ENTRY-LEVEL AND PAYS WELL — rare, apply first")
        elif level_tag == "senior-titled":
            notes.append("senior-titled — a stretch, check company size")
        elif level_tag == "entry-friendly":
            notes.append("entry-friendly — takes people without the years")
        if ask_pay_first:
            notes.append(f"pay guess under ${ESTIMATE_FLOOR // 1000}k, kept for its "
                         f"freedom: ASK BASE PAY FIRST")
        elif estimated_from_title:
            notes.append("salary ESTIMATED from title, not published")
        if geo_class == geo.CLASS_US:
            notes.append(geo.geo_tag(geo_class, geo_reason))
        if parsed.converted:
            notes.append(f"converted from {parsed.currency}")
        # High pay is good news, not a caveat. It used to land in the warning
        # line, which read like a problem. The salary is already displayed, so
        # nothing needs saying.
        if tz_soft:
            notes.append(f"fixed hours: {tz_soft[0]}")
        if negatives:
            notes.append(negatives[0])

        kept.append(Scored(
            listing=listing, salary=parsed, geo_class=geo_class,
            geo_reason=geo_reason, score=score, green=green, red=red,
            tz_blockers=tz_soft, tz_friendly=tz_friendly, tier=tier,
            notes=notes, fit_lane=fit_lane, fit_label=fit_label,
            freedom=freedom_score, freedom_reasons=freedom_reasons,
            ecosystem=ecosystem, company_labels=company_labels,
            level=level_tag,
            # Read the experience bar here, from the description the source
            # already handed us, for EVERY listing — not just the 200 that get a
            # page fetched. Added 2026-09-30 after the gate's first live run put
            # 6 roles in an 18-role digest past it untouched, including a
            # mongodb Project Manager asking 5+ years and a Storyblok
            # Documentation Engineer asking 4–5. Both were beyond the enrich cap,
            # so their wall was None, and the gate admits None.
            #
            # A gate that only covers the slice someone remembered to enrich is
            # not a gate. This costs no network: the description arrives with the
            # listing. enrich.py still overwrites this with the page verdict when
            # it reads one, because a full page beats a feed summary.
            wall=experience.wall_from_text(listing.title, listing.description),
        ))

    logger.info("prefilter: %d in, %d kept", len(listings), len(kept))
    for reason, count in rejections.most_common():
        logger.info("  rejected %5d  %s", count, reason)

    return kept, rejections


def is_wildcard(scored):
    """Explicitly hires without prior experience — a high-priority surprise."""
    return (
        "no experience required" in scored.green
        or "training provided" in scored.green
        or "will train" in scored.green
    )


def is_portable(scored):
    """
    Main-lane membership: work from anywhere, and a role the operator would take.

    Core and adjacent listings matched a role pattern by definition, so they
    always qualify. A `stretch` listing has to at least look like a job — that
    check keeps product-directory rows out of the lane read first.
    """
    if fit.is_off_lane(scored.fit_lane):
        return False
    # Home-base plan, 2026-10-05: the operator works remotely from a US home
    # base, with short trips abroad. A US-remote role no longer conflicts with
    # anything, so it joins the main lane. In-lane titles only, as the old US-only section
    # required: stretch there once meant a Canadian Armed Forces posting.
    if scored.geo_class == geo.CLASS_US:
        return scored.fit_lane in (fit.LANE_CORE, fit.LANE_ADJACENT)
    if scored.geo_class != geo.CLASS_ANYWHERE:
        return False
    if scored.fit_lane == fit.LANE_STRETCH:
        return fit.looks_like_a_role(scored.listing.title)
    return True


# is_diamond() removed deliberately. It returned True for anything sourced from
# Hacker News and the digest printed those two entries above every tier, so on
# 2026-08-15 the top slot of the day went to a man advertising his job board.
# Source is not quality.
