"""
Employer job boards, read straight from the source.

The five aggregators this pipeline started with all have the same shape of
problem: they mediate. WeWorkRemotely stamps its feed CATEGORY into a region
field, Jobicy appends a rail of other companies' jobs and injects its own
invented salary estimate, and RemoteOK carries product-directory rows that are
not jobs at all. Every lie the digest told on 2026-08-17 came from a middleman.

An employer's own board has none of that. One company, one list, structured
compensation on Ashby, and a location that is a fact rather than a bucket.

It also solves a channel problem measured early on but never fixed: a team
under 100 people scored 3/10 on findability THROUGH JOB BOARDS, because small
companies mostly do not post to them. They do run an ATS. All three of the big
ones expose a public read-only endpoint with no key:

    Ashby       api.ashbyhq.com/posting-api/job-board/<slug>
    Greenhouse  boards-api.greenhouse.io/v1/boards/<slug>/jobs
    Lever       api.lever.co/v0/postings/<slug>

The board list lives in config/ats-boards.json and is maintained by discover.py,
not by this module. Discovery is slow and occasional; this is the daily read.
"""

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BOARDS_CONFIG = Path(__file__).resolve().parent.parent / "config" / "ats-boards.json"

REQUEST_TIMEOUT = 12
POLITENESS_DELAY = 0.3
# A board that has gone quiet is not worth a request every morning. Discovery
# records the count it saw; anything at zero then is skipped until re-discovered.
MIN_JOBS_AT_DISCOVERY = 1

ENDPOINTS = {
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true",
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true",
    "lever": "https://api.lever.co/v0/postings/{slug}?mode=json",
}

_TAG = re.compile(r"<[^>]+>")


def load_boards(path=None):
    """Verified boards from config. A broken file means no ATS source, never a crash."""
    try:
        data = json.loads(Path(path or BOARDS_CONFIG).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    boards = data.get("boards") if isinstance(data, dict) else data
    if not isinstance(boards, list):
        return []

    out = []
    for board in boards:
        if not isinstance(board, dict):
            continue
        platform = str(board.get("platform") or "").lower()
        slug = str(board.get("ats_slug") or board.get("slug") or "").strip()
        if (platform not in ENDPOINTS and platform not in ENTERPRISE) or not slug:
            continue
        if int(board.get("jobs") or 0) < MIN_JOBS_AT_DISCOVERY:
            continue
        out.append({
            "company": board.get("company") or slug,
            "platform": platform,
            "slug": slug,
            "category": board.get("category") or "",
            "team_size": board.get("team_size"),
        })
    return out


def _get(url, user_agent):
    try:
        request = urllib.request.Request(
            url, headers={"User-Agent": user_agent, "Accept": "*/*"}
        )
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            return json.loads(response.read())
    except (urllib.error.URLError, urllib.error.HTTPError, OSError,
            TimeoutError, json.JSONDecodeError, ValueError):
        return None


def _clean(text):
    return re.sub(r"\s+", " ", _TAG.sub(" ", str(text or ""))).strip()


# Ashby postings can carry compensationTiers: the SAME role priced per location.
# One support posting publishes "San Francisco, New York City
# $86,250-$109,250" and "United States $75,000-$95,000" side by side, and the
# blended headline the board shows is "$75,000-$109,250". Reading the headline
# credits the operator with a San Francisco salary they will not be offered
# outside those metros.
#
# The operator spotted this on 2026-08-18 by reading the posting itself, before
# the parser did.
_TIER_METRO = re.compile(
    r"san francisco|new york|nyc|bay area|seattle|los angeles|boston|washington dc", re.I)
_TIER_NATIONAL = re.compile(
    r"united states|us average|remote\s*-\s*us|national|average|\bus\b", re.I)


def _national_tier(comp):
    """
    The tier a remote worker outside the expensive metros is actually paid on.

    Returns "" when the posting publishes no tiers, which leaves the blended
    summary in place: a wrong-but-published number beats an invented one.
    """
    for tier in comp.get("compensationTiers") or []:
        title = tier.get("title") or ""
        summary = tier.get("tierSummary") or ""
        if not summary:
            continue
        if _TIER_NATIONAL.search(title) and not _TIER_METRO.search(title):
            return summary
    return ""


# Ashby's blended compensationTierSummary silently DROPS the "On Target
# Earnings" prefix that the tier row itself carries. PermitFlow's Solutions
# Consultant publishes one tier reading "On Target Earnings $175K – $225K",
# and the blended summary reads "$175K – $225K". salary.py never saw the words
# and correctly parsed the wrong string, so a commission package was recorded
# as $175,000–$225,000 of guaranteed base and ranked 3rd overall on 2026-08-19.
#
# The tier rows are the employer's own labelling and the blend is a
# convenience string. So: when no national tier matched, fall back to a lone
# tier's summary, and where several tiers exist, carry a lost OTE label back
# onto the blend rather than dropping the whole blend on the floor.
_OTE_LABEL = re.compile(
    r"\b(?:ote|o\.t\.e\.|on[-\s]?target\s+(?:earnings|compensation|comp))\b", re.I)


def _tier_fallback(comp):
    """The most honest published string available when no national tier matched."""
    tiers = [t for t in (comp.get("compensationTiers") or [])
             if isinstance(t, dict) and (t.get("tierSummary") or "").strip()]
    blend = (comp.get("compensationTierSummary") or "").strip()

    if len(tiers) == 1:
        return tiers[0]["tierSummary"].strip()

    if blend and not _OTE_LABEL.search(blend):
        for t in tiers:
            m = _OTE_LABEL.search(t["tierSummary"])
            if m:
                # Prepend the employer's own word so salary.py discounts it.
                return f"{m.group(0)} {blend}"
    return blend


def _ashby(data, company):
    """
    Ashby. compensationTierSummary is a human string like "$162K – $280K • Offers
    Equity", which salary.py parses directly — a published figure from the
    employer, not a band inferred from a job title.

    isRemote is recorded but deliberately NOT treated as work-from-anywhere. On
    every board measured it means "no commute", not "any country", and conflating
    those two is the mistake that put Europe-only roles under a globe.

    It is, however, the only evidence that some postings give at all: Confido's
    Forward Deployed Engineer says "NYC Office" in its location and isRemote:
    false in its data, and never writes "onsite" in the prose. Of 1,413 Ashby
    postings read on 2026-08-17, 638 carried isRemote: false. Passed through as
    `workplace` for geo.is_remote(), which is where it decides anything.
    """
    rows = []
    for job in data.get("jobs") or []:
        if not isinstance(job, dict):
            continue
        comp_block = job.get("compensation") or {}
        comp = _national_tier(comp_block) or _tier_fallback(comp_block)
        location = job.get("location") or ""
        if job.get("isRemote") and not location:
            location = "Remote"
        # Ashby returns BOTH fields and they contradict each other. PermitFlow's
        # Solutions Consultant carries isRemote: true and workplaceType: "Hybrid",
        # with a posting that reads "hybrid schedule (3 in-office days per week)…
        # seeking NYC-based candidates". Reading isRemote alone passed it through
        # the remote gate and it ranked 3rd overall on 2026-08-19 — against the
        # operator's first hard constraint.
        #
        # workplaceType is Ashby's own answer and it distinguishes hybrid from
        # remote, so it wins. isRemote is the fallback for the postings that
        # omit it. This is the same rule the Lever parser below already applies.
        workplace_type = str(job.get("workplaceType") or "").strip().lower()
        remote_flag = job.get("isRemote")
        if workplace_type in ("onsite", "hybrid"):
            workplace = "onsite"
        elif workplace_type == "remote":
            workplace = "remote"
        elif remote_flag is None:
            workplace = ""
        else:
            workplace = "remote" if remote_flag else "onsite"
        rows.append({
            "workplace": workplace,
            "title": job.get("title", ""),
            "company": job.get("companyName") or company,
            "url": job.get("jobUrl") or job.get("applyUrl") or "",
            "salary_raw": comp,
            "region": location,
            "description": _clean(job.get("descriptionPlain") or job.get("descriptionHtml")),
            "job_type": job.get("employmentType", ""),
            "posted_at": job.get("publishedAt") or job.get("updatedAt"),
        })
    return rows


def _greenhouse(data, company):
    """
    Greenhouse. Pay is inside the content field when stated at all.

    No workplace field exists on this API, so these rows carry workplace="" and
    fall through to the text and region rules in geo.is_remote().
    """
    rows = []
    for job in data.get("jobs") or []:
        if not isinstance(job, dict):
            continue
        offices = job.get("offices") or []
        location = (job.get("location") or {}).get("name") or ", ".join(
            str(o.get("name")) for o in offices if isinstance(o, dict) and o.get("name")
        )
        rows.append({
            "title": job.get("title", ""),
            "company": company,
            "url": job.get("absolute_url", ""),
            "salary_raw": "",
            "region": location,
            "description": _clean(job.get("content")),
            "job_type": "",
            "posted_at": job.get("updated_at") or job.get("first_published"),
        })
    return rows


def _lever(data, company):
    """
    Lever. A flat list; categories carry the location.

    workplaceType is Lever's own answer and it distinguishes hybrid from remote,
    which the location string does not: of 134 Lever postings read on
    2026-08-17, 81 were hybrid, 15 onsite, 38 remote. Hybrid is onsite as far as
    the operator is concerned — it means a commute.
    """
    rows = []
    for job in data:
        if not isinstance(job, dict):
            continue
        categories = job.get("categories") or {}
        workplace = str(job.get("workplaceType") or "").lower()
        rows.append({
            "workplace": ("onsite" if workplace in ("onsite", "hybrid")
                          else ("remote" if workplace == "remote" else "")),
            "title": job.get("text", ""),
            "company": company,
            "url": job.get("hostedUrl") or job.get("applyUrl") or "",
            "salary_raw": str(categories.get("commitment") or ""),
            "region": str(categories.get("location") or ""),
            "description": _clean(job.get("descriptionPlain") or job.get("description")),
            "job_type": str(categories.get("commitment") or ""),
            "posted_at": job.get("createdAt"),
        })
    return rows


PARSERS = {"ashby": _ashby, "greenhouse": _greenhouse, "lever": _lever}


# Workday and Oracle, added 2026-10-08 so the hospitality / luxury lane can
# finally be read. The 2026-09-30 probe found Marriott, Hilton, Four Seasons and
# 35 others answer on none of the three platforms above; companies.json had paid
# +3 for that lane since August for employers the pipeline could never fetch.
#
# Both are enterprise boards with thousands of on-property jobs (a housekeeper
# in the Seychelles, a security officer in Cancun), so neither is read whole.
# Workday has no common remote facet across tenants, so its title list is read
# cheaply and only titles in the operator's lanes get the expensive detail request. Oracle
# carries WorkplaceType on every requisition, so a keyword search plus that
# field is enough.
#
# Slugs: workday "tenant/wdN/site", oracle "host/siteNumber".
ENTERPRISE_PAGE = 20
ENTERPRISE_MAX_LIST = 2000
ENTERPRISE_MAX_DETAIL = 30


def _send(url, user_agent, body=None):
    """GET, or POST when a JSON body is given. None on any failure."""
    try:
        request = urllib.request.Request(
            url, data=json.dumps(body).encode() if body is not None else None,
            headers={"User-Agent": user_agent, "Accept": "application/json",
                     "Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            return json.loads(response.read())
    except (urllib.error.URLError, urllib.error.HTTPError, OSError,
            TimeoutError, json.JSONDecodeError, ValueError):
        return None


def _in_lane(title):
    # Imported here, not at the top: fit is pure and cheap, but keeping ats.py
    # import-free of the scoring modules matches how sources.py imports ats.
    import fit
    lane, _ = fit.classify(title)
    return lane in (fit.LANE_CORE, fit.LANE_ADJACENT)


def _workplace_from(text):
    low = str(text or "").lower()
    if "hybrid" in low or "on-site" in low or "onsite" in low:
        return "onsite"
    if "remote" in low or "work from home" in low:
        return "remote"
    return ""


def _workday(board, user_agent):
    try:
        tenant, wd, site = board["slug"].split("/")
    except ValueError:
        return []
    base = f"https://{tenant}.{wd}.myworkdayjobs.com"
    api = f"{base}/wday/cxs/{tenant}/{site}"
    postings, offset = [], 0
    while offset < ENTERPRISE_MAX_LIST:
        data = _send(f"{api}/jobs", user_agent, {
            "appliedFacets": {}, "limit": ENTERPRISE_PAGE, "offset": offset,
            "searchText": ""})
        page = (data or {}).get("jobPostings") or []
        if not page:
            break
        postings.extend(p for p in page if isinstance(p, dict))
        offset += ENTERPRISE_PAGE
        if offset >= int((data or {}).get("total") or 0):
            break
        time.sleep(POLITENESS_DELAY)

    rows = []
    wanted = [p for p in postings if _in_lane(p.get("title", ""))]
    # Detail requests are capped, and a resort board lists hundreds of front-desk
    # jobs in the operator's lanes. Postings that say remote or home in their title or
    # location go first so the cap is spent on roles that can pass the gate.
    wanted.sort(key=lambda p: 0 if _workplace_from(
        f"{p.get('title', '')} {p.get('locationsText', '')}") == "remote" else 1)
    for posting in wanted[:ENTERPRISE_MAX_DETAIL]:
        path = posting.get("externalPath") or ""
        detail = (_send(f"{api}{path}", user_agent) or {}).get("jobPostingInfo") or {}
        time.sleep(POLITENESS_DELAY)
        location = detail.get("location") or posting.get("locationsText") or ""
        rows.append({
            "workplace": _workplace_from(detail.get("remoteType") or location),
            "title": detail.get("title") or posting.get("title", ""),
            "company": board["company"],
            "url": detail.get("externalUrl") or f"{base}/en-US/{site}{path}",
            "salary_raw": "",
            "region": location,
            "description": _clean(detail.get("jobDescription")),
            "job_type": detail.get("timeType", ""),
            "posted_at": detail.get("startDate"),
        })
    return rows


def _oracle(board, user_agent):
    try:
        host, site = board["slug"].split("/", 1)
    except ValueError:
        return []
    api = f"https://{host}/hcmRestApi/resources/latest"
    reqs, offset = [], 0
    while offset < ENTERPRISE_MAX_LIST:
        data = _send(
            f"{api}/recruitingCEJobRequisitions?onlyData=true"
            f"&expand=requisitionList.secondaryLocations&finder=findReqs;"
            f"siteNumber={site},keyword=remote,limit=25,offset={offset}", user_agent)
        items = (data or {}).get("items") or [{}]
        page = items[0].get("requisitionList") or []
        if not page:
            break
        reqs.extend(r for r in page if isinstance(r, dict))
        offset += 25
        if offset >= int(items[0].get("TotalJobsCount") or 0):
            break
        time.sleep(POLITENESS_DELAY)

    rows = []
    wanted = [r for r in reqs if str(r.get("WorkplaceType") or "").lower() == "remote"
              and _in_lane(r.get("Title", ""))]
    for req in wanted[:ENTERPRISE_MAX_DETAIL]:
        finder = urllib.parse.quote(
            f'ById;Id="{req.get("Id")}",siteNumber={site}', safe=';=,"')
        data = _send(f"{api}/recruitingCEJobRequisitionDetails?expand=all"
                     f"&onlyData=true&finder={finder}", user_agent) or {}
        detail = (data.get("items") or [{}])[0]
        time.sleep(POLITENESS_DELAY)
        text = " ".join(str(detail.get(k) or "") for k in (
            "ExternalDescriptionStr", "ExternalResponsibilitiesStr",
            "ExternalQualificationsStr"))
        rows.append({
            "workplace": "remote",
            "title": req.get("Title", ""),
            "company": board["company"],
            "url": f"https://{host}/hcmUI/CandidateExperience/en/sites/{site}/job/{req.get('Id')}",
            "salary_raw": "",
            "region": req.get("PrimaryLocation") or "",
            "description": _clean(text or req.get("ShortDescriptionStr")),
            "job_type": "",
            "posted_at": req.get("PostedDate"),
        })
    return rows


ENTERPRISE = {"workday": _workday, "oracle": _oracle}


def fetch(user_agent, logger, boards=None, limit=None):
    """
    Read every verified board. Returns a list of plain dicts for sources.py to
    turn into Listings, so this module never imports sources and the two cannot
    become circular.

    A dead board is logged and skipped. Forty boards at ~0.3s is well under the
    time the aggregators already take, and each one is a company the operator chose.
    """
    boards = load_boards() if boards is None else boards
    if limit:
        boards = boards[:limit]
    if not boards:
        logger.info("ats: no verified boards in config, skipping")
        return [], {}

    rows = []
    per_company = {}
    dead = 0
    for board in boards:
        if board["platform"] in ENTERPRISE:
            found = ENTERPRISE[board["platform"]](board, user_agent)
            if not found:
                dead += 1
            for row in found:
                row["ats_category"] = board["category"]
                row["ats_team_size"] = board.get("team_size")
            rows.extend(found)
            per_company[board["company"]] = len(found)
            continue
        url = ENDPOINTS[board["platform"]].format(slug=board["slug"])
        data = _get(url, user_agent)
        if data is None or (isinstance(data, dict) and not data.get("jobs")) or (
                isinstance(data, list) and not data):
            dead += 1
            per_company[board["company"]] = 0
            time.sleep(POLITENESS_DELAY)
            continue
        found = PARSERS[board["platform"]](data, board["company"])
        for row in found:
            row["ats_category"] = board["category"]
            # .get, not [], matching load_boards above. Hit 2026-09-30 by calling
        # fetch() with a board dict that had not been through load_boards: it
        # raised KeyError instead of degrading. Production survives only because
        # load_boards normalises the key, and the six hospitality boards added
        # that same day carry no team_size in config.
        row["ats_team_size"] = board.get("team_size")
        rows.extend(found)
        per_company[board["company"]] = len(found)
        time.sleep(POLITENESS_DELAY)

    logger.info("ats: %d boards read, %d quiet, %d postings",
                len(boards) - dead, dead, len(rows))
    return rows, per_company
