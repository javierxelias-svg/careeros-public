"""
Workday and Oracle readers, added 2026-10-08 for the hospitality / luxury lane.

Offline: ats._send is replaced with canned responses shaped like the live APIs
read that day (Four Seasons on Workday, Hilton Grand Vacations on Oracle).
What must hold: only titles in the target lanes cost a detail request, remote postings
are spent first, Oracle keeps only WorkplaceType Remote, and a bad slug or a
dead endpoint returns nothing instead of crashing the morning run.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ats  # noqa: E402

ats.POLITENESS_DELAY = 0
failures = []


def check(ok, label):
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
    if not ok:
        failures.append(label)


def fake_workday(url, user_agent, body=None):
    if url.endswith("/jobs"):
        return {"total": 3, "jobPostings": [
            {"title": "Housekeeping Attendant", "externalPath": "/job/a",
             "locationsText": "Four Seasons Seychelles"},
            {"title": "Guest Experience Manager", "externalPath": "/job/b",
             "locationsText": "Four Seasons Resort Tamarindo"},
            {"title": "Implementation Specialist", "externalPath": "/job/c",
             "locationsText": "Florida, USA (work from home)"},
        ]}
    path = url.rsplit("/job/", 1)[-1]
    return {"jobPostingInfo": {"title": {"b": "Guest Experience Manager",
                                         "c": "Implementation Specialist"}[path],
                               "location": "x", "jobDescription": "<p>Body</p>"}}


def fake_oracle(url, user_agent, body=None):
    if "recruitingCEJobRequisitions?" in url:
        return {"items": [{"TotalJobsCount": 2, "requisitionList": [
            {"Id": "1", "Title": "Implementation Specialist", "WorkplaceType": "Remote",
             "PrimaryLocation": "Orlando, FL, United States"},
            {"Id": "2", "Title": "Implementation Specialist", "WorkplaceType": "On-site",
             "PrimaryLocation": "Orlando, FL, United States"},
        ]}]}
    return {"items": [{"ExternalDescriptionStr": "<b>Help members</b>"}]}


print("=== Workday ===")
calls = []
ats._send = lambda u, a, b=None: (calls.append(u), fake_workday(u, a, b))[1]
rows = ats._workday({"slug": "fs/wd3/Search", "company": "Four Seasons"}, "ua")
titles = [r["title"] for r in rows]
check("Housekeeping Attendant" not in titles, "off-lane title never fetched")
check(titles[:1] == ["Implementation Specialist"], "work-from-home posting fetched first")
check(not any(u.endswith("/job/a") for u in calls), "no detail request for off-lane title")
check(rows[0]["description"] == "Body", "description cleaned of HTML")
check(ats._workday({"slug": "broken", "company": "x"}, "ua") == [], "bad slug returns []")

print("\n=== Oracle ===")
ats._send = fake_oracle
rows = ats._oracle({"slug": "h.oraclecloud.com/CX", "company": "HGV"}, "ua")
check(len(rows) == 1 and rows[0]["workplace"] == "remote", "only Remote requisitions kept")
check(rows[0]["url"].endswith("/sites/CX/job/1"), "apply link points at the requisition")
ats._send = lambda u, a, b=None: None
check(ats._oracle({"slug": "h/CX", "company": "x"}, "ua") == [], "dead endpoint returns []")

print("\n=== load_boards accepts enterprise platforms ===")
import json, tempfile  # noqa: E401,E402
with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
    json.dump({"boards": [{"company": "A", "platform": "workday", "slug": "t/wd1/s", "jobs": 5},
                          {"company": "B", "platform": "taleo", "slug": "x", "jobs": 5}]}, fh)
loaded = ats.load_boards(fh.name)
check([b["company"] for b in loaded] == ["A"], "workday loaded, unknown platform skipped")

print("\n" + "=" * 60)
if failures:
    print(f"FAILED {len(failures)}")
    sys.exit(1)
print("ALL ENTERPRISE TESTS PASS")
