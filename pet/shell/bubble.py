"""The speech bubble the pet talks through.

Dark bubble, light text — that reads on any wallpaper, which a light bubble
does not. The tail points down at the pet so it's obvious who's talking.
"""
from PySide6.QtCore import QPointF, QRect, QRectF, QSize, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen, QFontMetrics

BG = QColor(30, 23, 20, 240)
FG = QColor("#FBF3EE")

# A thin accent stripe down the left edge, tinted by mood — matches the
# antenna bulb so the two always agree about how the pet feels.
ACCENT = {
    "happy": QColor("#FFCF8F"),
    "nag": QColor("#7FD1E8"),
    "sleepy": QColor("#9B8FB5"),
    "alert": QColor("#FF9E6B"),
    "think": QColor("#C9B6F0"),
}

PAD_X, PAD_Y = 14, 10
TAIL_H = 9
RADIUS = 12


def measure(text: str, fm: QFontMetrics, max_w: int) -> QSize:
    """Size of the whole bubble including padding and tail."""
    inner_w = max(60, max_w - 2 * PAD_X)
    r = fm.boundingRect(QRect(0, 0, inner_w, 10000),
                        Qt.TextFlag.TextWordWrap, text)
    return QSize(min(max_w, r.width() + 2 * PAD_X),
                 r.height() + 2 * PAD_Y + TAIL_H)


def draw(p: QPainter, rect: QRect, tail_x: float, text: str, mood: str) -> None:
    """Draw the bubble into `rect`, with the tail tip at `tail_x` along the bottom."""
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    body = QRectF(rect.x(), rect.y(), rect.width(), rect.height() - TAIL_H)

    path = QPainterPath()
    path.addRoundedRect(body, RADIUS, RADIUS)

    # Tail, clamped so it always stays on the bubble even when the pet is
    # near a screen edge and the bubble has been shoved sideways.
    tx = max(body.left() + RADIUS + 8, min(body.right() - RADIUS - 8, tail_x))
    tail = QPainterPath(QPointF(tx - 8, body.bottom() - 1))
    tail.lineTo(QPointF(tx, body.bottom() + TAIL_H))
    tail.lineTo(QPointF(tx + 8, body.bottom() - 1))
    tail.closeSubpath()
    path = path.united(tail)

    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(BG))
    p.drawPath(path)

    accent = ACCENT.get(mood, ACCENT["happy"])
    p.save()
    p.setClipPath(path)
    p.setBrush(QBrush(accent))
    p.drawRect(QRectF(body.left(), body.top(), 3.5, body.height()))
    p.restore()

    p.setPen(QPen(FG))
    p.drawText(QRect(rect.x() + PAD_X, rect.y() + PAD_Y,
                     rect.width() - 2 * PAD_X, rect.height() - 2 * PAD_Y - TAIL_H),
               int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
               | int(Qt.TextFlag.TextWordWrap),
               text)
