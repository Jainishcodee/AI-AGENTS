"""Notes agent — appends what you said (after 'take a note ...') to notes.md."""
from datetime import datetime

import config
from .base import Agent


class NotesAgent(Agent):
    name = "Notes"
    description = "Appends a quick note to notes.md."

    def start(self, args: str = "") -> str:
        text = args.strip()
        if not text:
            return "What's the note, sir?"
        self._set_status("running")
        try:
            stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
            line = f"- [{stamp}] {text}\n"
            with open(config.NOTES_FILE, "a", encoding="utf-8") as f:
                f.write(line)
            return f"Noted, sir: {text!r}."
        except Exception as e:  # noqa: BLE001
            return f"Couldn't write the note, sir: {e}"
        finally:
            self._set_status("idle")
