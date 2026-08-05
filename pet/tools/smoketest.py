"""Run the real pet for a few seconds, then quit.

    python tools/smoketest.py

Drives the actual event loop — animation frames, the window mask, bubble
layout, the walk-to-deliver path, the nudge timers — so a paint error or a
dropped reminder shows up here instead of the first time you leave the pet
running for an hour.
"""
import os
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["SPEAK"] = "false"                  # don't talk over the test
os.environ["IDLE_WANDER_SEC"] = "1"            # force wandering to happen
os.environ["BUBBLE_MIN_SEC"] = "0.6"           # don't wait out real read times
os.environ["BUBBLE_SEC_PER_10_CHARS"] = "0.05"

from PySide6.QtCore import QTimer                       # noqa: E402
from PySide6.QtWidgets import QApplication              # noqa: E402

import config                                            # noqa: E402
from core import voice                                   # noqa: E402
from core.commander import Commander                     # noqa: E402
from core.events import bus                              # noqa: E402
from nudges.scheduler import Nudges                      # noqa: E402
from shell.tray import mascot_icon                       # noqa: E402
from shell.window import PetWindow                       # noqa: E402

RUN_MS = 18000
errors: list[str] = []
spoken: list[str] = []


def _hook(exc_type, exc, tb):
    errors.append("".join(traceback.format_exception(exc_type, exc, tb)))


def main() -> int:
    sys.excepthook = _hook
    voice.speak = lambda text: spoken.append(text)      # capture, don't vocalise

    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)

    win = PetWindow()
    win.show()
    nudges = Nudges(win)
    nudges.start()

    assert not mascot_icon().isNull(), "tray icon rendered empty"

    frames = []
    win._timer.timeout.connect(lambda: frames.append(1))

    long_line = ("a much longer line, to make sure the bubble wraps onto several "
                 "lines and the mask still lets you click it.")

    # Fired in a burst, deliberately faster than the pet can deliver them —
    # this is what used to silently drop reminders.
    QTimer.singleShot(300, lambda: bus.say.emit("walking over to nag you.", "nag"))
    QTimer.singleShot(600, lambda: bus.say.emit(long_line, "think"))
    QTimer.singleShot(900, lambda: bus.say.emit("third one, queued.", "alert"))
    QTimer.singleShot(1000, lambda: bus.say.emit("fourth reminder.", "nag"))
    QTimer.singleShot(1100, lambda: bus.say.emit("fifth reminder.", "nag"))
    # Optional chatter fired into the middle of the backlog. These are the ones
    # allowed to disappear; the reminders above are not.
    QTimer.singleShot(1050, lambda: bus.say_optional.emit("optional chatter one.", "think"))
    QTimer.singleShot(1150, lambda: bus.say_optional.emit("optional chatter two.", "think"))
    QTimer.singleShot(1200, nudges.battery_now)
    # Routing only — a phrase the pet can't act on. Never triggers a launch.
    commander = Commander(win)
    QTimer.singleShot(1500, lambda: commander.handle("what's the weather"))
    QTimer.singleShot(RUN_MS - 1500, lambda: setattr(win.state, "mood", "sleepy"))
    QTimer.singleShot(RUN_MS, app.quit)
    app.exec()

    fps = len(frames) / (RUN_MS / 1000)
    print(f"pet name       : {config.PET_NAME}")
    print(f"window         : {win.win_w}x{win.win_h} at ({win.x()}, {win.y()})")
    print(f"screen         : {win.screen_geo.width()}x{win.screen_geo.height()}")
    print(f"battery nudges : {'on' if nudges._has_battery else 'off (no battery)'}")
    print(f"frames         : {len(frames)}  (~{fps:.0f} fps)")
    print(f"mask empty?    : {win.mask().isEmpty()}")
    print(f"delivered      : {len(spoken)}")
    for s in spoken:
        print(f"   - {s[:60]}")

    ok = True
    if errors:
        print("\nFAILED — exceptions during run:\n" + "\n".join(errors))
        ok = False
    if fps < 30:
        print(f"\nFAILED — animation ran at {fps:.0f} fps, expected ~60")
        ok = False

    # Every queued line must actually arrive; that's the whole point of a
    # reminder. The greeting is emitted by the scheduler, so 5 total.
    for want in ("walking over to nag you.", long_line, "third one, queued.",
                 "fourth reminder.", "fifth reminder."):
        if want not in spoken:
            print(f"\nFAILED — reminder was dropped: {want[:50]!r}")
            ok = False
    if not any("%" in s for s in spoken):
        print("\nFAILED — battery status never delivered")
        ok = False

    print("\nOK" if ok else "")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
