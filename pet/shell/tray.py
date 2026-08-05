"""System-tray icon and menu.

The pet has no window chrome and never appears in the taskbar, so this is the
only way to quit it or summon it deliberately. The tray icon is the mascot
itself, rendered at runtime — one less asset to keep in sync.
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

import config
from core.events import bus
from shell.mascot import PetState
from shell.mascot import draw as draw_mascot


def mascot_icon(px: int = 64) -> QIcon:
    pm = QPixmap(px, px)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    draw_mascot(p, px / 2, px - 2, px * 0.92, PetState(mood="happy"))
    p.end()
    return QIcon(pm)


class Tray(QSystemTrayIcon):
    def __init__(self, window, nudges, app, ears=None) -> None:
        super().__init__(mascot_icon(), app)
        self._window = window
        self._ears = ears
        self.setToolTip(config.PET_NAME)

        menu = QMenu()
        self._add(menu, "Ask for something…", bus.command.emit)
        self._add(menu, "Come here", self._come)
        self._add(menu, "Water reminder", nudges.water_now)
        self._add(menu, "Motivate me", nudges.quote_now)
        self._add(menu, "Battery status", nudges.battery_now)
        menu.addSeparator()

        if self._ears is not None:
            self._ears_action = QAction(f'Listen for "{config.WAKE_WORD}"', menu)
            self._ears_action.setCheckable(True)
            self._ears_action.setChecked(True)
            self._ears_action.toggled.connect(self._toggle_ears)
            menu.addAction(self._ears_action)

        self._voice_action = QAction("Voice (speak out loud)", menu)
        self._voice_action.setCheckable(True)
        self._voice_action.setChecked(config.SPEAK)
        self._voice_action.toggled.connect(self._toggle_voice)
        menu.addAction(self._voice_action)

        menu.addSeparator()
        self._add(menu, f"Quit {config.PET_NAME}", app.quit)
        self.setContextMenu(menu)

        self.activated.connect(self._on_activate)

    @staticmethod
    def _add(menu: QMenu, label: str, fn) -> None:
        act = QAction(label, menu)
        act.triggered.connect(fn)
        menu.addAction(act)

    def _come(self) -> None:
        bus.say.emit("here. what do you need?", "happy")

    def _toggle_voice(self, on: bool) -> None:
        config.SPEAK = on
        bus.say_here.emit("out loud again." if on else "going quiet.", "happy")

    def _toggle_ears(self, on: bool) -> None:
        # Mute rather than stop: tearing down the model means a slow reload,
        # and you usually want the mic back within a minute.
        self._ears.set_muted(not on)
        bus.say_here.emit("ears on." if on else "not listening.", "happy")

    def _on_activate(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._window.poke()
            self._window.raise_()
