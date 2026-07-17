"""Base class for all Jarvis-managed agents.

Subclasses implement `start()`; the default `stop()` is a no-op. State changes
are pushed to `on_status_change(agent, status)` so the UI can redraw.
"""
from __future__ import annotations

import threading
from abc import ABC, abstractmethod


class Agent(ABC):
    name: str = "agent"
    description: str = ""

    def __init__(self):
        self._status = "idle"
        self._lock = threading.Lock()
        # patched by JarvisUI to redraw the status dot
        self.on_status_change = lambda agent, status: None

    # --- status -----------------------------------------------------------
    @property
    def status(self) -> str:
        return self._status

    def _set_status(self, s: str) -> None:
        self._status = s
        try:
            self.on_status_change(self, s)
        except Exception:  # noqa: BLE001 - UI errors must not crash the agent
            pass

    # --- behaviour --------------------------------------------------------
    @abstractmethod
    def start(self, args: str = "") -> str:
        """Kick off the agent. Returns a string Jarvis will speak/log."""

    def stop(self) -> str:
        return f"{self.name} doesn't support stopping."

    def info(self) -> str:
        return f"{self.name}: {self.description} Currently {self.status}."
