"""Rule-based command parser. Converts a transcribed phrase into an Intent."""
import re
from dataclasses import dataclass


@dataclass
class Intent:
    action: str          # start | stop | status | list | info | help | quit | unknown
    agent: str = ""
    args: str = ""


_START_VERBS = ("start", "run", "launch", "open", "fire", "begin", "kick off", "do")
_STOP_VERBS = ("stop", "kill", "cancel", "halt", "end", "shutdown")
_STATUS_WORDS = ("status", "doing", "running")
_LIST_PATTERNS = ("list agents", "what agents", "which agents", "show agents",
                  "what are our agents", "what are the agents", "list of agents",
                  "agents do you have", "agents we have")
_INFO_WORDS = ("what does", "tell me about", "info about", "info on")
_FILLERS = ("please", "could you", "would you", "can you", "hey", "jarvis", "sir")


def _clean(text: str) -> str:
    t = text.strip().lower()
    for f in _FILLERS:
        t = t.replace(f, " ")
    return re.sub(r"\s+", " ", t).strip()


def parse(text: str, agent_names) -> Intent:
    t = _clean(text)
    if not t:
        return Intent("unknown")

    if t in ("quit", "exit", "bye", "goodbye", "shut down jarvis", "shutdown jarvis"):
        return Intent("quit")
    if t in ("help", "what can you do"):
        return Intent("help")

    if any(p in t for p in _LIST_PATTERNS) and "stop" not in t and "start" not in t:
        return Intent("list")

    # locate a known agent name in the text
    target = ""
    for name in agent_names:
        if re.search(r"\b" + re.escape(name.lower()) + r"\b", t):
            target = name
            break

    has_start = any(re.search(r"\b" + v + r"\b", t) for v in _START_VERBS)
    has_stop = any(re.search(r"\b" + v + r"\b", t) for v in _STOP_VERBS)
    has_status = any(w in t for w in _STATUS_WORDS) and not has_start

    if has_stop:
        if "all" in t or "everything" in t:
            return Intent("stop", agent="*")
        return Intent("stop", agent=target)

    if has_status:
        return Intent("status", agent=target)

    if any(w in t for w in _INFO_WORDS):
        return Intent("info", agent=target)

    # --- agent-specific shortcuts ----------------------------------------
    m = re.match(r"(?:take a |make a |new )?notes?[: ]+(.+)", t)
    if m:
        return Intent("start", agent="Notes", args=m.group(1).strip())
    m = re.match(r"note that (.+)", t)
    if m:
        return Intent("start", agent="Notes", args=m.group(1).strip())

    m = re.match(r"(?:search(?: for)?|google|look up|find) (.+)", t)
    if m and not target:
        return Intent("start", agent="Search", args=m.group(1).strip())

    if "weather" in t and not target:
        m = re.search(r"(?:in|for|at) ([\w ]+)$", t)
        return Intent("start", agent="Weather", args=(m.group(1).strip() if m else ""))

    # generic start
    if target:
        args = t
        for v in _START_VERBS:
            args = re.sub(r"\b" + v + r"\b", "", args)
        args = re.sub(r"\b" + re.escape(target.lower()) + r"\b", "", args)
        return Intent("start", agent=target, args=args.strip(" ,.-"))

    return Intent("unknown")
