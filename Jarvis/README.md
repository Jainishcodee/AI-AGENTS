# Jarvis

A voice-driven multi-agent supervisor in CustomTkinter. Say **"Jarvis"** → it
asks *"Yes sir?"* → you give a command → it dispatches to one of its agents and
speaks the result. A dashboard window shows every agent live.

## Agents shipped

| Agent  | What it does |
|--------|--------------|
| **Mingo** | Runs the Microsoft Rewards searches on your spare account (spawns `..\Mingo\rewards_bot.py`). |
| **Weather** | Reports the current weather for a place (open-meteo, no API key). |
| **System** | Reads CPU, memory, disk and uptime via psutil. |
| **Notes** | Appends a timestamped note to `notes.md`. |
| **Search** | Opens a DuckDuckGo search in your default browser. |

## Commands

Voice (after the wake word) or just say it without the wake word — anything Jarvis hears after "Jarvis" goes through the same parser:

| Say | What happens |
|---|---|
| "what agents do you have" / "list agents" | speaks the registry |
| "start Mingo" | launches the rewards run |
| "stop Mingo" / "stop everything" | terminates |
| "status" / "what's Mingo doing" | reports state |
| "what's the weather in Tokyo" | weather for Tokyo |
| "system info" / "what's the system status" | CPU/mem/disk/uptime |
| "take a note buy milk" | appends to notes.md |
| "search for python decorators" | opens DuckDuckGo |
| "goodbye" / "quit" | closes Jarvis |

Buttons on each card do the same thing without voice.

## Setup

```powershell
cd "g:\AI AGENTS\Jarvis"
pip install -r requirements.txt
copy .env.example .env
# open .env and set MIC_INDEX to the index that worked in ../Mingo/mic_test.py
python jarvis.py
```

## Layout

```
Jarvis/
├── jarvis.py          # entry: wires registry + UI + voice thread
├── voice.py           # wake-word listen + one-shot listen + tts
├── nlu.py             # rule-based intent parser
├── orchestrator.py    # AgentRegistry
├── ui_ctk.py          # CustomTkinter dashboard
├── agents/
│   ├── base.py        # Agent ABC
│   ├── mingo.py       # subprocess wrapper
│   ├── weather.py     # open-meteo
│   ├── system_info.py # psutil
│   ├── notes.py       # notes.md append
│   └── search.py      # DuckDuckGo via webbrowser
├── config.py
└── logs/              # mingo.log lives here
```

## Adding a new agent

1. Create `agents/<name>.py`:
   ```python
   from .base import Agent

   class MyAgent(Agent):
       name = "Coffee"
       description = "Brews a virtual coffee."

       def start(self, args=""):
           self._set_status("running")
           try:
               return "Brewing, sir."
           finally:
               self._set_status("idle")
   ```
2. Register it in `jarvis.py` — add `MyAgent` to the registry loop.

That's it — it appears as a card, voice routing works automatically.

## Notes / gotchas

- Tkinter wants the main thread. The voice loop runs in a background thread and
  pushes UI changes via `root.after(0, ...)`. Don't touch widgets from the voice
  thread directly.
- Mingo runs as a subprocess so its Playwright/Chromium runtime is independent
  of Jarvis. Killing Jarvis won't auto-kill a Mingo run already in flight; use
  "stop Mingo" or close Mingo's Chromium window.
- Wake-word matching is fuzzy — "service", "jervis", etc. all count.
