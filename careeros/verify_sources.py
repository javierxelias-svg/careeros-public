#!/usr/bin/env python3
"""
Phase 0 source verification.

Hits every configured source once and reports what actually came back: status
code, payload size, record count, and one sample record. Writes the result to
verification/ as a dated receipt and stamps config/sources.json so the plan
reflects reality rather than assumption.

This exists because "the endpoint should work" is not evidence. Run:

    python3 careeros/verify_sources.py
"""

import json
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ElementTree
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _shared.paths import SOURCES_CONFIG, VERIFICATION_DIR  # noqa: E402

REQUEST_TIMEOUT = 30
POLITENESS_DELAY = 1.0


def fetch(url, user_agent):
    request = urllib.request.Request(
        url,
        headers={"User-Agent": user_agent, "Accept": "*/*"},
    )
    started = time.monotonic()
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
        body = response.read()
        status = response.status
    elapsed_ms = int((time.monotonic() - started) * 1000)
    return status, body, elapsed_ms


def summarize_json(body, source_id):
    data = json.loads(body.decode("utf-8", errors="replace"))
    if isinstance(data, dict):
        for key in ("jobs", "results", "data", "hits"):
            if isinstance(data.get(key), list):
                records = data[key]
                break
        else:
            return 0, {"_shape": "dict", "_keys": list(data.keys())[:12]}
    elif isinstance(data, list):
        records = data
        # RemoteOK puts a legal notice in slot 0.
        if source_id == "remoteok" and records and isinstance(records[0], dict):
            if "legal" in records[0]:
                records = records[1:]
    else:
        return 0, {"_shape": type(data).__name__}

    if not records:
        return 0, {}
    sample = records[0]
    if isinstance(sample, dict):
        trimmed = {}
        for key, value in list(sample.items())[:14]:
            text = str(value)
            trimmed[key] = text[:110] + ("…" if len(text) > 110 else "")
        return len(records), trimmed
    return len(records), {"_sample": str(sample)[:200]}


def summarize_rss(body):
    root = ElementTree.fromstring(body)
    items = root.findall(".//item")
    if not items:
        return 0, {}
    first = items[0]
    sample = {}
    for child in first:
        tag = child.tag.split("}")[-1]
        text = (child.text or "").strip()
        sample[tag] = text[:110] + ("…" if len(text) > 110 else "")
    return len(items), sample


def verify_source(source, user_agent):
    result = {
        "id": source["id"],
        "name": source["name"],
        "url": source["url"],
        "type": source["type"],
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    try:
        status, body, elapsed_ms = fetch(source["url"], user_agent)
    except urllib.error.HTTPError as exc:
        result.update(ok=False, status=exc.code, error=f"HTTP {exc.code} {exc.reason}")
        return result
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        result.update(ok=False, status=None, error=f"network: {exc}")
        return result

    result.update(status=status, bytes=len(body), elapsed_ms=elapsed_ms)

    try:
        if source["type"] in ("json_api", "algolia"):
            count, sample = summarize_json(body, source["id"])
        elif source["type"] == "rss":
            count, sample = summarize_rss(body)
        else:
            result.update(ok=False, error=f"unknown type {source['type']}")
            return result
    except (json.JSONDecodeError, ElementTree.ParseError, UnicodeDecodeError) as exc:
        result.update(ok=False, error=f"unparseable: {exc}")
        return result

    result.update(ok=count > 0, records=count, sample=sample)
    if count == 0:
        result["error"] = "parsed successfully but returned zero records"
    return result


def main():
    config = json.loads(SOURCES_CONFIG.read_text(encoding="utf-8"))
    user_agent = config.get("user_agent", "CareerOS/0.1")
    results = []

    for source in config["sources"]:
        print(f"\n--- {source['name']} ({source['id']}) ---")
        print(f"    {source['url']}")
        result = verify_source(source, user_agent)
        results.append(result)

        if result["ok"]:
            print(
                f"    PASS  status={result['status']} "
                f"records={result['records']} "
                f"bytes={result['bytes']} {result['elapsed_ms']}ms"
            )
            print("    sample fields:")
            for key, value in result.get("sample", {}).items():
                print(f"      {key}: {value}")
        else:
            print(f"    FAIL  {result.get('error')}")

        source["verified"] = {
            "ok": result["ok"],
            "checked_at": result["checked_at"],
            "records": result.get("records"),
            "error": result.get("error"),
        }
        if not result["ok"]:
            source["enabled"] = False
        time.sleep(POLITENESS_DELAY)

    SOURCES_CONFIG.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")

    VERIFICATION_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    receipt = VERIFICATION_DIR / f"source-verification-{stamp}.json"
    receipt.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")

    passed = sum(1 for r in results if r["ok"])
    print(f"\n{'=' * 60}")
    print(f"RESULT: {passed}/{len(results)} sources live")
    print(f"receipt: {receipt}")
    print(f"config stamped: {SOURCES_CONFIG}")
    for result in results:
        mark = "PASS" if result["ok"] else "FAIL"
        detail = (
            f"{result.get('records')} records"
            if result["ok"]
            else result.get("error", "")[:70]
        )
        print(f"  [{mark}] {result['id']}: {detail}")

    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
