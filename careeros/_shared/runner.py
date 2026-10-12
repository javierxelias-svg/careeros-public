"""
Run harness: logging, the crash wrapper, and the preflight gate.

Every CareerOS entry point goes through `guarded()`. It guarantees three
things that are easy to forget and expensive to miss:

  - a preflight failure alerts and exits 0, rather than crash-looping
  - any uncaught exception sends its traceback to Telegram before exiting
  - every run leaves a dated log file behind whether it succeeded or not
"""

import logging
import sys
import traceback
from datetime import datetime

from _shared import notify, preflight
from _shared.paths import LOGS_DIR, ensure_dirs

EXIT_OK = 0


def setup_logging(name="careeros", verbose=True):
    ensure_dirs()
    log_path = LOGS_DIR / f"careeros-{datetime.now().strftime('%Y-%m-%d')}.log"
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-7s %(message)s")
    )
    logger.addHandler(file_handler)

    if verbose:
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setFormatter(logging.Formatter("%(levelname)-7s %(message)s"))
        logger.addHandler(stream_handler)

    logger.info("log file: %s", log_path)
    return logger


def guarded(main_fn, name="careeros", require_delivery=True, skip_preflight=False):
    """
    Run `main_fn(logger)` with preflight, crash alerting, and logging.

    Always returns an exit code of 0. A launchd agent that exits non-zero on a
    predictable condition (no network at 6am, laptop asleep) produces noise and
    respawn behaviour that obscures real faults. Failures are reported by
    Telegram alert, which is the channel the operator actually watches.
    """
    logger = setup_logging(name)
    started = datetime.now()
    logger.info("=== %s run start ===", name)

    if not skip_preflight:
        ok, results = preflight.run(require_delivery=require_delivery)
        logger.info("preflight:\n%s", preflight.format_results(results))
        if not ok:
            failures = [
                f"{check}: {detail}" for check, passed, detail in results if not passed
            ]
            message = "Preflight failed, run aborted.\n\n" + "\n".join(failures)
            logger.error(message)
            notify.alert(message)
            return EXIT_OK

    try:
        main_fn(logger)
    except Exception:
        tb = traceback.format_exc()
        logger.error("uncaught exception:\n%s", tb)
        notify.alert(f"Crashed during {name}.\n\n{tb[-2500:]}")
        return EXIT_OK

    elapsed = (datetime.now() - started).total_seconds()
    logger.info("=== %s run complete in %.1fs ===", name, elapsed)
    return EXIT_OK
