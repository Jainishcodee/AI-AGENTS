"""Jarvis — voice-driven multi-agent supervisor.

Say "Jarvis" → "Yes sir?" → give a command (start/stop/status/etc).
The CustomTkinter dashboard shows every agent live; you can also click
Start/Stop on cards. All audio (mic + TTS) is owned by a single voice thread.
"""
from __future__ import annotations

import threading

import config
from agents.mingo import MingoAgent
from agents.notes import NotesAgent
from agents.search import SearchAgent
from agents.system_info import SystemInfoAgent
from agents.weather import WeatherAgent
from nlu import Intent, parse
from orchestrator import AgentRegistry
from ui_hud import JarvisHUD as JarvisUI
from voice import Voice


class Jarvis:
    def __init__(self):
        self.registry = AgentRegistry()
        for cls in (MingoAgent, WeatherAgent, SystemInfoAgent, NotesAgent, SearchAgent):
            self.registry.register(cls())
        self.ui = JarvisUI(self)
        self.voice = Voice(
            mic_index=config.MIC_INDEX,
            energy_threshold=config.ENERGY_THRESHOLD,
            wake_word=config.WAKE_WORD,
            speak_enabled=config.SPEAK,
            command_handler=self.handle_command,
            on_log=self.ui.log,
            on_state=self.ui.set_state,
        )

    # ---- callbacks ------------------------------------------------------
    def handle_command(self, transcript: str) -> str:
        """Run on the voice thread. Returns the reply to speak."""
        if not transcript:
            return "I didn't catch that, sir."
        names = [a.name for a in self.registry.list()]
        intent = parse(transcript, names)
        return self._execute(intent)

    def execute_button(self, action: str, agent_name: str) -> None:
        """Run on the Tk thread (button click). Spawn a worker — DO NOT
        call voice methods on the Tk thread."""
        def worker():
            reply = self._execute(Intent(action, agent=agent_name))
            if reply:
                self.voice.say(reply)
        threading.Thread(target=worker, daemon=True).start()

    # ---- intent dispatcher ---------------------------------------------
    def _execute(self, intent: Intent) -> str:
        if intent.action == "list":
            agents = self.registry.list()
            names = ", ".join(a.name for a in agents)
            return f"You have {len(agents)} agents, sir: {names}."

        if intent.action == "help":
            return ("Tell me to start or stop an agent, ask their status, "
                    "ask for the weather, system info, take a note, or do a web search.")

        if intent.action == "quit":
            self.ui.log("Shutting down...")
            self.voice.shutdown()
            self.ui.root.after(800, self.ui.root.destroy)
            return "Goodbye, sir."

        if intent.action == "start":
            if not intent.agent or intent.agent == "*":
                return "Which agent should I start, sir?"
            a = self.registry.find(intent.agent)
            if not a:
                return f"I don't have an agent called {intent.agent}, sir."
            try:
                return a.start(intent.args)
            except Exception as e:  # noqa: BLE001
                return f"{a.name} crashed on start: {e}"

        if intent.action == "stop":
            if intent.agent == "*":
                running = [a for a in self.registry.list() if a.status == "running"]
                if not running:
                    return "Nothing is running, sir."
                return " ".join(a.stop() for a in running)
            a = self.registry.find(intent.agent)
            if not a:
                return "Which agent should I stop, sir?"
            return a.stop()

        if intent.action == "status":
            if intent.agent:
                a = self.registry.find(intent.agent)
                return a.info() if a else f"No agent called {intent.agent}, sir."
            parts = [f"{a.name} is {a.status}" for a in self.registry.list()]
            return ". ".join(parts) + "."

        if intent.action == "info":
            if intent.agent:
                a = self.registry.find(intent.agent)
                return a.info() if a else f"No agent called {intent.agent}, sir."
            return "Which agent, sir?"

        return "Sorry sir, I didn't understand."

    # ---- bootstrap ------------------------------------------------------
    def run(self):
        self.ui.log("=" * 50)
        self.ui.log("  Jarvis — multi-agent supervisor")
        self.ui.log("=" * 50)
        self.voice.start()
        try:
            self.ui.run()
        finally:
            self.voice.shutdown()


if __name__ == "__main__":
    Jarvis().run()
