"""
Regressions for the remote gate, 2026-08-17.

Six of the highest-scoring roles in the live pool were onsite jobs, all of them
scored 10/10 on "fully remote" — the operator's first hard constraint. Every
case below is one of those postings, quoted from the posting itself.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import geo  # noqa: E402
import prefilter  # noqa: E402
import sources  # noqa: E402


FAILURES = []


def check(label, got, want):
    if got != want:
        FAILURES.append(f"{label}: got {got!r}, want {want!r}")


# --------------------------------------------------------------------------
# 1. The ATS said so in a field, and the prose never said it at all.
#
# Confido's Forward Deployed Engineer ($200K-$270K) reads "NYC Office" in its
# location and isRemote: false in its data, and the word onsite appears nowhere
# in the description. Only the field can catch this one.
# --------------------------------------------------------------------------
def test_platform_flag_decides():
    body = ("Confido is building AI for financial operations. What you'll do: "
            "build LLM systems. Benefits: 401(k) through Vestwell. Paid "
            "relocation support - we'll help you make the move to NYC.")
    check("Confido FDE",
          geo.is_remote("NYC Office", body, workplace="onsite", source="ats")[0],
          False)
    check("Lever hybrid",
          geo.is_remote("Mexico City", "AI Engineer at Kavak",
                        workplace="onsite", source="ats")[0],
          False)
    check("flag says remote, prose is quiet",
          geo.is_remote("The Americas", "Customer Success Manager",
                        workplace="remote", source="ats")[0],
          True)


# --------------------------------------------------------------------------
# 2. The disclosure sits past the old 1,200-character window.
#
# "in person" is at character 3,404 in Reducto's posting, 2,210 in Arini's and
# 5,360 in Retell AI's. Same shape as the pay section sitting below the 3,000
# character cut, fixed in the lean pass.
# --------------------------------------------------------------------------
def test_onsite_sentence_late_in_the_body():
    filler = "We are an early stage company building document AI. " * 60
    check("Reducto, in person at 3k+",
          geo.is_remote("San Francisco Office",
                        filler + "This is an in person role at our office in SF.",
                        source="ats")[0],
          False)
    check("Auctor, 5 days per week",
          geo.is_remote("New York",
                        filler + "This role is based in New York, NY, in person 5 days per week.",
                        source="ats")[0],
          False)
    check("PermitFlow, in-office Mon/Wed/Fri",
          geo.is_remote("New York City, NY",
                        filler + "This is a hybrid role based in our New York City "
                        "office (in-office Monday, Wednesday, and Friday).",
                        source="ats")[0],
          False)


# --------------------------------------------------------------------------
# 3. An employer board that never mentions remote work is not offering it.
#
# Retell AI's Senior Forward Deployed Engineer (Spanish Fluency Required) —
# $200-300K, 50 people, Latin American customers, and a $300/month COMMUTER
# reimbursement for Redwood City. The prose says "Onsite/Virtual Interviews"
# and nothing else about where the work happens.
# --------------------------------------------------------------------------
def test_employer_board_needs_a_positive_signal():
    body = ("As a Senior Forward Deployed Engineer, you'll deliver Retell's "
            "voice AI to enterprise clients. Location: Redwood City, CA, US. "
            "$300/month commuter reimbursement (gas, Caltrain, etc.)")
    check("Retell FDE",
          geo.is_remote("San Francisco Bay Area", body, source="ats")[0], False)
    check("same posting on an aggregator is judged as before",
          geo.is_remote("San Francisco Bay Area", body, source="remoteok")[0], True)
    check("a phrase describing the arrangement passes it",
          geo.is_remote("Curitiba", body + " You can work remotely.",
                        source="ats")[0],
          True)
    check("a remote region field passes it",
          geo.is_remote("Remote - AMER", body, source="ats")[0], True)


def test_the_word_alone_is_not_the_arrangement():
    """
    Scale AI's eighteen Forward Deployed roles — New York, San Francisco,
    London, Doha, the word remote nowhere in any of them — stayed alive on
    "full-stack / distributed systems engineering" while this was measured.
    The body has to describe where the work happens, not use the word.
    """
    for body in (
        "Strong foundation in full-stack / distributed systems engineering.",
        "Experience securing untrusted workloads (FaaS, CI sandboxes, remote notebooks).",
        "A platform that is secure by default and deployable anywhere.",
    ):
        check(f"not a signal: {body[:38]}",
              geo.is_remote("New York, NY", body, source="ats")[0], False)


# --------------------------------------------------------------------------
# 4. The rules must not cost a single genuinely remote listing.
#
# Every case here survived the gate in the 2026-08-17 replay and is on the
# curated list. The region field outranks a body phrase: Labelbox repeats a
# "3 days per week in office" line on postings whose location reads "Remote,
# United States", and Remote.com's "Benefits Operations Specialist - AMER"
# mentions relocation while being fully remote — which is why relocation is
# not evidence of anything.
# --------------------------------------------------------------------------
def test_real_remote_roles_survive():
    keep = [
        ("The Americas", "Work from anywhere: Oyster has no borders or HQ. 40 days off.", "ats"),
        ("Remote", "PostHog is a natively remote company. Tuesdays and Thursdays "
                   "are meeting-free days.", "ats"),
        ("Remote", "We hire globally. There are no Supabase offices, but we provide "
                   "a WeWork membership.", "ats"),
        ("Home based - Worldwide", "Distributed work environment with twice-yearly "
                                   "team sprints in person.", "ats"),
        ("Anywhere in the World", "The salary range is location independent.", "weworkremotely"),
        ("Remote-AMER", "Relocation to another country is supported. We work async.", "ats"),
        ("Remote, United States", "Our recruiting team is in office 3 days per week.", "ats"),
    ]
    for region, body, source in keep:
        check(f"keeps {region}", geo.is_remote(region, body, source=source)[0], True)


# --------------------------------------------------------------------------
# 5. The flag has to survive the trip from ats.py to the gate, and must stay
#    out of `searchable` — the word "remote" landing in the text a keyword
#    filter reads would corrupt the geo classification it exists to inform.
# --------------------------------------------------------------------------
def test_workplace_is_plumbed_but_not_searchable():
    listing = sources.Listing(title="Forward Deployed Engineer", company="Confido",
                              region="NYC Office", description="Build LLM systems.",
                              source="ats", workplace="onsite")
    check("workplace kept", listing.workplace, "onsite")
    check("not searchable", "onsite" in listing.searchable.lower(), False)
    check("aggregator default", sources.Listing(title="x").workplace, "")

    kept, rejections = prefilter.run([listing], _QuietLog())
    check("rejected by the gate", len(kept), 0)
    check("reason recorded",
          any("onsite" in reason for reason in rejections), True)


class _QuietLog:
    def info(self, *a, **k):
        pass

    def warning(self, *a, **k):
        pass

    def error(self, *a, **k):
        pass

    def debug(self, *a, **k):
        pass


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    if FAILURES:
        print(f"FAIL test_remote_gate.py ({len(FAILURES)})")
        for failure in FAILURES:
            print("   ", failure)
        return 1
    print("PASS test_remote_gate.py")
    return 0


if __name__ == "__main__":
    sys.exit(run())
