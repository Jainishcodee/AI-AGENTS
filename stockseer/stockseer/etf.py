"""Gold and silver ETFs: is the price fair, and does that matter?

An ETF has something a stock does not -- a published fair value. The fund
declares a NAV every evening, so unlike "is Cupid expensive", "is GOLDBEES
expensive" has a real answer: compare the traded price to the NAV.

That gap is the premium (paying above fair value) or discount (below). It is
the one thing about an ETF that is knowable rather than predicted, and it is
where Indian retail quietly loses money: during a metal squeeze these can trade
several percent above NAV, and buying there means giving that back when the gap
closes, no matter what gold or silver does.

Prices come from the exchange. NAVs come from AMFI, the industry body every
Indian fund reports to, via the free api.mfapi.in mirror.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .data import load_prices, load_prices_live

log = logging.getLogger(__name__)

CACHE = Path(__file__).resolve().parent.parent / "cache"
NAV_API = "https://api.mfapi.in/mf/{code}"
UA = {"User-Agent": "Mozilla/5.0 (compatible; StockSeer/0.1)"}


@dataclass(frozen=True)
class Fund:
    ticker: str
    amfi_code: str | None
    name: str
    metal: str
    peer: str | None = None      # borrow this fund's NAV when it has none


# Tata's ETFs file only their Fund-of-Fund NAV with AMFI, so their premium is
# measured against a peer tracking the same metal, rescaled. Less exact than a
# published NAV, and flagged as approximate wherever it is used.
REGISTRY: dict[str, Fund] = {
    "GOLDBEES.NS": Fund("GOLDBEES.NS", "140088", "Nippon India ETF Gold BeES", "gold"),
    "SILVERBEES.NS": Fund("SILVERBEES.NS", "149758", "Nippon India Silver ETF", "silver"),
    "TATAGOLD.NS": Fund("TATAGOLD.NS", None, "Tata Gold ETF", "gold", peer="GOLDBEES.NS"),
    "TATSILV.NS": Fund("TATSILV.NS", None, "Tata Silver ETF", "silver", peer="SILVERBEES.NS"),
}


def _fetch_json(url: str, timeout: int = 60) -> dict:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def nav_history(amfi_code: str, refresh: bool = False,
                max_age_hours: float = 12.0) -> pd.Series:
    """Daily NAV for one scheme, cached to disk.

    NAV is published once each evening, so re-fetching within the day buys
    nothing and only risks a rate limit.
    """
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"nav_{amfi_code}.csv"
    fresh = path.exists() and (time.time() - path.stat().st_mtime) < max_age_hours * 3600

    if fresh and not refresh:
        s = pd.read_csv(path, index_col=0, parse_dates=True)["nav"]
    else:
        data = _fetch_json(NAV_API.format(code=amfi_code)).get("data", [])
        if not data:
            raise ValueError(f"AMFI scheme {amfi_code} returned no NAV history")
        parsed = {}
        for row in data:
            val = row.get("nav")
            if val in (None, "", "N.A."):
                continue
            parsed[pd.to_datetime(row["date"], format="%d-%m-%Y")] = float(val)
        s = pd.Series(parsed, name="nav").sort_index()
        s.to_frame().to_csv(path)

    return s[s > 0].sort_index()


def premium_series(ticker: str, start: str = "2022-01-01",
                   refresh: bool = False) -> pd.DataFrame:
    """Traded price against NAV, aligned by date.

    NAV is struck after the close, so a same-day comparison is the right one:
    both describe the same trading session.
    """
    fund = REGISTRY.get(ticker)
    if fund is None:
        raise ValueError(f"{ticker} is not a tracked ETF; known: {sorted(REGISTRY)}")

    # Live: a premium computed from a two-day-old close is not a premium,
    # it is a history lesson. This number exists to be acted on today.
    px = load_prices_live(ticker, start=start, min_rows=30)
    close = px["Close"]
    live_src = px.attrs.get("live_source", "cached")

    if fund.amfi_code:
        nav = nav_history(fund.amfi_code, refresh)
        approx = False
    else:
        peer = REGISTRY[fund.peer]
        peer_nav = nav_history(peer.amfi_code, refresh)
        peer_px = load_prices_live(peer.ticker, start=start, min_rows=30)["Close"]
        common = close.index.intersection(peer_px.index)
        if len(common) < 30:
            raise ValueError(f"not enough overlap between {ticker} and {peer.ticker}")
        # Rescale the peer NAV into this fund's units via the median price
        # ratio, so levels are comparable despite different unit sizes.
        scale = float((close.loc[common] / peer_px.loc[common]).median())
        nav = peer_nav * scale
        approx = True

    idx = close.index.intersection(nav.index)
    if len(idx) < 30:
        raise ValueError(f"{ticker}: only {len(idx)} days where price and NAV overlap")

    df = pd.DataFrame({"close": close.loc[idx], "nav": nav.loc[idx]})
    df["premium"] = df["close"] / df["nav"] - 1.0
    df.attrs["approx"] = approx
    df.attrs["fund"] = fund
    df.attrs["live_source"] = live_src
    # NAV is published after the close, so today's live price has no same-day
    # NAV and the intersection above drops it. Keep both here: the newest NAV
    # is at most one session stale, which is far closer to fair value than a
    # two-day-old traded price.
    df.attrs["live_close"] = float(close.iloc[-1])
    df.attrs["live_nav"] = float(nav.iloc[-1])
    df.attrs["live_premium"] = float(close.iloc[-1] / nav.iloc[-1] - 1.0)
    df.attrs["live_date"] = str(close.index[-1].date())
    df.attrs["nav_date"] = str(nav.index[-1].date())
    return df


# --------------------------------------------------------------------------- #
# Does the premium actually matter?
# --------------------------------------------------------------------------- #
@dataclass
class PremiumStudy:
    ticker: str
    name: str
    n: int
    approx: bool
    mean_premium: float
    sd_premium: float
    p5: float
    p95: float
    current: float
    current_z: float
    pct_days_above_1pct: float
    half_life_days: float
    spread_top_vs_bottom: float
    buckets: pd.DataFrame
    price: float = 0.0
    nav: float = 0.0
    as_of: str = ""
    nav_date: str = ""
    indicative: float = 0.0      # live price vs last NAV; includes the day's move
    nav_is_stale: bool = False


def study_premium(ticker: str, horizon: int = 21, start: str = "2022-01-01",
                  refresh: bool = False) -> PremiumStudy:
    """Split history by premium and compare what happened next.

    If the premium is meaningless, forward returns look the same in every
    bucket. If paying a premium is a real mistake, the top bucket lags.
    """
    df = premium_series(ticker, start, refresh)
    prem = df["premium"]
    fwd = df["close"].shift(-horizon) / df["close"] - 1.0

    # How fast the gap closes, from an AR(1) fit on the premium itself.
    dev = prem - prem.mean()
    lag = dev.shift(1).dropna()
    cur = dev.loc[lag.index]
    denom = float((lag * lag).sum())
    rho = float(np.clip((lag * cur).sum() / denom, 1e-6, 0.999999)) if denom else 0.5
    half_life = float(np.log(0.5) / np.log(rho)) if 0 < rho < 1 else float("inf")

    work = pd.DataFrame({"premium": prem, "fwd": fwd}).dropna()
    labels = ["deep discount", "discount", "fair", "premium", "high premium"]
    try:
        work["bucket"] = pd.qcut(work["premium"], 5, labels=labels)
    except ValueError:
        work["bucket"] = pd.cut(work["premium"], 5, labels=labels)

    buckets = work.groupby("bucket", observed=True).agg(
        days=("fwd", "size"),
        avg_premium=("premium", "mean"),
        fwd_return=("fwd", "mean"),
        win_rate=("fwd", lambda s: float((s > 0).mean())),
    )

    spread = float("nan")
    if len(buckets) >= 2:
        spread = float(buckets["fwd_return"].iloc[0] - buckets["fwd_return"].iloc[-1])

    sd = float(prem.std())

    # Settled: the newest date where a traded price and its own NAV both exist.
    # Indicative: today's live price against the last published NAV, which also
    # carries the metal's move since that NAV was struck. Only the settled one
    # is a premium; the indicative one is shown for context and never judged.
    settled = float(prem.iloc[-1])
    stale = df.attrs.get("live_date", "") != df.attrs.get("nav_date", "")
    indicative = float(df.attrs.get("live_premium", settled))
    return PremiumStudy(
        ticker=ticker, name=REGISTRY[ticker].name, n=len(df),
        approx=bool(df.attrs.get("approx")),
        mean_premium=float(prem.mean()), sd_premium=sd,
        p5=float(prem.quantile(0.05)), p95=float(prem.quantile(0.95)),
        current=settled,
        current_z=float((settled - prem.mean()) / sd) if sd > 0 else 0.0,
        indicative=indicative,
        nav_is_stale=stale,
        price=float(df.attrs.get("live_close", df["close"].iloc[-1])),
        nav=float(df.attrs.get("live_nav", df["nav"].iloc[-1])),
        as_of=str(df.attrs.get("live_date", "")),
        nav_date=str(df.attrs.get("nav_date", "")),
        pct_days_above_1pct=float((prem > 0.01).mean()),
        half_life_days=half_life,
        spread_top_vs_bottom=spread,
        buckets=buckets,
    )


def verdict(s: PremiumStudy) -> tuple[str, str]:
    """Is today a fair price to pay? Says nothing about the metal's direction."""
    p = s.current * 100
    if s.current >= s.p95:
        return ("EXPENSIVE - WAIT",
                f"You would pay {p:+.2f}% above fair value, near the most "
                f"expensive this has been. That gap has closed in about "
                f"{s.half_life_days:.0f} days historically, which is a loss "
                f"even if the metal goes nowhere.")
    if s.current > 0.01:
        return ("SLIGHTLY EXPENSIVE",
                f"You would pay {p:+.2f}% above fair value. Small, but it is a "
                f"cost you avoid by waiting a few days.")
    if s.current <= s.p5:
        return ("CHEAP - GOOD PRICE",
                f"Trading {p:+.2f}% below fair value, near the cheapest it has "
                f"been. You get the metal at a discount.")
    if s.current < -0.005:
        return ("GOOD PRICE", f"Trading {p:+.2f}% below fair value.")
    return ("FAIR PRICE", f"Within {abs(p):.2f}% of fair value. Normal.")


def scan_and_notify(tickers: list[str] | None = None, start: str = "2022-01-01",
                    refresh: bool = True) -> list:
    """Alert only when the price is genuinely away from fair value.

    Nothing fires on an ordinary day. A gold ETF sitting within half a percent
    of NAV is not news, and an alert that arrives daily is one you stop
    reading -- which is how you miss the day it matters.
    """
    from datetime import date

    from .notify import hub

    pushed = []
    for ticker in (tickers or list(REGISTRY)):
        try:
            s = study_premium(ticker, start=start, refresh=refresh)
        except Exception as exc:
            log.warning("%s: %s", ticker, exc)
            continue

        v, why = verdict(s)
        if v not in ("EXPENSIVE - WAIT", "CHEAP - GOOD PRICE"):
            continue

        cheap = v.startswith("CHEAP")
        approx = "\n(fair value estimated from a peer fund)" if s.approx else ""
        n = hub().alert(
            kind="etf_cheap" if cheap else "etf_expensive",
            urgency="act" if cheap else "info",
            title=(f"{ticker.replace('.NS', '')} is cheap "
                   f"({s.current * 100:+.2f}% vs fair value)" if cheap else
                   f"{ticker.replace('.NS', '')} is dear "
                   f"({s.current * 100:+.2f}% vs fair value)"),
            body=(f"{s.name}\n{why}\n\n"
                  f"Normal gap is {s.sd_premium * 100:.2f}%. "
                  f"It closes in about {s.half_life_days:.0f} days.{approx}"),
            symbol=ticker,
            dedupe_key=f"etf:{v}:{ticker}:{date.today().isoformat()}",
            premium=s.current, verdict=v,
        )
        if n:
            pushed.append(n)
    return pushed


def print_study(s: PremiumStudy) -> None:
    bar = "=" * 68
    pct = lambda v: f"{v * 100:+.2f}%"                                 # noqa: E731

    print(f"\n{bar}")
    print(f" {s.ticker}   {s.name}")
    print(bar)
    if s.approx:
        print("  NOTE: this fund does not publish a NAV to AMFI. Fair value is")
        print("        estimated from a peer tracking the same metal.")

    v, why = verdict(s)
    print(f"\n  TODAY:  {v}")
    print(f"          {why}")

    print(f"\n  PRICE VS FAIR VALUE ({s.n} days)")
    print(f"    right now         {pct(s.current)}   ({s.current_z:+.1f} sd from normal)")
    print(f"    usual             {pct(s.mean_premium)}   +/- {s.sd_premium * 100:.2f}%")
    print(f"    cheapest 5%       below {pct(s.p5)}")
    print(f"    dearest 5%        above {pct(s.p95)}")
    print(f"    over 1% expensive on {s.pct_days_above_1pct * 100:.0f}% of days")
    print(f"    gap closes in     ~{s.half_life_days:.0f} days (half of it)")

    print("\n  WHAT HAPPENED NEXT (1 month later, by price paid)")
    print(f"    {'bucket':<16}{'days':>6}{'paid':>10}{'next 1m':>10}{'win%':>8}")
    for name, row in s.buckets.iterrows():
        print(f"    {str(name):<16}{int(row['days']):>6}"
              f"{row['avg_premium'] * 100:>9.2f}%{row['fwd_return'] * 100:>9.2f}%"
              f"{row['win_rate'] * 100:>7.0f}%")

    # The bucket table looks like it says "pay more, earn more". It does not.
    # These funds drift to a premium precisely when the metal is running and
    # buyers pile in, so the top bucket is really a momentum bucket wearing a
    # premium label. Reading it as causal would have you buying at the worst
    # prices on purpose, so the confound is stated rather than left implied.
    if s.spread_top_vs_bottom == s.spread_top_vs_bottom:
        gap = s.spread_top_vs_bottom * 100
        if gap < 0:
            print(f"\n    Careful: buying at a premium looks better here "
                  f"({abs(gap):.2f}%), but that is")
            print("    momentum, not the premium. These trade dear exactly when the")
            print("    metal is rallying. It is not a reason to pay above fair value.")
        else:
            print(f"\n    Buying cheap beat buying dear by {gap:+.2f}% "
                  f"over the next month.")

    print("\n  WHAT THIS IS GOOD FOR")
    print(f"    The gap is small ({s.sd_premium * 100:.2f}% typical) and closes in")
    print(f"    ~{s.half_life_days:.0f} days. So it will not make you money -- it")
    print(f"    just stops you overpaying on the {s.pct_days_above_1pct * 100:.0f}% "
          f"of days it is over 1% dear.")
    print(f"{bar}\n")
