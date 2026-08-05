"""Everything the pet says on a schedule.

Offline lists on purpose — a water reminder should never depend on an API key,
a rate limit, or your wifi. Phase 2 lets the brain write fresh lines when it's
available, but these stay as the fallback.
"""
import random

WATER = [
    "water. now. I'll wait.",
    "hydration check — go fill the bottle.",
    "you haven't had water in a while, boss.",
    "drink something. that headache later is optional.",
    "sip break. 30 seconds, that's all I'm asking.",
    "your brain is 73% water and you're running it dry.",
    "bottle. mouth. repeat. go.",
    "I'll stop nagging when the glass is empty.",
]

LOW_BATTERY = [
    "battery's at {pct}% — plug me in before I nap.",
    "{pct}% left. charger. please.",
    "we're running on fumes here, {pct}%.",
    "power's low ({pct}%). save your work, then find the cable.",
]

FULL_BATTERY = [
    "{pct}% — you can unplug now, it's happy.",
    "fully fed at {pct}%. pull the cable, save the cells.",
    "charged to {pct}%. unplug and let it breathe.",
]

GREETING = [
    "back online. what are we building?",
    "hey boss. I'm around if you need me.",
    "awake and watching your battery.",
]

# Short on purpose — a quote you have to squint at is a quote you skip.
QUOTES = [
    "Done beats perfect. Ship it.",
    "You don't need more time, you need fewer tabs.",
    "The work you're avoiding takes 20 minutes.",
    "Consistency outruns intensity. Every time.",
    "Start ugly. Fix it while it's moving.",
    "Nobody remembers the draft. They remember the thing.",
    "Small steps still point the same direction.",
    "Discipline is choosing what you want most over what you want now.",
    "You can't edit a blank page.",
    "The obstacle is usually the next step in disguise.",
    "Progress hides in boring repetitions.",
    "You've survived 100% of your worst days so far.",
    "Motivation follows action. Not the other way round.",
    "One hard thing, done today, beats ten planned.",
    "Rest is part of the work, not a break from it.",
    "Compare to yesterday-you. Nobody else.",
    "If it's worth doing, it's worth doing badly at first.",
    "The gap between knowing and doing is where everything happens.",
    "Focus is saying no to good things.",
    "You're closer than it feels from inside it.",
]


def water() -> str:
    return random.choice(WATER)


def low_battery(pct: int) -> str:
    return random.choice(LOW_BATTERY).format(pct=pct)


def full_battery(pct: int) -> str:
    return random.choice(FULL_BATTERY).format(pct=pct)


def greeting() -> str:
    return random.choice(GREETING)


def quote() -> str:
    return random.choice(QUOTES)
