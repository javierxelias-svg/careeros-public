#!/usr/bin/env python3
"""
Part-time (bridge) lane tests.

    python3 careeros/tests/test_bridge.py

Added 2026-10-26: a part-time bridge job hunted in parallel with the full-time
search, with its own hourly floor (EXAMPLE values here: $30/hr bridge, $85k
full-time). Before this, every part-time role was judged against the FULL-TIME
floor: salary.py annualises an hourly rate at 2080 hours, so "$35/hr, 20
hrs/week" read as $72,800 and was dropped as "published salary below $85k".
The digest had almost never shown one.

Pinned here:
  1. A part-time role at $35/hr survives the prefilter and is marked bridge.
  2. A part-time role at $25/hr is dropped, with a reason that names the
     bridge floor rather than the full-time one.
  3. A full-time role at $72,800 is still dropped by the $85k floor.
  4. Bridge roles never take a full-time slot (no 1099 in the main lane) and
     appear in their own section of the digest.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import digest  # noqa: E402
import prefilter  # noqa: E402
import sources  # noqa: E402

FAILURES = []


def check(label, got, want=True):
    ok = got == want
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + ("" if ok else f" -> got {got!r}"))
    if not ok:
        FAILURES.append(label)


class _QuietLog:
    def info(self, *a, **k):
        pass

    warning = debug = info


def listing(title, salary_raw, job_type=""):
    return sources.Listing(
        title=title, company="Bridgeco " + title, url="https://example.test/" + title,
        salary_raw=salary_raw, region="Remote, US", job_type=job_type,
        description="Fully remote. Async team, flexible hours. You will review "
                    "and improve AI customer support answers.",
    )


def main():
    print("\n=== prefilter: part-time judged by the hour ===")
    good = listing("Part-Time AI Support Specialist", "$35/hr")
    low = listing("Part-Time AI Support Specialist II", "$25/hr")
    full = listing("AI Support Specialist", "$35/hr")
    kept, rejections = prefilter.run([good, low, full], _QuietLog())
    titles = {k.listing.title: k for k in kept}
    check("$35/hr part-time is kept", good.title in titles)
    check("$35/hr part-time is marked bridge",
          getattr(titles.get(good.title), "bridge", None), True)
    check("$25/hr part-time is dropped", low.title in titles, False)
    check("its reason names the $30/hr bridge floor",
          any("$30/hr" in r for r in rejections), True)
    check("$35/hr FULL-TIME ($72,800) still fails the $85k floor",
          full.title in titles, False)

    print("\n=== digest: bridge roles get their own lane ===")
    bridge_item = titles.get(good.title)
    if bridge_item is None:
        FAILURES.append("no bridge item to route")
    else:
        pairs = [(0, bridge_item)]
        chosen, main_lane, wild, us_only, *_ = digest.select(pairs)
        check("bridge role never takes a full-time slot", len(chosen), 0)
        bridge = digest.select_bridge(pairs, chosen)
        check("bridge role is selected for the part-time lane", len(bridge), 1)
        msg = digest.build(chosen + bridge, main_lane, wild, us_only, 0, 0, 0,
                           {"fetched": 1, "kept": 1, "sources_live": 1,
                            "sources_total": 1},
                           "test", bridge=bridge)
        check("digest has a PART-TIME section", "PART-TIME" in msg)
        check("entry shows the hourly rate", "up to $35/hr" in msg)
        scam = prefilter.run([sources.Listing(
            title="Freelance Writer", company="IAPWE", url="https://example.test/w",
            salary_raw="$75/hr", region="Remote", job_type="freelance",
            description="Fully remote. Async team, flexible hours.")], _QuietLog())[0]
        check("pay-to-play gig board is never offered",
              len(digest.select_bridge([(9, s) for s in scam], [])), 0)
        check("no full-time annual figure on a part-time entry",
              "$72,800" in msg or "/yr net" in msg, False)

    print("\n=== sources: Mercor expert gigs ===")
    import json
    body = json.dumps({"listings": [
        {"listingId": "a", "title": "Spanish Linguistic Experts", "status": "active",
         "payRateFrequency": "hourly", "rateMin": 50, "rateMax": 50,
         "commitment": "part-time", "workArrangement": "remote",
         "eligibleResidenceLocation": None, "hoursPerWeek": 20,
         "description": "Evaluate LLM answers in Spanish."},
        {"listingId": "b", "title": "German Expert", "status": "active",
         "payRateFrequency": "hourly", "rateMin": 60, "rateMax": 60,
         "eligibleResidenceLocation": ["DEU"], "description": "x"},
        {"listingId": "c", "title": "Task Rater", "status": "active",
         "payRateFrequency": "per-task", "rateMin": 5, "rateMax": 5,
         "description": "x"},
    ]}).encode()
    rows = sources._norm_mercor(body)
    check("only the hourly, residence-open listing survives",
          [r.title for r in rows], ["Spanish Linguistic Experts"])
    if rows:
        check("pay written per hour", rows[0].salary_raw, "$50-$50/hr")
        check("job type marks it a contract",
              "contract" in rows[0].job_type)
        check("posting link", rows[0].url, "https://work.mercor.com/jobs/a")

    print("\n=== sources: Alignerr gigs ===")
    body = json.dumps({"total": 4, "jobs": [
        {"id": "x1", "title": "Software Engineer (AI Training)", "pay": "$20-100/hr",
         "description": "Software Engineers in Shanghai..."},
        {"id": "x2", "title": "Software Engineer (AI Training)", "pay": "$20-100/hr",
         "description": "Software Engineers in Miami..."},
        {"id": "x3", "title": "AI Chatbot Tester", "pay": "$40-120/hr", "description": "x"},
        {"id": "x4", "title": "Bonus Task", "pay": "$500 per task", "description": "x"},
    ]}).encode()
    rows = sources._norm_alignerr(body, "test", read_pages=False)
    check("one row per title+pay, hourly only",
          [r.title for r in rows], ["Software Engineer (AI Training)", "AI Chatbot Tester"])
    if rows:
        check("Alignerr posting link", rows[0].url, "https://www.alignerr.com/jobs/x1")
        check("Alignerr job type marks it a contract", "contract" in rows[0].job_type)

    print("\n=== bridge_fits: the operator's skills, no credential, no sales ===")
    for title, want in [
        ("Spanish Tutors", True),
        ("Generalist Expert", True),
        ("AI Developer Trace Task Auditor", True),
        ("Multilingual Primary Care Physician (MD) — Clinical Documentation & AI", False),
        ("Securities, Commodities, and Financial Services Sales Agents", False),
        ("Electrical Test Automation Engineer", False),
        ("Voice Actor: CX Agent Voice Cloning (USA)", False),
        ("Voice Actor: CX Agent Voice Cloning (Spanish - Latin America)", True),
        ("Clinical Mental Health Expert — AI Conversation Evaluation", False),
        ("Kubernetes Task Auditor", False),
        ("[LONG PROJECT] Anonymization Writer", True),
        ("Language & Audio Expert", True),
        ("Audio Engineer (Speech / TTS Audio Specialist) – French", False),
        ("Legal Expert, Spanish (Spain)", False),
        ("Voice Actor: CX Agent Voice Cloning (Spanish - Mexico)", False),
        # Alignerr, 2026-11-01
        ("Software Developer — Get Paid to Build Your Own Project with an AI Coding Assistant", True),
        ("AI Chatbot Tester", True),
        ("Spanish Language Expert", True),
        ("Prompt Writer", True),
        ("TypeScript Developer", True),
        ("Frontend JavaScript Developer", True),
        ("Mathematician – Formalization & AI Foundations (Remote Contract)", False),
        ("Physics Subject Matter Expert - AI Content Specialist", False),
        ("Experto en Física – AI Content Specialist", False),
        ("Finance Analyst (Spanish Fluency Required)", False),
        ("AI Red Team Penetration Tester", False),
        ("Coding Expert -  Go (Golang)", False),
        ("Coding Expert -  Java", False),
        ("Senior Rust Engineer — AI Data & Infrastructure", False),
        ("Voice Talent - UK English (Scotland)", False),
        ("Voice Performer- Spanish (Mexico)", False),
        ("Hebrew Language Expert", False),
        ("Entrepreneurship Instructor (AI Training)", False),
    ]:
        item = type("S", (), {"listing": sources.Listing(title=title)})()
        check(f"{title[:50]!r} -> {want}", prefilter.bridge_fits(item), want)

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILED")
        sys.exit(1)
    print("ALL PASS")


if __name__ == "__main__":
    main()
