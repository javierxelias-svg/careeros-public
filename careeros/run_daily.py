#!/usr/bin/env python3
"""
CareerOS daily run — Phase 1 entry point.

    python3 careeros/run_daily.py            # full run, sends to Telegram
    python3 careeros/run_daily.py --dry-run  # print the message, send nothing
    python3 careeros/run_daily.py --if-due   # send only if today's digest has
                                             # not gone out yet and it is past
                                             # the delivery hour. Safe to call
                                             # every half hour.

Pipeline: fetch → normalize → prefilter → dedupe → rank → format → send →
commit. The ledger is written only after Telegram confirms delivery, so a
failed send means tomorrow retries rather than losing those listings forever.
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import curated  # noqa: E402
import dedupe  # noqa: E402
import digest  # noqa: E402
import enrich  # noqa: E402
import forms  # noqa: E402
import prefilter  # noqa: E402
import sources  # noqa: E402
from _shared import notify, runner  # noqa: E402
from _shared.paths import SENT_DIR, ensure_dirs  # noqa: E402


def _archive(date_label, message, chosen, stats):
    ensure_dirs()
    path = SENT_DIR / f"{datetime.now().strftime('%Y-%m-%d')}.json"
    payload = {
        "date": date_label,
        "stats": stats,
        "message": message,
        "listings": [
            {
                **item.listing.as_dict(),
                "tier": item.tier,
                "score": item.score,
                # Kept so the ranking can be calibrated against what actually
                # got applied to, rather than tuned on vibes.
                "fit_lane": item.fit_lane,
                "fit_label": item.fit_label,
                "freedom": item.freedom,
                "geo_class": item.geo_class,
                "company_labels": item.company_labels,
                "salary": item.salary.as_dict(),
                "green": item.green,
                "red": item.red,
            }
            for _, item in chosen
        ],
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


# The hour, local, before which a catch-up run stays quiet. Without it a laptop
# that wakes at 02:00 for a maintenance window would deliver the digest at 02:00.
DELIVERY_HOUR = 6


def already_sent_today():
    """True when state/sent/<today>.json exists — the archive is written only
    after Telegram confirms, so its presence is proof of delivery."""
    return (SENT_DIR / f"{datetime.now().strftime('%Y-%m-%d')}.json").exists()


def is_due(now=None):
    """
    (due, reason) for a --if-due invocation.

    Why this exists: on 2026-08-18 the 06:00 calendar event fired while the Mac
    was in DarkWake — awake enough for launchd to try, not awake enough to run a
    GUI-domain agent. launchd returned EX_CONFIG (78), no Python process ever
    started, so nothing wrote a log and nothing raised an alert. The operator
    found out because the operator's phone was quiet. A calendar event on a laptop that
    sleeps is a hope, not a schedule; this makes the run idempotent instead, so
    any wake-up during the day delivers the day's digest exactly once.
    """
    now = now or datetime.now()
    if already_sent_today():
        return False, "already delivered today"
    if now.hour < DELIVERY_HOUR:
        return False, f"before {DELIVERY_HOUR:02d}:00 local, holding"
    return True, "due"


def make_main(dry_run):
    def main(logger):
        date_label = datetime.now().strftime("%b %-d, %Y")

        listings, source_status = sources.fetch_all(logger)
        sources_live = sum(1 for v in source_status.values() if "listings" in str(v))
        logger.info("fetched %d listings from %d sources", len(listings), sources_live)

        kept, rejections = prefilter.run(listings, logger)

        seen = dedupe.load_seen()
        logger.info("ledger holds %d live keys", len(seen))
        fresh = dedupe.filter_new(kept, seen, logger)

        # Open the job pages before ranking. Only survivors, only the top slice,
        # so this is tens of requests rather than hundreds. Everything downstream
        # then works on published pay and real residency rules instead of a band
        # guessed from a job title. See enrich.py for why this exists.
        user_agent = sources.load_config().get(
            "user_agent", "CareerOS/0.1 (personal job search)"
        )
        enriched, beyond_cap = enrich.run(
            fresh, user_agent, logger, ranker=digest.rank
        )

        (chosen, main_lane, wildcards, us_only, overflow, suppressed,
         walled) = digest.select(fresh)

        # Read each chosen role's application form, so the digest can say which
        # ones are quick and which ask for years. See forms.py.
        forms.annotate([item for _, item in chosen], user_agent, logger)

        stats = {
            "fetched": len(listings),
            "kept": len(kept),
            "new": len(fresh),
            "sources_live": sources_live,
            "sources_total": len(source_status),
            # Key must match what prefilter actually emits. v1 read a string
            # that no longer existed, so this counter was permanently 0.
            "no_salary": rejections.get(
                "no salary stated and role family unrecognised", 0
            ),
            "enriched": enriched,
            "beyond_cap": beyond_cap,
        }
        message = digest.build(
            chosen, main_lane, wildcards, us_only, overflow, suppressed, walled,
            stats, date_label
        )

        logger.info("digest:\n%s", message)

        # The curated page rebuilds from the whole surviving pool, not just from
        # what is new today, so a role stays on the list until it disappears from
        # the boards. Wrapped because a broken page must never cost the operator
        # the operator's digest: the Telegram send is the run's actual job.
        try:
            path, curated_meta = curated.run(
                kept, logger=logger, scanned=len(listings))
            logger.info("curated page ready: %s (%s)", path, curated_meta)
        except Exception as exc:  # noqa: BLE001 - deliberately broad, see above
            logger.error("curated page FAILED, digest unaffected: %s", exc,
                         exc_info=True)

        if dry_run:
            print("\n" + "=" * 60)
            print("DRY RUN — nothing sent, ledger untouched")
            print("=" * 60)
            print(message)
            print("=" * 60)
            logger.info("dry run complete, no send, no ledger write")
            return

        parts = digest.split_messages(message)
        message_ids = []
        for index, part in enumerate(parts):
            message_id = notify.send(part)
            if message_id is None:
                logger.error(
                    "delivery failed on part %d/%d — ledger NOT written, "
                    "will retry tomorrow", index + 1, len(parts)
                )
                raise RuntimeError("Telegram delivery failed; see state/ALERT-*.txt")
            message_ids.append(message_id)

        logger.info("delivered %d message(s), message_ids=%s", len(parts), message_ids)
        archive = _archive(date_label, message, chosen, stats)
        logger.info("archived to %s", archive)
        dedupe.commit(chosen, logger)

    return main


def parse_args():
    parser = argparse.ArgumentParser(description="CareerOS daily job digest")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="print the digest instead of sending; leaves the ledger untouched",
    )
    parser.add_argument(
        "--if-due", action="store_true", dest="if_due",
        help="exit quietly unless today's digest is still owed; for a catch-up "
             "schedule on a machine that sleeps",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    if args.if_due:
        due, why = is_due()
        if not due:
            print(f"not due: {why}")
            sys.exit(0)
    sys.exit(
        runner.guarded(
            make_main(args.dry_run),
            name="careeros-daily",
            require_delivery=not args.dry_run,
        )
    )
