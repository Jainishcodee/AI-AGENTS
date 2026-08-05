"""The window the pet lives in.

Frameless + translucent + always-on-top, positioned along the bottom of the
screen. The window is much bigger than the pet (it has to hold the speech
bubble too), so a QRegion mask is applied to keep the empty area click-through
— without it the pet would eat clicks on whatever is behind it.
"""
import math
import random
import time
from collections import deque

from PySide6.QtCore import QPoint, QPointF, QRect, Qt, QTimer
from PySide6.QtGui import QCursor, QFont, QFontMetrics, QGuiApplication, QPainter, QRegion
from PySide6.QtWidgets import QApplication, QWidget

import config
from core import voice
from core.events import bus
from shell import bubble as bubble_ui
from shell.mascot import PetState
from shell.mascot import draw as draw_mascot
from shell.mascot import footprint as mascot_footprint

FRAME_MS = 16                    # ~60fps
BLINK_DUR = 0.16
STEP_HZ = 2.2                    # leg cycles per second at the strolling speed
DELIVER_SEC = 2.2                # a nudge must reach you within this long
MAX_QUEUE = 5                    # past this, optional chatter gets shed
BUBBLE_MAX_W = 300

# Said when you poke it. Deliberately short — a bubble you can't read in one
# glance is worse than no bubble.
POKE_LINES = [
    "oi.", "hi boss", "yes?", "that tickles", "I'm awake, I'm awake",
    "need something?", "at your service", "*blinks*",
]


def _clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


class PetWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool                      # keeps it out of alt-tab
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setWindowTitle(f"{config.PET_NAME} (pet)")

        self.scale = config.PET_SCALE
        self.size_px = 100.0 * self.scale
        self.win_w = int(max(110 * self.scale, BUBBLE_MAX_W) + 40)
        self.win_h = int(115 * self.scale + 170)
        self.setFixedSize(self.win_w, self.win_h)

        self.pet_cx = self.win_w / 2.0
        self.pet_baseline = self.win_h - 4.0

        screens = QGuiApplication.screens()
        idx = _clamp(config.SCREEN_INDEX, 0, len(screens) - 1)
        self.screen_geo = screens[idx].availableGeometry()

        self.state = PetState()
        self._font = QFont("Segoe UI", 10)

        # position (pet's centre, in screen coords)
        self.x_pos = float(self.screen_geo.center().x())
        self.y_top = float(self.screen_geo.bottom() - self.win_h + 1)
        self._apply_pos()

        # motion
        self._target_x: float | None = None
        self._on_arrive = None
        self._speed = config.WALK_SPEED

        # speech
        self._bubble_text = ""
        self._bubble_rect: QRect | None = None
        self._bubble_until = 0.0
        self._pending: tuple[str, str] | None = None
        # Unbounded on purpose. A maxlen here silently discards the oldest
        # entry, which is how reminders quietly go missing. Overflow is handled
        # by dropping *optional* chatter instead — see say().
        self._queue: deque[tuple[str, str, bool, bool]] = deque()
        self._busy = False        # walking to deliver, or bubble still up

        # timers / idle tracking
        self._t = 0.0
        self._blinking: float | None = None
        self._blink_at = time.monotonic() + random.uniform(2.0, 5.0)
        self._last_active = time.monotonic()
        self._next_wander = time.monotonic() + config.IDLE_WANDER_SEC

        # dragging / clicking
        self._drag_off: QPoint | None = None
        self._dragged = False
        self._click_timer = QTimer(self)
        self._click_timer.setSingleShot(True)
        self._click_timer.timeout.connect(self._poke_reply)

        bus.say.connect(lambda t, m: self.say(t, m, walk=True))
        bus.say_here.connect(lambda t, m: self.say(t, m, walk=False))
        bus.say_optional.connect(lambda t, m: self.say(t, m, walk=True, droppable=True))

        self._update_mask()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(FRAME_MS)

    # ---------- geometry ----------

    def _bounds(self) -> tuple[float, float]:
        half = self.win_w / 2.0
        return (self.screen_geo.left() + half * 0.35,
                self.screen_geo.right() - half * 0.35)

    def _apply_pos(self) -> None:
        self.move(int(self.x_pos - self.win_w / 2), int(self.y_top))

    # ---------- speaking ----------

    def say(self, text: str, mood: str = "happy", walk: bool = True,
            droppable: bool = False) -> None:
        """Queue something to say. If `walk`, the pet trots to your cursor first.

        Queued rather than spoken immediately: a reminder arriving while the
        pet is mid-sentence must wait its turn, not vanish.

        `droppable` marks optional chatter — quotes, idle chirps. When a backlog
        builds up (you came back from lunch to four pending nudges) that chatter
        is shed to keep the pet from monologuing. Reminders never are.
        """
        self.poke()
        if any(q[0] == text for q in self._queue):
            return                             # already waiting to say exactly this

        self._queue.append((text, mood, walk, droppable))

        while len(self._queue) > MAX_QUEUE:
            optional = next((i for i, q in enumerate(self._queue) if q[3]), None)
            if optional is None:
                break                          # all of it matters — say it all
            del self._queue[optional]

        self._pump()

    def _pump(self) -> None:
        if self._busy or not self._queue:
            return
        text, mood, walk, _ = self._queue.popleft()
        self._pending = (text, mood)
        self._busy = True

        if not walk:
            self._begin_speak()
            return

        lo, hi = self._bounds()
        target = _clamp(float(QCursor.pos().x()), lo, hi)
        # Idle wandering is a stroll; delivering a nudge is not. Scale speed to
        # distance so it always lands within DELIVER_SEC — otherwise a reminder
        # fired from the far edge of a wide screen shows up twenty seconds
        # late, which is useless for "drink water now".
        speed = max(config.WALK_SPEED * 2.5,
                    abs(target - self.x_pos) / DELIVER_SEC)
        self.walk_to(target, self._begin_speak, speed=speed)

    def _begin_speak(self) -> None:
        if self._pending is None:
            return
        text, mood = self._pending
        self._pending = None
        self.state.mood = mood
        self._bubble_text = text
        secs = max(config.BUBBLE_MIN_SEC,
                   len(text) / 10.0 * config.BUBBLE_SEC_PER_10_CHARS)
        self._bubble_until = time.monotonic() + secs
        self._relayout_bubble()
        voice.speak(text)
        self.update()

    def _relayout_bubble(self) -> None:
        if not self._bubble_text:
            self._bubble_rect = None
        else:
            fm = QFontMetrics(self._font)
            size = bubble_ui.measure(self._bubble_text, fm, BUBBLE_MAX_W)
            x = int(_clamp(self.pet_cx - size.width() / 2,
                           4, self.win_w - size.width() - 4))
            y = int(max(2, self.pet_baseline - 112 * self.scale - size.height() - 4))
            self._bubble_rect = QRect(x, y, size.width(), size.height())
        self._update_mask()

    # ---------- motion ----------

    def walk_to(self, x: float, on_arrive=None, speed: float | None = None) -> None:
        lo, hi = self._bounds()
        self._target_x = _clamp(x, lo, hi)
        self._on_arrive = on_arrive
        self._speed = speed or config.WALK_SPEED
        if abs(self._target_x - self.x_pos) < 3.0:      # already there
            self._target_x = None
            self._on_arrive = None
            if on_arrive:
                on_arrive()

    def poke(self) -> None:
        self._last_active = time.monotonic()
        if self.state.mood == "sleepy":
            self.state.mood = "happy"

    # ---------- frame ----------

    def _tick(self) -> None:
        dt = FRAME_MS / 1000.0
        now = time.monotonic()
        self._t += dt
        st = self.state

        st.breathe = (self._t * 0.22) % 1.0

        # blinking (skipped while asleep — the eyes stay shut)
        if st.mood == "sleepy":
            st.blink = 1.0
        elif self._blinking is not None:
            self._blinking += dt
            if self._blinking >= BLINK_DUR:
                self._blinking = None
                st.blink = 0.0
                self._blink_at = now + random.uniform(2.0, 6.0)
            else:
                st.blink = math.sin(self._blinking / BLINK_DUR * math.pi)
        elif now >= self._blink_at:
            self._blinking = 0.0

        # pupils follow the mouse
        eye_x = self.x() + self.pet_cx
        eye_y = self.y() + self.pet_baseline - 76 * self.scale
        cur = QCursor.pos()
        st.look = QPointF(_clamp((cur.x() - eye_x) / 260.0, -1.0, 1.0),
                          _clamp((cur.y() - eye_y) / 260.0, -1.0, 1.0))

        # walking
        if self._target_x is not None:
            diff = self._target_x - self.x_pos
            if abs(diff) < 2.0:
                self.x_pos = self._target_x
                self._target_x = None
                st.walking = False
                self._apply_pos()
                cb, self._on_arrive = self._on_arrive, None
                if cb:
                    cb()
            else:
                step = self._speed * dt
                self.x_pos += math.copysign(min(step, abs(diff)), diff)
                st.facing = 1 if diff > 0 else -1
                st.walking = True
                # Legs cycle faster when it's hurrying, or the trot looks like
                # a moonwalk.
                st.walk_phase = (st.walk_phase
                                 + dt * STEP_HZ * (self._speed / config.WALK_SPEED)
                                 ** 0.5) % 1.0
                self._apply_pos()
        else:
            st.walking = False

        # bubble expiry — frees the pet to deliver whatever queued up behind it
        if self._bubble_text and now >= self._bubble_until:
            self._bubble_text = ""
            if st.mood in ("nag", "alert", "think"):
                st.mood = "happy"
            self._relayout_bubble()
            self._busy = False
            self._pump()

        # nap after a long quiet stretch
        if (st.mood != "sleepy" and not self._bubble_text
                and now - self._last_active > config.SLEEP_AFTER_MIN * 60):
            st.mood = "sleepy"

        # idle wandering
        if (now >= self._next_wander and self._target_x is None
                and not self._bubble_text and st.mood != "sleepy"):
            lo, hi = self._bounds()
            self.walk_to(random.uniform(lo, hi))
            self._next_wander = now + config.IDLE_WANDER_SEC * random.uniform(0.6, 1.6)

        self.update()

    def paintEvent(self, _ev) -> None:
        p = QPainter(self)
        p.setFont(self._font)
        if self._bubble_rect and self._bubble_text:
            bubble_ui.draw(p, self._bubble_rect, self.pet_cx,
                           self._bubble_text, self.state.mood)
        draw_mascot(p, self.pet_cx, self.pet_baseline, self.size_px, self.state)

    def _update_mask(self) -> None:
        """Only the pet (and the bubble, when up) should catch mouse events."""
        u = self.scale
        # Sized from whatever body is actually in use — sprite art is wider and
        # taller than the vector pet, and a mask cut for the wrong one either
        # eats clicks meant for the desktop or leaves the pet unclickable.
        pw, ph = mascot_footprint(self.size_px)
        body = QRect(int(self.pet_cx - pw / 2), int(self.pet_baseline - ph),
                     int(pw), int(ph))
        region = QRegion(body, QRegion.RegionType.Ellipse)
        core = QRect(int(self.pet_cx - pw * 0.34), int(self.pet_baseline - ph * 0.62),
                     int(pw * 0.68), int(ph * 0.62))
        region = region.united(QRegion(core))
        feet = QRect(int(self.pet_cx - 32 * u), int(self.pet_baseline - 20 * u),
                     int(64 * u), int(20 * u))
        region = region.united(QRegion(feet))
        if self._bubble_rect:
            region = region.united(QRegion(self._bubble_rect))
        self.setMask(region)

    # ---------- mouse ----------

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_off = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self._dragged = False
            self.poke()
            bus.poked.emit()

    def mouseMoveEvent(self, e) -> None:
        if self._drag_off is None or not (e.buttons() & Qt.MouseButton.LeftButton):
            return
        self._dragged = True
        self._target_x = None
        self._on_arrive = None
        pt = e.globalPosition().toPoint() - self._drag_off
        self.move(pt)
        self.x_pos = pt.x() + self.win_w / 2.0
        self.y_top = float(pt.y())

    def mouseReleaseEvent(self, e) -> None:
        was_drag, self._dragged = self._dragged, False
        self._drag_off = None
        if not was_drag and not self._bubble_text:
            # Hold the chirp for one double-click interval. A double-click
            # opens the command bar, and blurting "oi." over it looks broken.
            self._click_timer.start(QApplication.doubleClickInterval())

    def _poke_reply(self) -> None:
        if not self._bubble_text:
            self.say(random.choice(POKE_LINES), "happy", walk=False, droppable=True)

    def mouseDoubleClickEvent(self, e) -> None:
        self._click_timer.stop()
        self.poke()
        bus.command.emit()
