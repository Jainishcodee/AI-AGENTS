"""Mingo as a Jarvis-managed agent.

Spawns ../Mingo/rewards_bot.py as a separate Python subprocess so Mingo's
runtime stays isolated from Jarvis's. A background thread watches the process
and flips status back to 'idle' when it exits.
"""
import subprocess
import sys
import threading
from pathlib import Path

import config
from .base import Agent


class MingoAgent(Agent):
    name = "Mingo"
    description = "Runs Microsoft Rewards searches on your spare account."

    def __init__(self):
        super().__init__()
        self.proc: subprocess.Popen | None = None
        self.log_path: Path = config.LOGS_DIR / "mingo.log"

    def start(self, args: str = "") -> str:
        with self._lock:
            if self.proc and self.proc.poll() is None:
                return "Mingo is already running, sir."
            script = config.MINGO_DIR / "rewards_bot.py"
            if not script.exists():
                return f"I can't find Mingo at {script}, sir."
            log_fp = open(self.log_path, "ab")
            try:
                self.proc = subprocess.Popen(
                    [sys.executable, "-u", str(script)],
                    cwd=str(config.MINGO_DIR),
                    stdout=log_fp,
                    stderr=subprocess.STDOUT,
                )
            except Exception as e:  # noqa: BLE001
                log_fp.close()
                return f"Couldn't launch Mingo: {e}"
            self._set_status("running")
            threading.Thread(target=self._watch, args=(log_fp,), daemon=True).start()
            return "Starting Mingo, sir. Running the Microsoft Rewards on the spare account."

    def _watch(self, log_fp) -> None:
        try:
            self.proc.wait()
        finally:
            try:
                log_fp.close()
            except Exception:  # noqa: BLE001
                pass
            self._set_status("idle")

    def stop(self) -> str:
        with self._lock:
            if self.proc and self.proc.poll() is None:
                self.proc.terminate()
                self._set_status("stopping")
                return "Stopping Mingo, sir."
        return "Mingo isn't running, sir."

    def info(self) -> str:
        loc = f" (logs at {self.log_path})" if self.status == "running" else ""
        return f"Mingo: {self.description} Currently {self.status}{loc}."
