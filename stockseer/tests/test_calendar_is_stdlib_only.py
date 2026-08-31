"""The IPO calendar must import and run on a bare Python.

The daily alert job deliberately skips ``pip install``: the whole scan is
standard library, and skipping the install keeps the run to about thirty
seconds on a free runner.

Nothing enforced that, so it broke silently. A commit taught the message
builder to quote the measured base rate and imported ``load_base_rate`` from
``study``, which pulls in numpy and pandas at module level to do the actual
research. The function itself needs neither -- only ``json`` and ``date`` --
but the import dragged the whole scientific stack behind it and the job died
with ``ModuleNotFoundError: No module named 'numpy'``.

The failure was hard to read, because the traceback appeared *after* the scan
had printed the IPO it found. The log looked healthy right up to the crash, and
several days of alerts were lost to what looked like an intermittent network
fault.

This test makes the constraint executable: block the scientific stack outright
and drive the alert path end to end. If someone adds a heavy import to it
again, this fails on their machine rather than at 07:37 on a deadline morning.
"""
from __future__ import annotations

import sys

import pytest

# Everything the alert path must survive without. yfinance and sklearn are here
# because they are the other easy accidents -- both sit one import away in
# sibling modules.
BLOCKED = {"numpy", "pandas", "sklearn", "scipy", "yfinance", "matplotlib",
           "joblib", "smartapi", "SmartApi"}


class _Blocker:
    """Import hook that refuses the scientific stack."""

    def find_module(self, name, path=None):
        return self if name.split(".")[0] in BLOCKED else None

    def load_module(self, name):
        raise ImportError(f"No module named {name!r} (blocked by this test)")


@pytest.fixture
def bare_python():
    """Run the body as though nothing had been pip-installed."""
    saved = {k: v for k, v in sys.modules.items()
             if k.split(".")[0] in BLOCKED or k.startswith("stockseer")}
    for name in list(sys.modules):
        if name.split(".")[0] in BLOCKED or name.startswith("stockseer"):
            del sys.modules[name]
    blocker = _Blocker()
    sys.meta_path.insert(0, blocker)
    try:
        yield
    finally:
        sys.meta_path.remove(blocker)
        for name in list(sys.modules):
            if name.split(".")[0] in BLOCKED or name.startswith("stockseer"):
                del sys.modules[name]
        sys.modules.update(saved)


def test_the_blocker_actually_blocks(bare_python):
    """Guard the guard: a no-op hook would make every test below vacuous."""
    with pytest.raises(ImportError):
        import numpy  # noqa: F401


def test_base_rate_loads_without_numpy(bare_python):
    from stockseer.ipo.base_rate import load_base_rate

    rate = load_base_rate()
    assert 0.0 < rate["median"] < 1.0
    assert rate["n"] > 0


def test_push_and_config_import_without_numpy(bare_python):
    """The transport is the last thing that may fail on a bare runner."""
    from stockseer import push  # noqa: F401
    from stockseer.config import setting  # noqa: F401


def test_calendar_builds_a_message_without_numpy(bare_python):
    """The end-to-end case that actually broke."""
    from stockseer.ipo.calendar import CalendarEvent, _message
    from stockseer.ipo.registry import IPO, Subscription

    ipo = IPO(symbol="LUMINO", company="Lumino Industries Limited",
              issue_price=82.0, listing_date=None, price_range="Rs.78 to Rs.82")
    ipo.ipo_end = "2026-08-31"
    ev = CalendarEvent(
        ipo, "closes_today", "critical",
        Subscription(symbol="LUMINO", retail_x=29.8, qib_x=55.0, nii_x=143.7),
        None)

    title, body = _message(ev)
    assert "LUMINO" in title
    # The odds are the number the reader decides on, so their absence means the
    # message degraded even though it rendered.
    assert "1 in" in body
    assert "5 PM" in body


def test_cli_calendar_entrypoint_imports_without_numpy(bare_python):
    """`python -m stockseer.cli ipo calendar` must reach its handler.

    The CLI defers pandas and sklearn behind each subcommand precisely so this
    holds; a stray module-level import would undo it.
    """
    from stockseer.cli import cmd_ipo  # noqa: F401
