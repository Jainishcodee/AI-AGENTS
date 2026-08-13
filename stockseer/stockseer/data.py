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

    out = _clean(df, ticker)
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
