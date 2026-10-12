#!/usr/bin/env python3
"""
Board discovery — the unconventional channels.

    python3 careeros/discover.py            # all channels, rewrite config/ats-boards.json
    python3 careeros/discover.py --channel yc
    python3 careeros/discover.py --dry-run  # report, write nothing

This is NOT part of the daily run. It is slow, chatty, and the answer barely
changes week to week: it probes several hundred companies to find which ones
expose a job feed, then writes the survivors to config/ats-boards.json, which
ats.py reads every morning in a few seconds.

Why bother, when five aggregators already exist: an early measurement put a team
under 100 people at 3/10 findability THROUGH JOB BOARDS. Small companies mostly
do not post there. That is a channel problem and no amount of filtering fixes it.
So instead of asking a job board who is hiring, these channels ask the companies.

Three channels, in order of what they produced on 2026-08-17:

  yc         The YC directory, filtered to Active AND isHiring AND 11-100 people
             AND AI-tagged AND batch 2021 or later. 205 candidates -> 80 boards ->
             1,011 open roles at a median team size of 25. Free, no key.
  categories The named companies in config/companies.json — the operator's
             seven categories. 108 candidates -> 40 boards -> 1,765 roles.
  hn         Hacker News full-text search, NOT the monthly thread. Someone writing
             "we're hiring a solutions engineer" in any comment, anywhere. 37% of
             matches carry real hiring intent; the rest are people discussing the
             job title, which is what the intent filter is for.

The team-size floor of 11 is deliberate. 348 of the 553 YC companies that passed
every other filter have ten people or fewer, and a company that size is not
paying $95k for a solutions hire. They are counted and reported, not probed.
"""

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import ats  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
BOARDS_OUT = REPO / "config" / "ats-boards.json"
COMPANIES_IN = REPO / "config" / "companies.json"

YC_DIRECTORY = "https://yc-oss.github.io/api/companies/all.json"
# Set your own contact address: API operators ask scrapers to identify themselves.
USER_AGENT = "CareerOS/0.1 (personal job search; contact you@example.com)"

TEAM_MIN, TEAM_MAX = 11, 100
BATCH_FROM = 2021
PROBE_DELAY = 0.15
REQUEST_TIMEOUT = 8

AI_WORDS = ("ai", "artificial intelligence", "machine learning", "generative",
            "llm", "agents")

# Someone stating they are hiring, as opposed to discussing a job title. Without
# this, a search for "forward deployed engineer" returns mostly people explaining
# that Palantir invented the term.
HIRING_INTENT = re.compile(
    r"\b(?:we(?:'re| are)? hiring|we're looking for|join (?:our|the) team|"
    r"apply(?: here|:| at)|email me|reach out|send (?:your|me) (?:cv|resume)|"
    r"now hiring|open role|role is (?:open|remote))\b|"
    r"\b(?:jobs?|careers?|hiring)@", re.I,
)
DISCUSSION = re.compile(
    r"\b(?:palantir (?:calls|uses)|the term|title is|i think|heard it said|"
    r"what does|anyone know|curious|used to be called)\b", re.I,
)
HN_QUERIES = [
    '"forward deployed engineer"',
    '"solutions engineer" remote',
    '"customer engineer" hiring',
    '"applied ai" engineer hiring',
    '"solutions architect" remote hiring',
    '"technical account manager" remote',
]


def _get(url, timeout=REQUEST_TIMEOUT):
    try:
        request = urllib.request.Request(
            url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"}
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read())
    except (urllib.error.URLError, urllib.error.HTTPError, OSError,
            TimeoutError, json.JSONDecodeError, ValueError):
        return None


def slug_variants(*names):
    """Every plausible ATS slug for a company name, most likely first."""
    out = []
    for name in names:
        text = str(name or "").lower()
        squashed = re.sub(r"[^a-z0-9]+", "", text)
        hyphenated = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
        out.extend([squashed, hyphenated])
    seen = set()
    return [s for s in out if s and not (s in seen or seen.add(s))][:3]


def probe_board(*names):
    """Return (platform, slug, job_count) for the first feed that answers."""
    for slug in slug_variants(*names):
        for platform, template in ats.ENDPOINTS.items():
            data = _get(template.format(slug=slug))
            if data is None:
                continue
            if platform == "lever" and isinstance(data, list) and data:
                return platform, slug, len(data)
            if not isinstance(data, dict):
                continue
            if platform == "ashby" and data.get("jobs"):
                return platform, slug, len(data["jobs"])
            if platform == "greenhouse" and (data.get("meta") or {}).get("total"):
                return platform, slug, data["meta"]["total"]
    return None


# ─── channels ─────────────────────────────────────────────────────────────────

def channel_yc(logger):
    """YC companies that say they are hiring and are small enough to be reachable."""
    data = _get(YC_DIRECTORY, timeout=30)
    if not isinstance(data, list):
        logger("  yc: directory unavailable, skipping")
        return []

    def batch_year(company):
        found = re.search(r"(20\d\d)", str(company.get("batch") or ""))
        return int(found.group(1)) if found else 0

    def is_ai(company):
        blob = " ".join([
            str(company.get("industry", "")), str(company.get("subindustry", "")),
            " ".join(str(t) for t in (company.get("tags") or [])),
        ]).lower()
        return any(word in blob for word in AI_WORDS)

    hiring = [c for c in data if c.get("status") == "Active" and c.get("isHiring")]
    ai_small = [
        c for c in hiring
        if isinstance(c.get("team_size"), int) and is_ai(c) and batch_year(c) >= BATCH_FROM
    ]
    too_small = [c for c in ai_small if c["team_size"] < TEAM_MIN]
    candidates = [c for c in ai_small if TEAM_MIN <= c["team_size"] <= TEAM_MAX]
    logger(f"  yc: {len(data)} companies -> {len(hiring)} hiring -> "
           f"{len(candidates)} in the {TEAM_MIN}-{TEAM_MAX} band "
           f"({len(too_small)} too small to pay the operator's floor, not probed)")

    boards = []
    for index, company in enumerate(candidates, 1):
        hit = probe_board(company.get("slug"), company.get("name"))
        if hit:
            platform, slug, count = hit
            boards.append({
                "company": company["name"], "category": "yc_small_ai",
                "platform": platform, "ats_slug": slug, "slug": slug,
                "jobs": count, "team_size": company["team_size"],
                "batch": company.get("batch"), "one_liner": company.get("one_liner"),
            })
        if index % 25 == 0:
            logger(f"    yc: {index}/{len(candidates)} probed, {len(boards)} found")
        time.sleep(PROBE_DELAY)
    return boards


def channel_categories(logger):
    """The companies the operator named, from the seven categories in companies.json."""
    try:
        config = json.loads(COMPANIES_IN.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger("  categories: config/companies.json unreadable, skipping")
        return []

    targets = [
        (name, entry["id"])
        for entry in config.get("categories", [])
        if entry.get("enabled") is not False
        for name in entry.get("companies", [])
    ]
    logger(f"  categories: {len(targets)} named companies to probe")

    boards = []
    for index, (name, category) in enumerate(targets, 1):
        hit = probe_board(name)
        if hit:
            platform, slug, count = hit
            boards.append({
                "company": name, "category": category, "platform": platform,
                "ats_slug": slug, "slug": slug, "jobs": count, "team_size": None,
            })
        if index % 25 == 0:
            logger(f"    categories: {index}/{len(targets)} probed, {len(boards)} found")
        time.sleep(PROBE_DELAY)
    return boards


def channel_hn(logger):
    """
    Companies naming themselves in any Hacker News comment, not just the monthly
    thread. Returns candidate company names with the comment that surfaced them —
    these are LEADS, and the probe decides whether a board exists.
    """
    leads = {}
    searched = kept = 0
    for query in HN_QUERIES:
        url = ("https://hn.algolia.com/api/v1/search?query="
               f"{urllib.parse.quote(query)}&tags=comment&hitsPerPage=50")
        data = _get(url, timeout=20)
        hits = (data or {}).get("hits") or []
        searched += len(hits)
        for hit in hits:
            text = re.sub(r"<[^>]+>", " ", hit.get("comment_text") or "")
            if not HIRING_INTENT.search(text) or DISCUSSION.search(text[:200]):
                continue
            kept += 1
            # The convention is "Company | Role | Location | ...".
            first = text.strip().split("\n")[0][:160]
            parts = [p.strip() for p in re.split(r"\||—|·", first) if p.strip()]
            if parts and 2 <= len(parts[0]) <= 40:
                leads.setdefault(parts[0], hit.get("objectID"))
        time.sleep(1.2)

    logger(f"  hn: {searched} comments, {kept} with hiring intent "
           f"({100 * kept // max(1, searched)}%), {len(leads)} company leads")

    boards = []
    for index, name in enumerate(sorted(leads), 1):
        hit = probe_board(name)
        if hit:
            platform, slug, count = hit
            boards.append({
                "company": name, "category": "hn_mentioned", "platform": platform,
                "ats_slug": slug, "slug": slug, "jobs": count, "team_size": None,
                "hn_comment": f"https://news.ycombinator.com/item?id={leads[name]}",
            })
        if index % 25 == 0:
            logger(f"    hn: {index}/{len(leads)} probed, {len(boards)} found")
        time.sleep(PROBE_DELAY)
    return boards


CHANNELS = {"yc": channel_yc, "categories": channel_categories, "hn": channel_hn}


def merge(boards, pinned=()):
    """
    Deduplicate on (platform, slug). First writer wins, so channel order matters.

    `pinned` entries are boards a human added to config/ats-boards.json by hand
    and marked "pinned": true. They go in FIRST, so discovery can refresh nothing
    about them and can never drop them.

    Why: this function's output replaces the whole board list on every run. Four
    boards added by hand on 2026-08-18 would have disappeared the next time discovery ran, silently, with the digest simply
    getting quieter.
    """
    seen = set()
    out = []
    for board in list(pinned) + list(boards):
        key = (board["platform"], board.get("ats_slug") or board.get("slug"))
        if key in seen:
            continue
        seen.add(key)
        out.append(board)
    return sorted(out, key=lambda b: (b["category"], -(b.get("jobs") or 0)))


def main():
    parser = argparse.ArgumentParser(description="Discover employer job boards")
    parser.add_argument("--channel", action="append", choices=sorted(CHANNELS),
                        help="run only this channel; repeatable")
    parser.add_argument("--dry-run", action="store_true",
                        help="report what was found, write nothing")
    args = parser.parse_args()

    def logger(message):
        print(message, flush=True)

    names = args.channel or list(CHANNELS)
    logger(f"discovering across channels: {', '.join(names)}")

    found = []
    for name in names:
        logger(f"\n[{name}]")
        found.extend(CHANNELS[name](logger))

    # Hand-pinned boards are read back out of the existing config before the
    # list is rebuilt, so a discovery run cannot delete a human's choice.
    pinned = []
    try:
        prior = json.loads(BOARDS_OUT.read_text(encoding="utf-8"))
        pinned = [b for b in (prior.get("boards") or []) if b.get("pinned")]
    except (OSError, json.JSONDecodeError, AttributeError):
        pinned = []
    if pinned:
        logger(f"carrying {len(pinned)} pinned board(s) through untouched")

    boards = merge(found, pinned=pinned)
    roles = sum(b.get("jobs") or 0 for b in boards)
    logger(f"\n{len(boards)} boards, {roles} open roles")
    by_category = {}
    for board in boards:
        entry = by_category.setdefault(board["category"], [0, 0])
        entry[0] += 1
        entry[1] += board.get("jobs") or 0
    for category, (count, total) in sorted(by_category.items()):
        logger(f"  {category:18s} {count:4d} boards {total:6d} roles")

    if args.dry_run:
        logger("\nDRY RUN — config/ats-boards.json untouched")
        return 0

    # Preserve the prose fields a human wrote; replace only the board list.
    existing = {}
    try:
        existing = json.loads(BOARDS_OUT.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass
    existing = existing if isinstance(existing, dict) else {}
    existing["boards"] = boards
    existing["discovered_at"] = time.strftime("%Y-%m-%d")
    existing["_endpoints"] = ats.ENDPOINTS
    BOARDS_OUT.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")
    logger(f"wrote {BOARDS_OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
