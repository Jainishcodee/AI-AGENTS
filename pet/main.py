"""Desktop pet — entry point.

    python main.py

Phase 1: it lives on your screen, wanders, and nags you about water, battery
and the occasional bit of motivation. Voice control and task automation land
in later phases; see README.md.
"""
import sys

from PySide6.QtWidgets import QApplication, QSystemTrayIcon

import config
from core import voice
from core.commander import Commander
from nudges.scheduler import Nudges
from shell.tray import Tray
from shell.window import PetWindow


def main() -> int:
    app = QApplication(sys.argv)
    # The pet has no real window to close, so closing the bubble must not exit.
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName(config.PET_NAME)

    voice.start()

    window = PetWindow()
    window.show()

    nudges = Nudges(window)
    nudges.start()

    commander = Commander(window)        # listens on bus.command

    if QSystemTrayIcon.isSystemTrayAvailable():
        Tray(window, nudges, app).show()
    else:
        print("(no system tray available — quit with Ctrl+C in this console)")

    print(f"{config.PET_NAME} is on screen. Drag to move, click to poke, "
          f"double-click to ask it for something, right-click the tray icon "
          f"for the menu.")
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
