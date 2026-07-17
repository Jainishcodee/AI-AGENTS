"""Central config for Jarvis. Values come from a local .env file (see .env.example)."""
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


# --- Voice ---
WAKE_WORD = os.getenv("WAKE_WORD", "jarvis").strip().lower()
SPEAK = _bool("SPEAK", True)
MIC_INDEX = _int_or_none("MIC_INDEX")
ENERGY_THRESHOLD = _int_or_none("ENERGY_THRESHOLD")

# --- Mingo integration ---
_mingo_env = os.getenv("MINGO_DIR", "").strip()
MINGO_DIR = Path(_mingo_env).resolve() if _mingo_env else (ROOT.parent / "Mingo").resolve()

# --- Weather (OpenWeatherMap) ---
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "").strip()
WEATHER_LOCATION = os.getenv("WEATHER_LOCATION", "Mumbai").strip()

# --- Notes ---
NOTES_FILE = ROOT / "notes.md"

# --- Logs ---
LOGS_DIR = ROOT / "logs"
LOGS_DIR.mkdir(exist_ok=True)
