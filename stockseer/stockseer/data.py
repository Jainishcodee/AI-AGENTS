"""Price data loading, with an on-disk CSV cache so repeat runs stay offline."""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).resolve().parent.parent / "cache"
OHLCV = ["Open", "High", "Low", "Close", "Volume"]


def _cache_path(ticker: str, start: str, end: str, interval: str, cache_dir: Path) -> Path:
    safe = ticker.replace("^", "idx-").replace("/", "-").replace("=", "-")
    return Path(cache_dir) / f"{safe}__{start}__{end}__{interval}.csv"


def _flatten(raw: pd.DataFrame) -> pd.DataFrame:
    """yfinance returns MultiIndex columns for a single ticker in recent versions."""
    df = raw.copy()
    if isinstance(df.columns, pd.MultiIndex):
        # Level 0 holds the field name (Close/High/...), level 1 the ticker.
        df.columns = df.columns.get_level_values(0)
    df.columns = [str(c) for c in df.columns]
    return df


def _clean(df: pd.DataFrame, ticker: str) -> pd.DataFrame:
    missing = [c for c in OHLCV if c not in df.columns]
    if missing:
        raise ValueError(f"{ticker}: downloaded frame is missing columns {missing}")
    out = df[OHLCV].copy()
    out.index = pd.to_datetime(out.index).tz_localize(None)
    out.index.name = "Date"
    out = out[~out.index.duplicated(keep="last")].sort_index()
    out = out.astype("float64")
    # A zero/NaN close is a bad print, not a real observation.
    out = out[out["Close"].notna() & (out["Close"] > 0)]
    return out



def _repair_splits(df: pd.DataFrame, drop: float = -0.35, jump: float = 0.60,
                   ticker: str = "") -> pd.DataFrame:
    """Undo split jumps the data provider failed to adjust.

    NSE applies circuit limits of at most 20% a day, so a single-day move of
    -90% is not a crash -- it is an unadjusted split or bonus. Yahoo misses
    these on several ETFs (GOLDBEES 2019-12-19, MON100 2021-06-17), and left
    alone they poison every derived number: drawdown, volatility, the
    momentum screen, and the "biggest fall" line the risk check prints.

    Each artifact is repaired by rescaling all earlier bars onto the post-split
    level, which is what an adjusted series should have looked like.
    """
    out = df.copy()
    for _ in range(6):                      # a series can hold several splits
        ret = out["Close"].pct_change()
        hits = ret[(ret <= drop) | (ret >= jump)]
        if hits.empty:
            break
        when = hits.index[0]
        factor = float(1.0 + hits.iloc[0])
        if not (0 < factor < 10):
            break
        cols = ["Open", "High", "Low", "Close"]
        out.loc[out.index < when, cols] *= factor
        out.loc[out.index < when, "Volume"] /= factor
        log.info("%s: repaired an unadjusted split of %.3fx on %s",
                 ticker or "series", factor, when.date())
    return out


def load_prices(
    ticker: str,
    start: str = "2012-01-01",
    end: str | None = None,
    interval: str = "1d",
    cache_dir: Path | str = CACHE_DIR,
    refresh: bool = False,
    min_rows: int = 260,
) -> pd.DataFrame:
    """Return an adjusted OHLCV frame indexed by date.

    Prices are split/dividend adjusted (``auto_adjust=True``), which is what you
    want for return modelling: a 1:10 split must not look like a -90% day.
    """
    end = end or date.today().isoformat()
    path = _cache_path(ticker, start, end, interval, Path(cache_dir))

    if path.exists() and not refresh:
        log.info("cache hit %s", path.name)
        df = pd.read_csv(path, index_col=0, parse_dates=True)
    else:
        import yfinance as yf

        log.info("downloading %s %s..%s (%s)", ticker, start, end, interval)
        raw = yf.download(
            ticker,
            start=start,
            end=end,
            interval=interval,
            auto_adjust=True,
            progress=False,
            actions=False,
        )
        if raw is None or len(raw) == 0:
            raise ValueError(
                f"No data returned for {ticker!r}. Check the symbol "
                f"(NSE needs a .NS suffix, e.g. RELIANCE.NS; BSE uses .BO)."
            )
        df = _flatten(raw)
        path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(path)

    out = _repair_splits(_clean(df, ticker), ticker=ticker)
    # Modelling needs a year of history, but IPO work is the opposite case: a
    # freshly listed stock has a handful of bars by definition, and that is the
    # data. Callers studying listings pass a small `min_rows`.
    if len(out) < min_rows:
        raise ValueError(
            f"{ticker}: only {len(out)} usable rows, need {min_rows}. Widen "
            f"--start, pick a more liquid symbol, or lower min_rows."
        )
    log.info("%s: %d rows, %s .. %s", ticker, len(out), out.index[0].date(), out.index[-1].date())
    return out


def load_benchmark(ticker: str, index: pd.DatetimeIndex, **kwargs) -> pd.DataFrame:
    """Load a benchmark and align it to an existing price index.

    Reindexing forward-fills only: on a day the benchmark did not trade we carry
    the last known close, we never look ahead to the next one.
    """
    bench = load_prices(ticker, **kwargs)
    return bench.reindex(index).ffill()


# --------------------------------------------------------------------------- #
# Live price overlay
# --------------------------------------------------------------------------- #
_LIVE_FEED = []          # single-slot cache; a login per symbol is wasteful


def _live_feed():
    """One Angel session per process, not one per symbol."""
    if not _LIVE_FEED:
        from .live.feed import get_feed

        _LIVE_FEED.append(get_feed("auto"))
    return _LIVE_FEED[0]


def current_price(ticker: str) -> tuple[float | None, str]:
    """Today's price from Angel, falling back to the last cached close.

    Returns ``(price, source)``. Never raises: a missing live quote should
    degrade to stale data with a visible label, not break the caller.
    """
    try:
        feed = _live_feed()
        if getattr(feed, "delayed_seconds", 0) <= 60:
            return float(feed.quote(ticker).price), feed.name
    except Exception as exc:
        log.debug("%s: no live quote (%s)", ticker, exc)
    return None, "none"


def with_live_price(df: pd.DataFrame, ticker: str) -> pd.DataFrame:
    """Patch the last row with the live price, or append today's bar.

    **Opt-in on purpose.** A mid-session bar is incomplete -- its high, low and
    close are still moving -- so feeding it to a backtest would score the model
    on a bar that does not exist yet. Only tools answering "what is it worth
    right now" should ask for this.
    """
    price, source = current_price(ticker)
    if price is None or price <= 0:
        return df

    out = df.copy()
    today = pd.Timestamp(date.today())
    last = out.index[-1].normalize()

    if last == today:
        row = out.iloc[-1].copy()
        row["Close"] = price
        row["High"] = max(float(row["High"]), price)
        row["Low"] = min(float(row["Low"]), price)
        out.iloc[-1] = row
    else:
        prev = float(out["Close"].iloc[-1])
        out.loc[today] = {
            "Open": prev, "High": max(prev, price),
            "Low": min(prev, price), "Close": price,
            "Volume": float(out["Volume"].iloc[-1]),
        }
    out.attrs["live_source"] = source
    out.attrs["live_price"] = price
    return out


def load_prices_live(ticker: str, **kwargs) -> pd.DataFrame:
    """History from the cache, today's price from the exchange."""
    return with_live_price(load_prices(ticker, **kwargs), ticker)
