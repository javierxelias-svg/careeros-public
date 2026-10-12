"""
Stage 2: open the job page.

Every source in this pipeline hands over a summary, not a posting. WeWorkRemotely
truncates its RSS description before the compensation block; RemoteOK writes 0
for unknown pay. So the machine estimated salaries from job titles, and on
2026-08-17 a spot-check against the live pages found the estimates wrong in one
direction every time — three of three too high, one by 2.3x, presenting a
$48,000-$65,000 role as "~$109,000-$151,000" inside the operator's target band.

The same check found the opposite failure. Four of eight listings published a
real salary on the page while the digest said "pay not stated", including a
Vercel role at $208,000-$312,000. See verification/2026-08-17-pool-spotcheck.md.

The premise in estimate.py — "85% of listings never state pay" — was measuring
the feed, not the market. The pay is usually there. Nobody was opening the page.

Three things come back that nothing else can supply:

  1. The published salary, which retires the estimate and unlocks a real tier.
  2. Location locks written in the body. "Based in EMEA" is invisible to
     geo.title_region_lock(), which can only read the title.
  3. Whether the employer will actually permit living in another country. This
     is the operator's stated first requirement and the pipeline had no notion of it: a
     feed that says "Anywhere in the World" is a category, not a work permit.

Only listings that already cleared the hard gates and the ledger get fetched, and
only the top ENRICH_LIMIT of those by rank. Anything skipped is logged and
counted, never silently dropped.
"""

import hashlib
import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

import experience
import fit
import geo
import prefilter
import salary as salary_mod
from _shared.paths import STATE_DIR

# Raised from 30 to 200 on 2026-09-28.
#
# The old value was correct when it was written: "on 2026-08-17 the pool
# reaching this stage was 8-26 listings, so 30 covers a normal morning with
# room to spare." The pool is no longer 8-26. The 2026-09-28 run logged
# "enrich: 30 pages read, 2062 beyond the cap of 30" — so 2,062 listings were
# ranked on their feed summary alone, and the three things only this module can
# establish went unchecked on all of them:
#
#   the published salary, which retires an estimate and unlocks a real tier;
#   location locks written in the body, invisible to a title-only check;
#   whether the employer will actually permit living in another country.
#
# That last one is the operator's stated first requirement, so a cap that skips it on 98%
# of the pool was not a performance setting, it was a silent quality ceiling.
#
# 200 is sized against the budget that now applies rather than the laptop that
# used to: the GitHub Actions job allows 30 minutes and the 2026-09-28 cloud run
# finished in 4m31s. At roughly 1.5s per page — POLITENESS_DELAY plus fetch —
# 200 pages adds about five minutes, landing near ten. The footer still reports
# anything beyond the cap, so the next time this number goes stale it says so
# out loud instead of waiting six weeks to be noticed.
ENRICH_LIMIT = 200

# Temporary work from abroad, added 2026-10-05 with the home-base plan.
TEMP_ABROAD_LABEL = "work-abroad weeks"
TEMP_ABROAD = re.compile(
    r"\bwork(?:ing)?\s+from\s+(?:anywhere|abroad)\s+(?:for\s+)?(?:up\s+to\s+)?"
    r"\d+\s+(?:weeks?|days?|months?)\b|"
    r"\b\d+\s+(?:weeks?|days?)\s+(?:of\s+|a\s+year\s+)?"
    r"(?:work(?:ing)?\s+from\s+(?:anywhere|abroad)|wfa)\b|"
    r"\bworkations?\b|"
    r"\bwork(?:ing)?[- ](?:from[- ])?abroad\s+(?:policy|program|allowance|weeks?)\b",
    re.I,
)
REQUEST_TIMEOUT = 20
POLITENESS_DELAY = 1.0
CACHE_TTL_SECONDS = 60 * 60 * 24 * 3
MAX_PAGE_BYTES = 2_000_000

CACHE_DIR = STATE_DIR / "pages"

_TAG = re.compile(r"<(?:script|style)[^>]*>.*?</(?:script|style)>", re.I | re.S)
_MARKUP = re.compile(r"<[^>]+>")
_SPACE = re.compile(r"\s+")

# A figure with a currency on it. Symbol OR three-letter code: MailerLite writes
# "Yearly gross salary range: USD 48,000 - 65,000" with no symbol anywhere, and a
# symbol-only pattern read that page as stating no salary at all.
_CURRENCY = (
    r"(?:[\$€£]|\b(?:usd|eur|gbp|cad|aud|chf|sek|nok|dkk|pln|inr|brl|mxn)\b)"
)
# Must END on a digit or a k. Written as \d[\d,.]* it swallowed the full stop in
# "$140,000. Glassdoor estimate: $200,000", so the match ran on into the next
# sentence and dragged that sentence's estimate language in with it — which then
# disqualified a perfectly good published range.
_AMOUNT = r"\s?\d(?:[\d,.]*\d)?\s?[kK]?"

# Pay sentences. Anchored on a money word so a random "$50" in a benefits list
# does not become the salary, and bounded so the match cannot run across the
# whole page into an unrelated figure.
PAY_SENTENCE = re.compile(
    r"(?:base (?:pay|salary|compensation)|salary range|compensation range|"
    r"pay range|salary|compensation|base|pay|rate|we (?:pay|offer))"
    r"[^.!?\n]{0,140}?"
    + _CURRENCY + _AMOUNT
    + r"(?:\s*(?:-|–|—|to)\s*" + _CURRENCY + r"?" + _AMOUNT + r")?"
    r"[^.!?\n]{0,40}",
    re.I,
)

# The operator can live in another country. Every pattern here has to describe the
# EMPLOYMENT RELATIONSHIP, not a sentiment about remote work, because the text
# being searched includes the job board's own page furniture.
#
# "digital nomad" was in this list for one run and fired on RemoteOK's navigation
# menu — "🌍 Become a digital nomad" — which tagged a coffee roaster and a retail
# "Team Member" as roles workable from another continent. Board marketing copy is not an
# employer commitment. Anything that reads like a headline stays out; only
# sentences a company writes about who it can legally pay belong here.
ABROAD_YES = [
    (r"\bwe (?:can )?hire (?:from )?(?:anywhere|globally|worldwide|in any country)\b|"
     r"\bhiring (?:globally|worldwide|in any country)\b|"
     r"\bwe employ people (?:anywhere|globally|worldwide)\b", "hires globally"),
    (r"\bemployer of record\b|\bthrough an eor\b|"
     r"\b(?:via|through|using) (?:deel|remote\.com|oyster|multiplier|papaya|"
     r"velocity global|globalization partners)\b", "employer of record"),
    (r"\byou (?:can|may) (?:work|live) (?:from )?(?:any(?:where|\s?country)|"
     r"wherever you want)\b|"
     r"\bwork from any country\b|\blive and work (?:from )?anywhere\b",
     "works from any country"),
    (r"\bwe (?:are|'re) timezone[- ]agnostic\b|\bany time ?zone is (?:fine|welcome)\b|"
     r"\bno timezone requirement\b", "any timezone"),
    (r"\bno restriction on (?:your )?location\b|"
     r"\bwe do not (?:restrict|limit) where you live\b", "no location restriction"),
]

# These override any "anywhere" claim. A residency requirement decides whether
# living abroad is possible at all, and with it any tax treatment that depends
# on where the work is performed.
ABROAD_NO = [
    (r"\bmust (?:reside|be located|live|be based|be a resident)\b[^.]{0,60}"
     r"\b(?:u\.?s\.?a?|united states|america)\b", "requires US residence"),
    (r"\bu\.?s\.?\s*(?:based|residents?|resident)\s*(?:only|required)?\b", "US residents only"),
    (r"\b(?:authorized|authorised|eligible) to work in the u\.?s\.?a?\b", "US work authorisation"),
    (r"\bw-?2 (?:only|employees? only)\b", "W-2 only"),
    (r"\bno (?:international|overseas) (?:applicants?|candidates?|hires?)\b",
     "no international hires"),
    (r"\bmust (?:reside|be located|live|be based)\b[^.]{0,60}"
     r"\b(?:eu|europe|emea|uk|canada|latam|apac|australia|india)\b",
     "requires non-US residence"),
    (r"\bcannot (?:hire|employ)\b[^.]{0,60}\boutside\b", "cannot hire outside region"),
    (r"\bthis role (?:is|must be) (?:based|located) in\b", "role is location-based"),
]

# Everything past this is somebody else's job. Deliberately narrow: "Other Jobs",
# "More Jobs" and "Latest Jobs" were in this list for one run and they are
# NAVIGATION links — on a WeWorkRemotely page "All Other Jobs" sits 14% of the way
# in, so the posting itself was being thrown away and every real salary vanished
# from the digest. Only phrases that introduce a recommendations rail belong here.
RELATED_BOUNDARY = re.compile(
    r"\b(?:related jobs?|similar jobs?|recommended jobs?|"
    r"jobs you (?:might|may) like|you might also (?:like|be interested)|"
    r"apply to similar|similar positions?|related positions?)\b",
    re.I,
)

# Sources whose job page is ONE posting, so a salary found on it belongs to the
# job being looked at.
#
# This is an allowlist because the alternative failed on real data. An aggregator
# serves the posting plus a rail of other companies' jobs and, in Jobicy's case,
# its own invented "estimated US market range". Reading pay off those pages
# published PolicyMe's CAD 221,800-300,100 as an ecosio salary on 2026-08-17.
#
# The aggregators that are excluded here mostly do not need it: Jobicy states pay
# in its feed on 52% of listings and Himalayas gives minSalary/maxSalary directly,
# so their numbers arrive structured and trustworthy through sources.py. It is
# WeWorkRemotely — which publishes no salary field at all — whose page has to be
# read, and its pages reproduce the employer's posting in full.
PAGE_SALARY_SOURCES = frozenset({
    "weworkremotely_all",
    "weworkremotely_programming",
    # An employer's own ATS page is the single-posting case by definition. There
    # is no rail of other companies' jobs on it and nobody has injected a market
    # estimate into it, which makes it the most trustworthy page in the pipeline.
    "ats",
})

# A figure the site worked out for itself is not a figure the employer published.
# Jobicy prints an "estimated US market range" inside the posting body, which
# would otherwise be promoted to confidence="published" — the exact dishonesty
# the estimate/published split exists to prevent.
ESTIMATE_LANGUAGE = re.compile(
    r"\b(?:estimated?|estimates?|market range|market rate|typical(?:ly)?\s+"
    r"(?:pays|range|salary)|glassdoor|levels\.fyi|payscale|our data|we estimate|"
    r"projected|industry average|comparable roles?)\b",
    re.I,
)

_PAY_MIN = 30_000
_PAY_MAX = 900_000

_ABROAD_YES = [(re.compile(p, re.I), label) for p, label in ABROAD_YES]
_ABROAD_NO = [(re.compile(p, re.I), label) for p, label in ABROAD_NO]


def _cache_path(url):
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:32]
    return CACHE_DIR / f"{digest}.json"


def _read_cache(url, now):
    path = _cache_path(url)
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(record, dict):
        return None
    if now - float(record.get("fetched_at") or 0) > CACHE_TTL_SECONDS:
        return None
    return record.get("text")


def _write_cache(url, text, now):
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _cache_path(url).write_text(
            json.dumps({"url": url, "fetched_at": now, "text": text}),
            encoding="utf-8",
        )
    except OSError:
        pass  # A cache that cannot be written is a slower run, not a failed one.


def page_text(url, user_agent, now=None, sleep=True):
    """
    Return the page as plain text, or None.

    Never raises. A job board that rate-limits, redirects oddly or serves
    JavaScript must degrade this stage to a no-op, not take down the digest.
    """
    if not isinstance(url, str) or not url.lower().startswith(("http://", "https://")):
        return None

    now = time.time() if now is None else now
    cached = _read_cache(url, now)
    if cached is not None:
        return cached

    try:
        request = urllib.request.Request(
            url, headers={"User-Agent": user_agent, "Accept": "*/*"}
        )
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            body = response.read(MAX_PAGE_BYTES)
    except (urllib.error.URLError, urllib.error.HTTPError, OSError,
            TimeoutError, ValueError):
        return None
    finally:
        if sleep:
            time.sleep(POLITENESS_DELAY)

    text = body.decode("utf-8", errors="replace")
    text = _TAG.sub(" ", text)
    text = _MARKUP.sub(" ", text)
    import html as html_mod
    text = html_mod.unescape(text)
    text = _SPACE.sub(" ", text).strip()

    _write_cache(url, text, now)
    return text


def posting_only(text):
    """
    Cut the page where the posting ends and the recommendations begin.

    An aggregator serves one job and then a rail of other people's jobs. On
    2026-08-17 an ecosio listing was published with CAD 221,800-300,100 lifted
    from a PolicyMe role further down the same page.
    """
    if not text:
        return ""
    boundary = RELATED_BOUNDARY.search(text)
    return text[:boundary.start()] if boundary else text


def find_salary(text, currency_hint=None):
    """
    The employer's own published salary, or UNKNOWN.

    Takes the FIRST plausible band in document order, not the largest. Taking
    the largest was a bug: it made the function seek out the most attractive
    number anywhere on the page, which on an aggregator is reliably a different
    company's job. The posting's own figure comes first; everything after the
    recommendations rail belongs to someone else.

    Sentences carrying estimate language are refused outright. A site's own
    guess must never be promoted to confidence="published" — that would put the
    invented numbers straight back into the digest through a new door.
    """
    if not text:
        return salary_mod.UNKNOWN

    body = posting_only(text)
    for sentence in PAY_SENTENCE.findall(body)[:12]:
        if ESTIMATE_LANGUAGE.search(sentence):
            continue
        parsed = salary_mod.parse(sentence, currency_hint=currency_hint)
        if parsed.confidence != "published":
            continue
        top = parsed.top or 0
        if _PAY_MIN <= top <= _PAY_MAX:
            return parsed
    return salary_mod.UNKNOWN


def abroad_verdict(text):
    """
    Return (verdict, reasons) where verdict is True, False or None.

    True  — the posting says the employee can live in another country.
    False — the posting requires residence somewhere specific.
    None  — the posting does not say, which is not permission.

    A residency requirement beats a work-from-anywhere claim. Boards and
    companies both write "remote, work from anywhere" in a headline and "must
    reside in the US" in the fine print, and the fine print is the one that
    decides whether living abroad is actually allowed.
    """
    if not text:
        return None, []

    blocked = [label for pattern, label in _ABROAD_NO if pattern.search(text)]
    if blocked:
        return False, blocked

    allowed = [label for pattern, label in _ABROAD_YES if pattern.search(text)]
    if allowed:
        return True, allowed

    return None, []


def reconsider(scored, text):
    """
    Rewrite a Scored in place from what the page actually says.

    Returns a list of change descriptions, for the log. Four things can change:
    the salary and its tier, the geo class, the abroad verdict, and the score.
    """
    changes = []
    if not text:
        return changes

    # 1. Real pay retires the estimate — but only from a page that is one job.
    published = salary_mod.UNKNOWN
    if scored.listing.source in PAGE_SALARY_SOURCES:
        published = find_salary(text, currency_hint=scored.salary.currency)
    if published.confidence == "published":
        was = scored.salary
        if was.confidence != "published":
            scored.salary = published
            scored.notes = [
                n for n in scored.notes
                if "ESTIMATED from title" not in n and "pay not stated" not in n
            ]
            changes.append(
                f"pay {was.display()} ({was.confidence}) -> {published.display()} (page)"
            )
            if was.confidence == "estimated" and (was.top or 0) > (published.top or 0):
                gap = (was.top or 0) - (published.top or 0)
                changes.append(f"estimate was ${gap:,.0f} too high")

    # 2. A location lock written in the body, past the reach of the title check.
    body_class, body_reason = geo.classify_geo("", text[:6000], "")
    if (scored.geo_class == geo.CLASS_ANYWHERE
            and body_class == geo.CLASS_BLOCKED):
        scored.geo_class = body_class
        scored.geo_reason = f"page: {body_reason}"
        scored.freedom_reasons = [
            r for r in scored.freedom_reasons if r != "work from anywhere"
        ]
        changes.append(f"geo A -> {body_class} ({body_reason})")

    # 2b. A short work-from-abroad allowance. Under the home-base plan this is
    # the thing the operator asks for: a few weeks abroad, then home.
    if TEMP_ABROAD.search(text) and TEMP_ABROAD_LABEL not in scored.green:
        scored.green = list(scored.green) + [TEMP_ABROAD_LABEL]
        changes.append("work-abroad weeks")

    # 3. Can the employee live in another country? The operator's first requirement.
    verdict, reasons = abroad_verdict(text)
    if verdict is True:
        if "works from another country" not in scored.green:
            scored.green = list(scored.green) + ["works from another country"]
        changes.append(f"abroad: yes ({reasons[0]})")
    elif verdict is False:
        scored.notes = list(scored.notes) + [f"cannot work abroad: {reasons[0]}"]
        if scored.geo_class == geo.CLASS_ANYWHERE:
            scored.geo_class = geo.CLASS_US
            scored.geo_reason = f"page: {reasons[0]}"
            scored.freedom_reasons = [
                r for r in scored.freedom_reasons if r != "work from anywhere"
            ]
        changes.append(f"abroad: NO ({reasons[0]})")

    # 4. How high is the bar, really. The operator asked on 2026-09-29 whether the
    # titles demand more experience than they sound like they do; the answer
    # turned out to run both ways, so it is reported per role instead of
    # guessed. Only readable here — 6 in 10 postings state no number, and the
    # title alone cannot tell the difference between a wall and a flourish.
    #
    # The page is NOT the only source, and assuming it was cost a day. Ashby and
    # Greenhouse serve their job pages as JavaScript shells — 187 of 532 cached
    # pages say only "You need to enable JavaScript to run this app" — so the
    # first version of the gate marked Supabase, Elastic, MongoDB, Render and
    # Replit roles "bar unknown" and let all of them through. Measured 2026-09-30:
    # 951 of 952 listings from those same boards carry a FULL description from
    # the ATS API, median 9,035 characters, because ats.py already reads
    # Ashby's descriptionPlain and Greenhouse's content. The text was in hand the
    # whole time; only the HTML was missing.
    #
    # Deliberately narrow: the fallback feeds the WALL and nothing else. Salary,
    # geo and the abroad verdict above were all tuned against page text, and
    # swapping their input wholesale would change three tested behaviours to fix
    # one. Widen it only with measurements for each.
    wall_text = text
    wall_source = "page"
    if not experience.page_is_readable(wall_text):
        wall_text = scored.listing.description or ""
        wall_source = "ATS description"
    height, why, years = experience.wall_from_text(scored.listing.title, wall_text)
    scored.wall = (height, why, years)
    if wall_source != "page" and height != experience.UNREADABLE:
        changes.append(f"wall read from the ATS description, page was a JS shell")
    admitted, reason = experience.admits(height, years)
    if not admitted:
        changes.append(f"BLOCKED, {reason}: {why[:60]}")
    elif height == experience.UNREADABLE:
        changes.append("wall unknown, page needs JavaScript")

    # 5. Re-tier and re-score on the corrected facts.
    scored.tier = prefilter.assign_tier(
        scored.salary, scored.green, scored.red, scored.geo_class, scored.fit_lane
    )
    scored.freedom, scored.freedom_reasons = _rescore_freedom(scored, text)
    scored.score = _rescore(scored)
    return changes


def _rescore_freedom(scored, text):
    import freedom
    # The page is the fuller copy of the posting, so its written evidence wins
    # over the feed's excerpt.
    return freedom.score(
        scored.geo_class, scored.tz_friendly, scored.tz_blockers, scored.green,
        text=f"{scored.listing.searchable}\n{text}", fit_label=scored.fit_label,
        large_employer="large employer" in (scored.company_labels or []),
    )


def _rescore(scored):
    """Recompute the prefilter score from the corrected salary and geo class."""
    import company as company_mod
    pay_bonus = 0
    if scored.salary.top:
        if scored.salary.top >= prefilter.GREAT_PAY:
            pay_bonus = 3
        elif scored.salary.top >= prefilter.STRONG_PAY:
            pay_bonus = 2
    company_points, _ = company_mod.score(scored.listing.company)
    return (len(scored.green) - len(scored.red)
            + geo.geo_score(scored.geo_class)
            + pay_bonus
            + fit.LANE_SCORE.get(scored.fit_lane, 0)
            + (prefilter.ECOSYSTEM_BONUS if scored.ecosystem else 0)
            + (prefilter.TRAINING_BONUS
               if prefilter.training_signals(scored.green) else 0)
            + company_points
            - (geo.SOFT_TZ_PENALTY if scored.tz_blockers else 0))


def run(keyed_items, user_agent, logger, limit=ENRICH_LIMIT, ranker=None):
    """
    Enrich the highest-ranked candidates in place.

    `keyed_items` is the (key, Scored) list from dedupe.filter_new. Returns
    (enriched_count, skipped_count) so the digest can report the cap rather than
    imply everything was checked.
    """
    ordered = ranker(keyed_items) if ranker else list(keyed_items)
    # A Staff or Senior title is blocked whatever the page says, so reading it
    # buys no verdict. On 2026-10-01 these took 66 of the 199 pages read while
    # 1,781 listings went unchecked beyond the cap.
    ordered = [
        pair for pair in ordered
        if experience.wall_height(pair[1].listing.title, "")[0]
        not in experience.BLOCKED_HEIGHTS
    ]
    targets = ordered[:limit]
    skipped = max(0, len(ordered) - len(targets))

    enriched = 0
    for _, item in targets:
        text = page_text(item.listing.url, user_agent)
        if text is None:
            logger.info("  enrich: no page for %s", item.listing.url[:88])
            continue
        enriched += 1
        for change in reconsider(item, text):
            logger.info("  enrich: %s — %s", item.listing.title[:44], change)

    logger.info("enrich: %d pages read, %d beyond the cap of %d",
                enriched, skipped, limit)
    return enriched, skipped
