"""Market data feeds behind one interface.

Two implementations ship: Yahoo (free, no setup, ~15 minutes delayed on NSE) and
Angel One SmartAPI (free, real-time, needs credentials). The rest of the system
talks to :class:`Feed` and never learns which one it got -- so rules developed
against delayed data run unchanged on live ticks.

A feed reports its own latency rather than pretending. A monitor that thinks
15-minute-old prices are live will place stops that were already breached.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

import pandas as pd

log = logging.getLogger(__name__)

IST = "Asia/Kolkata"
OHLCV = ["Open", "High", "Low", "Close", "Volume"]


@dataclass(frozen=True)
class Quote:
    symbol: str
    price: float
    at: datetime
    change_pct: float | None = None
    volume: float | None = None
    delayed_seconds: int = 0

    @property
    def is_live(self) -> bool:
        return self.delayed_seconds <= 60


@dataclass(frozen=True)
class Bar:
    symbol: str
    at: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


class Feed(ABC):
    """A source of historical bars and current quotes."""

    name: str = "feed"
    delayed_seconds: int = 0

    @abstractmethod
    def history(self, symbol: str, interval: str = "5m", days: int = 30) -> pd.DataFrame:
        """Intraday OHLCV indexed by IST timestamp."""

    @abstractmethod
    def quote(self, symbol: str) -> Quote:
        """Most recent price available from this feed."""

    def quotes(self, symbols: list[str]) -> dict[str, Quote]:
        out = {}
        for s in symbols:
            try:
                out[s] = self.quote(s)
            except Exception as exc:
                log.warning("%s: quote failed for %s (%s)", self.name, s, exc)
        return out

    def describe(self) -> str:
        if self.delayed_seconds <= 60:
            return f"{self.name} (real-time)"
        return f"{self.name} (~{self.delayed_seconds // 60} min delayed)"


# --------------------------------------------------------------------------- #
# Yahoo -- works with zero setup, but delayed
# --------------------------------------------------------------------------- #
class YahooFeed(Feed):
    name = "yahoo"
    delayed_seconds = 15 * 60

    # Yahoo's intraday retention, which is not negotiable.
    MAX_DAYS = {"1m": 7, "2m": 60, "5m": 60, "15m": 60, "30m": 60, "60m": 730}

    def history(self, symbol: str, interval: str = "5m", days: int = 30) -> pd.DataFrame:
        import yfinance as yf

        cap = self.MAX_DAYS.get(interval, 60)
        if days > cap:
            log.warning("yahoo keeps only %d days of %s bars; asked for %d",
                        cap, interval, days)
            days = cap

        raw = yf.download(symbol, period=f"{days}d", interval=interval,
                          progress=False, auto_adjust=False)
        if raw is None or len(raw) == 0:
            raise ValueError(f"no intraday data for {symbol!r} at {interval}")
        return _normalise(raw)

    def quote(self, symbol: str) -> Quote:
        bars = self.history(symbol, interval="5m", days=2)
        last = bars.iloc[-1]
        prev_close = bars["Close"].iloc[-2] if len(bars) > 1 else last["Close"]
        at = bars.index[-1].to_pydatetime()
        return Quote(
            symbol=symbol,
            price=float(last["Close"]),
            at=at,
            change_pct=float(last["Close"] / prev_close - 1.0) if prev_close else None,
            volume=float(last["Volume"]),
            delayed_seconds=self.delayed_seconds,
        )


def _normalise(raw: pd.DataFrame) -> pd.DataFrame:
    df = raw.copy()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df.columns = [str(c) for c in df.columns]
    missing = [c for c in OHLCV if c not in df.columns]
    if missing:
        raise ValueError(f"feed returned no {missing}")
    df = df[OHLCV].astype("float64")

    idx = pd.to_datetime(df.index)
    idx = idx.tz_localize(IST) if idx.tz is None else idx.tz_convert(IST)
    df.index = idx
    df.index.name = "at"

    df = df[~df.index.duplicated(keep="last")].sort_index()
    return df[df["Close"].notna() & (df["Close"] > 0)]


def get_feed(prefer: str = "auto") -> Feed:
    """Return the best available feed.

    ``auto`` uses Angel One when credentials are present and falls back to Yahoo
    otherwise -- loudly, so a delayed feed is never mistaken for a live one.
    """
    if prefer in ("auto", "angel"):
        try:
            from .angel import AngelFeed

            feed = AngelFeed.from_env()
            log.info("using %s", feed.describe())
            return feed
        except Exception as exc:
            if prefer == "angel":
                raise
            log.warning("Angel One unavailable (%s); falling back to delayed Yahoo data", exc)
    return YahooFeed()
