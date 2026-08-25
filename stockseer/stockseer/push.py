"""Push alerts to a phone via ntfy.sh, with no PC in the path.

The local queue in ``notify.py`` needs Jarvis to poll it, which needs the PC
awake and reachable. That is fine at a desk and useless at 10:00 on a listing
morning when the machine is asleep in another room.

ntfy inverts it: StockSeer POSTs to a public relay, the phone holds a standing
subscription, and the alert arrives whether the sender still exists or not. That
is what lets the whole thing run on a throwaway GitHub Actions box.

    NTFY_TOPIC=jainish-ipo-x7k2m9        pick something long and unguessable
    NTFY_TOKEN=tk_...                    optional; from a free ntfy.sh account
    NTFY_SERVER=https://ntfy.sh          override for a self-hosted relay

**Treat the topic name as a password.** Without a token, ntfy has no accounts:
anyone who guesses the topic can read your alerts and post to them.

**A token matters most from CI.** Anonymous publishing is metered per source
IP, and a GitHub runner shares its IP with every other job on the platform, so
the budget is frequently already spent. Authenticated requests are metered
against your account instead, which is why the same push can succeed from home
and fail from Actions.
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request

log = logging.getLogger(__name__)

DEFAULT_SERVER = "https://ntfy.sh"

# Why the last push failed, so callers can print a cause rather than
# "rejected". Cleared on success.
LAST_ERROR: dict[str, str] = {}

# ntfy priority 1-5. Android maps 5 to an insistent, repeating alert that also
# pierces Do Not Disturb -- which is right for a stop-loss and wrong for an FYI.
PRIORITY = {"info": 3, "act": 4, "critical": 5}

# Emoji shortcodes ntfy renders as the notification icon, so the alert is
# identifiable in the shade before any text is read.
TAGS = {
    "ipo_closes_today": "rotating_light",
    "ipo_closes_tomorrow": "hourglass_flowing_sand",
    "ipo_opens_today": "calendar",
    "ipo_opens_soon": "calendar",
    "ipo_lists_tomorrow": "bell",
    "ipo_listing_soon": "eyes",
    "ipo_listed": "chart_with_upwards_trend",
    "ipo_buy": "moneybag",
    "ipo_near_target": "dart",
    "ipo_near_stop": "warning",
    "ipo_exit": "octagonal_sign",
    "test": "white_check_mark",
}


def _env(name: str) -> str:
    """Read a setting from the environment, falling back to .env.

    Goes through `config`, which has no third-party imports, so this keeps
    working on a runner that never ran `pip install`.
    """
    from .config import setting

    return setting(name)


def configured() -> bool:
    return bool(_env("NTFY_TOPIC"))


def topic() -> str:
    return _env("NTFY_TOPIC")


def token() -> str:
    return _env("NTFY_TOKEN")


def server() -> str:
    return (_env("NTFY_SERVER") or DEFAULT_SERVER).rstrip("/")


def push(title: str, body: str, urgency: str = "info", kind: str = "",
         click: str | None = None, timeout: int = 10,
         attempts: int = 3) -> bool:
    """Send one notification. Returns True if the relay accepted it.

    Never raises: a failed push must not take down the watcher mid-session. A
    missed alert is bad; a crashed monitor that stops sending *all* of them is
    worse.
    """
    if not configured():
        log.debug("NTFY_TOPIC not set; skipping push")
        return False

    url = f"{server()}/{topic()}"
    headers = {
        "Title": title.encode("utf-8", "replace").decode("latin-1", "replace"),
        "Priority": str(PRIORITY.get(urgency, 3)),
        "Tags": TAGS.get(kind, "chart_with_upwards_trend"),
    }
    if click:
        headers["Click"] = click
    tok = token()
    if tok:
        headers["Authorization"] = f"Bearer {tok}"

    # Retried because the most likely failure is transient. ntfy.sh meters per
    # source IP with a token bucket that refills one request every 5 seconds,
    # so the first backoff is 6s -- a 2s retry would arrive before the bucket
    # has anything in it and just burn another attempt. Backing off properly
    # also avoids the fail2ban ban that hammering through 429s can earn.
    delay = 6.0
    for attempt in range(1, attempts + 1):
        req = urllib.request.Request(url, data=body.encode("utf-8"),
                                     headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if 200 <= resp.status < 300:
                    log.info("pushed: %s", title)
                    LAST_ERROR.clear()
                    return True
                LAST_ERROR["reason"] = f"HTTP {resp.status}"
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", "replace")[:160].strip()
            except Exception:
                pass
            LAST_ERROR["reason"] = f"HTTP {exc.code} {exc.reason}" + (
                f" -- {detail}" if detail else "")
            # 4xx other than rate limiting will not improve by trying again.
            if exc.code != 429 and 400 <= exc.code < 500:
                break
        except Exception as exc:
            LAST_ERROR["reason"] = f"{type(exc).__name__}: {exc}"

        if attempt < attempts:
            log.info("push attempt %d failed (%s); retrying in %.0fs",
                     attempt, LAST_ERROR.get("reason"), delay)
            time.sleep(delay)
            delay *= 2

    log.warning("ntfy push failed: %s", LAST_ERROR.get("reason"))
    return False


def push_notification(notif) -> bool:
    """Send a :class:`stockseer.notify.Notification`."""
    return push(title=notif.title, body=notif.body,
                urgency=notif.urgency, kind=notif.kind)


def describe() -> str:
    if not configured():
        return "push: off (set NTFY_TOPIC to enable)"
    t = topic()
    masked = f"{t[:4]}…{t[-3:]}" if len(t) > 8 else "…"
    auth = "token" if token() else "anonymous"
    return f"push: {server()}/{masked} ({auth})"


def self_test() -> dict:
    """Send a test alert at each priority so the phone can be checked once."""
    results = {}
    for urgency in ("info", "act", "critical"):
        results[urgency] = push(
            title=f"StockSeer test ({urgency})",
            body=("If this arrived, alerts will reach you with the PC off "
                  "and Jarvis closed.\n"
                  "Critical alerts also pierce Do Not Disturb."),
            urgency=urgency, kind="test",
        )
    return results
