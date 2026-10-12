"""
Corporate-culture red flags, the operator's four signals, 2026-10-08: rigid hierarchy,
meetings / face time, corporate tone, return-to-office pressure. Size is no
longer a signal; these read the posting's own words.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import prefilter  # noqa: E402

CASES = [
    ("This role reports directly to the SVP of Customer Operations.", "rigid hierarchy"),
    ("You will work in a matrixed organization across regions.", "rigid hierarchy"),
    ("Core hours are 9am-5pm ET with daily standups.", "meetings / face time"),
    ("A world-class, results-driven self-starter delivering best-in-class outcomes.",
     "corporate tone"),
    ("We are remote-friendly and you must live within commuting distance.", "office pressure"),
    ("Expect in-person weeks each quarter at our hub.", "office pressure"),
]
CLEAN = [
    "As Implementation Manager, you will report to the Vice President of Customer Success.",
    # One buzzword is everywhere (1,275 of 10,820 postings say world-class).
    "Join a world-class team building developer tools, fully remote.",
    "Fully remote, async-first. Write things down, own outcomes, take real vacation.",
    "We publish salaries. No meetings on Tuesdays and Thursdays.",
]

failures = []
for text, want in CASES:
    _, red = prefilter.find_flags(text)
    ok = want in red
    print(f"  [{'PASS' if ok else 'FAIL'}] {want:<22} <- {text[:60]}")
    if not ok:
        failures.append(f"{want!r} missed in {text!r} (got {red})")
for text in CLEAN:
    _, red = prefilter.find_flags(text)
    culture = {"rigid hierarchy", "meetings / face time", "corporate tone", "office pressure"}
    ok = not (set(red) & culture)
    print(f"  [{'PASS' if ok else 'FAIL'}] no culture flag    <- {text[:60]}")
    if not ok:
        failures.append(f"false culture flag on {text!r}: {red}")

print("\n" + "=" * 60)
if failures:
    print(f"FAILED {len(failures)}")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print("ALL CULTURE TESTS PASS")
