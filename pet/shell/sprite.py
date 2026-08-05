"""Drawing the pet from image files instead of vector paths.

Art lives in `art/` as `pet_<mood>.png` — `pet_idle.png` is the only required
one. Anything missing falls back to `idle`, and if `art/` is empty altogether
the hand-painted mascot in mascot.py is used instead, so the pet always has a
body regardless of what's on disk.

Scaled pixmaps are cached per (mood, height, facing): rescaling a 500px PNG
sixty times a second is pure waste, and the pet only uses a handful of sizes.
"""
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QTransform

import config

ART = Path(config.ROOT) / "art"
FALLBACK = "idle"


class SpriteSet:
    def __init__(self, folder: Path = ART) -> None:
        self.folder = folder
        self._originals: dict[str, QPixmap] = {}
        self._scaled: dict[tuple, QPixmap] = {}
        self._scanned = False

    def _scan(self) -> None:
        """Load once, lazily — QPixmap needs a QGuiApplication to exist first."""
        if self._scanned:
            return
        self._scanned = True
        if not self.folder.is_dir():
            return
        for f in sorted(self.folder.glob("pet_*.png")):
            pm = QPixmap(str(f))
            if not pm.isNull():
                self._originals[f.stem[len("pet_"):]] = pm

    def available(self) -> bool:
        self._scan()
        return FALLBACK in self._originals

    def moods(self) -> list[str]:
        self._scan()
        return sorted(self._originals)

    def aspect(self) -> float:
        """width / height of the base sprite, for sizing the window mask."""
        self._scan()
        pm = self._originals.get(FALLBACK)
        return (pm.width() / pm.height()) if pm and pm.height() else 1.0

    def get(self, mood: str, height: int, facing: int) -> QPixmap | None:
        self._scan()
        if height < 4:
            return None
        key = (mood, height, facing)
        hit = self._scaled.get(key)
        if hit is not None:
            return hit

        base = self._originals.get(mood) or self._originals.get(FALLBACK)
        if base is None:
            return None

        pm = base.scaledToHeight(height, Qt.TransformationMode.SmoothTransformation)
        if facing < 0:
            pm = pm.transformed(QTransform().scale(-1, 1),
                                Qt.TransformationMode.SmoothTransformation)

        # A pet that wanders all day would otherwise accumulate a pixmap for
        # every size it ever animated through.
        if len(self._scaled) > 64:
            self._scaled.clear()
        self._scaled[key] = pm
        return pm


sprites = SpriteSet()
