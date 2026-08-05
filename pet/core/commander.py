"""Turns what you typed into something the pet does.

No model involved. Phase 2 puts a local LLM *in front* of this to handle
free-form speech, but the routing itself stays plain code — an instruction the
pet can't parse must fail loudly, not get guessed at.
"""
import os
from pathlib import Path

from PySide6.QtCore import QObject, QPoint

from core.events import bus
from shell.ask import CommandBar, Picker
from skills import apps

OPEN_VERBS = ("open", "launch", "start", "run", "fire up", "boot up", "boot")
FILLER_PREFIX = ("the", "my", "up")
FILLER_SUFFIX = ("for me", "please", "now", "app", "application")


def parse_open(text: str) -> str | None:
    """'launch up my brave please' -> 'brave'. None if it isn't an open request."""
    t = " ".join(text.lower().split())
    for verb in sorted(OPEN_VERBS, key=len, reverse=True):
        if t == verb:
            return ""                      # "open" with no target
        if t.startswith(verb + " "):
            t = t[len(verb) + 1:]
            break
    else:
        return None

    changed = True
    while changed:
        changed = False
        for w in FILLER_PREFIX:
            if t.startswith(w + " "):
                t, changed = t[len(w) + 1:], True
        for w in FILLER_SUFFIX:
            if t.endswith(" " + w):
                t, changed = t[:-(len(w) + 1)], True
    return t.strip()


class Commander(QObject):
    def __init__(self, window) -> None:
        super().__init__(window)
        self._window = window
        bus.command.connect(self.prompt)

    def _anchor(self) -> QPoint:
        w = self._window
        return QPoint(int(w.x() + w.width() / 2), int(w.y() + w.height() * 0.35))

    def prompt(self) -> None:
        text = CommandBar.ask(self._anchor(), self._window)
        if text:
            self.handle(text)

    def handle(self, text: str) -> None:
        target = parse_open(text)
        if target is None:
            bus.say_here.emit(
                "I only know how to open apps so far — try \"open brave\".", "think")
            return
        if not target:
            bus.say_here.emit("open what?", "think")
            return
        self.open_app(target)

    # --- the app-opening skill ---

    def open_app(self, query: str) -> None:
        match = apps.find(query)

        if match.confident is not None:
            self._launch(match.confident, learned=match.taught)
            return

        # Never guess. Ask, and remember the answer.
        bus.say_here.emit(f"I don't know \"{query}\" yet — show me which one.", "think")
        options = [(a.name, a.target) for a in match.candidates]
        chosen = Picker.choose(f"Which one is \"{query}\"?", options,
                               self._anchor(), self._window)
        if chosen is None:
            bus.say_here.emit("okay, skipped.", "happy")
            return

        target, remember = chosen
        entry = apps.AppEntry(Path(target).stem if target.endswith((".lnk", ".url"))
                              else target, target)
        if remember:
            apps.remember(query, entry)
        self._launch(entry, learned=remember, taught_now=remember)

    def _launch(self, entry: apps.AppEntry, learned: bool,
                taught_now: bool = False) -> None:
        try:
            entry.launch()
        except OSError as e:
            # A stale recipe (app uninstalled/moved) must not stick around
            # silently failing forever.
            bus.say_here.emit(f"couldn't open {entry.name} — {e.strerror or e}.", "alert")
            return

        if taught_now:
            bus.say_here.emit(f"got it — {entry.name}. I'll remember.", "happy")
        elif learned:
            bus.say_here.emit(f"opening {entry.name}.", "happy")
        else:
            bus.say_here.emit(f"opening {entry.name}.", "happy")
