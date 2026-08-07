"""Score anyone's stock recommendations against what actually happened.

Point this at a paid advisory, a Telegram channel, a YouTube analyst, a broker
research desk, or your own gut calls. It applies the same triple-barrier test the
built-in rules go through, so a marketing claim becomes a measured number.

Three design choices carry all the honesty:

* **Scored from the published timestamp**, never from a convenient later entry.
  If a call went out at 10:05 you are filled at 10:05, not at the day's low.
* **A random-entry baseline runs alongside.** In a rising market almost any long
  call looks good; the question is whether these calls beat picking the same
  symbols on random days. This is the shuffled-label control, applied to people.
* **Costs are charged**, because a call you cannot trade profitably is not a
  good call.
"""

from __future__ import annotations

import csv
import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

CALLS_DIR = Path(__file__).resolve().parent.parent.parent / "artifacts" / "advisors"


@dataclass
class Call:
    """One recommendation, as published."""

    source: str
    symbol: str
    side: str                    # "long" | "short"
    published_at: str            # ISO timestamp -- when it became actionable
    entry: float | None = None   # None -> fill at the close of the published bar
    stop: float | None = None
    target: float | None = None
    horizon_days: int = 10
    note: str = ""
    id: str = ""

    def when(self) -> pd.Timestamp:
        return pd.Timestamp(self.published_at)


@dataclass
class CallOutcome:
    call: Call
    filled_at: str
    fill_price: float
    exit_at: str
    exit_price: float
    result: str                  # "target" | "stop" | "timeout"
    r_multiple: float
    pct_return: float
    bars_held: int


@dataclass
class SourceStats:
    source: str
    n_calls: int
    n_scored: int
    hit_rate: float
    stop_rate: float
    timeout_rate: float
    avg_r: float
    expectancy_r: float
    avg_pct: float
    median_days_held: float
    # The control: same symbols, same holding period, random entry dates.
    baseline_avg_pct: float
    edge_vs_baseline: float
    edge_t_stat: float
    calls_needed: float          # scored calls required to prove this edge at t=2

    @property
    def verdict(self) -> str:
        if self.n_scored < 30:
            return f"too few calls ({self.n_scored}) to judge"
        if self.edge_t_stat < 2.0:
            if self.edge_vs_baseline > 0 and self.calls_needed == self.calls_needed:
                return (f"positive but unproven -- needs ~{self.calls_needed:.0f}"
                        f" calls to confirm, has {self.n_scored}")
            return "no measurable edge over random entry"
        if self.expectancy_r <= 0:
            return "beats random entry but still loses after costs"
        return f"real edge (t = {self.edge_t_stat:.1f})"


class CallLog:
    """Append-only store of recommendations."""

    def __init__(self, path: Path | str | None = None):
        self.path = Path(path or (CALLS_DIR / "calls.json"))
        self.calls: list[Call] = []
        if self.path.exists():
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            self.calls = [Call(**c) for c in raw]

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps([asdict(c) for c in self.calls], indent=2), encoding="utf-8"
        )

    def add(self, call: Call) -> Call:
        call.id = call.id or f"{call.source}-{len(self.calls) + 1:04d}"
        self.calls.append(call)
        self.save()
        return call

    def import_csv(self, path: Path | str, source: str | None = None) -> int:
        """Bulk import. Expected columns: symbol, side, published_at, and
        optionally entry, stop, target, horizon_days, source, note."""
        added = 0
        with Path(path).open(newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                def num(key):
                    val = (row.get(key) or "").strip()
                    return float(val) if val else None

                self.add(Call(
                    source=row.get("source") or source or "unknown",
                    symbol=row["symbol"].strip(),
                    side=(row.get("side") or "long").strip().lower(),
                    published_at=row["published_at"].strip(),
                    entry=num("entry"), stop=num("stop"), target=num("target"),
                    horizon_days=int(row.get("horizon_days") or 10),
                    note=row.get("note", ""),
                ))
                added += 1
        return added

    def sources(self) -> list[str]:
        return sorted({c.source for c in self.calls})


# --------------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------------- #
def _walk_barriers(
    bars: pd.DataFrame, start_i: int, side: str, fill: float,
    stop: float, target: float, max_bars: int,
) -> tuple[str, float, int]:
    """Return (result, exit_price, bars_held) walking forward bar by bar."""
    high, low, close = (bars["High"].to_numpy(), bars["Low"].to_numpy(),
                        bars["Close"].to_numpy())
    long = side == "long"
    last = min(start_i + max_bars, len(close) - 1)

    for j in range(start_i + 1, last + 1):
        hit_stop = low[j] <= stop if long else high[j] >= stop
        hit_target = high[j] >= target if long else low[j] <= target
        # Ambiguous bar: assume the stop. Same rule as the intraday evaluator.
        if hit_stop:
            return "stop", stop, j - start_i
        if hit_target:
            return "target", target, j - start_i
    return "timeout", close[last], max(last - start_i, 1)


def score_calls(
    calls: list[Call],
    load_bars,
    cost_pct: float = 0.0011,
    default_stop_pct: float = 0.05,
    default_target_pct: float = 0.10,
    baseline_samples: int = 40,
    seed: int = 11,
) -> tuple[list[CallOutcome], dict[str, SourceStats]]:
    """Score every call and compare each source against random entry.

    ``load_bars(symbol)`` must return a daily OHLCV frame covering the call
    dates -- normally ``stockseer.data.load_prices``.
    """
    rng = np.random.default_rng(seed)
    outcomes: list[CallOutcome] = []
    by_source: dict[str, list[CallOutcome]] = {}
    baseline: dict[str, list[float]] = {}

    cache: dict[str, pd.DataFrame] = {}
    for call in calls:
        try:
            if call.symbol not in cache:
                cache[call.symbol] = load_bars(call.symbol)
            bars = cache[call.symbol]
        except Exception as exc:
            log.warning("no data for %s: %s", call.symbol, exc)
            continue

        when = call.when()
        if when.tzinfo is not None:
            when = when.tz_localize(None)
        # First bar at or after publication -- you cannot buy before the call.
        pos = bars.index.searchsorted(when)
        if pos >= len(bars) - 1:
            log.info("%s: published beyond available data", call.id)
            continue

        fill = call.entry if call.entry else float(bars["Close"].iloc[pos])
        long = call.side == "long"
        stop = call.stop or (fill * (1 - default_stop_pct) if long
                             else fill * (1 + default_stop_pct))
        target = call.target or (fill * (1 + default_target_pct) if long
                                 else fill * (1 - default_target_pct))

        result, exit_px, held = _walk_barriers(
            bars, pos, call.side, fill, stop, target, call.horizon_days
        )
        raw = (exit_px - fill) / fill if long else (fill - exit_px) / fill
        pct = raw - cost_pct
        risk = abs(fill - stop) / fill
        r = pct / risk if risk > 0 else float("nan")

        out = CallOutcome(
            call=call,
            filled_at=str(bars.index[pos].date()),
            fill_price=fill,
            exit_at=str(bars.index[min(pos + held, len(bars) - 1)].date()),
            exit_price=exit_px,
            result=result,
            r_multiple=r,
            pct_return=pct,
            bars_held=held,
        )
        outcomes.append(out)
        by_source.setdefault(call.source, []).append(out)

        # Control: same symbol, same holding period, entries picked at random.
        sample = []
        limit = len(bars) - call.horizon_days - 1
        if limit > 50:
            for i in rng.integers(0, limit, size=baseline_samples):
                a = float(bars["Close"].iloc[i])
                b = float(bars["Close"].iloc[i + call.horizon_days])
                move = (b - a) / a if long else (a - b) / a
                sample.append(move - cost_pct)
        baseline.setdefault(call.source, []).extend(sample)

    stats = {}
    for source, outs in by_source.items():
        rs = np.array([o.r_multiple for o in outs], dtype="float64")
        pcts = np.array([o.pct_return for o in outs], dtype="float64")
        base = np.array(baseline.get(source, []), dtype="float64")
        base_mean = float(base.mean()) if base.size else 0.0

        edge = float(pcts.mean()) - base_mean
        # Standard error of the call-return mean; the baseline is large enough
        # that its own error is negligible by comparison.
        se = float(pcts.std(ddof=1) / np.sqrt(len(pcts))) if len(pcts) > 1 else float("nan")

        stats[source] = SourceStats(
            source=source,
            n_calls=sum(1 for c in calls if c.source == source),
            n_scored=len(outs),
            hit_rate=float(np.mean([o.result == "target" for o in outs])),
            stop_rate=float(np.mean([o.result == "stop" for o in outs])),
            timeout_rate=float(np.mean([o.result == "timeout" for o in outs])),
            avg_r=float(np.nanmean(rs)),
            expectancy_r=float(np.nanmean(rs)),
            avg_pct=float(pcts.mean()),
            median_days_held=float(np.median([o.bars_held for o in outs])),
            baseline_avg_pct=base_mean,
            edge_vs_baseline=edge,
            edge_t_stat=edge / se if se and se == se and se > 0 else float("nan"),
            # Sample size for t = 2, from n = (2 * sd / edge)^2. Usually a
            # sobering number: single-call returns are so noisy that even a
            # strong picker needs hundreds of calls before the edge is provable.
            calls_needed=(
                (2.0 * float(pcts.std(ddof=1)) / edge) ** 2
                if len(pcts) > 1 and edge > 0 else float("nan")
            ),
        )
    return outcomes, stats


def print_scorecard(stats: dict[str, SourceStats]) -> None:
    if not stats:
        print("\n No calls could be scored. Check symbols and published_at dates.\n")
        return

    print(f"\n{'=' * 78}")
    print(" ADVISORY SCORECARD  --  measured against random entry in the same names")
    print("=" * 78)
    header = (f"{'source':<20}{'n':>5}{'hit%':>7}{'stop%':>7}{'avg R':>8}"
              f"{'avg %':>8}{'base %':>8}{'edge t':>8}")
    print(header)
    print("-" * len(header))
    for s in sorted(stats.values(), key=lambda x: -(x.edge_t_stat if x.edge_t_stat == x.edge_t_stat else -99)):
        print(f"{s.source:<20}{s.n_scored:>5}{s.hit_rate * 100:>7.1f}"
              f"{s.stop_rate * 100:>7.1f}{s.avg_r:>+8.3f}{s.avg_pct * 100:>+8.2f}"
              f"{s.baseline_avg_pct * 100:>+8.2f}{s.edge_t_stat:>8.2f}")
    print()
    for s in stats.values():
        print(f" {s.source:<20} {s.verdict}")
    print("\n 'base %' is what random entries in the same symbols over the same"
          "\n holding period returned. Beating it is the whole job -- in a rising"
          "\n market, long calls make money without any skill at all.\n")
