"""The recipe book — everything the pet has been taught.

This is the memory behind the never-guess rule. The pet doesn't improvise on
tasks it hasn't seen; it asks you once, records what you picked, and from then
on the answer is a dictionary lookup. No model, no scoring, no drift.

Stored as plain JSON so you can open it, read it, and delete a bad entry with
a text editor.
"""
import json
import threading
from pathlib import Path

import config

BOOK = config.ROOT / "recipes.json"
_lock = threading.Lock()


def _norm(q: str) -> str:
    return " ".join(q.lower().split())


class RecipeBook:
    def __init__(self, path: Path = BOOK) -> None:
        self.path = path
        self._data = {"apps": {}}
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            return
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                self._data.update(loaded)
        except (json.JSONDecodeError, OSError) as e:
            # A corrupt book must not stop the pet from starting; it just means
            # it has forgotten things and will ask again.
            print(f"(couldn't read {self.path.name}: {e} — starting fresh)")

    def save(self) -> None:
        with _lock:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._data, indent=2), encoding="utf-8")
            tmp.replace(self.path)          # atomic, so a crash can't truncate it

    # --- apps ---

    def app_for(self, query: str) -> str | None:
        """The exact target you taught for this phrase, or None."""
        return self._data["apps"].get(_norm(query))

    def learn_app(self, query: str, target: str) -> None:
        self._data["apps"][_norm(query)] = target
        self.save()

    def forget_app(self, query: str) -> None:
        if self._data["apps"].pop(_norm(query), None) is not None:
            self.save()

    def known_apps(self) -> dict[str, str]:
        return dict(self._data["apps"])


book = RecipeBook()
