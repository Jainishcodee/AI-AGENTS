"""Settings for the desktop pet. Everything comes from a local .env file
(copy .env.example). Nothing is uploaded anywhere.

Kept deliberately flat and boring — this file is the one place to look when
the pet is nagging too often or standing in the wrong place.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


def _int(name: str, default: int) -> int:
    v = os.getenv(name, "").strip()
    return int(v) if v.lstrip("-").isdigit() else default


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, "").strip())
    except ValueError:
        return default


# --- Identity ---
# Same character as the Jarvis phone app, so the PC pet and the phone mascot
# read as one creature rather than two mascots.
PET_NAME = os.getenv("PET_NAME", "Jarvis").strip() or "Jarvis"
PET_SCALE = _float("PET_SCALE", 1.0)          # 0.7 = small, 1.4 = chunky

# --- Voice ---
SPEAK = _bool("SPEAK", True)                   # pyttsx3, offline Windows SAPI5
TTS_RATE = _int("TTS_RATE", 178)

# --- Where it lives ---
# Which monitor edge the pet walks along. 0 = primary screen.
SCREEN_INDEX = _int("SCREEN_INDEX", 0)
WALK_SPEED = _float("WALK_SPEED", 70.0)        # pixels per second
IDLE_WANDER_SEC = _float("IDLE_WANDER_SEC", 25.0)   # how often it strolls somewhere new
SLEEP_AFTER_MIN = _float("SLEEP_AFTER_MIN", 8.0)    # naps if you don't touch it

# --- Browser (used from Phase 3 for recorded web tasks) ---
# Brave, Chrome and Edge are all Chromium, so Playwright drives any of them via
# executable_path — no bundled browser download needed. Brave first, because
# that's what actually gets used here.
_BROWSERS = [
    r"%PROGRAMFILES%\BraveSoftware\Brave-Browser\Application\brave.exe",
    r"%PROGRAMFILES(X86)%\BraveSoftware\Brave-Browser\Application\brave.exe",
    r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\brave.exe",
    r"%PROGRAMFILES%\Google\Chrome\Application\chrome.exe",
    r"%PROGRAMFILES(X86)%\Microsoft\Edge\Application\msedge.exe",
]


def _find_browser() -> str:
    for raw in _BROWSERS:
        p = Path(os.path.expandvars(raw))
        if p.is_file():
            return str(p)
    return ""


BROWSER_PATH = os.getenv("BROWSER_PATH", "").strip() or _find_browser()

# Recorded web tasks run in their own profile dir, so the pet never has to
# borrow (or lock) the browser window you're actually using. You sign in once.
BROWSER_PROFILE = str(ROOT / "browser_profile")

# --- Nudges ---
WATER_INTERVAL_MIN = _float("WATER_INTERVAL_MIN", 45.0)
QUOTE_INTERVAL_MIN = _float("QUOTE_INTERVAL_MIN", 120.0)
BATTERY_LOW_PCT = _int("BATTERY_LOW_PCT", 25)   # nags you to plug in below this
BATTERY_FULL_PCT = _int("BATTERY_FULL_PCT", 85)  # nags you to unplug above this
BATTERY_POLL_SEC = _float("BATTERY_POLL_SEC", 60.0)

# Don't nag between these hours (24h clock). Set both to 0 to disable.
QUIET_START_HOUR = _int("QUIET_START_HOUR", 1)
QUIET_END_HOUR = _int("QUIET_END_HOUR", 8)

# How long a speech bubble stays up, per 10 characters of text (seconds).
BUBBLE_SEC_PER_10_CHARS = _float("BUBBLE_SEC_PER_10_CHARS", 0.55)
BUBBLE_MIN_SEC = _float("BUBBLE_MIN_SEC", 3.5)


def in_quiet_hours(hour: int) -> bool:
    """True if `hour` falls inside the do-not-disturb window.

    Handles the usual wrap-around case (quiet from 01:00 to 08:00) as well as
    a same-day window, and treats start == end as 'never quiet'.
    """
    start, end = QUIET_START_HOUR, QUIET_END_HOUR
    if start == end:
        return False
    if start < end:
        return start <= hour < end
    return hour >= start or hour < end
