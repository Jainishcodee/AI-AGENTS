"""The pet itself, drawn with QPainter — no sprite sheets, no Rive, no Lottie.

Same choice as the Jarvis phone mascot (lib/widgets/mascot.dart): hand-painted
vector means the creature scales to any DPI, needs zero assets, and its mood is
a parameter rather than a folder of PNGs. Keep it that way unless the character
genuinely outgrows it.

Everything is drawn inside a normalised 100x100 box and scaled by `size`, so
tweaking proportions here never breaks the window layout.
"""
import math
from dataclasses import dataclass, field

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QBrush, QColor, QFont, QPainter, QPainterPath, QPen,
                           QRadialGradient)

# --- palette (openclaw red, matching Jarvis) ---
BODY = QColor("#D97757")
BODY_DARK = QColor("#B0512F")
BELLY = QColor("#F2A98D")
INK = QColor("#3A241B")
EYE_WHITE = QColor("#FFF8F4")
SHADOW = QColor(0, 0, 0, 46)

# The antenna bulb is the pet's mood light — it's the fastest read at a glance.
MOOD_GLOW = {
    "happy": QColor("#FFCF8F"),
    "nag": QColor("#7FD1E8"),      # water-blue when it's pestering you
    "sleepy": QColor("#9B8FB5"),
    "alert": QColor("#FF9E6B"),
    "think": QColor("#C9B6F0"),
}


@dataclass
class PetState:
    """Everything the painter needs to know. The window mutates this each frame."""
    mood: str = "happy"
    blink: float = 0.0          # 0 = open, 1 = shut
    walk_phase: float = 0.0     # cycles 0..1 while walking
    walking: bool = False
    facing: int = 1             # +1 right, -1 left
    look: QPointF = field(default_factory=lambda: QPointF(0.0, 0.0))  # pupils, -1..1
    breathe: float = 0.0        # 0..1, drives the idle squash


def _glow_for(mood: str) -> QColor:
    return MOOD_GLOW.get(mood, MOOD_GLOW["happy"])


def draw(p: QPainter, cx: float, baseline: float, size: float, st: PetState) -> None:
    """Draw the pet standing on `baseline`, horizontally centred on `cx`."""
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    u = size / 100.0                      # one normalised unit in device pixels
    bounce = abs(math.sin(st.walk_phase * math.tau)) if st.walking else 0.0
    hop = bounce * 3.0 * u
    squash = 1.0 + 0.025 * math.sin(st.breathe * math.tau)

    # Shadow tightens as the pet leaves the ground — this is what sells the hop.
    shadow_w = 52 * u * (1.0 - 0.18 * bounce)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(SHADOW))
    p.drawEllipse(QRectF(cx - shadow_w / 2, baseline - 5 * u, shadow_w, 9 * u))

    body_h = 62 * u * squash
    body_w = 66 * u / squash
    body_top = baseline - hop - 12 * u - body_h
    body = QRectF(cx - body_w / 2, body_top, body_w, body_h)

    _feet(p, cx, baseline - hop, u, st)
    _antennae(p, cx, body_top, u, st)
    _body(p, body, u)
    _face(p, body, u, st)


def _body(p: QPainter, body: QRectF, u: float) -> None:
    g = QRadialGradient(body.center().x(), body.top() + body.height() * 0.28,
                        body.width() * 0.95)
    g.setColorAt(0.0, BODY.lighter(114))
    g.setColorAt(1.0, BODY_DARK)
    p.setBrush(QBrush(g))
    p.setPen(QPen(BODY_DARK.darker(118), 2.2 * u))
    p.drawRoundedRect(body, body.width() * 0.5, body.height() * 0.46)

    belly = QRectF(body.center().x() - body.width() * 0.26,
                   body.center().y() + body.height() * 0.02,
                   body.width() * 0.52, body.height() * 0.40)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(BELLY))
    p.drawRoundedRect(belly, belly.width() * 0.5, belly.height() * 0.5)


def _feet(p: QPainter, cx: float, baseline: float, u: float, st: PetState) -> None:
    swing = math.sin(st.walk_phase * math.tau) * 5.0 * u if st.walking else 0.0
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(BODY_DARK))
    for side, offset in ((-1, swing), (1, -swing)):
        fx = cx + side * 14 * u + offset * 0.7
        fy = baseline - 12 * u - max(0.0, offset) * 0.45
        p.drawEllipse(QRectF(fx - 9 * u, fy, 18 * u, 12 * u))


def _antennae(p: QPainter, cx: float, body_top: float, u: float, st: PetState) -> None:
    glow = _glow_for(st.mood)
    sway = (math.sin(st.walk_phase * math.tau) * 3.0 * u if st.walking
            else math.sin(st.breathe * math.tau) * 1.5 * u)
    for side in (-1, 1):
        base = QPointF(cx + side * 14 * u, body_top + 8 * u)
        tip = QPointF(cx + side * 25 * u + sway, body_top - 20 * u)
        path = QPainterPath(base)
        path.quadTo(QPointF(cx + side * 27 * u, body_top - 6 * u), tip)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(BODY_DARK, 3.2 * u, Qt.PenStyle.SolidLine,
                      Qt.PenCapStyle.RoundCap))
        p.drawPath(path)

        halo = QRadialGradient(tip, 8 * u)
        halo.setColorAt(0.0, QColor(glow.red(), glow.green(), glow.blue(), 210))
        halo.setColorAt(1.0, QColor(glow.red(), glow.green(), glow.blue(), 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(halo))
        p.drawEllipse(tip, 8 * u, 8 * u)
        p.setBrush(QBrush(glow))
        p.drawEllipse(tip, 3.2 * u, 3.2 * u)


def _face(p: QPainter, body: QRectF, u: float, st: PetState) -> None:
    eye_y = body.top() + body.height() * 0.40
    dx = body.width() * 0.21
    for side in (-1, 1):
        _eye(p, QPointF(body.center().x() + side * dx, eye_y), u, st)

    if st.mood == "nag":
        _brows(p, body, eye_y, dx, u)

    _mouth(p, QPointF(body.center().x() + st.facing * 1.5 * u, eye_y + 16 * u), u, st)

    if st.mood == "sleepy":
        _zzz(p, body, u)


def _eye(p: QPainter, c: QPointF, u: float, st: PetState) -> None:
    rw, rh = 9.5 * u, 11.0 * u
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(EYE_WHITE))
    p.drawEllipse(c, rw, rh)

    px = c.x() + st.look.x() * 3.2 * u
    py = c.y() + st.look.y() * 3.6 * u
    p.setBrush(QBrush(INK))
    p.drawEllipse(QPointF(px, py), 4.6 * u, 5.2 * u)
    p.setBrush(QBrush(QColor(255, 255, 255, 225)))
    p.drawEllipse(QPointF(px - 1.7 * u, py - 2.1 * u), 1.6 * u, 1.6 * u)

    # Eyelid drops from the top. Clipped to the eye so it never smears the body.
    if st.blink > 0.01:
        p.save()
        clip = QPainterPath()
        clip.addEllipse(c, rw + 0.6 * u, rh + 0.6 * u)
        p.setClipPath(clip)
        p.setBrush(QBrush(BODY.lighter(108)))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRect(QRectF(c.x() - rw - 2 * u, c.y() - rh - 2 * u,
                          2 * rw + 4 * u, (2 * rh + 4 * u) * st.blink))
        p.restore()

        # Lash crease. Without it a shut eye is just a blank patch of body and
        # the sleeping pet looks faceless rather than asleep.
        if st.blink > 0.45:
            t = (st.blink - 0.45) / 0.55
            y = c.y() - rh + rh * st.blink
            depth = 3.4 * u * t
            crease = QPainterPath(QPointF(c.x() - rw * 0.9, y - depth * 0.5))
            crease.quadTo(c.x(), y + depth, c.x() + rw * 0.9, y - depth * 0.5)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(INK, 2.2 * u, Qt.PenStyle.SolidLine,
                          Qt.PenCapStyle.RoundCap))
            p.drawPath(crease)


def _brows(p: QPainter, body: QRectF, eye_y: float, dx: float, u: float) -> None:
    """Inner ends angled down — the universal 'I'm not asking again' face."""
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(INK, 2.6 * u, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    y = eye_y - 15 * u
    for side in (-1, 1):
        x = body.center().x() + side * dx
        p.drawLine(QPointF(x + side * 6 * u, y), QPointF(x - side * 6 * u, y + 4.5 * u))


def _mouth(p: QPainter, c: QPointF, u: float, st: PetState) -> None:
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(INK, 2.4 * u, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))

    if st.mood == "alert":
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(INK))
        p.drawEllipse(c, 4.5 * u, 5.5 * u)
    elif st.mood == "nag":
        path = QPainterPath(QPointF(c.x() - 6 * u, c.y() + 1.5 * u))
        path.quadTo(c.x(), c.y() - 3 * u, c.x() + 6 * u, c.y() + 1.5 * u)
        p.drawPath(path)
    elif st.mood == "think":
        path = QPainterPath(QPointF(c.x() - 6 * u, c.y()))
        path.cubicTo(c.x() - 2 * u, c.y() - 3.5 * u,
                     c.x() + 2 * u, c.y() + 3.5 * u,
                     c.x() + 6 * u, c.y())
        p.drawPath(path)
    elif st.mood == "sleepy":
        p.drawLine(QPointF(c.x() - 3.5 * u, c.y()), QPointF(c.x() + 3.5 * u, c.y()))
    else:
        path = QPainterPath(QPointF(c.x() - 7 * u, c.y() - 2 * u))
        path.quadTo(c.x(), c.y() + 6.5 * u, c.x() + 7 * u, c.y() - 2 * u)
        p.drawPath(path)


def _zzz(p: QPainter, body: QRectF, u: float) -> None:
    """Floating z's. Drawn twice — dark then light — because the pet sits on
    whatever wallpaper you happen to have, and a single-colour z disappears
    against half of them.
    """
    p.save()                      # the font must not leak back to the caller
    p.setBrush(Qt.BrushStyle.NoBrush)
    for size, ox, oy, alpha in ((7, 24, -4, 235), (10, 33, -17, 180), (13, 44, -33, 120)):
        f = QFont("Segoe UI", max(6, int(size * u * 1.3)))
        f.setBold(True)
        p.setFont(f)
        at = QPointF(body.center().x() + ox * u, body.top() + oy * u)
        p.setPen(QPen(QColor(40, 24, 18, alpha)))
        p.drawText(QPointF(at.x() + 1.4 * u, at.y() + 1.4 * u), "z")
        p.setPen(QPen(QColor(255, 244, 236, alpha)))
        p.drawText(at, "z")
    p.restore()
