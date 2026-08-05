"""The local model — a fallback, not the main path.

Plain string parsing handles "open brave" instantly and cannot invent anything.
This runs only when that fails, because the model is both slow (~4s) and
willing to make things up: asked about "i'm so tired today" it happily returned
a reminder nobody requested. So its output is a *suggestion* that still has to
clear the recipe gate and (by default) a confirmation click.

Runs on a worker thread — a 4-second blocking HTTP call on the Qt thread would
freeze the pet mid-step.
"""
import json
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

import config

SYSTEM = """You convert a user's request into JSON for a desktop assistant.
Reply with ONLY a JSON object, no prose, no markdown fence.

Schema: {"action": "<open_app|question|chat|unknown>", "target": "<string>"}

- open_app : they want a program launched. target = the program name only.
- question : they asked something factual. target = the question.
- chat     : small talk or a statement, not a request. target = "".
- unknown  : you cannot tell. target = "".

Rules:
- Never invent a program name that was not mentioned.
- A statement about how they feel is "chat", never a task.
- If they did not ask for something to happen, it is not a task."""

# Actions the pet knows how to carry out. Anything else the model dreams up is
# discarded rather than attempted.
ACTIONABLE = {"open_app"}


@dataclass
class Intent:
    action: str
    target: str
    from_model: bool = True      # always true here; kept for the caller's clarity

    @property
    def actionable(self) -> bool:
        return self.action in ACTIONABLE and bool(self.target.strip())


def _ping(timeout: float = 2.0) -> bool:
    try:
        urllib.request.urlopen(f"{config.OLLAMA_HOST}/api/tags", timeout=timeout)
        return True
    except (urllib.error.URLError, OSError):
        return False


def _exe() -> str | None:
    for raw in (r"%LOCALAPPDATA%\Programs\Ollama\ollama.exe",
                r"%PROGRAMFILES%\Ollama\ollama.exe"):
        p = Path(os.path.expandvars(raw))
        if p.is_file():
            return str(p)
    return shutil.which("ollama")


def available() -> bool:
    """Can we use the brain at all? Fast — never blocks the UI thread.

    True if the server is already up *or* we know how to start it. The actual
    start happens lazily on the worker thread, so the pet doesn't need Ollama
    running in the background all day just in case.
    """
    if not config.BRAIN_ENABLED:
        return False
    return _ping(0.4) or _exe() is not None


def ensure_running(timeout: float = 25.0) -> bool:
    """Start the Ollama server if it isn't up. Blocking — worker thread only."""
    if _ping():
        return True
    exe = _exe()
    if exe is None:
        return False
    try:
        # DETACHED so the server outlives this pet process, CREATE_NO_WINDOW so
        # it doesn't flash a console over whatever you're doing.
        subprocess.Popen([exe, "serve"],
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
                         | getattr(subprocess, "DETACHED_PROCESS", 0),
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError as e:
        print(f"(couldn't start ollama: {e})")
        return False

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _ping(1.0):
            print("[brain] started ollama on demand")
            return True
        time.sleep(0.5)
    return False


def parse_sync(text: str) -> Intent | None:
    """Blocking. Call from a worker thread, never the UI thread."""
    body = json.dumps({
        "model": config.OLLAMA_MODEL,
        "messages": [{"role": "system", "content": SYSTEM},
                     {"role": "user", "content": text}],
        "stream": False,
        "format": "json",                 # Ollama constrains the output shape
        "options": {"temperature": 0, "num_ctx": 2048},
    }).encode()
    req = urllib.request.Request(f"{config.OLLAMA_HOST}/api/chat", data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=config.OLLAMA_TIMEOUT) as r:
            payload = json.loads(r.read())
        got = json.loads(payload["message"]["content"])
    except (urllib.error.URLError, OSError, json.JSONDecodeError, KeyError) as e:
        print(f"(brain unavailable: {e})")
        return None

    action = str(got.get("action", "unknown")).strip().lower()
    target = str(got.get("target", "")).strip()
    return Intent(action, target)


class _Job(QRunnable):
    def __init__(self, brain: "Brain", text: str) -> None:
        super().__init__()
        self._brain = brain
        self._text = text

    def run(self) -> None:
        """Always answer, even on failure.

        Without this guard an exception escapes into Qt, which prints a warning
        and drops it — and the commander, still waiting on `parsed`, leaves you
        staring at a pet that never replied. A failed parse must come back as
        "I couldn't work that out", never as silence.
        """
        try:
            intent = parse_sync(self._text) if ensure_running() else None
        except Exception as e:  # noqa: BLE001 - a dead model must not kill the pet
            print(f"[brain] {type(e).__name__}: {e}")
            intent = None

        try:
            self._brain.parsed.emit(self._text, intent)
        except RuntimeError:
            pass        # pet shut down while this was in flight; nobody's listening


class Brain(QObject):
    # original text, Intent or None
    parsed = Signal(str, object)

    def parse_async(self, text: str) -> None:
        QThreadPool.globalInstance().start(_Job(self, text))
