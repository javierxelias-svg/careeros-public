"""
Company-category scoring.

Target company categories exist because an applicant's edge is often not the
resume — it is the overlap between a company's customers and the applicant's
own history. A company whose customers you have served sees that history as
domain knowledge nobody else applying has.

The categories, and which are live, are set in config/companies.json.

Name matching only, from config/companies.json. Deliberately not inferred from
the description: a posting mentions "creators" and "hotels" for many reasons,
and a guess here would put the digest right back to scoring vibes.

The large-employer penalty is the other half of the module and matters as much.
One of the operator's stated preferences is "not corporate". A penalty rather
than a filter, because a genuinely good role at a big company should still be
visible; it just must not lead the digest. On 2026-08-17 a survey surfaced
mostly very large employers, a company shape the operator had already ranked
lower, so this is encoded rather than remembered.
"""

import json
import re
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "companies.json"

_CACHE = None


def _normalize(name):
    """Lowercase, drop punctuation and legal suffixes, collapse whitespace."""
    value = re.sub(r"[^a-z0-9 &.]+", " ", str(name or "").lower())
    value = re.sub(
        r"\b(?:inc|llc|ltd|limited|corp|corporation|co|gmbh|bv|ag|sa|srl|ab|oy|"
        r"plc|holdings|group|labs|technologies|technology|software)\b",
        " ", value,
    )
    return re.sub(r"\s+", " ", value).strip()


def _load(path=None):
    """Read the config once. A missing or broken file means no scoring, never a crash."""
    try:
        data = json.loads(Path(path or CONFIG_PATH).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return [], set(), 0
    if not isinstance(data, dict):
        return [], set(), 0

    categories = []
    for entry in data.get("categories") or []:
        if not isinstance(entry, dict) or entry.get("enabled") is False:
            continue
        names = {_normalize(n) for n in (entry.get("companies") or [])}
        names.discard("")
        if not names:
            continue
        categories.append((
            entry.get("label") or entry.get("id") or "target category",
            int(entry.get("points") or 0),
            names,
        ))

    large = data.get("large_employers") or {}
    large_names = {_normalize(n) for n in (large.get("companies") or [])}
    large_names.discard("")
    large_points = int(large.get("points") or 0)

    return categories, large_names, large_points


def config(path=None):
    global _CACHE
    if _CACHE is None or path is not None:
        loaded = _load(path)
        if path is None:
            _CACHE = loaded
        return loaded
    return _CACHE


def score(company_name, path=None):
    """
    Return (points, labels).

    `labels` is what the digest prints, so the operator can see WHY a listing
    was promoted rather than trusting the number. A company can match a target
    category and the large-employer list at once — Rippling is in both — and the
    points simply sum, which is the honest answer: right customers, wrong size.
    """
    categories, large_names, large_points = config(path)
    name = _normalize(company_name)
    if not name:
        return 0, []

    points = 0
    labels = []

    for label, category_points, names in categories:
        if _matches(name, names):
            points += category_points
            labels.append(label)

    if _matches(name, large_names):
        points += large_points
        labels.append("large employer")

    return points, labels


EVIDENCE_PATH = CONFIG_PATH.parent / "terms-proven-evidence.json"

# Term numbers as the 2026-10-12 audit used them. 2 (no on-call) and 3 (no
# quota) were proven in writing by nobody, so they never print.
_TERM_NAMES = {
    "1": "fully remote", "4": "pay published", "5": "time-off minimum",
    "6": "async", "7": "work from anywhere", "8": "health covered",
}
_EVIDENCE_CACHE = None


def proven_terms(company_name, path=None):
    """
    The terms this employer proves on its own pages, as short names, or [].

    Read from the audit file, not from the posting, so the digest can say WHY
    an employer is on the terms-proven list. A missing or broken file means no
    names, never a crash.
    """
    global _EVIDENCE_CACHE
    if _EVIDENCE_CACHE is None or path is not None:
        entries = []
        try:
            data = json.loads(
                Path(path or EVIDENCE_PATH).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        for entry in (data.get("qualifying") or []) if isinstance(data, dict) else []:
            if not isinstance(entry, dict):
                continue
            names = {_normalize(n) for n in
                     [entry.get("company")] + list(entry.get("name_variants") or [])}
            names.discard("")
            terms = [_TERM_NAMES[k] for k in sorted(entry.get("terms_proven") or {})
                     if k in _TERM_NAMES]
            if names and terms:
                entries.append((names, terms))
        if path is not None:
            return _lookup(company_name, entries)
        _EVIDENCE_CACHE = entries
    return _lookup(company_name, _EVIDENCE_CACHE)


def _lookup(company_name, entries):
    name = _normalize(company_name)
    if not name:
        return []
    for names, terms in entries:
        if _matches(name, names):
            return terms
    return []


def _matches(name, names):
    """
    Exact normalized match, or the config name as a whole-word prefix.

    Whole-word so "remote" does not match "Remotasks" and "kit" does not match
    "Kitchen Brains". Prefix so "Deel" matches "Deel Inc" after normalization
    already stripped the suffix, and "sabre hospitality" matches "Sabre
    Hospitality Solutions".
    """
    if name in names:
        return True
    return any(
        name == candidate or name.startswith(candidate + " ")
        for candidate in names
    )
