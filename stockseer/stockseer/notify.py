"""Alert store with delivery tracking.

Jarvis polls this over HTTP rather than StockSeer pushing to it. That choice is
deliberate: push needs FCM, a Google project, a server certificate and a device
token refresh loop. Polling needs a phone on the same wifi. For alerts that
matter over a 90-minute window, polling every 20 seconds is indistinguishable
from push and has no moving parts to break on listing morning.

Delivery is tracked so an alert vibrates the phone exactly once. Duplicate
buzzing during a fast-moving listing is how a useful alert becomes noise the
user swipes away without reading.
"""

from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

log = logging.getLogger(__name__)

STORE = Path(__file__).resolve().parent.parent / "artifacts" / "notifications.json"
_LOCK = threading.Lock()


def _now() -> float:
    return time.monotonic()

# Android vibration patterns, in milliseconds: [wait, buzz, wait, buzz, ...].
#
# Every pattern runs 2-3 seconds. A market alert competes with a pocket, a
# conversation, and a phone lying face-down on a desk -- a 200ms tick loses all
# three. Long enough to notice, and the *rhythm* carries the urgency so you know
# whether to look before you look:
#
#   info      two slow buzzes            ~2.1s   an FYI
#   act       three heavy buzzes         ~2.9s   a decision is due
#   critical  six rapid pulses           ~3.2s   money is moving right now
PATTERNS = {
    "info":     [0, 900, 300, 900],
    "act":      [0, 800, 250, 800, 250, 800],
    "critical": [0, 400, 150, 400, 150, 400, 150, 400, 150, 400, 150, 400],
}


@dataclass
class Notification:
    kind: str                 # "ipo_open" | "ipo_closing" | "listing" | "exit" | ...
    urgency: str              # "info" | "act" | "critical"
    title: str
    body: str
    symbol: str = ""
    created_at: str = ""
    id: str = ""
    delivered: bool = False
    delivered_at: str | None = None
    pushed: bool = False              # reached the phone via the ntfy relay
    pushed_at: str | None = None
    data: dict = field(default_factory=dict)

    def __post_init__(self):
        self.id = self.id or uuid.uuid4().hex[:12]
        self.created_at = self.created_at or datetime.now().astimezone().isoformat(
            timespec="seconds")

    @property
    def vibration(self) -> list[int]:
        return PATTERNS.get(self.urgency, PATTERNS["info"])


def _delivered(n) -> bool:
    """Did this alert actually reach a human?

    Three ways it counts, and the distinction is what makes a retry possible:

    * ``pushed``            -- the relay accepted it.
    * ``handed_to_client``  -- Jarvis was polling and will collect it.
    * ``push_skipped``      -- no transport is configured at all, so there is
      nothing to retry and re-queueing would only duplicate the local record.

    Anything else is an alert that was written down and never sent, which is
    exactly the case that must be allowed to try again on the next run.
    """
    return bool(getattr(n, "pushed", False)
                or n.data.get("handed_to_client")
                or n.data.get("push_skipped"))


class NotificationHub:
    def __init__(self, path: Path | str | None = None, keep: int = 400):
        self.path = Path(path or STORE)
        self.keep = keep
        self.items: list[Notification] = []
        self._last_poll = 0.0
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            self.items = [Notification(**n) for n in raw]
        except (json.JSONDecodeError, TypeError) as exc:
            log.warning("notification store unreadable (%s); starting fresh", exc)
            self.items = []

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps([asdict(n) for n in self.items[-self.keep:]], indent=2),
            encoding="utf-8",
        )

    # ------------------------------------------------------------------ #
    def push(self, notif: Notification, dedupe_key: str | None = None) -> Notification | None:
        """Store an alert. Returns None if `dedupe_key` was already seen.

        Dedupe matters more than it looks: the watcher re-evaluates every few
        seconds, and without a key a single stop breach would buzz continuously.
        """
        with _LOCK:
            if dedupe_key:
                # Suppress only a copy that actually reached someone.
                #
                # The key is recorded before the push is attempted, which was
                # harmless while every run started with an empty store. Once
                # the CI job began restoring `artifacts/` from cache, it stopped
                # being harmless: a push that failed on the first run of the day
                # left its key on disk, so every later run saw "already sent",
                # queued nothing, and exited 0. Five scheduled retries became
                # five no-ops that reported success -- the precise silent
                # failure this alerting exists to prevent.
                if any(n.data.get("dedupe") == dedupe_key and _delivered(n)
                       for n in self.items):
                    return None
                # Drop the undelivered older copy so the store does not grow a
                # duplicate for every retry of the same event.
                self.items = [n for n in self.items
                              if n.data.get("dedupe") != dedupe_key]
                notif.data["dedupe"] = dedupe_key
            self.items.append(notif)
            self._save()
        log.info("[%s] %s", notif.urgency, notif.title)

        # Fan out to the relay only when Jarvis is not already collecting.
        #
        # Both transports delivering the same alert means the phone buzzes
        # twice for one event -- exactly the noise that gets notifications
        # swiped away unread. Jarvis gives richer alerts (custom vibration
        # rhythms, full body text), so it wins when it is present; ntfy is the
        # fallback for when the PC is off and nothing is polling.
        try:
            from .push import configured, push_notification

            if not configured():
                # Nothing is wrong here on a laptop with Jarvis polling, but on
                # a cloud runner it means the alert reached nobody. The caller
                # decides whether that is fatal; the flag makes it visible.
                notif.data.setdefault("push_skipped", "no NTFY_TOPIC")
            elif self.client_recently_polled():
                # Jarvis is live and will collect this from pending(). That is
                # a real delivery, so it must count for dedupe -- otherwise the
                # watcher re-queues the same alert every few seconds.
                notif.data["handed_to_client"] = True
                with _LOCK:
                    self._save()
            else:
                if push_notification(notif):
                    # Record it, or Jarvis re-buzzes for this alert the next
                    # time it connects -- possibly days later, for an event
                    # that is long over.
                    notif.pushed = True
                    notif.pushed_at = datetime.now().astimezone().isoformat(
                        timespec="seconds")
                    with _LOCK:
                        self._save()
        except Exception as exc:
            log.debug("push transport unavailable: %s", exc)
        return notif

    # ------------------------------------------------------------------ #
    def note_poll(self) -> None:
        """Called when a client fetches pending alerts."""
        self._last_poll = _now()

    def client_recently_polled(self, within: float = 90.0) -> bool:
        """Is Jarvis actively collecting right now?

        The window is generous relative to the 5-20s poll interval, so one
        dropped request does not cause a duplicate buzz.
        """
        return (_now() - self._last_poll) < within

    def alert(self, kind: str, urgency: str, title: str, body: str,
              symbol: str = "", dedupe_key: str | None = None,
              **data) -> Notification | None:
        return self.push(
            Notification(kind=kind, urgency=urgency, title=title, body=body,
                         symbol=symbol, data=data),
            dedupe_key=dedupe_key,
        )

    def pending(self, limit: int = 20, max_age_hours: float = 12.0
                ) -> list[Notification]:
        """Alerts still owed to Jarvis.

        Excludes anything ntfy already delivered, and anything stale. A market
        alert from two days ago is not news -- buzzing about it on reconnect
        trains you to ignore the one that arrives during the session.
        """
        cutoff = datetime.now().astimezone() - timedelta(hours=max_age_hours)
        out = []
        for n in self.items:
            if n.delivered or n.pushed:
                continue
            try:
                if datetime.fromisoformat(n.created_at) < cutoff:
                    continue
            except (TypeError, ValueError):
                pass
            out.append(n)
        with _LOCK:
            return out[:limit]

    def mark_delivered(self, ids: list[str]) -> int:
        stamp = datetime.now().astimezone().isoformat(timespec="seconds")
        n = 0
        with _LOCK:
            for item in self.items:
                if item.id in ids and not item.delivered:
                    item.delivered = True
                    item.delivered_at = stamp
                    n += 1
            if n:
                self._save()
        return n

    def recent(self, limit: int = 50) -> list[Notification]:
        with _LOCK:
            return list(reversed(self.items[-limit:]))

    def clear(self) -> None:
        with _LOCK:
            self.items = []
            self._save()


_HUB: NotificationHub | None = None


def hub() -> NotificationHub:
    global _HUB
    if _HUB is None:
        _HUB = NotificationHub()
    return _HUB
