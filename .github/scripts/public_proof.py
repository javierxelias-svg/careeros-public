#!/usr/bin/env python3
"""
Write proof/latest.json and proof/README.md: the public receipt that this copy
of CareerOS ran today against the live job boards.

    python3 .github/scripts/public_proof.py                      # run everything
    python3 .github/scripts/public_proof.py --from-log out.txt --duration 583
                                                                 # parse a saved run

Only counts are written. No job titles, companies, links or pay ever reach the
committed files: the dry run's full output stays on the runner and is thrown
away when the job ends.

If the dry run fails, the receipt says so ("status": "failed") and the numbers
are left empty. A receipt that guesses is worse than no receipt.
"""

import argparse
import json
import os
import platform
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TESTS_DIR = ROOT / "careeros" / "tests"
PROOF_DIR = ROOT / "proof"
DRY_RUN_TIMEOUT = 25 * 60  # seconds; a normal run takes about 10 minutes

# The engine's own log lines, read as written by careeros/ats.py,
# careeros/run_daily.py and careeros/prefilter.py.
PATTERNS = {
    "boards": re.compile(r"ats: (\d+) boards read, (\d+) quiet, (\d+) postings"),
    "fetched": re.compile(r"fetched (\d+) listings from (\d+) sources"),
    "kept": re.compile(r"prefilter: (\d+) in, (\d+) kept"),
}
DONE_MARKER = "=== careeros-daily run complete in"
DRY_MARKER = "DRY RUN — nothing sent"


def count_tests():
    """Run every test file the suite runs; count files passed and [PASS] lines."""
    sys.path.insert(0, str(TESTS_DIR))
    from run_all import TESTS  # the same list the official suite uses

    files_passed, checks_passed, checks_failed = 0, 0, 0
    for name in TESTS:
        proc = subprocess.run([sys.executable, str(TESTS_DIR / name)],
                              capture_output=True, text=True)
        out = proc.stdout + proc.stderr
        checks_passed += out.count("[PASS]")
        checks_failed += out.count("[FAIL]")
        if proc.returncode == 0:
            files_passed += 1
    return {"files_total": len(TESTS), "files_passed": files_passed,
            "checks_passed": checks_passed, "checks_failed": checks_failed}


def sources_total():
    """How many sources the run tries: the employer boards as one, plus each
    enabled feed in config/sources.json (same rule as sources.fetch_all)."""
    config = json.loads((ROOT / "config" / "sources.json").read_text("utf-8"))
    feeds = [s for s in config.get("sources", [])
             if isinstance(s, dict) and s.get("enabled")]
    return len(feeds) + (1 if config.get("ats_enabled", True) else 0)


def run_dry_run():
    """Run the engine with no Telegram keys at all, so it cannot send."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("TELEGRAM_")}
    started = time.monotonic()
    try:
        proc = subprocess.run(
            [sys.executable, str(ROOT / "careeros" / "run_daily.py"), "--dry-run"],
            capture_output=True, text=True, env=env, timeout=DRY_RUN_TIMEOUT)
        output, code = proc.stdout + proc.stderr, proc.returncode
    except subprocess.TimeoutExpired:
        output, code = "", "timeout"
    return output, code, time.monotonic() - started


def parse(output, code):
    """Turn the run's output into (status, reason, numbers)."""
    if code == "timeout":
        return "failed", f"timed out after {DRY_RUN_TIMEOUT // 60} minutes", {}
    # The engine always exits 0 by design (careeros/_shared/runner.py), so
    # success is proved by its own completion line, not by the exit code.
    if "Preflight failed" in output:
        return "failed", "preflight check failed (network or config)", {}
    if "uncaught exception" in output:
        return "failed", "engine crashed during the run", {}
    if code != 0:
        return "failed", f"engine exited with code {code}", {}
    if DONE_MARKER not in output or DRY_MARKER not in output:
        return "failed", "run did not reach its completion line", {}

    found = {key: pattern.search(output) for key, pattern in PATTERNS.items()}
    missing = [key for key, match in found.items() if match is None]
    if missing:
        return "failed", f"log lines missing: {', '.join(missing)}", {}

    read, quiet, _ = (int(x) for x in found["boards"].groups())
    fetched, live = (int(x) for x in found["fetched"].groups())
    numbers = {
        "sources_live": live,
        "sources_total": sources_total(),
        "boards_read": read,
        "boards_quiet": quiet,
        "listings_fetched": fetched,
        "kept_after_filters": int(found["kept"].group(2)),
    }
    return "ok", "", numbers


def render_readme(proof):
    n = proof.get("numbers") or {}
    t = proof["tests"]
    when = proof["run_at_utc"].replace("T", " ").replace("Z", " UTC")
    lines = [
        "# Latest public run",
        "",
        "This file is rewritten by a robot every day "
        "([workflow](../.github/workflows/public-proof.yml)). It is the receipt "
        "that this public copy of CareerOS actually ran today: the tests, then "
        "the real engine against live job boards, in dry-run mode (it builds "
        "the digest and sends nothing).",
        "",
        "Only counts are published here. No job titles, companies, links or pay.",
        "",
        "| | |",
        "|---|---|",
        f"| **Status** | {'Ran clean' if proof['status'] == 'ok' else 'FAILED: ' + proof['reason']} |",
        f"| **When** | {when} |",
        f"| **Took** | {proof['duration_seconds'] // 60} min {proof['duration_seconds'] % 60} s |",
    ]
    if proof["status"] == "ok":
        lines += [
            f"| **Sources answering** | {n['sources_live']} of {n['sources_total']} |",
            f"| **Employer job boards read** | {n['boards_read']} "
            f"(plus {n['boards_quiet']} with nothing posted) |",
            f"| **Listings fetched** | {n['listings_fetched']:,} |",
            f"| **Kept after the hard rules** | {n['kept_after_filters']:,} |",
        ]
    lines += [
        f"| **Test files passing** | {t['files_passed']} of {t['files_total']} |",
        f"| **Checks passing** | {t['checks_passed']} |",
        f"| **Python** | {proof['python']} |",
        f"| **Run log** | [{proof['run_url']}]({proof['run_url']}) |",
        "",
        "Machine-readable copy: [latest.json](latest.json).",
        "",
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--from-log", help="parse a saved dry-run output instead of running")
    parser.add_argument("--duration", type=float, default=0.0,
                        help="seconds the saved run took (with --from-log)")
    args = parser.parse_args()

    run_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    tests = count_tests()

    if args.from_log:
        output, code, duration = Path(args.from_log).read_text("utf-8"), 0, args.duration
    else:
        output, code, duration = run_dry_run()
    status, reason, numbers = parse(output, code)

    server = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    repo = os.environ.get("GITHUB_REPOSITORY", "javierxelias-svg/careeros-public")
    run_id = os.environ.get("GITHUB_RUN_ID")
    proof = {
        "status": status,
        "reason": reason,
        "run_at_utc": run_at,
        "duration_seconds": int(round(duration)),
        "numbers": numbers or None,
        "tests": tests,
        "python": platform.python_version(),
        "run_url": f"{server}/{repo}/actions/runs/{run_id}" if run_id
                   else f"{server}/{repo}/actions/workflows/public-proof.yml",
    }

    PROOF_DIR.mkdir(exist_ok=True)
    (PROOF_DIR / "latest.json").write_text(json.dumps(proof, indent=2) + "\n", "utf-8")
    (PROOF_DIR / "README.md").write_text(render_readme(proof), "utf-8")

    # Aggregate numbers only, so the public Actions log matches the receipt.
    print(json.dumps(proof, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
