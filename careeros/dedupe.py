"""
Deduplication ledger.

Keyed on normalized company + title, deliberately NOT on URL. Job boards
repost the same role with a fresh URL constantly, and URL-keying would resend
the same job every week — the single most annoying failure mode this machine
could have.

Entries expire after 60 days, because a role genuinely reopening months later
is real news worth surfacing again.
"""

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone

from _shared.paths import SEEN_LEDGER, ensure_dirs

TTL_DAYS = 60

NOISE_WORDS = re.compile(
    r"\b(?:inc|llc|ltd|limited|corp|corporation|co|gmbh|bv|ag|sa|srl|"
    r"remote|remotely|hiring|urgent|new|full[- ]?time|part[- ]?time|"
    r"contract|freelance|m/f/d|m/w/d|h/f)\b",
    re.I,
)
PUNCT = re.compile(r"[^a-z0-9 ]+")
SPACES = re.compile(r"\s+")

# Boards list one role once per territory. On 2026-08-16 "Senior Solutions
# Architect" and "Senior Solutions Architect- West Coast" took slots 2 and 3 of
# the digest as separate jobs. A trailing territory is stripped before keying.
#
# End-anchored and unbounded on neither side by design: only a region word
# sitting at the very end comes off. Matching mid-title would collapse "Head of
# Europe Sales" to "Head of", and merging two genuinely different roles means
# silently never showing one of them — worse than showing a duplicate.
REGION_SUFFIX = re.compile(
    r"[\s,\-–—(\[|/]+"
    r"(?:remote\s+in\s+)?"
    r"(?:west\s*coast|east\s*coast|emea|apac|latam|amer|americas|"
    r"north\s+america|european\s+union|europe|uk|u\.?s\.?a?|canada|australia|"
    r"india|germany|west|east|central|midwest|southeast|northeast)"
    r"[\s,/&+]*(?:only|region|based)?[\s)\]]*$",
    re.I,
)


def normalize(text):
    """Lowercase, strip punctuation and boilerplate, collapse whitespace."""
    if not text:
        return ""
    value = str(text).lower()
    value = PUNCT.sub(" ", value)
    value = NOISE_WORDS.sub(" ", value)
    value = SPACES.sub(" ", value)
    return value.strip()


def strip_region_suffix(title, max_passes=3):
    """Drop trailing territory qualifiers: 'Manager - Canada, Europe' -> 'Manager'."""
    value = str(title or "").strip()
    for _ in range(max_passes):
        trimmed = REGION_SUFFIX.sub("", value).strip()
        # Never strip the title down to nothing — a posting called "EMEA" is a
        # bad title, not an absent job.
        if trimmed == value or not trimmed:
            break
        value = trimmed
    return value


def make_key(company, title):
    basis = f"{normalize(company)}|{normalize(strip_region_suffix(title))}"
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:32]


def _parse_date(value):
    try:
        return datetime.fromisoformat(str(value)).replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def load_seen(ttl_days=TTL_DAYS):
    """
    Return the set of keys still within the TTL window.

    A corrupt line is skipped rather than fatal — a half-written ledger entry
    from an interrupted run must not stop tomorrow's digest.
    """
    if not SEEN_LEDGER.exists():
        return set()

    cutoff = datetime.now(timezone.utc) - timedelta(days=ttl_days)
    keys = set()
    try:
        content = SEEN_LEDGER.read_text(encoding="utf-8")
    except OSError:
        return set()

    for line in content.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict):
            continue
        sent_on = _parse_date(record.get("sent_on") or record.get("first_seen"))
        if sent_on is not None and sent_on < cutoff:
            continue

        # Both the stored key and a freshly computed one. The keying rule gains
        # cases as dedupe learns — territory suffixes landed 2026-08-17 — and a
        # ledger holding only keys from the old rule would resend every affected
        # job exactly once, which is the failure mode this module exists to stop.
        stored = record.get("key")
        if stored:
            keys.add(stored)
        company, title = record.get("company"), record.get("title")
        if company or title:
            keys.add(make_key(company, title))
    return keys


# When the same job reaches us twice, this decides which copy is kept. The
# employer's own board wins, always.
#
# Braze's "Customer Success Manager II" arrives from WeWorkRemotely stamped
# <region>Anywhere in the World</region> and from Braze's own Greenhouse board
# as "Remote - Spain". Same key, opposite meaning, and only arrival order
# decided which one the operator saw — the operator cannot work in Spain. Airtable's
# "Senior Solutions Architect" is the same story against "Remote - US".
# WeWorkRemotely stamps that region on ~95 of every 100 items because it is the
# CATEGORY being fetched, not a fact about the job.
SOURCE_RANK = {"ats": 0}
AGGREGATOR_RANK = 1

# Merging "- West" and "- East" into one key is correct: they are one job, and
# showing both wastes a digest slot. Choosing WHICH one survives is not
# arbitrary, and until 2026-08-19 it was.
#
# One employer listed a Mid-Market Implementation Specialist role twice, identical but for
# the timezone each seat requires: the West posting asks for "the PST or MST
# timezone", the East one for "the EST or CST timezone". Dedupe kept West.
# For an operator on US Eastern or Atlantic time, West means a workday running
# roughly noon to 9pm and East means a normal one. Same title, same pay,
# opposite life — and the wrong one was the one shown.
#
# So a US sub-region suffix is not noise here, it is a working-hours
# requirement. It still gets stripped for keying (one job, one slot) but it now
# decides which copy survives.
_WEST = re.compile(
    r"[\s,\-–—(\[|/]\s*(?:remote\s+in\s+)?"
    r"(?:west(?:\s*coast)?|pacific|mountain|pst|mst)\b"
    r"|\b(?:pst|mst|pacific|mountain)\s+time(?:\s*zone)?\b", re.I)
_EAST = re.compile(
    r"[\s,\-–—(\[|/]\s*(?:remote\s+in\s+)?"
    r"(?:east(?:\s*coast)?|eastern|central|atlantic|est|cst)\b"
    r"|\b(?:est|cst|eastern|central)\s+time(?:\s*zone)?\b", re.I)


def _timezone_penalty(item):
    """
    0 for a seat inside the operator's own timezone band, 1 for neutral,
    2 for one that would push the operator's workday into the evening.

    Read from the title only. The posting body states the requirement too, but
    it is not always fetched at dedupe time and a wrong guess here silently
    hides a job — so an unmarked posting stays neutral rather than being
    ranked down on a hunch.
    """
    title = str(getattr(item.listing, "title", "") or "")
    if _EAST.search(title):
        return 0
    if _WEST.search(title):
        return 2
    return 1


def _source_rank(item):
    return SOURCE_RANK.get(item.listing.source, AGGREGATOR_RANK)


def _pick_rank(item):
    """Employer board first, then the seat that fits the operator's clock."""
    return (_source_rank(item), _timezone_penalty(item))


def filter_new(scored_items, seen_keys, logger):
    """
    Drop anything already in the ledger. Also dedupes within this batch,
    preferring the employer's own board over any aggregator copy.
    """
    fresh = []
    batch_keys = set()
    duplicates = 0
    displaced = 0

    ordered = sorted(scored_items, key=_pick_rank)
    for item in ordered:
        key = make_key(item.listing.company, item.listing.title)
        if key in seen_keys or key in batch_keys:
            duplicates += 1
            if key in batch_keys and _source_rank(item) > 0:
                displaced += 1
            continue
        batch_keys.add(key)
        fresh.append((key, item))

    logger.info("dedupe: %d duplicates dropped, %d new", duplicates, len(fresh))
    if displaced:
        logger.info("dedupe: %d aggregator copies lost to the employer's own board",
                    displaced)
    return fresh


def commit(keyed_items, logger):
    """
    Append sent listings to the ledger.

    Called only AFTER delivery is confirmed. If the send failed, nothing is
    recorded, and tomorrow's run retries these listings rather than burying
    them permanently.
    """
    ensure_dirs()
    today = datetime.now(timezone.utc).date().isoformat()
    lines = []
    for key, item in keyed_items:
        lines.append(json.dumps({
            "key": key,
            "title": item.listing.title,
            "company": item.listing.company,
            "url": item.listing.url,
            "salary": item.salary.display(),
            "tier": item.tier,
            "source": item.listing.source,
            "geo_class": item.geo_class,
            "first_seen": today,
            "sent_on": today,
        }, ensure_ascii=False))

    if not lines:
        return 0

    with SEEN_LEDGER.open("a", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")
    logger.info("ledger: %d entries committed", len(lines))
    return len(lines)
