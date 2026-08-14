"""Push alerts to a phone via ntfy.sh, with no PC in the path.

The local queue in ``notify.py`` needs Jarvis to poll it, which needs the PC
awake and reachable. That is fine at a desk and useless at 10:00 on a listing
morning when the machine is asleep in another room.

ntfy inverts it: StockSeer POSTs to a public relay, the phone holds a standing
subscription, and the alert arrives whether the sender still exists or not. That
is what lets the whole thing run on a throwaway GitHub Actions box.

    NTFY_TOPIC=jainish-ipo-x7k2m9        pick something long and unguessable
    NTFY_SERVER=https://ntfy.sh          override for a self-hosted relay

**The topic name is the only secret.** ntfy has no accounts; anyone who guesses
the topic can read your alerts and post to it. Treat it like a password.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request

log = logging.getLogger(__name__)

DEFAULT_SERVER = "https://ntfy.sh"

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


def configured() -> bool:
    return bool(os.environ.get("NTFY_TOPIC", "").strip())


def topic() -> str:
    return os.environ.get("NTFY_TOPIC", "").strip()


def server() -> str:
    return os.environ.get("NTFY_SERVER", DEFAULT_SERVER).rstrip("/")


def push(title: str, body: str, urgency: str = "info", kind: str = "",
         click: str | None = None, timeout: int = 10) -> bool:
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

    req = urllib.request.Request(url, data=body.encode("utf-8"),
                                 headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            ok = 200 <= resp.status < 300
            if ok:
                log.info("pushed: %s", title)
            return ok
    except urllib.error.HTTPError as exc:
        log.warning("ntfy rejected the push (%s): %s", exc.code, exc.reason)
    except Exception as exc:
        log.warning("ntfy push failed: %s", exc)
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
    return f"push: {server()}/{masked}"


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
