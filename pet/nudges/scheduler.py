"""Decides *when* the pet comes over to bother you.

All timing runs on QTimer rather than background threads, so a nudge can touch
the pet directly without any cross-thread hand-off. Nudges are emitted on the
event bus; the window decides how to deliver them.
"""
from datetime import datetime

from PySide6.QtCore import QObject, QTimer

import config
from core.events import bus
from nudges import lines

try:
    import psutil
except ImportError:      # battery nudges simply switch off
    psutil = None


def _muted() -> bool:
    return config.in_quiet_hours(datetime.now().hour)


class Nudges(QObject):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._timers: list[QTimer] = []

        # Battery nudges are edge-triggered: we fire once when you cross the
        # threshold, then stay quiet until the condition clears. Otherwise the
        # pet would scream every 60 seconds from 24% down to zero.
        self._warned_low = False
        self._warned_full = False
        self._has_battery = psutil is not None and psutil.sensors_battery() is not None

    def start(self) -> None:
        self._every(config.WATER_INTERVAL_MIN * 60_000, self._water)
        self._every(config.QUOTE_INTERVAL_MIN * 60_000, self._quote)
        if self._has_battery:
            self._every(config.BATTERY_POLL_SEC * 1000, self._battery)
        else:
            print("(no battery detected — charging reminders disabled)")

        # Say hello a moment after launch, once the window has settled.
        QTimer.singleShot(1800, lambda: bus.say_here.emit(lines.greeting(), "happy"))

    def _every(self, ms: float, fn) -> None:
        t = QTimer(self)
        t.timeout.connect(fn)
        t.start(max(1000, int(ms)))
        self._timers.append(t)

    # --- individual nudges ---

    def _water(self) -> None:
        if not _muted():
            bus.say.emit(lines.water(), "nag")

    def _quote(self) -> None:
        if not _muted():
            bus.say_optional.emit(lines.quote(), "think")   # nice-to-have, sheddable

    def _battery(self) -> None:
        b = psutil.sensors_battery()
        if b is None:
            return
        pct = int(round(b.percent))

        if not b.power_plugged and pct <= config.BATTERY_LOW_PCT:
            if not self._warned_low:
                self._warned_low = True
                bus.say.emit(lines.low_battery(pct), "alert")   # ignores quiet hours
        elif b.power_plugged or pct > config.BATTERY_LOW_PCT + 5:
            self._warned_low = False

        if b.power_plugged and pct >= config.BATTERY_FULL_PCT:
            if not self._warned_full and not _muted():
                self._warned_full = True
                bus.say.emit(lines.full_battery(pct), "nag")
        elif not b.power_plugged:
            self._warned_full = False

    # --- manual triggers (tray menu) ---

    def water_now(self) -> None:
        bus.say.emit(lines.water(), "nag")

    def quote_now(self) -> None:
        bus.say.emit(lines.quote(), "think")

    def battery_now(self) -> None:
        if not self._has_battery:
            bus.say.emit("no battery on this machine — I can't help there.", "think")
            return
        b = psutil.sensors_battery()
        pct = int(round(b.percent))
        plug = "plugged in" if b.power_plugged else "on battery"
        bus.say.emit(f"{pct}%, {plug}.", "happy")
