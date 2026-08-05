"""One tiny signal bus so nudges, skills and the voice layer can talk to the
pet without importing the window (and without touching Qt widgets from a
background thread — emit a signal instead, Qt queues it onto the UI thread).
"""
from PySide6.QtCore import QObject, Signal


class EventBus(QObject):
    # text, mood — asks the pet to walk over to the user and say something.
    say = Signal(str, str)

    # text, mood — say it right where the pet is standing, no walking.
    say_here = Signal(str, str)

    # Optional chatter (quotes, idle chirps). Shed first when a backlog builds
    # up, so the pet never monologues — reminders are never shed.
    say_optional = Signal(str, str)

    # Fired when the user interacts (click/drag), so the nap timer resets.
    poked = Signal()

    # Ask the pet for something — opens the command bar.
    command = Signal()


bus = EventBus()


# Moods drive the face and the bubble tint. Keep this list short; every mood
# needs a matching branch in mascot.py.
MOODS = ("happy", "nag", "sleepy", "alert", "think")
