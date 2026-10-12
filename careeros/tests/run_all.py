#!/usr/bin/env python3
"""
Run every test file, return non-zero if any fail.

    python3 careeros/tests/run_all.py

ENGINEERING.md requires the suite to be runnable in one command. Before this
existed the four files had to be invoked separately, which meant in practice
that only the one being worked on ever got run.
"""

import subprocess
import sys
from pathlib import Path

TESTS = [
    "test_salary.py",
    "test_enterprise.py",
    "test_culture.py",
    "test_salary_clause.py",
    "test_salary_ote.py",
    "test_ashby_tiers.py",
    "test_experience.py",
    "test_applied.py",
    "test_fit_terms.py",
    "test_curated.py",
    "test_estimate.py",
    "test_fit.py",
    "test_netpay.py",
    "test_gap.py",
    "test_freedom.py",
    "test_geo_title.py",
    "test_dedupe.py",
    "test_company.py",
    "test_enrich.py",
    "test_digest_entry.py",
    "test_tier.py",
    "test_ecosystem.py",
    "test_lean.py",
    "test_remote_gate.py",
    "test_builder_forms.py",
]


def main():
    here = Path(__file__).resolve().parent
    results = []

    for name in TESTS:
        path = here / name
        if not path.exists():
            print(f"MISSING {name}")
            results.append((name, 1))
            continue
        proc = subprocess.run(
            [sys.executable, str(path)], capture_output=True, text=True
        )
        # Print the child's own output so a failure is diagnosable from here
        # rather than requiring a second run of the individual file.
        if proc.returncode != 0:
            print(proc.stdout)
            print(proc.stderr, file=sys.stderr)
        results.append((name, proc.returncode))

    print("=" * 60)
    for name, code in results:
        print(f"  [{'PASS' if code == 0 else 'FAIL'}] {name}")

    failed = [name for name, code in results if code != 0]
    print("=" * 60)
    if failed:
        print(f"SUITE FAILED — {len(failed)} of {len(results)}: {', '.join(failed)}")
        return 1
    print(f"ALL {len(results)} TEST FILES PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
