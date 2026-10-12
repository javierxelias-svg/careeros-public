"""
Read the application FORM before the operator opens it.

The form is the gate, not the posting. A hand-written note in August read "No
years requirement" off a posting whose form demanded two years and said "if
not, please do not apply"; another employer ran the other way. On 2026-10-01
the operator asked for a way to apply "easier and faster", and the fastest
application is the one never started because the form would have stopped it on
question one.

So for each role in the digest this fetches the form's required questions and
prints one line:

  ⚡ quick form: 7 questions, no years asked
  ⛔ form asks about experience: "How many years of SaaS implementation…"
  📝 form: 14 questions, 3 written answers

Greenhouse publishes questions on its public board API. Ashby has no public
form API; the endpoint below is the one its own job pages call, so it can change
without notice. Every failure returns None and the role prints with no form line.
Unknown is never reported as quick.
"""

import json
import re
import urllib.request

TIMEOUT = 10

_GREENHOUSE = re.compile(
    r"(?:job-boards|boards)(?:\.eu)?\.greenhouse\.io/([\w-]+)/jobs/(\d+)", re.I)
_ASHBY = re.compile(r"jobs\.ashbyhq\.com/([\w.-]+)/([0-9a-f-]{36})", re.I)
# Greenhouse jobs embedded on the company's own site ("...?gh_jid=8122751").
# The board slug is not in the URL; ats.py stores it as the company name.
_GH_JID = re.compile(r"[?&]gh_jid=(\d+)", re.I)

_ASHBY_QUERY = (
    "query ApiJobPosting($organizationHostedJobsPageName: String!, "
    "$jobPostingId: String!) { jobPosting(organizationHostedJobsPageName: "
    "$organizationHostedJobsPageName, jobPostingId: $jobPostingId) { "
    "applicationForm { sections { fieldEntries { ... on FormFieldEntry { "
    "isRequired field } } } } } }"
)

# A required question that asks the applicant to state experience they may not have.
_YEARS_Q = re.compile(
    r"\b(?:years?|yrs)\b[^?]{0,80}\bexperience\b|"
    r"\bexperience\b[^?]{0,80}\b(?:years?|yrs)\b|"
    r"\bhow\s+(?:many|much)\s+(?:years|experience)\b|"
    r"\bdo\s+you\s+have\s+\d+\+?\s*(?:years?|yrs)\b",
    re.I,
)

QUICK_MAX_QUESTIONS = 12
QUICK_MAX_ESSAYS = 1


def _fetch(req):
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def greenhouse_questions(board, job_id, user_agent):
    url = (f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs/{job_id}"
           "?questions=true")
    data = _fetch(urllib.request.Request(url, headers={"User-Agent": user_agent}))
    if not isinstance(data, dict):
        return None
    out = []
    for q in data.get("questions") or []:
        if not isinstance(q, dict):
            continue
        kinds = [f.get("type", "") for f in q.get("fields") or [] if isinstance(f, dict)]
        out.append((q.get("label") or "", bool(q.get("required")),
                    "essay" if "textarea" in kinds else "other"))
    return out


def ashby_questions(org, posting_id, user_agent):
    body = json.dumps({
        "operationName": "ApiJobPosting",
        "variables": {"organizationHostedJobsPageName": org,
                      "jobPostingId": posting_id},
        "query": _ASHBY_QUERY,
    }).encode()
    req = urllib.request.Request(
        "https://jobs.ashbyhq.com/api/non-user-graphql?op=ApiJobPosting",
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": user_agent},
    )
    data = _fetch(req)
    posting = ((data or {}).get("data") or {}).get("jobPosting") if isinstance(data, dict) else None
    form = (posting or {}).get("applicationForm") if isinstance(posting, dict) else None
    if not isinstance(form, dict):
        return None
    out = []
    for section in form.get("sections") or []:
        for entry in (section or {}).get("fieldEntries") or []:
            field = (entry or {}).get("field") if isinstance(entry, dict) else None
            if not isinstance(field, dict):
                continue
            out.append((field.get("title") or "", bool(entry.get("isRequired")),
                        "essay" if field.get("type") == "LongText" else "other"))
    return out


def questions_for(url, user_agent, company=""):
    """Required-and-optional form questions as (label, required, kind), or None."""
    match = _GREENHOUSE.search(url or "")
    if match:
        return greenhouse_questions(match.group(1), match.group(2), user_agent)
    match = _GH_JID.search(url or "")
    slug = re.sub(r"[^a-z0-9-]", "", (company or "").lower())
    if match and slug:
        return greenhouse_questions(slug, match.group(1), user_agent)
    match = _ASHBY.search(url or "")
    if match:
        return ashby_questions(match.group(1), match.group(2), user_agent)
    return None


def verdict(questions):
    """One digest line for a list of (label, required, kind), or None if unknown."""
    if not questions:
        return None
    required = [q for q in questions if q[1]]
    for label, _, _ in required:
        if _YEARS_Q.search(label):
            short = label.strip().replace("\n", " ")
            if len(short) > 60:
                short = short[:57].rstrip() + "…"
            return f"⛔ form asks about experience: \"{short}\""
    essays = sum(1 for q in required if q[2] == "essay")
    if len(required) <= QUICK_MAX_QUESTIONS and essays <= QUICK_MAX_ESSAYS:
        return f"⚡ quick form: {len(required)} questions, no years asked"
    return f"📝 form: {len(required)} questions, {essays} written answers"


def annotate(items, user_agent, logger):
    """Set item.form_tag on each Scored item that has a readable form."""
    read = 0
    for item in items:
        try:
            tag = verdict(questions_for(item.listing.url, user_agent,
                                        item.listing.company))
        except Exception as exc:  # network, JSON shape, anything: report nothing
            logger.info("  form: unreadable for %s (%s)", item.listing.url[:80],
                        type(exc).__name__)
            tag = None
        item.form_tag = tag
        if tag:
            read += 1
    logger.info("forms: %d of %d read", read, len(items))
    return read
