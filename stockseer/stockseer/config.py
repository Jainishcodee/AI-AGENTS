"""Settings loading, with no dependencies at all.

Deliberately importable on a bare Python. The .env reader used to live in
``live/angel.py``, which imports pandas -- so on a GitHub runner that skips
``pip install`` (the calendar job, to stay fast) the fallback silently failed
and any setting not passed as a real environment variable vanished.

Keep this module free of third-party imports.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

log = logging.getLogger(__name__)

_LOADED = False


def _candidates() -> tuple[Path, ...]:
    here = Path(__file__).resolve()
    return (
        here.parent.parent / ".env",   # repo root:   stockseer/.env
        here.parent / ".env",          # package dir: stockseer/stockseer/.env
        Path.cwd() / ".env",
    )


def load_dotenv(force: bool = False) -> bool:
    """Read the first .env found into the environment. Never overwrites.

    Real environment variables always win -- that is what lets GitHub Actions
    inject secrets over whatever a checked-out .env might contain.
    """
    global _LOADED
    if _LOADED and not force:
        return True

    for path in _candidates():
        if not path.exists():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            log.debug("could not read %s: %s", path, exc)
            continue

        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip().strip("\"'"))
        log.debug("loaded settings from %s", path)
        _LOADED = True
        return True
    return False


def setting(name: str, default: str = "") -> str:
    """Environment first, then .env, then the default."""
    val = os.environ.get(name, "").strip()
    if val:
        return val
    load_dotenv()
    return os.environ.get(name, "").strip() or default
