"""The session loop: poll, evaluate, alert, manage open positions.

Deliberately conservative about two things:

* **Only completed bars generate signals.** A rule evaluated on a forming bar
  fires and un-fires as the price moves, which produces alerts that were never
  real. The current bar is dropped until it closes.
* **Exit alerts outrank entry alerts.** Missing an entry costs you an
  opportunity; missing an exit costs you money.
"""

from __future__ import annotations

import json
import logging
import time as _time
from dataclasses import asdict, dataclass
from datetime import datetime, time
from pathlib import Path

import pandas as pd

from ..costs import CostModel
from ..sizing import size_position
from .feed import Feed, get_feed
from .intraday import SESSION_CLOSE, SESSION_OPEN, enrich
from .ledger import Ledger
from .rules import REGISTRY, RuleStats, Signal, evaluate_all, live_signals

log = logging.getLogger(__name__)

ALERT_FILE = Path(__file__).resolve().parent.parent.parent / "artifacts" / "alerts.json"


@dataclass
class Alert:
    kind: str            # "entry" | "exit" | "risk"
    urgency: str         # "info" | "act"
    symbol: str
    message: str
    at: str
    detail: dict


def market_is_open(now: datetime | None = None) -> bool:
    now = now or datetime.now()
    if now.weekday() >= 5:
        return False
    return SESSION_OPEN <= now.time() <= SESSION_CLOSE


def _drop_forming_bar(bars: pd.DataFrame, interval_minutes: int) -> pd.DataFrame:
    """Remove the in-progress bar so rules only ever see settled data."""
    if bars.empty:
        return bars
    last = bars.index[-1]
    now = pd.Timestamp.now(tz=last.tz)
    if (now - last).total_seconds() < interval_minutes * 60:
        return bars.iloc[:-1]
    return bars


class Monitor:
    def __init__(
        self,
        symbols: list[str],
        feed: Feed | None = None,
        ledger: Ledger | None = None,
        interval: str = "5m",
        capital: float = 40_000.0,
        risk_pct: float = 0.01,
        stop_atr: float = 1.0,
        target_atr: float = 1.5,
        min_expectancy: float = 0.0,
        min_signals: int = 30,
        paper: bool = True,
    ):
        self.symbols = symbols
        self.feed = feed or get_feed()
        self.ledger = ledger or Ledger(capital=capital)
        self.interval = interval
        self.interval_minutes = int(interval.rstrip("m")) if interval.endswith("m") else 5
        self.capital = capital
        self.risk_pct = risk_pct
        self.stop_atr = stop_atr
        self.target_atr = target_atr
        self.min_expectancy = min_expectancy
        self.min_signals = min_signals
        self.paper = paper
        self.rule_stats: dict[str, dict[str, RuleStats]] = {}
        self.costs = CostModel()
        self._seen: set[tuple[str, str, str]] = set()

    # ------------------------------------------------------------------ #
    def calibrate(self, days: int = 55) -> None:
        """Measure every rule on recent history before letting any of them fire.

        A rule that has not cleared its break-even expectancy on this symbol is
        muted. This is the difference between an alerting system and a random
        notification generator.
        """
        for symbol in self.symbols:
            try:
                bars = self.feed.history(symbol, self.interval, days)
            except Exception as exc:
                log.warning("calibration failed for %s: %s", symbol, exc)
                continue
            stats = evaluate_all(
                bars, stop_atr=self.stop_atr, target_atr=self.target_atr
            )
            self.rule_stats[symbol] = {s.rule: s for s in stats}
            live = [s.rule for s in stats if self._rule_allowed(s)]
            log.info("%s: %d/%d rules cleared calibration (%s)",
                     symbol, len(live), len(stats), ", ".join(live) or "none")

    def _rule_allowed(self, st: RuleStats) -> bool:
        return (
            st.n_signals >= self.min_signals
            and st.expectancy_r == st.expectancy_r
            and st.expectancy_r > self.min_expectancy
        )

    # ------------------------------------------------------------------ #
    def scan(self) -> list[Alert]:
        alerts: list[Alert] = []
        alerts.extend(self._check_open_positions())   # exits first, always
        alerts.extend(self._check_entries())
        if alerts:
            self._publish(alerts)
        return alerts

    def _check_open_positions(self) -> list[Alert]:
        out = []
        for trade in self.ledger.open_trades():
            try:
                q = self.feed.quote(trade.symbol)
            except Exception as exc:
                log.warning("quote failed for %s: %s", trade.symbol, exc)
                continue

            price = q.price
            long = trade.side == "long"
            hit_stop = price <= trade.stop if long else price >= trade.stop
            hit_target = price >= trade.target if long else price <= trade.target
            unrealised = ((price - trade.entry) if long else (trade.entry - price)) * trade.qty

            if hit_stop:
                out.append(Alert(
                    "exit", "act", trade.symbol,
                    f"STOP HIT on {trade.id} at {price:.2f} "
                    f"(stop {trade.stop:.2f}) -- exit now, loss ~Rs {unrealised:,.0f}",
                    q.at.isoformat(), {"trade_id": trade.id, "price": price},
                ))
            elif hit_target:
                out.append(Alert(
                    "exit", "act", trade.symbol,
                    f"TARGET HIT on {trade.id} at {price:.2f} "
                    f"(target {trade.target:.2f}) -- book ~Rs {unrealised:,.0f}",
                    q.at.isoformat(), {"trade_id": trade.id, "price": price},
                ))
            elif datetime.now().time() >= time(15, 10):
                out.append(Alert(
                    "exit", "act", trade.symbol,
                    f"SESSION CLOSING with {trade.id} open at {price:.2f} "
                    f"(P&L ~Rs {unrealised:,.0f}) -- square off before 15:20",
                    q.at.isoformat(), {"trade_id": trade.id, "price": price},
                ))
        return out

    def _check_entries(self) -> list[Alert]:
        out = []
        for symbol in self.symbols:
            try:
                bars = self.feed.history(symbol, self.interval, days=5)
            except Exception as exc:
                log.warning("history failed for %s: %s", symbol, exc)
                continue

            bars = _drop_forming_bar(bars, self.interval_minutes)
            if len(bars) < 30:
                continue

            stats = self.rule_stats.get(symbol, {})
            allowed = [r for r in REGISTRY
                       if r.name in stats and self._rule_allowed(stats[r.name])]
            if not allowed:
                continue

            for sig in live_signals(bars, symbol, allowed, self.stop_atr,
                                    self.target_atr, stats):
                key = (symbol, sig.rule, str(sig.at))
                if key in self._seen:
                    continue
                self._seen.add(key)
                out.append(self._entry_alert(sig))
        return out

    def _entry_alert(self, sig: Signal) -> Alert:
        pos = size_position(
            capital=self.capital,
            entry=sig.price,
            stop=sig.stop if sig.side == "long" else sig.price - abs(sig.price - sig.stop),
            target=sig.target if sig.side == "long" else sig.price + abs(sig.target - sig.price),
            risk_pct=self.risk_pct,
            model=self.costs,
        )
        hit = sig.stats.get("hit_rate", float("nan"))
        exp = sig.stats.get("expectancy_r", float("nan"))
        n = sig.stats.get("n_signals", 0)
        msg = (
            f"{sig.rule} fired on {sig.symbol} at {sig.price:.2f}\n"
            f"  entry {sig.price:.2f}  stop {sig.stop:.2f}  target {sig.target:.2f}"
            f"  ({sig.rr:.2f}R)\n"
            f"  size {pos.qty} sh = Rs {pos.position_value:,.0f}, "
            f"risking Rs {pos.net_risk:,.0f}\n"
            f"  this rule historically: {hit * 100:.0f}% hit, "
            f"{exp:+.3f}R expectancy over {n:.0f} signals"
        )
        return Alert("entry", "info", sig.symbol, msg,
                     sig.at.isoformat(), {**asdict(sig), "qty": pos.qty,
                                          "at": sig.at.isoformat()})

    def _publish(self, alerts: list[Alert]) -> None:
        """Write alerts where Jarvis can pick them up."""
        ALERT_FILE.parent.mkdir(parents=True, exist_ok=True)
        existing = []
        if ALERT_FILE.exists():
            try:
                existing = json.loads(ALERT_FILE.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                existing = []
        existing.extend(asdict(a) for a in alerts)
        ALERT_FILE.write_text(json.dumps(existing[-500:], indent=2, default=str),
                              encoding="utf-8")

    # ------------------------------------------------------------------ #
    def run(self, poll_seconds: int = 60, once: bool = False) -> None:
        mode = "PAPER" if self.paper else "LIVE"
        print(f"\n StockSeer monitor [{mode}]  feed: {self.feed.describe()}")
        print(f" watching: {', '.join(self.symbols)}")
        print(f" capital Rs {self.capital:,.0f}, risking {self.risk_pct * 100:.1f}%/trade\n")

        if self.feed.delayed_seconds > 60:
            print(f" WARNING: this feed is ~{self.feed.delayed_seconds // 60} minutes "
                  f"delayed. Fine for studying rules,\n"
                  f"          too slow to act on intraday stops. "
                  f"Add Angel One credentials for live ticks.\n")

        if not self.rule_stats:
            print(" calibrating rules on recent history...")
            self.calibrate()
            print()

        while True:
            if not market_is_open():
                print(f" [{datetime.now():%H:%M:%S}] market closed")
                if once:
                    return
                _time.sleep(min(poll_seconds * 5, 300))
                continue

            for alert in self.scan():
                marker = "!!" if alert.urgency == "act" else "  "
                print(f" {marker} [{datetime.now():%H:%M:%S}] {alert.message}\n")

            if once:
                return
            _time.sleep(poll_seconds)
