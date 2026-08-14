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
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)

STORE = Path(__file__).resolve().parent.parent / "artifacts" / "notifications.json"
_LOCK = threading.Lock()

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
    data: dict = field(default_factory=dict)

    def __post_init__(self):
        self.id = self.id or uuid.uuid4().hex[:12]
        self.created_at = self.created_at or datetime.now().astimezone().isoformat(
            timespec="seconds")

    @property
    def vibration(self) -> list[int]:
        return PATTERNS.get(self.urgency, PATTERNS["info"])


class NotificationHub:
    def __init__(self, path: Path | str | None = None, keep: int = 400):
        self.path = Path(path or STORE)
        self.keep = keep
        self.items: list[Notification] = []
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
                if any(n.data.get("dedupe") == dedupe_key for n in self.items):
                    return None
                notif.data["dedupe"] = dedupe_key
            self.items.append(notif)
            self._save()
        log.info("[%s] %s", notif.urgency, notif.title)

        # Fan out to the phone directly, if a relay is configured. Done after
        # the local save so a push failure can never lose the alert: Jarvis can
        # still collect it from the queue when the PC is next reachable.
        try:
            from .push import configured, push_notification

            if configured():
                push_notification(notif)
        except Exception as exc:
            log.debug("push transport unavailable: %s", exc)
        return notif

    def alert(self, kind: str, urgency: str, title: str, body: str,
              symbol: str = "", dedupe_key: str | None = None,
              **data) -> Notification | None:
        return self.push(
            Notification(kind=kind, urgency=urgency, title=title, body=body,
                         symbol=symbol, data=data),
            dedupe_key=dedupe_key,
        )

    def pending(self, limit: int = 20) -> list[Notification]:
        with _LOCK:
            return [n for n in self.items if not n.delivered][:limit]

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
