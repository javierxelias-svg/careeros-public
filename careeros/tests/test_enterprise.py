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

# Recruitee, Gem and Workable, added 2026-10-13. Canned rows are shaped like
# the live answers read that day (MailerLite, Retool, Hugging Face).
print("\n=== Recruitee ===")
rows = ats._recruitee({"offers": [
    {"title": "Onboarding Specialist", "company_name": "MailerLite", "remote": True,
     "hybrid": False, "on_site": False, "city": "Vilnius", "country": "Lithuania",
     "salary": {"min": "70000", "max": "90000", "period": "year", "currency": "EUR"},
     "description": "<p>Body</p>", "requirements": "<p>Reqs</p>",
     "careers_url": "https://mailerlite.recruitee.com/o/x"},
    {"title": "Office Manager", "remote": True, "hybrid": True, "salary": None},
    "not a dict",
]}, "fallback")
check(len(rows) == 2, "non-dict offer skipped")
check(rows[0]["workplace"] == "remote" and rows[0]["region"] == "Remote, Vilnius, Lithuania",
      "remote offer keeps its country in the region")
check(rows[0]["salary_raw"] == "€70,000 - €90,000", "structured pay becomes a readable range")
check(rows[0]["description"] == "Body Reqs", "description and requirements joined, HTML cleaned")
check(rows[1]["workplace"] == "onsite" and rows[1]["company"] == "fallback",
      "hybrid wins over remote; missing company falls back")

print("\n=== Gem ===")
rows = ats._gem([
    {"title": "Solutions Engineer", "location_type": "remote",
     "location": {"name": "United States"}, "content_plain": "Body",
     "absolute_url": "https://jobs.gem.com/retool/1"},
    {"title": "Software Engineer", "location_type": "hybrid", "location": None},
], "Retool")
check([r["workplace"] for r in rows] == ["remote", "onsite"], "location_type decides workplace")
check(rows[0]["region"] == "United States" and rows[1]["region"] == "", "missing location is empty")


def fake_workable(url, user_agent, body=None):
    calls.append(url)
    if url.endswith("/jobs"):
        if body and body.get("token") == "p2":
            return {"results": [{"title": "Implementation Specialist", "shortcode": "B2",
                                 "workplace": "remote",
                                 "location": {"city": "", "country": "United States"}}]}
        return {"nextPage": "p2", "results": [
            {"title": "Housekeeping Attendant", "shortcode": "A1", "workplace": "on_site"},
            {"title": "Customer Success Manager", "shortcode": "C3", "workplace": "hybrid",
             "location": {"city": "Dublin", "country": "Ireland"}}]}
    return {"description": "<p>Desc</p>", "requirements": "<p>Req</p>", "benefits": None}


print("\n=== Workable ===")
calls.clear()
ats._send = fake_workable
rows = ats._workable({"slug": "acme", "company": "Acme"}, "ua")
check([r["title"] for r in rows] == ["Implementation Specialist", "Customer Success Manager"],
      "second page read; remote posting fetched first; off-lane title dropped")
check(not any(u.endswith("/A1") for u in calls), "no detail request for off-lane title")
check(rows[0]["region"] == "Remote, United States" and rows[0]["workplace"] == "remote",
      "remote posting keeps its country")
check(rows[1]["workplace"] == "onsite" and rows[1]["region"] == "Dublin, Ireland",
      "hybrid is onsite")
check(rows[0]["description"] == "Desc Req" and rows[0]["url"].endswith("/acme/j/B2/"),
      "detail text joined; apply link built")
ats._send = lambda u, a, b=None: None
check(ats._workable({"slug": "x", "company": "x"}, "ua") == [], "dead endpoint returns []")

print("\n" + "=" * 60)
if failures:
    print(f"FAILED {len(failures)}")
    sys.exit(1)
print("ALL ENTERPRISE TESTS PASS")
