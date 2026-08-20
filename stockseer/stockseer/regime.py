"""Market regime snapshot: recorded now, tested later.

The listing-day edge measures t = 1.02 over 38 listings -- a coin flip with a
small positive tilt. A plausible reason is that it is not one number at all but
two: a real edge in calm markets and a real anti-edge in frightened ones,
averaging to nothing.

That is testable, but **not on 38 listings.** Splitting a t = 1.02 sample in
half gives ~19 a side, and any split of that will look meaningful. So this
module only *records*. Nothing here conditions an alert or changes a position.
In a year there will be enough listings to test it properly; concluding today
would cost the strategy.

India VIX earns its place on measured grounds. Against NIFTY:

    next day      corr +0.019   t = +1.02    nothing
    next week     corr +0.057   t = +3.06    weak
    next month    corr +0.175   t = +9.46    real

So the level carries information about the month ahead, not the day. Note the
sign trap: a high VIX *level* preceded +2.18% months, while a fast *rise* in
VIX (>30% in 5 days) preceded -1.06% months. Level and change say opposite
things, and conflating them would invert the signal.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass

log = logging.getLogger(__name__)

# Verified to resolve. GIFT Nifty has no Yahoo ticker -- it needs NSE IX or a
# broker feed -- so it is deliberately absent rather than silently wrong.
TICKERS = {
    "vix": "^INDIAVIX",
    "nifty": "^NSEI",
    "banknifty": "^NSEBANK",
    "nasdaq": "^IXIC",
    "dow": "^DJI",
}

# Buckets from the measured quintiles, not round numbers.
CALM, NORMAL, STRESSED = 12.0, 16.0, 22.0


@dataclass
class Regime:
    vix: float | None = None
    vix_change_5d: float | None = None
    vix_band: str = "unknown"
    nifty_1d: float | None = None
    banknifty_1d: float | None = None
    nasdaq_overnight: float | None = None
    dow_overnight: float | None = None
    as_of: str = ""

    @property
    def summary(self) -> str:
        bits = []
        if self.vix is not None:
            bits.append(f"VIX {self.vix:.1f} ({self.vix_band})")
        if self.nasdaq_overnight is not None:
            bits.append(f"Nasdaq {self.nasdaq_overnight * 100:+.1f}%")
        if self.nifty_1d is not None:
            bits.append(f"NIFTY {self.nifty_1d * 100:+.1f}%")
        return "  ".join(bits) or "regime unavailable"


def _band(vix: float) -> str:
    if vix < CALM:
        return "calm"
    if vix < NORMAL:
        return "normal"
    if vix < STRESSED:
        return "stressed"
    return "fearful"


def snapshot() -> Regime:
    """Read the market's mood. Never raises -- a missing feed yields None."""
    from datetime import datetime

    from .data import load_prices

    def last_change(ticker: str, days: int = 1) -> tuple[float | None, float | None]:
        try:
            c = load_prices(ticker, start="2024-01-01", min_rows=30)["Close"]
            level = float(c.iloc[-1])
            chg = float(c.iloc[-1] / c.iloc[-1 - days] - 1.0) if len(c) > days else None
            return level, chg
        except Exception as exc:
            log.debug("%s unavailable (%s)", ticker, exc)
            return None, None

    vix, _ = last_change(TICKERS["vix"])
    _, vix5 = last_change(TICKERS["vix"], 5)
    _, nifty = last_change(TICKERS["nifty"])
    _, bank = last_change(TICKERS["banknifty"])
    _, ndx = last_change(TICKERS["nasdaq"])
    _, dji = last_change(TICKERS["dow"])

    return Regime(
        vix=vix, vix_change_5d=vix5,
        vix_band=_band(vix) if vix is not None else "unknown",
        nifty_1d=nifty, banknifty_1d=bank,
        nasdaq_overnight=ndx, dow_overnight=dji,
        as_of=datetime.now().astimezone().isoformat(timespec="seconds"),
    )


def as_payload() -> dict:
    """Regime fields to attach to an alert, for later analysis."""
    try:
        return asdict(snapshot())
    except Exception as exc:
        log.debug("regime snapshot failed: %s", exc)
        return {}
