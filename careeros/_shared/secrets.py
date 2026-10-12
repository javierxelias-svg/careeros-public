"""
Secret retrieval for CareerOS.

Keychain first, environment second. Never assume launchd inherited a shell
environment, because it did not — launchd agents start with a nearly empty
environment regardless of what is in .zshrc.

Usage:
    from _shared.secrets import get_secret
    token = get_secret("TELEGRAM_BOT_TOKEN")          # None if missing
    token = get_secret("TELEGRAM_BOT_TOKEN", required=True)  # raises if missing
"""

import os
import subprocess
import time

SECURITY_BIN = "/usr/bin/security"
KEYCHAIN_TIMEOUT = 10
RETRY_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 1


class MissingSecret(RuntimeError):
    """Raised when a required secret is not available from any source."""


def _from_keychain(name):
    """Read a generic password from the login Keychain. Returns '' on any failure."""
    if not os.path.exists(SECURITY_BIN):
        return ""
    for attempt in range(RETRY_ATTEMPTS):
        try:
            result = subprocess.run(
                [SECURITY_BIN, "find-generic-password", "-s", name, "-w"],
                capture_output=True,
                text=True,
                timeout=KEYCHAIN_TIMEOUT,
            )
        except (subprocess.TimeoutExpired, OSError):
            if attempt < RETRY_ATTEMPTS - 1:
                time.sleep(RETRY_DELAY_SECONDS)
                continue
            return ""
        if result.returncode == 0:
            return (result.stdout or "").strip()
        # returncode 44 means "not found" — a real answer, not a transient fault.
        # Retrying it wastes time, so stop.
        if result.returncode == 44:
            return ""
        if attempt < RETRY_ATTEMPTS - 1:
            time.sleep(RETRY_DELAY_SECONDS)
    return ""


def get_secret(name, required=False):
    """
    Return the secret value for `name`, or None if unavailable.

    Order: Keychain, then environment variable. If `required` and neither has
    it, raise MissingSecret so preflight can report a specific dependency
    rather than failing later with an opaque error.
    """
    value = _from_keychain(name) or os.environ.get(name, "").strip()
    if not value:
        if required:
            raise MissingSecret(
                f"{name} not found in Keychain or environment. "
                f"Store it with: security add-generic-password -a \"$USER\" "
                f"-s {name} -w '<value>'"
            )
        return None
    return value


def has_secret(name):
    """True if the secret is retrievable. Used by preflight without exposing the value."""
    return bool(get_secret(name))
