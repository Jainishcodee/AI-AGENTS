"""Does a request take the right path? Launches nothing, opens no dialogs.

    python tools/test_routing.py

Three things must hold:
  1. Plain phrasing never wakes the model (it's ~4s and can invent things).
  2. A statement that isn't a request must NOT become a task.
  3. Anything the model concluded must ask before acting.
"""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["SPEAK"] = "false"
os.environ["VOICE_INPUT"] = "false"

from PySide6.QtCore import QTimer                       # noqa: E402
from PySide6.QtWidgets import QApplication              # noqa: E402

from core import brain, commander as cmd_mod, voice     # noqa: E402
from core.commander import Commander                    # noqa: E402
from shell.window import PetWindow                      # noqa: E402
from skills import apps                                 # noqa: E402

said: list[str] = []
launched: list[str] = []
confirms: list[str] = []
brain_calls: list[str] = []
fails: list[str] = []

_real_parse = brain.parse_sync


def _spy_parse(text):
    brain_calls.append(text)
    return _real_parse(text)


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{'  — ' + detail if detail else ''}")
    if not ok:
        fails.append(label)


def run(app, c, text: str, seconds: float = 25.0) -> None:
    """Feed one request and pump the event loop until it settles."""
    said.clear(); launched.clear(); confirms.clear(); brain_calls.clear()
    c.handle(text)
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        app.processEvents()
        # A model round-trip is done once it has spoken something conclusive.
        if launched or confirms or any(
                s for s in said if s not in ("thinking…",)):
            break
        time.sleep(0.02)
    for _ in range(40):                      # let the follow-up bubble land
        app.processEvents()
        time.sleep(0.01)


def main() -> int:
    voice.speak = lambda t: said.append(t)
    brain.parse_sync = _spy_parse
    apps.AppEntry.launch = lambda self: launched.append(self.name)

    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    win = PetWindow()
    c = Commander(win)

    if not brain.available():
        print("Ollama isn't running — start it, then re-run this test.")
        return 1

    # Auto-answer the confirmation so nothing blocks; record that it was asked.
    class FakeConfirm:
        answer = True

        @staticmethod
        def ask(heard, proposal, anchor, parent=None):
            confirms.append(proposal)
            return FakeConfirm.answer

    cmd_mod.Confirm = FakeConfirm

    print("1. plain phrasing must skip the model entirely")
    run(app, c, "open brave")
    check("brave launched", bool(launched), str(launched))
    check("model NOT consulted", not brain_calls, f"calls={brain_calls}")
    check("no confirmation needed", not confirms)

    print("\n2. a statement is not a task")
    run(app, c, "i'm so tired today")
    check("model was consulted", bool(brain_calls))
    check("nothing launched", not launched, str(launched))
    check("no task invented", not confirms, str(confirms))
    check("said so plainly", any("can do yet" in s for s in said), str(said))

    print("\n3. model-derived action must ask first")
    run(app, c, "i could really use notepad right now")
    check("model was consulted", bool(brain_calls))
    if confirms:
        check("asked before acting", True, confirms[0])
        check("then launched", bool(launched), str(launched))
    else:
        # Acceptable outcome: the model didn't read it as a request at all.
        check("asked before acting", not launched,
              "model read it as chat, nothing launched — also fine")

    print("\n4. declining a model action does nothing")
    FakeConfirm.answer = False
    run(app, c, "i could really use notepad right now")
    check("nothing launched after 'No'", not launched, str(launched))

    print("\nOK" if not fails else f"\n{len(fails)} FAILED: {fails}")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
