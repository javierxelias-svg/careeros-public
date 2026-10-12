"""
The curated list, regenerated from every daily run.

Why this exists as code rather than as a hand-written page: the operator asked
for a list that adds new listings every 24 hours. A page written by hand is
accurate on the day it is written and stale the next morning. This module
rebuilds it from whatever the pipeline found today.

Two kinds of entry, and the difference is shown on the page rather than hidden:

  REVIEWED   analysis written by hand, stored in config/curated-notes.json and
             keyed by company and title. Survives regeneration.
  AUTO       a listing that appeared later. Its offer, pros, cons and questions
             are derived mechanically from the posting text and the flags the
             scorer already computes, and it is labelled "not reviewed yet" so
             a machine-written paragraph is never mistaken for a human one.

The wall is reported, never used to filter. The operator intends to apply to
some roles above the experience they ask for. The machine's job is to say HOW
far above, not to make that call.
"""

import json
import re
from pathlib import Path

import dedupe
import experience
import fit
import geo

ROOT = Path(__file__).resolve().parent.parent
NOTES_PATH = ROOT / "config" / "curated-notes.json"
PINNED_PATH = ROOT / "config" / "curated-pinned.json"
TEMPLATE_PATH = Path(__file__).resolve().parent / "templates" / "curated.html"
DEFAULT_OUT = ROOT / "outputs" / "private" / "thirty-doors.html"

TARGET_COUNT = 60
# EXAMPLE operator setting: the lowest band top the curated page will show.
# Set your own.
PAY_FLOOR = 65_000

# The title families the operator named for themselves. Anything outside them is not a
# curation candidate however well it pays.
FAMILY_PATTERNS = [
    ("solutions", r"\bsolutions?\s+(?:engineer|architect|consultant)\b|\bsales engineer\b|\bpartner solution"),
    ("fde", r"\bforward[- ]deployed\b|\bdeployment strategist\b"),
    ("implementation", r"\bimplementation\b|\bonboarding\b|\bmigration specialist\b|\bprofessional services\b"),
    ("support", r"\bsupport engineer\b|\btechnical support\b|\bcustomer support\b|\bproduct support\b|"
                r"\bsupport (?:specialist|operations)\b|\bcustomer success engineer\b|"
                r"\btechnical account manager\b|\bcustomer engineer\b"),
    ("ai", r"\bai engineer\b|\bapplied ai\b|\bai (?:solutions?|automation)\b|\bagent(?:ic)? engineer\b|"
           r"\bautomation engineer\b|\bintegrations? engineer\b|\bforward deployed researcher\b"),
    ("success", r"\bcustomer success manager\b|\bsuccess manager\b|\bengagement manager\b|"
                r"\baccount manager\b"),
]
_FAMILY = [(name, re.compile(pattern, re.I)) for name, pattern in FAMILY_PATTERNS]

# Titles that contain "manager" but are individual contributor customer-facing
# roles, not people management. Checked FIRST, because the exclusion below ate
# every one of them: on 2026-08-18 several Technical Customer Success Manager
# roles the operator was actively considering vanished from the list. A word in
# a title is not a job description.
IC_MANAGER_TITLE = re.compile(
    r"\b(customer success manager|technical account manager|account manager|"
    r"partner manager|implementation manager|success manager|engagement manager)\b", re.I)

# Roles the operator cannot get and does not want: people management and executive level.
EXCLUDE_TITLE = re.compile(
    r"\b(director|vp|vice president|head of|chief|president|"
    r"people manager|engineering manager|senior manager|manager of|"
    r"manager,)\b|\bmanager$", re.I)

# A title naming a country, a region outside the Americas, or a clearance is a
# door the operator cannot walk through, whatever the company's remote policy says. Elastic
# alone published Mumbai, Sydney, NATO, Federal Civilian and SLED variants of the
# same architect role, and all five ranked before roles the operator could actually take.
LOCKED_TITLE = re.compile(
    r"\b(mumbai|bangalore|india|sydney|australia|singapore|japan|korea|china|"
    r"nato|emea|apac|dach|benelux|nordics|norben|semea|iberia|"
    r"uk|london|ireland|germany|france|spain|poland|israel|sweden|"
    r"federal|sled|public sector|defen[cs]e|clearance|national security)\b", re.I)

# Evidence the page shows as "what they offer", in priority order.
EVIDENCE = [
    ("eor", r"employer of record", "Employs through an employer of record"),
    ("anywhere", r"work from anywhere|from anywhere in the world|we hire globally|"
                 r"no (?:offices|headquarters)|fully (?:remote|distributed)", "Location is not a policy question there"),
    ("americas", r"\bamericas\b|latin america|latam|south america", "Americas scope"),
    ("locationpay", r"location[- ]independent|independent of location|same pay (?:everywhere|regardless)",
     "Pay does not move when you do"),
    ("pto", r"unlimited (?:pto|time off|vacation)|\d{2}\+? days (?:of )?(?:pto|paid time off|vacation)|"
            r"flexible (?:pto|time off|vacation)|generous (?:pto|time off|vacation)", "Time off you can actually take"),
    ("async", r"\basync(?:hronous)?\b|no core hours|flexible (?:hours|working hours)|own your schedule|deep (?:work|focus)",
     "Async or flexible hours"),
    ("equity", r"\bequity\b|stock options|\brsus?\b|\besop\b", "Equity"),
    ("training", r"mentorship|we will train|learning budget|professional development|growth and development",
     "Training or mentorship named"),
    ("stipend", r"home office (?:budget|stipend)|equipment (?:budget|stipend)|co-?working|wellness stipend",
     "Home office or co-working budget"),
]
_EVIDENCE = [(key, re.compile(pattern, re.I), label) for key, pattern, label in EVIDENCE]

# Money that only arrives if a target is met. Separate from salary.py's OTE
# detection because commission can be named without the letters O T E.
VARIABLE_PAY = re.compile(
    r"\bote\b|on[- ]target earnings|\bcommission\b|\bquota\b|variable compensation|"
    r"base \+ variable|sales target", re.I)

# ---------------------------------------------------------------------------
# The life test
#
# The operator's own specification, stated 2026-08-18: six-figure pay for work
# the operator can actually do, time off that can be taken, freedom to move, the operator's own
# schedule, and no golden cage.
#
# Seven tests, all of which must pass. The point is not to filter the list down
# to the survivors, it is to show every role WHICH of the seven it fails, so the
# failures become interview questions instead of surprises after signing.
#
# Measured 2026-08-18 across 63 curated roles: exactly one passed all seven, and
# the rarest property by a distance was a stated flexible schedule (23 of 63).
# That is partly real and partly a measurement artefact: plenty of companies are
# flexible and simply never write it down. So it is reported, never used to hide.
LIFE_PTO = re.compile(
    r"unlimited (?:pto|time off|vacation)|generous (?:pto|time off|vacation)|"
    r"flexible (?:pto|time off|vacation|paid time off)|\d{2}\+? days", re.I)
LIFE_SCHEDULE = re.compile(
    r"\basync(?:hronous)?\b|flexible (?:hours|working hours|schedule)|no core hours|"
    r"own your schedule|craft your calendar|manage your own time", re.I)
LIFE_PAGER = re.compile(
    r"on[- ]call|pager duty|24/7|weekend (?:rotation|coverage)|shift work", re.I)
# A posting that says "no on-call" is advertising the opposite of on-call, and
# reading it as a pager duty inverts the best signal a posting can give the operator.
# Negated mentions are removed before the search rather than matched around.
NO_PAGER = re.compile(
    r"\b(?:no|without|never any|zero|free from)\s+(?:formal\s+|scheduled\s+)?"
    r"(?:on[- ]call|pager(?: duty)?|weekend (?:rotation|coverage)|shift work)", re.I)
SIX_FIGURES = 100_000

# ---------------------------------------------------------------------------
# What a band actually offers the operator
#
# Operator correction, 2026-08-18: a posted six-figure range is not a six-figure
# offer; the top of a US band is usually priced for San Francisco and New York.
#
# Testing the ceiling was the same error as reading on-target earnings as
# salary, one layer down: taking the most optimistic end of a range and calling
# it the number. The top of a posted band belongs to the expensive metros and to
# candidates who have already done the job for pay. The operator lives outside
# those metros and is new to the field.
#
# The model is deliberately crude, because a precise-looking guess would be
# worse than an honest rough one:
#
#   company adjusts pay by location  ->  the floor of the band
#   pay is location independent      ->  lower quartile, no geography penalty
#   nothing stated                   ->  lower quartile
#
# Sanity check: it puts a $75,000-$109,250 support band at $83,562, close to an
# independent hand estimate of a realistic first offer.
GEO_ADJUSTED = re.compile(
    r"geo(?:graphic)? (?:range|differential|pay)|location[- ]adjusted|"
    r"cost of (?:labor|living)|varies by location|location factor|"
    r"pay (?:range|band)s? (?:by|per) (?:location|country|region)|"
    r"depending on (?:your )?location", re.I)
LOCATION_INDEPENDENT = re.compile(
    r"location[- ]independent|independent of location|"
    r"same (?:pay|rate) (?:everywhere|regardless)", re.I)
LOWER_QUARTILE = 0.25


def likely_offer(role, text=""):
    """(number, why) — what the band is likely to mean for the operator, not its ceiling."""
    low, high = role.get("lo") or 0, role.get("hi") or 0
    if not high:
        return 0, "no band published"
    if LOCATION_INDEPENDENT.search(text or ""):
        return round(low + LOWER_QUARTILE * (high - low)), "lower quartile, and the band does not move if you do"
    if GEO_ADJUSTED.search(text or ""):
        return low, "the floor: this company sets pay by location, and yours is a cheap one"
    return round(low + LOWER_QUARTILE * (high - low)), "lower quartile, since the top of a band is for expensive cities and people who have done the job for pay"


def life_test(role, text):
    """Seven booleans, in the operator's terms. All must pass."""
    return {
        "Six figures": (role.get("likely") or likely_offer(role, text)[0]) >= SIX_FIGURES,
        "Time off you can take": bool(LIFE_PTO.search(text or "")),
        "Your own schedule": bool(LIFE_SCHEDULE.search(text or "")),
        "Nothing follows you home": not LIFE_PAGER.search(NO_PAGER.sub(" ", text or "")),
        "Move without asking": role["port"] != "ask",
        "All base, no quota": not role["variable"],
        "Reachable today": role["wall"] <= 1,
    }


# How much the operator would be stretching, by how high the bar is set. Say
# how much, in plain terms, per role.
# Re-keyed 2026-09-30 to the new wall scale in experience.py. The curated page
# keeps showing all five heights even though the DIGEST now filters 4 and 5 out:
# the page is the place the operator goes deliberately to look at the stretch,
# the digest is what arrives whether asked or not. Filter the push, keep the
# pull.
WING = {
    experience.UNREADABLE: ("Bar unknown",
        "This posting would not load without JavaScript, so nothing here read its "
        "requirements. Open the link before deciding anything."),
    0: ("Apply as you are",
        "Nothing here to wing. No years demanded and no level in the title."),
    1: ("Apply as you are",
        "Architect or Manager in the title is the shape of the role, not a level, and "
        "no number is asked. Nothing here to wing."),
    6: ("Level, not years",
        "The title claims senior but the posting names no number, so the bar is "
        "judgement rather than arithmetic. That is the kind you can argue with "
        "evidence — and the digest no longer sends these, by operator decision on "
        "2026-09-30. The page still shows them."),
    2: ("Apply as you are",
        "One year asked, which you can answer honestly. Attach something running."),
    3: ("Small stretch",
        "Two to three years asked. Your practice is deeper than most three-year resumes. "
        "Say that plainly and attach something running."),
    4: ("Lottery ticket",
        "Staff or principal in the title. That is a claim about scope you have not had "
        "yet, not about years, and no demo closes it. Send it last if at all."),
    5: ("Real stretch",
        "Four or more years asked. This is a genuine gap. Worth sending with a demo "
        "attached, and worth expecting silence more often than not."),
}


# A city, region or office bolted onto a title. Cloudflare posts the SAME Senior
# Customer Engineer role fourteen times, once per city, and on 2026-08-18 those
# fourteen rows filled half the page. The role is one role; the city is a filing
# detail. Grafana does the same with East Coast and West Coast, Ashby with
# Americas East and West.
LOCATION_WORD = re.compile(
    r"^(?:remote|hybrid|onsite|in[- ]office|"
    r"nyc|new york|ny|san francisco|sf|bay area|los angeles|la|seattle|austin|chicago|boston|"
    r"denver|atlanta|miami|dallas|houston|phoenix|detroit|raleigh|charlotte|cincinnati|"
    r"minneapolis|philadelphia|nashville|portland|san diego|salt lake city|"
    r"toronto|vancouver|calgary|montreal|ottawa|"
    r"london|dublin|berlin|munich|paris|madrid|barcelona|amsterdam|lisbon|warsaw|krakow|"
    r"stockholm|copenhagen|zurich|milan|rome|"
    r"sydney|melbourne|auckland|tokyo|osaka|seoul|singapore|hong kong|shenzhen|beijing|"
    r"shanghai|bangalore|mumbai|delhi|tel aviv|dubai|"
    r"east coast|west coast|central us|east|west|central|"
    r"est|pst|cst|mst|utc|usa|u\.s\.|us|uk|canada|"
    r"[a-z]{2})$",   # trailing state or province code, as in "Charlotte, NC"
    re.I)
_SPLIT = re.compile(r"\s*[|(),\u2013-]\s*")


def base_title(title):
    """
    The role without its city or region suffix, for deduplication.

    Trailing segments are dropped while they read as locations. "Americas" and
    "AMER" are NOT in the vocabulary: those describe who the operator could be
    employed by, which is the whole point of the search, so they stay.
    """
    if not title:
        return ""
    parts = [p for p in _SPLIT.split(title.strip()) if p]
    while len(parts) > 1 and LOCATION_WORD.match(parts[-1].strip()):
        parts.pop()
    return " - ".join(parts).strip() or title


def slug(company, title):
    """Stable key for hand-written notes. Survives small title edits."""
    text = f"{company}|{title}".lower()
    return re.sub(r"[^a-z0-9|]+", "-", text).strip("-")


def is_management(title):
    """
    True for people management and executive titles.

    Not a raw regex test: "Technical Account Manager" and "Customer Success
    Manager" both match the exclusion and are both rescued, because the word
    manager in those titles describes a customer relationship, not a team.
    """
    if not title:
        return False
    return bool(EXCLUDE_TITLE.search(title)) and not IC_MANAGER_TITLE.search(title)


def family_of(title):
    for name, pattern in _FAMILY:
        if pattern.search(title or ""):
            return name
    return None


def portability(item, text):
    """
    "yes" the posting or the company already solves it, "americas" the region
    covers the operator's home region (the Americas), "ask" the posting is silent.

    Silent is not no. It is the first question of the first call.
    """
    if re.search(r"employer of record|work from anywhere|we hire globally|"
                 r"location[- ]independent|no offices", text or "", re.I):
        return "yes"
    if item.geo_class == geo.CLASS_ANYWHERE:
        return "yes"
    if re.search(r"\bamericas\b|latin america|latam|north america", text or "", re.I):
        return "americas"
    return "ask"


def offers_from(text):
    return [label for _key, pattern, label in _EVIDENCE if pattern.search(text or "")]


def auto_notes(item, role):
    """
    Mechanical analysis for a listing that arrived after the hand-written pass.

    Honest rather than clever: it repeats what the posting and the scorer
    already established, and says so. Anything it cannot know it turns into a
    question for the first call instead of a claim.
    """
    green = [g for g in item.green][:4]
    red = [r for r in item.red][:3]
    pros = []
    if role["wall"] == 0:
        pros.append("No years requirement and no level in the title")
    if role["conf"] == "published":
        pros.append("Pay published on the posting rather than estimated")
    if role["port"] != "ask":
        pros.append("Portable, or close enough that one question settles it")
    pros += [f"Scored on: {g}" for g in green[:2]]

    cons = []
    if role["variable"]:
        cons.append("Mentions variable pay or commission. Confirm the split before anything else")
    if role["wall"] >= 3:
        cons.append(f"Real stretch. Posting says: {role['wallWhy'] or 'experience required'}")
    if role["conf"] != "published":
        cons.append("Pay is estimated from the title, not published")
    cons += [f"Flagged: {r}" for r in red[:2]]

    return {
        "reviewed": False,
        "offer": offers_from(role["_text"]) or ["Nothing beyond the basics stated in the posting"],
        "pros": pros[:4] or ["In your lane by title"],
        "cons": cons[:4] or ["Nothing obvious, which usually means the posting is thin"],
        "angle": "Not reviewed yet. Read the posting, then lead with the pairing: you build the "
                 "thing and you can explain it to the person signing the cheque.",
        "ask": "“If I moved elsewhere in the Americas in about a year, could you keep employing me, "
               "directly or through an employer of record?”",
    }


def fit_score(role):
    """Rank for the plan, not for the salary."""
    score = min(role.get("likely") or role["hi"], 180_000) / 1000 * 0.25
    score += 35 if role["conf"] == "published" else 0
    score += 26 if role["lane"] == fit.LANE_CORE else 10
    # Re-keyed 2026-09-30 with the wall scale. UNREADABLE scores like a senior
    # title and no number: the page might say anything, so it neither earns the
    # clean bonus nor takes the stretch penalty.
    score += {experience.UNREADABLE: 26,
              0: 42, 1: 38, 2: 38, 3: 20, 4: 0, 5: 6, 6: 26}[role["wall"]]
    # A bonus alone was not enough: a $256k role asking five years still outranked
    # a door the operator could walk through today, because pay and freedom made
    # the gap back. Year one needs a job that is actually gettable, so a high wall costs points
    # rather than merely failing to earn them.
    score -= {experience.UNREADABLE: 0,
              0: 0, 1: 0, 2: 0, 3: 0, 4: 26, 5: 16, 6: 0}[role["wall"]]
    score += role["freedom"] * 4
    score += {"yes": 30, "americas": 18, "ask": 0}[role["port"]]
    score -= 34 if role["variable"] else 0
    score += 10 if role["reviewed"] else 0
    score += 5 * role.get("lifeScore", 0)
    return round(score, 1)


def build(items, notes=None, target=TARGET_COUNT, pinned=None):
    """Scored listings in, ranked curated roles out."""
    notes = notes if notes is not None else load_notes()
    pinned = pinned if pinned is not None else load_pinned()
    seen, roles = set(), []

    # This function collapses "(West)" and "(East)" onto one family_key, which
    # is right — one job, one row. Which copy wins was arrival order, which is
    # not. One employer listed the same Implementation Specialist role as both,
    # identical but for the timezone each seat requires; for an operator on the
    # US East Coast the PST/MST seat is a late workday and the EST/CST one is
    # normal. On 2026-08-19 the page showed West. A stable sort by timezone fit puts the right seat first, and
    # leaves every unmarked posting exactly where it was.
    items = sorted(items, key=dedupe._timezone_penalty)

    for item in items:
        listing = item.listing
        title = listing.title or ""
        if fit.is_off_lane(item.fit_lane) or is_management(title):
            continue
        if LOCKED_TITLE.search(title):
            continue
        family = family_of(title)
        if family is None:
            continue
        salary = item.salary
        if not salary.top or salary.top < PAY_FLOOR:
            continue
        low = salary.base_low or salary.base_high or 0
        high = salary.base_high or salary.base_low or 0
        if low > high:
            # Fivetran published $134,000-$111,714 on 2026-08-18. Read in order
            # that is a band whose floor is above its ceiling, and every number
            # derived from it, the likely offer most of all, comes out wrong.
            low, high = high, low
        if low and low < 40_000:
            continue
        # Deduplicate on the role, not on the city it was filed under.
        key = slug(listing.company, title)
        family_key = slug(listing.company, base_title(title))
        if key in seen or family_key in seen:
            continue
        seen.add(key)
        seen.add(family_key)

        text = getattr(listing, "description", "") or ""
        height, why, _years = experience.wall_height(title, text)
        role = {
            "key": key,
            "t": title,
            "c": listing.company,
            "url": getattr(listing, "url", ""),
            "fam": family,
            "lo": round(low),
            "hi": round(high),
            "conf": salary.confidence,
            "basis": salary.basis,
            "ote": ({"lo": round(salary.low), "hi": round(salary.high),
                     "note": ("split published by the company" if salary.split_stated
                              else "80/20 assumed, split not published")}
                    if salary.is_ote else None),
            "wall": height,
            "wallWhy": why,
            "wing": {"label": WING[height][0], "line": WING[height][1]},
            "lane": item.fit_lane,
            "freedom": item.freedom,
            "port": portability(item, text),
            "variable": bool(VARIABLE_PAY.search(text)) or bool(salary.is_ote),
            "_text": text,
        }
        role["likely"], role["likelyWhy"] = likely_offer(role, text)
        role["life"] = life_test(role, text)
        role["lifeScore"] = sum(role["life"].values())
        note = notes.get(key)
        role["reviewed"] = bool(note)
        role.update(note or auto_notes(item, role))
        role["fit"] = fit_score(role)
        roles.append(role)

    roles.sort(key=lambda r: (-r["fit"], r["c"]))
    roles = merge_pinned(roles[:target], pinned)
    roles.sort(key=lambda r: (-r["fit"], r["c"]))
    for role in roles:
        role.pop("_text", None)
    return roles


def load_pinned(path=PINNED_PATH):
    """Roles carried forward from earlier sessions. Optional file."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return data if isinstance(data, list) else []


def merge_pinned(roles, pinned):
    """
    Add pinned roles the live pool did not return.

    A pinned role the pool DID return is dropped in favour of the live one, whose
    pay and wall reading are today's rather than last week's.
    """
    live = {role["key"] for role in roles}
    for entry in pinned:
        key = entry.get("key") or slug(entry.get("c", ""), entry.get("t", ""))
        if key in live:
            continue
        entry = dict(entry)
        entry["key"] = key
        entry["pinned"] = True
        entry.setdefault("reviewed", True)
        if "likely" not in entry:
            entry["likely"], entry["likelyWhy"] = likely_offer(entry, entry.get("text", ""))
        if "life" not in entry:
            entry["life"] = life_test(entry, entry.get("text", ""))
        entry["lifeScore"] = sum(entry["life"].values())
        if "wing" not in entry:
            label, line = WING[entry.get("wall", 1)]
            entry["wing"] = {"label": label, "line": line}
        entry["fit"] = fit_score(entry)
        roles.append(entry)
    return roles


def load_notes(path=NOTES_PATH):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def render(roles, meta, out_path=DEFAULT_OUT, template_path=TEMPLATE_PATH):
    """Write the page. The template owns the design; this owns the data."""
    template = Path(template_path).read_text(encoding="utf-8")
    page = template.replace("__ROLE_DATA__", json.dumps(roles, ensure_ascii=False))
    page = page.replace("__META_DATA__", json.dumps(meta, ensure_ascii=False))
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    return out


def run(items, logger=None, out_path=DEFAULT_OUT, scanned=0, built=None):
    """Called by run_daily after the digest. Never allowed to break the run."""
    from datetime import datetime
    roles = build(items)
    reviewed = sum(1 for r in roles if r["reviewed"])
    meta = {
        "built": built or datetime.now().strftime("%-d %B %Y"),
        "lifePass": sum(1 for r in roles if r.get("lifeScore") == 7),
        "lifeNear": sum(1 for r in roles if r.get("lifeScore") == 6),
        "scanned": scanned,
        "count": len(roles),
        "reviewed": reviewed,
        "auto": len(roles) - reviewed,
    }
    path = render(roles, meta, out_path=out_path)
    if logger:
        logger.info("curated list: %d roles (%d reviewed, %d auto) -> %s",
                    len(roles), reviewed, len(roles) - reviewed, path)
    return path, meta
