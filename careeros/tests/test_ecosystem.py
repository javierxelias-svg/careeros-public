#!/usr/bin/env python3
"""
Anthropic-ecosystem signal tests.

    python3 careeros/tests/test_ecosystem.py

The operator named the Claude/Anthropic stack as the target stack on 2026-08-15, so a
job inside it is worth a year of paid apprenticeship in the bet the operator has already
made. Two properties are pinned here:

  1. The signal fires on Anthropic-stack language and NOT on generic AI noise —
     "we use ChatGPT" is already covered by the AI-native green flag and must
     not trigger this one.
  2. It cannot rescue an off-lane role. A Claude shop hiring a lawyer is still
     hiring a lawyer.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import fit  # noqa: E402
import geo  # noqa: E402
import prefilter  # noqa: E402
import salary as salary_mod  # noqa: E402

# (text, should_fire, label)
CASES = [
    ("We build on Anthropic's API", True, "Anthropic named"),
    ("Experience with Claude required", True, "Claude named"),
    ("You'll work in Claude Code daily", True, "Claude Code"),
    ("We ship MCP servers for enterprise", True, "MCP servers"),
    ("Familiarity with the Model Context Protocol", True, "MCP spelled out"),
    ("We use ChatGPT and Copilot", False, "generic AI is not this signal"),
    ("LLM experience preferred", False, "generic LLM is not this signal"),
    ("Managed care provider (MCP) billing", False, "MCP acronym collision"),
    ("Microsoft Certified Professional preferred", False, "MCP acronym collision"),
    ("A regular software job", False, "no signal"),
]

PUBLISHED = salary_mod.Salary(
    low=110_000.0, high=140_000.0, confidence="published", raw="$110k-$140k",
)


def main():
    failures = []

    print("=== find_ecosystem() fires precisely ===")
    for text, should_fire, label in CASES:
        found = prefilter.find_ecosystem(text)
        ok = bool(found) == should_fire
        mark = "PASS" if ok else "FAIL"
        print(f"  [{mark}] {label:38s} {str(found) if found else '-'}")
        if not ok:
            failures.append(f"{label}: text={text!r} want={should_fire} got={found}")

    print("\n=== the bonus cannot rescue an off-lane role ===")
    lane, _ = fit.classify("Associate General Counsel, Corporate")
    tier = prefilter.assign_tier(
        PUBLISHED, ["AI-native", "async", "founder-led"], [],
        geo.CLASS_ANYWHERE, lane,
    )
    ok = tier == "C"
    print(f"  [{'PASS' if ok else 'FAIL'}] lawyer job at a Claude shop -> {tier}")
    if not ok:
        failures.append(f"ecosystem bonus lifted an off-lane role to {tier}")

    print("\n=== bonus is large enough to matter ===")
    ok = prefilter.ECOSYSTEM_BONUS >= 3
    print(f"  [{'PASS' if ok else 'FAIL'}] ECOSYSTEM_BONUS = "
          f"{prefilter.ECOSYSTEM_BONUS} (>= geo bonus of 3)")
    if not ok:
        failures.append("ecosystem bonus too small to outrank geography")

    print("\n" + "=" * 60)
    if failures:
        print(f"FAILED {len(failures)}")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("ALL ECOSYSTEM TESTS PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
