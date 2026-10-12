"""
Fetching and normalization.

Each source speaks its own dialect. This module turns all of them into one
Listing shape so every downstream stage — prefilter, dedupe, digest — works on
a single record type and never needs to know where a job came from.

Field names here were read off live responses (see verification/), not guessed
from documentation.
"""

import html
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ElementTree
from datetime import datetime, timezone

from _shared.paths import RAW_DIR, SOURCES_CONFIG, ensure_dirs

REQUEST_TIMEOUT = 30
POLITENESS_DELAY = 1.0
HN_COMMENT_LIMIT = 200

TAG_RE = re.compile(r"<[^>]+>")
WHITESPACE_RE = re.compile(r"[ \t]+")
# A variation selector or zero-width joiner with no emoji in front of it.
# Boards write decorative emoji into titles; some get stripped upstream and
# leave the modifier behind, so "🗺️ Location Services Engineer" reached the
# digest as "️ Location Services Engineer" with a stray invisible character in
# the lead position. Anchored to start-or-whitespace so a modifier doing real
# work inside an emoji sequence is left alone.
ORPHAN_MODIFIER_RE = re.compile(r"(?:^|(?<=\s))[︎️‍]+")
URL_LIKE = re.compile(r"^(?:https?://|www\.)\S*$", re.I)

# Text that marks an HN comment as something other than a job posting.
NOT_A_JOB_POST = re.compile(
    r"\b(?:seeking work|i'?m (?:looking|available|a )|i would love to|"
    r"i'?d love to (?:join|work)|looking for (?:a|my next) (?:role|job|position)|"
    r"available for (?:hire|work|freelance)|my resume|my cv|here'?s my|"
    r"can i apply|is this remote\?|does anyone know)\b",
    re.I,
)


class Listing:
    """One job posting, normalized."""

    __slots__ = (
        "title", "company", "url", "salary_raw", "salary_min", "salary_max",
        "region", "description", "source", "posted_at", "tags", "job_type",
        "workplace",
    )

    def __init__(self, title="", company="", url="", salary_raw="",
                 salary_min=None, salary_max=None, region="", description="",
                 source="", posted_at=None, tags=None, job_type="",
                 workplace=""):
        self.title = clean_text(title)
        self.company = clean_text(company)
        self.url = url or ""
        self.salary_raw = clean_text(salary_raw)
        self.salary_min = salary_min
        self.salary_max = salary_max
        self.region = clean_text(region)
        self.description = clean_text(description)
        self.source = source
        self.posted_at = posted_at
        self.tags = tags or []
        self.job_type = job_type or ""
        # "remote", "onsite" or "" — what the ATS itself said, never inferred.
        # Deliberately kept OUT of `searchable`: the word "remote" landing in the
        # text a keyword filter reads would corrupt the geo classification it is
        # meant to inform.
        self.workplace = workplace or ""

    @property
    def searchable(self):
        """Everything a keyword filter should look at, in one string."""
        return "\n".join(
            [self.title, self.company, self.region, self.job_type,
             " ".join(str(t) for t in self.tags), self.description]
        )

    def as_dict(self):
        return {
            "title": self.title,
            "company": self.company,
            "url": self.url,
            "salary_raw": self.salary_raw,
            "region": self.region,
            "source": self.source,
            "posted_at": self.posted_at,
            "job_type": self.job_type,
        }

    def __repr__(self):
        return f"<Listing {self.title!r} @ {self.company!r} [{self.source}]>"


def clean_text(value):
    """
    Strip HTML tags and entities down to readable plain text.

    Unescape BEFORE stripping, then repeat. Stripping first left every
    entity-encoded posting fully marked up: `&lt;p&gt;` survives TAG_RE
    untouched and html.unescape() then turns it into a literal `<p>`, so the
    "clean" text still carried tags and attributes. Several employer boards
    double-encode, which is how `<span class="link-annotation-unknown-block-
    id-1691622878">` reached the salary parser and published a Product Manager
    role at $8,320–$18,720 — digits read out of a CSS class name and inferred
    as an hourly rate.

    Two passes: one for the encoding, one for markup the first pass revealed.
    """
    if value is None:
        return ""
    text = str(value)
    for _ in range(2):
        text = html.unescape(text)
        text = TAG_RE.sub(" ", text)
    text = ORPHAN_MODIFIER_RE.sub("", text)
    text = WHITESPACE_RE.sub(" ", text)
    return text.strip()


def load_config():
    return json.loads(SOURCES_CONFIG.read_text(encoding="utf-8"))


def _fetch(url, user_agent):
    request = urllib.request.Request(
        url, headers={"User-Agent": user_agent, "Accept": "*/*"}
    )
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
        return response.read()


def _save_raw(source_id, body):
    """Keep the raw payload before parsing, so a parse bug is diagnosable."""
    ensure_dirs()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    path = RAW_DIR / f"{stamp}-{source_id}.raw"
    try:
        path.write_bytes(body)
    except OSError:
        pass


# ─── per-source normalizers ───────────────────────────────────────────────────

def _norm_remoteok(body):
    data = json.loads(body.decode("utf-8", errors="replace"))
    if not isinstance(data, list):
        return []
    listings = []
    for record in data:
        if not isinstance(record, dict) or "legal" in record:
            continue  # slot 0 is RemoteOK's legal notice, not a job
        salary_min = record.get("salary_min") or None
        salary_max = record.get("salary_max") or None
        # RemoteOK writes 0 for "unknown", which must not read as "$0".
        if salary_min in (0, "0"):
            salary_min = None
        if salary_max in (0, "0"):
            salary_max = None
        raw = ""
        if salary_min or salary_max:
            raw = f"${salary_min or salary_max:,.0f} - ${salary_max or salary_min:,.0f}"
        listings.append(Listing(
            title=record.get("position") or record.get("title", ""),
            company=record.get("company", ""),
            url=record.get("apply_url") or record.get("url", ""),
            salary_raw=raw,
            salary_min=salary_min,
            salary_max=salary_max,
            region=record.get("location", ""),
            description=record.get("description", ""),
            source="remoteok",
            posted_at=record.get("date"),
            tags=record.get("tags") or [],
        ))
    return listings


def _norm_remotive(body):
    data = json.loads(body.decode("utf-8", errors="replace"))
    jobs = data.get("jobs") if isinstance(data, dict) else None
    if not isinstance(jobs, list):
        return []
    listings = []
    for record in jobs:
        if not isinstance(record, dict):
            continue
        listings.append(Listing(
            title=record.get("title", ""),
            company=record.get("company_name", ""),
            url=record.get("url", ""),
            salary_raw=record.get("salary", ""),
            region=record.get("candidate_required_location", ""),
            description=record.get("description", ""),
            source="remotive",
            posted_at=record.get("publication_date"),
            tags=record.get("tags") or [],
            job_type=record.get("job_type", ""),
        ))
    return listings


def _period_salary(low, high, period, currency):
    """
    Return (salary_min, salary_max, salary_raw).

    A structured salary field goes straight through prefilter as PUBLISHED ANNUAL
    pay, so a monthly or hourly figure must never be handed over that way — it
    would read a €5,000/month role as €5,000/year. Non-annual periods are emitted
    as text instead, with the period named, and salary.py does the conversion it
    already knows how to do.
    """
    if not (low or high):
        return None, None, ""
    period = str(period or "").strip().lower()
    currency = (currency or "USD").strip().upper()
    if period in ("", "year", "yearly", "annual", "annually", "per year"):
        return low, high, ""
    span = f"{low or high} - {high or low}"
    return None, None, f"{currency} {span} per {period.replace('ly', '')}"


def _norm_himalayas(body):
    """
    Himalayas. The only source that states location and timezone as DATA.

    `locationRestrictions` is a list of countries and `timezoneRestrictions` a
    list of UTC offsets, which is the fact every other feed makes the pipeline
    guess at from a title or a category name. Formatted as "X only" so
    geo.classify_geo reads a bare country as a restriction — its blocked patterns
    require that word, and "Brazil" alone would otherwise fall through to
    "location unstated".
    """
    data = json.loads(body.decode("utf-8", errors="replace"))
    jobs = data.get("jobs") if isinstance(data, dict) else None
    if not isinstance(jobs, list):
        return []

    listings = []
    for record in jobs:
        if not isinstance(record, dict):
            continue
        places = [str(p) for p in (record.get("locationRestrictions") or []) if p]
        region = f"{', '.join(places)} only" if places else "Anywhere in the World"
        low, high, raw = _period_salary(
            record.get("minSalary"), record.get("maxSalary"),
            record.get("salaryPeriod"), record.get("currency"),
        )
        # Himalayas serves literal placeholder company names — one record comes
        # back with companyName "name" while its URL says /companies/ioet/. The
        # slug is the reliable field. This matters beyond cosmetics: dedupe is
        # keyed on company + title, so a placeholder collapses unrelated jobs
        # from different employers onto one key and MAX_PER_COMPANY counts them
        # as the same company.
        company = (record.get("companyName") or "").strip()
        if company.lower() in ("", "name", "company", "unknown"):
            company = (record.get("companySlug") or "").strip() or company

        listings.append(Listing(
            title=record.get("title", ""),
            company=company,
            url=record.get("applicationLink") or record.get("guid", ""),
            salary_raw=raw,
            salary_min=low,
            salary_max=high,
            region=region,
            description=record.get("description") or record.get("excerpt", ""),
            source="himalayas",
            posted_at=record.get("pubDate"),
            tags=[str(t) for t in (record.get("categories") or []) if t],
            job_type=record.get("employmentType", ""),
        ))
    return listings


def _norm_jobicy(body):
    """
    Jobicy. Best published-salary coverage of any aggregator measured — 52% on
    2026-08-17, against RemoteOK's 4% on the same day.
    """
    data = json.loads(body.decode("utf-8", errors="replace"))
    jobs = data.get("jobs") if isinstance(data, dict) else None
    if not isinstance(jobs, list):
        return []

    listings = []
    for record in jobs:
        if not isinstance(record, dict):
            continue
        low, high, raw = _period_salary(
            record.get("salaryMin"), record.get("salaryMax"),
            record.get("salaryPeriod"), record.get("salaryCurrency"),
        )
        listings.append(Listing(
            title=record.get("jobTitle", ""),
            company=record.get("companyName", ""),
            url=record.get("url", ""),
            salary_raw=raw,
            salary_min=low,
            salary_max=high,
            region=record.get("jobGeo", ""),
            description=record.get("jobDescription") or record.get("jobExcerpt", ""),
            source="jobicy",
            posted_at=record.get("pubDate"),
            tags=[str(record.get("jobIndustry") or "")],
            job_type=str(record.get("jobType") or ""),
        ))
    return listings


def _norm_rss(body, source_id):
    root = ElementTree.fromstring(body)
    listings = []
    for item in root.findall(".//item"):
        fields = {}
        for child in item:
            tag = child.tag.split("}")[-1]
            fields[tag] = (child.text or "").strip()

        # WeWorkRemotely packs "Company: Job Title" into <title>.
        raw_title = fields.get("title", "")
        company, _, title = raw_title.partition(":")
        if not title:
            company, title = "", raw_title

        listings.append(Listing(
            title=title.strip() or raw_title,
            company=company.strip(),
            url=fields.get("link") or fields.get("guid", ""),
            salary_raw="",  # WWR states pay inside the description, if at all
            region=fields.get("region", ""),
            description=fields.get("description", ""),
            source=source_id,
            posted_at=fields.get("pubDate"),
            tags=[fields.get("category", "")] if fields.get("category") else [],
            job_type=fields.get("type", ""),
        ))
    return listings


def _norm_hn(body, user_agent):
    """
    Two-step: find the newest 'Who is hiring?' thread, then pull its comments.

    Each top-level comment is one job posting written by a human in free text,
    so the Listing is deliberately sparse — title and company get extracted by
    heuristic and the description carries the real content.
    """
    data = json.loads(body.decode("utf-8", errors="replace"))
    hits = data.get("hits") if isinstance(data, dict) else None
    if not isinstance(hits, list) or not hits:
        return []

    thread = None
    for hit in hits:
        if isinstance(hit, dict) and "who is hiring" in str(hit.get("title", "")).lower():
            thread = hit
            break
    if thread is None:
        return []

    story_id = thread.get("objectID")
    if not story_id:
        return []

    url = (
        "https://hn.algolia.com/api/v1/search"
        f"?tags=comment,story_{story_id}&hitsPerPage={HN_COMMENT_LIMIT}"
    )
    try:
        comments_body = _fetch(url, user_agent)
        comments = json.loads(comments_body.decode("utf-8", errors="replace"))
    except (urllib.error.URLError, urllib.error.HTTPError, OSError,
            TimeoutError, json.JSONDecodeError):
        return []

    hits = comments.get("hits") if isinstance(comments, dict) else None
    if not isinstance(hits, list):
        return []

    listings = []
    for comment in hits:
        if not isinstance(comment, dict):
            continue

        # Only top-level comments are job posts. Replies are candidates
        # applying, people asking questions, or arguments about salaries —
        # none of which are jobs, and all of which parse into nonsense.
        if str(comment.get("parent_id")) != str(comment.get("story_id")):
            continue

        text = clean_text(comment.get("comment_text", ""))
        if len(text) < 60:
            continue
        if NOT_A_JOB_POST.search(text[:400]):
            continue

        # The convention is "Company | Role | Location | ..." on the first line.
        first_line = text.split("\n")[0][:220]
        parts = [p.strip() for p in re.split(r"\||—|·", first_line) if p.strip()]
        parts = [p for p in parts if not URL_LIKE.match(p)]
        company = parts[0] if parts else "(see post)"
        title = parts[1] if len(parts) > 1 else "(role in post)"
        listings.append(Listing(
            title=title[:120],
            company=company[:80],
            url=f"https://news.ycombinator.com/item?id={comment.get('objectID')}",
            salary_raw=text,  # pay is stated inline when stated at all
            region=first_line,
            description=text,
            source="hn_whoishiring",
            posted_at=comment.get("created_at"),
            tags=["hn"],
        ))
    return listings


NORMALIZERS = {
    "remoteok": lambda body, ua: _norm_remoteok(body),
    "remotive": lambda body, ua: _norm_remotive(body),
    "himalayas": lambda body, ua: _norm_himalayas(body),
    "jobicy": lambda body, ua: _norm_jobicy(body),
    "weworkremotely_all": lambda body, ua: _norm_rss(body, "weworkremotely_all"),
    "weworkremotely_programming": lambda body, ua: _norm_rss(body, "weworkremotely_programming"),
    "hn_whoishiring": _norm_hn,
}


def _fetch_ats(user_agent, logger):
    """
    Employer boards from config/ats-boards.json, via ats.py.

    Handled outside the NORMALIZERS loop because it is not one URL — it is one
    request per company, and the company list is config, not a source entry.
    """
    import ats

    rows, _ = ats.fetch(user_agent, logger)
    listings = []
    for row in rows:
        listings.append(Listing(
            title=row.get("title", ""),
            company=row.get("company", ""),
            url=row.get("url", ""),
            salary_raw=row.get("salary_raw", ""),
            region=row.get("region", ""),
            description=row.get("description", ""),
            source="ats",
            posted_at=row.get("posted_at"),
            tags=[t for t in [row.get("ats_category")] if t],
            job_type=row.get("job_type", ""),
            workplace=row.get("workplace", ""),
        ))
    return listings


def fetch_all(logger):
    """
    Fetch every enabled source.

    A failing source is logged and skipped — one dead endpoint must never take
    down the whole run. Returns (listings, per_source_status).
    """
    config = load_config()
    user_agent = config.get("user_agent", "CareerOS/0.1")
    listings = []
    status = {}

    if config.get("ats_enabled", True):
        try:
            found = _fetch_ats(user_agent, logger)
            listings.extend(found)
            status["ats"] = f"{len(found)} listings"
        except Exception as exc:  # noqa: BLE001 — a new source must not break the run
            logger.error("ats failed: %s", exc)
            status["ats"] = "error"

    for source in config.get("sources", []):
        if not isinstance(source, dict) or not source.get("enabled"):
            continue
        source_id = source.get("id", "?")
        normalizer = NORMALIZERS.get(source_id)
        if normalizer is None:
            logger.warning("no normalizer for source %s, skipping", source_id)
            status[source_id] = "no normalizer"
            continue

        try:
            body = _fetch(source["url"], user_agent)
            _save_raw(source_id, body)
            found = normalizer(body, user_agent)
        except urllib.error.HTTPError as exc:
            logger.error("%s failed: HTTP %s", source_id, exc.code)
            status[source_id] = f"HTTP {exc.code}"
            continue
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            logger.error("%s failed: %s", source_id, exc)
            status[source_id] = "network error"
            continue
        except (json.JSONDecodeError, ElementTree.ParseError, UnicodeDecodeError) as exc:
            logger.error("%s unparseable: %s", source_id, exc)
            status[source_id] = "parse error"
            continue

        logger.info("%s: %d listings", source_id, len(found))
        status[source_id] = f"{len(found)} listings"
        listings.extend(found)
        time.sleep(POLITENESS_DELAY)

    return listings, status
