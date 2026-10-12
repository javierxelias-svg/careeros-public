#!/usr/bin/env python3
"""
Experience-wall tests, run with plain python3.

    python3 careeros/tests/test_experience.py

Cases 1 and 2 in the "real postings" block are the two defects that made the
first version of this detector under-report walls. Both are frozen here.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import experience  # noqa: E402

YEARS_CASES = [
    ("5+ years of experience in a technical role", 5, "plus form with the word experience"),
    ("Minimum of 10 years of experience in SaaS", 10, "minimum of"),
    # A stated range is one requirement, and its floor is the bar they will
    # actually consider. Separate requirements elsewhere in a posting are each
    # binding, so those take the highest. Different rules on purpose.
    ("3-5 years in customer success", 3, "range takes the floor, not the ceiling"),
    ("two years of professional experience", 2, "word number"),
    ("8+ yrs building distributed systems", 8, "abbreviated years"),
    ("What You Bring 2+ years of experience in project operations", 2, "bring form"),

    # --- real postings that broke the first version ---
    ("QUALIFICATIONS (MUST-HAVE) - 5+ years in a customer-facing, technical role such as",
     5, "no word 'experience' anywhere near the figure"),
    ("Willingness to travel up to 4 times a year for internal events. "
     "What You Bring 2+ years of experience in project operations",
     2, "a travel clause must not swallow the real wall that follows it"),
    ("WHO YOU ARE - 7+ years in B2B SaaS sales with at least 3 years in front-line",
     7, "highest figure wins"),

    # --- correctly refused ---
    ("Annual offsite: once a year the whole company gathers", None, "once a year"),
    ("Generous number of vacation days each year", None, "each year"),
    ("Applicants must be at least 18 years of age", None, "age is not experience"),
    ("Owns the 5-year product roadmap", None, "a roadmap is not a requirement"),
    ("Growing more than 100 percent year over year", None, "growth claim"),
    ("Founded 6 years ago in Berlin", None, "years ago"),
    ("International travel at least twice a year, usually for one week", None, "twice a year"),
    ("", None, "empty"),
    (None, None, "None input"),
]

TITLE_CASES = [
    ("Senior Solutions Engineer", True, "senior"),
    ("Staff Forward Deployed Engineer", True, "staff"),
    ("Director of Support", True, "director"),
    ("Solutions Architect", True, "architect is a level in practice"),
    ("Support Engineer", False, "plain"),
    ("Mid-Market Implementation Specialist", False, "mid-market is a segment, not a level"),
    ("Customer Success Engineer", False, "plain"),
]

# Re-cut 2026-09-30 when the wall became a gate. The buckets changed shape, so
# every case here is restated against the new scale rather than adjusted.
HEIGHT_CASES = [
    ("Support Engineer", "no numbers here at all", 0, "nothing in the way"),
    ("Senior Support Engineer", "no numbers here at all", 6, "senior in the title"),
    ("Snr Support Engineer", "no numbers here at all", 6,
     "Snr is not Sr, and the old pattern never matched it"),
    ("Solutions Architect", "no numbers here at all", 1,
     "Architect is the shape of the role, not a level"),
    ("Support Engineering Manager", "no numbers here at all", 1,
     "Manager is often an IC title"),
    ("Lead Generation Specialist", "no numbers here at all", 1,
     "lead generation is not a lead role"),
    ("Support Engineer", "1+ year of experience required", 2, "one year, admitted"),
    ("Support Engineer", "2+ years of experience required", 3, "two years, blocked"),
    ("Support Engineer", "5+ years of experience required", 5, "mid wall"),
    ("Support Engineer", "8+ years of experience required", 5, "high wall"),
    ("Principal Customer Engineer", "no numbers here at all", 4,
     "principal is scope, not years, and outranks a stated 2"),
    # Shipped and caught the same day: the first cut tested `if years is None`
    # first, so the seniority block only ran when no number was stated. "Senior
    # Implementation Specialist @ block", asking 4 years, reached a verified
    # digest with Senior in its title. A gate any posting can bypass by stating a
    # number is not a gate.
    ("Senior Implementation Specialist", "4+ years of experience", 6,
     "a senior title still blocks when years ARE stated"),
    ("Staff Engineer", "2+ years of experience", 4,
     "so does staff"),
    ("Implementation Specialist", "4+ years of experience", 5,
     "and the same posting without the word Senior is admitted"),
]

# The gate itself. These are the cases that decide what reaches the operator's phone.
ADMIT_CASES = [
    ("Support Engineer", "no numbers here at all", True, "clean"),
    ("Senior Support Engineer", "no numbers at all", False,
     "senior with no number is blocked — operator's call, 2026-09-30"),
    ("Solutions Architect", "no numbers at all", True,
     "a PRIMARY TARGET LANE must survive the seniority block"),
    ("Support Engineering Manager", "no numbers at all", True,
     "Manager alone is not a level claim"),
    ("Support Engineer", "1+ year of experience required", True, "one year is answerable"),
    # Years stopped blocking on 2026-09-30, hours after they started. The posting
    # is a soft signal and the form is the gate: one posting read "No years
    # requirement" while its form demanded two, and another posting read
    # senior with no gate on the form at all. Years now sort, via
    # rank_penalty, and the form is read on a weekly shortlist.
    ("Support Engineer", "2+ years of experience required", True,
     "two years is admitted now, and ranked below a clean role"),
    ("Support Engineer", "3-5 years of experience in a similar role", True,
     "a range floor of 3 is admitted and penalised, not discarded"),
    ("Support Engineer", "8+ years of experience required", True,
     "even eight years is only a penalty — the form decides"),
    ("Senior Support Engineer", "4+ years of experience required", False,
     "but a senior TITLE blocks regardless of the number beside it"),
    ("Principal Customer Engineer", "no numbers here at all", False, "scope the operator has not had"),
]

# An unread page must not read as a clean page — the inversion that made this
# filter dangerous to switch on. 187 of 532 cached pages are JavaScript shells.
JS_SHELL = "Solutions Engineer @ Bretton AI You need to enable JavaScript to run this app."
REAL_PAGE = "We are hiring. " * 200


def readability_cases():
    return [
        (JS_SHELL, False, "Ashby JavaScript shell is not readable"),
        (REAL_PAGE, True, "a real posting is"),
        ("", False, "empty is not readable"),
        (None, False, "None is not readable"),
    ]


def main():
    failures = []

    print("=== years_required() ===")
    for text, want, label in YEARS_CASES:
        got, _evidence = experience.years_required(text)
        ok = got == want
        print(f"  [{'PASS' if ok else 'FAIL'}] {label:52s} -> {got}")
        if not ok:
            failures.append(f"{label}: want {want}, got {got}")

    print("\n=== has_seniority_title() ===")
    for title, want, label in TITLE_CASES:
        got = experience.has_seniority_title(title)
        ok = got == want
        print(f"  [{'PASS' if ok else 'FAIL'}] {label:52s} {title[:34]:36s} -> {got}")
        if not ok:
            failures.append(f"{label}: want {want}, got {got}")

    print("\n=== wall_height() ===")
    for title, text, want, label in HEIGHT_CASES:
        got, _why, _years = experience.wall_height(title, text)
        ok = got == want
        print(f"  [{'PASS' if ok else 'FAIL'}] {label:52s} -> {got}")
        if not ok:
            failures.append(f"{label}: want {want}, got {got}")

    print("\n=== admits() — the gate ===")
    for title, text, want, label in ADMIT_CASES:
        height, _why, years = experience.wall_height(title, text)
        got, reason = experience.admits(height, years)
        ok = got == want
        print(f"  [{'PASS' if ok else 'FAIL'}] {label:52s} -> {got} {reason}")
        if not ok:
            failures.append(f"{label}: want {want}, got {got}")

    print("\n=== page_is_readable() ===")
    read_cases = readability_cases()
    for text, want, label in read_cases:
        got = experience.page_is_readable(text)
        ok = got == want
        print(f"  [{'PASS' if ok else 'FAIL'}] {label:52s} -> {got}")
        if not ok:
            failures.append(f"{label}: want {want}, got {got}")

    print("\n=== unreadable is admitted, and labelled ===")
    admitted, _ = experience.admits(experience.UNREADABLE, None)
    label_text = experience.wall_label(experience.UNREADABLE)
    for cond, label in (
        (admitted is True, "UNREADABLE is admitted, not blocked"),
        (bool(label_text) and "unknown" in label_text,
         "UNREADABLE carries a label saying the bar is unknown"),
    ):
        print(f"  [{'PASS' if cond else 'FAIL'}] {label}")
        if not cond:
            failures.append(label)

    print("\n=== a blocked senior role still reports its real years ===")
    h, _w, y = experience.wall_from_text(
        "Senior Implementation Specialist", "4+ years of experience" + " filler" * 400)
    lab = experience.wall_label(h, y)
    ok = lab == "asks 4+ years" and experience.rank_penalty(h, y) == 2
    print(f"  [{'PASS' if ok else 'FAIL'}] years survive the title verdict -> {lab!r}")
    if not ok:
        failures.append(f"blocked senior role lost its years: {lab!r}")

    print("\n=== rank_penalty(): the years still cost something ===")
    # A penalty that does not change the order is not a penalty. This is the
    # mistake the seniority rule made for six weeks: it lived in prefilter's
    # `score`, the fifth key in digest.rank, and moved nothing visible. So the
    # penalty is asserted to be MONOTONIC in the years asked.
    body = " filler" * 400
    pens = []
    for text in ("no years at all", "1+ year of experience", "3+ years of experience",
                 "5+ years of experience", "9+ years of experience"):
        h, _w, y = experience.wall_from_text("Support Engineer", text + body)
        pens.append(experience.rank_penalty(h, y))
    ok = pens == sorted(pens) and pens[0] == 0 and pens[-1] == 3
    print(f"  [{'PASS' if ok else 'FAIL'}] penalty rises with the years asked -> {pens}")
    if not ok:
        failures.append(f"rank_penalty not monotonic: {pens}")

    print("\n=== wall_from_text(): absent text is never clean ===")
    # The inversion that appeared twice in one afternoon, now pinned: first when
    # the length test lived inside wall_height, then again when prefilter started
    # reading the bar from listing.description and an empty feed scored as
    # height 0, nothing in the way.
    for text, want, label in (
        ("", experience.UNREADABLE, "empty text is unknown, not clean"),
        (None, experience.UNREADABLE, "None is unknown, not clean"),
        (JS_SHELL, experience.UNREADABLE, "a JavaScript shell is unknown"),
        (REAL_PAGE, 0, "a real posting with no years is genuinely clean"),
    ):
        got, _why, _y = experience.wall_from_text("Support Engineer", text)
        ok = got == want
        print(f"  [{'PASS' if ok else 'FAIL'}] {label:52s} -> {got}")
        if not ok:
            failures.append(f"{label}: want {want}, got {got}")

    print("\n=== a blocked title stays blocked when the page will not render ===")
    # Until 2026-10-01 these came back UNREADABLE, which admits() lets through.
    for title in ("Senior AI Engineer", "Staff Solutions Engineer"):
        got, _why, _y = experience.wall_from_text(title, JS_SHELL)
        ok = not experience.admits(got)[0]
        print(f"  [{'PASS' if ok else 'FAIL'}] {title:52s} -> {got}")
        if not ok:
            failures.append(f"{title} on a JS shell admitted: {got}")

    print("\n=== wall_label() prints the stated floor, never the bucket ===")
    # The defect this pins: "3-5 years" printed as "asks 1-3 years" and sent the
    # operator to a form that wanted three. Found on Customer Success Manager @ Fin.
    height, _why, years = experience.wall_height(
        "Customer Success Manager", "3-5 years of experience in a customer role")
    got = experience.wall_label(height, years)
    ok = got == "asks 3+ years"
    print(f"  [{'PASS' if ok else 'FAIL'}] 3-5 years prints as its floor -> {got!r}")
    if not ok:
        failures.append(f"range label: want 'asks 3+ years', got {got!r}")

    total = (len(YEARS_CASES) + len(TITLE_CASES) + len(HEIGHT_CASES)
             + len(ADMIT_CASES) + len(read_cases) + 4 + 3 + 2)
    print("\n" + "=" * 60)
    if failures:
        print(f"FAILED {len(failures)}/{total}")
        for f in failures:
            print("  - " + f)
        return 1
    print(f"ALL {total} EXPERIENCE TESTS PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
