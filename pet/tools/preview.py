"""Render the mascot in every mood to a PNG, without launching the pet.

    python tools/preview.py [out.png]

Useful for tweaking mascot.py — a paint bug is much easier to see in a
contact sheet than by restarting the app and waiting for the right mood.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
# Deliberately NOT forcing the offscreen platform: it ships without a font
# database, so every string renders as tofu boxes and you can't check the
# bubble. The native platform paints into a QPixmap without ever showing
# a window, which is what we want.
if os.environ.get("PET_PREVIEW_OFFSCREEN"):
    os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtCore import QPointF, QRect, Qt                    # noqa: E402
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication                        # noqa: E402

from shell import bubble as bubble_ui                             # noqa: E402
from shell.mascot import MOOD_GLOW, PetState                      # noqa: E402
from shell.mascot import draw as draw_mascot                      # noqa: E402

CELL_W, CELL_H = 200, 210
SIZE = 110.0

SAMPLES = [
    ("happy", "idle", dict(mood="happy")),
    ("happy", "walking", dict(mood="happy", walking=True, walk_phase=0.25)),
    ("happy", "mid-blink", dict(mood="happy", blink=0.65)),
    ("nag", "water", dict(mood="nag", look=QPointF(-0.8, 0.3))),
    ("alert", "battery", dict(mood="alert", look=QPointF(0.7, -0.4))),
    ("think", "quote", dict(mood="think")),
    ("sleepy", "napping", dict(mood="sleepy", blink=1.0)),
    ("happy", "looking up", dict(mood="happy", look=QPointF(0.0, -1.0))),
]


def main() -> int:
    app = QApplication([])
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "preview.png")

    cols = 4
    rows = (len(SAMPLES) + cols - 1) // cols
    pm = QPixmap(cols * CELL_W, rows * CELL_H + 120)
    pm.fill(QColor("#2A2320"))

    p = QPainter(pm)
    p.setFont(QFont("Segoe UI", 9))

    for i, (mood, label, kw) in enumerate(SAMPLES):
        cx = (i % cols) * CELL_W + CELL_W / 2
        cy = (i // cols) * CELL_H + CELL_H - 26
        draw_mascot(p, cx, cy, SIZE, PetState(**kw))
        p.setPen(QColor("#B9A99F"))
        p.drawText(QRect(int(cx - CELL_W / 2), int(cy + 4), CELL_W, 20),
                   int(Qt.AlignmentFlag.AlignHCenter), f"{mood} / {label}")

    # A speech bubble, at the width the pet actually uses.
    p.setFont(QFont("Segoe UI", 10))
    text = "water. now. I'll wait."
    size = bubble_ui.measure(text, QFontMetrics(p.font()), 300)
    rect = QRect(30, rows * CELL_H + 30, size.width(), size.height())
    bubble_ui.draw(p, rect, rect.x() + 60, text, "nag")

    text2 = "battery's at 22% — plug me in before I nap."
    size2 = bubble_ui.measure(text2, QFontMetrics(p.font()), 300)
    rect2 = QRect(rect.right() + 40, rows * CELL_H + 30, size2.width(), size2.height())
    bubble_ui.draw(p, rect2, rect2.center().x(), text2, "alert")

    p.end()
    pm.save(str(out))
    print(f"wrote {out.resolve()}  ({pm.width()}x{pm.height()})")
    print("moods:", ", ".join(MOOD_GLOW))
    del app
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
