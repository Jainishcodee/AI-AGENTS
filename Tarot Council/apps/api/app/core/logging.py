"""Logging setup. Deliberately minimal; structured fields go through `extra`."""

from __future__ import annotations

import logging
import sys

_CONFIGURED = False


def setup_logging(level: str = "INFO") -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-7s %(name)-28s %(message)s", "%H:%M:%S")
    )
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    # httpx logs every request at INFO; that is one line per stage and drowns
    # the events we actually care about.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
