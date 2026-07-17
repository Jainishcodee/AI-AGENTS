"""Central configuration for Mingo. Values come from a local .env file
(see .env.example). Nothing here is uploaded anywhere."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


def _int_or_none(name: str):
    v = os.getenv(name, "").strip()
    return int(v) if v.lstrip("-").isdigit() else None


# --- SPARE Microsoft account (optional; blank = sign in manually once) ---
MS_EMAIL = os.getenv("MS_EMAIL", "").strip()
MS_PASSWORD = os.getenv("MS_PASSWORD", "").strip()

# --- Browser ---
EDGE_PROFILE_DIR = str(ROOT / "edge_profile")
HEADLESS = _bool("HEADLESS", False)
DESKTOP_SEARCHES = int(os.getenv("DESKTOP_SEARCHES", "32"))
MOBILE_SEARCHES = int(os.getenv("MOBILE_SEARCHES", "22"))

# --- Voice ---
WAKE_WORD = os.getenv("WAKE_WORD", "mingo").strip().lower()
SPEAK = _bool("SPEAK", True)
MIC_INDEX = _int_or_none("MIC_INDEX")            # run `python mic_test.py` to find this
ENERGY_THRESHOLD = _int_or_none("ENERGY_THRESHOLD")  # set if calibration picks a bad value

# --- Email reminder for the MAIN account ---
SMTP_EMAIL = os.getenv("SMTP_EMAIL", "").strip()
SMTP_APP_PASSWORD = os.getenv("SMTP_APP_PASSWORD", "").strip()
REMINDER_TO = os.getenv("REMINDER_TO", SMTP_EMAIL).strip()
REMINDER_INTERVAL_HOURS = float(os.getenv("REMINDER_INTERVAL_HOURS", "3"))
SEND_REMINDER_ON_START = _bool("SEND_REMINDER_ON_START", False)
