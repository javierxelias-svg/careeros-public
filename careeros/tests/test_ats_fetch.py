"""
ats.fetch() tagging, and what one unusable board may do to the others.

Offline: ats._get is replaced with canned Greenhouse-shaped feeds.
What must hold: every row from a board carries that board's team size, and a
feed that is not empty but holds no usable postings ({"jobs": [null]}) neither
crashes the scan nor changes another board's rows.
"""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ats  # noqa: E402

ats.POLITENESS_DELAY = 0
failures = []
logger = logging.getLogger("test_ats_fetch")


def check(ok, label):
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
    if not ok:
        failures.append(label)


FEEDS = {
    "three": {"jobs": [{"title": t, "absolute_url": f"https://x/{t}"} for t in "abc"]},
    "nulls": {"jobs": [None]},
}
ats._get = lambda url, user_agent: FEEDS[url.split("/boards/")[1].split("/")[0]]


def board(slug, team_size):
    return {"company": slug, "platform": "greenhouse", "slug": slug,
            "category": "test", "team_size": team_size}


def run(*boards):
    """The rows, or None if fetch() raised: a crash has to read as a FAIL line."""
    try:
        return ats.fetch("ua", logger, boards=list(boards))[0]
    except Exception as exc:  # noqa: BLE001
        print(f"  fetch() raised {type(exc).__name__}: {exc}")
        return None


def sizes(rows):
    return None if rows is None else [r.get("ats_team_size") for r in rows]


print("\n=== Every row of a board carries its team size ===")
rows = run(board("three", 10))
check(sizes(rows) == [10, 10, 10], f"three postings tagged [10, 10, 10], got {sizes(rows)}")

print("\n=== Unusable board first ===")
rows = run(board("nulls", 99), board("three", 10))
check(rows is not None, "fetch() does not raise")
check(sizes(rows) == [10, 10, 10], f"later board's rows survive, got {sizes(rows)}")

print("\n=== Unusable board after a good one ===")
rows = run(board("three", 10), board("nulls", 99))
check(sizes(rows) == [10, 10, 10], f"earlier board's rows keep their size, got {sizes(rows)}")

print("\n" + "=" * 60)
if failures:
    print(f"FAILED {len(failures)}")
    sys.exit(1)
print("ALL ATS FETCH TESTS PASS")
