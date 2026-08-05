"""Desktop pet — entry point.

    python main.py

Phase 1: it lives on your screen, wanders, and nags you about water, battery
and the occasional bit of motivation. Voice control and task automation land
in later phases; see README.md.
"""
import signal
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

import config
from core import voice
from core.commander import Commander
from core.ears import Ears
from core.events import bus
from nudges.scheduler import Nudges
from shell.tray import Tray
from shell.window import PetWindow


def _on_ears_ready(ok: bool, message: str) -> None:
    print(f"[ears] {message}")
    if not ok:
        # Voice failing must never be silent — otherwise you stand there
        # talking to a pet that was never listening.
        bus.say_here.emit(message, "alert")


def _enable_ctrl_c(app) -> QTimer:
    """Make Ctrl+C in the console actually quit.

    Qt's event loop never returns to the interpreter, so Python's SIGINT
    handler would otherwise sit unrun until the next Qt event — which for an
    idle pet can be never. A timer that does nothing forces the interpreter to
    tick, and the handler fires. Keep a reference: a garbage-collected QTimer
    stops firing.
    """
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    tick = QTimer()
    tick.timeout.connect(lambda: None)
    tick.start(250)
    return tick


def main() -> int:
    app = QApplication(sys.argv)
    # The pet has no real window to close, so closing the bubble must not exit.
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName(config.PET_NAME)
    _ctrl_c = _enable_ctrl_c(app)

    voice.start()

    window = PetWindow()
    window.show()

    nudges = Nudges(window)
    nudges.start()

    commander = Commander(window)        # listens on bus.command

    ears = None
    if config.VOICE_INPUT:
        ears = Ears(window)
        ears.wake.connect(commander.on_wake)
        ears.heard.connect(commander.on_heard)
        ears.ready.connect(_on_ears_ready)
        ears.start()

    if QSystemTrayIcon.isSystemTrayAvailable():
        Tray(window, nudges, app, ears).show()
    else:
        print("(no system tray available — quit with Ctrl+C in this console)")

    print(f"{config.PET_NAME} is on screen. Drag to move, click to poke, "
          f"double-click to ask it for something, right-click the tray icon "
          f"for the menu.")
    print("To stop: tray icon -> Quit, or Ctrl+C here.")

    code = app.exec()

    # Both own daemon threads. Daemons die with the process anyway, but asking
    # them to stop first means the mic is released and any half-spoken line is
    # finished rather than cut off mid-word.
    if ears is not None:
        ears.stop()
    voice.stop()
    return code


if __name__ == "__main__":
    sys.exit(main())
