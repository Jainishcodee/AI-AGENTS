"""Paper-trading ledger.

The survival model says the outcome hinges almost entirely on one unknown: your
true win rate against the ~42% break-even line. This file exists to measure it
without paying tuition. Same signals, same sizing, same discipline -- the only
thing missing is the money.

It also computes the confidence interval around your win rate, because "I am at
60% after 8 trades" and "I am at 60% after 200 trades" are different claims, and
only one of them is evidence.
"""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

import numpy as np

from ..costs import CostModel

LEDGER_DIR = Path(__file__).resolve().parent.parent.parent / "artifacts" / "journal"


@dataclass
class Trade:
    id: str
    symbol: str
    rule: str
    side: str
    opened_at: str
    entry: float
    stop: float
    target: float
    qty: int
    paper: bool = True
    closed_at: str | None = None
    exit: float | None = None
    exit_reason: str | None = None
    costs: float = 0.0
    note: str = ""

    @property
    def is_open(self) -> bool:
        return self.exit is None

    @property
    def risk_amount(self) -> float:
        return abs(self.entry - self.stop) * self.qty

    def pnl(self) -> float:
        if self.exit is None:
            return 0.0
        raw = (self.exit - self.entry) if self.side == "long" else (self.entry - self.exit)
        return raw * self.qty - self.costs

    def r_multiple(self) -> float:
        risk = self.risk_amount
        return self.pnl() / risk if risk else float("nan")


@dataclass
class Stats:
    n_closed: int
    n_open: int
    wins: int
    losses: int
    win_rate: float
    win_rate_lo: float          # 95% interval -- the honest version of the number
    win_rate_hi: float
    avg_win_r: float
    avg_loss_r: float
    expectancy_r: float
    total_pnl: float
    total_costs: float
    best_r: float
    worst_r: float
    max_consecutive_losses: int


class Ledger:
    """Append-only trade journal backed by JSON."""

    def __init__(self, path: Path | str | None = None, capital: float = 40_000.0):
        self.path = Path(path or (LEDGER_DIR / "paper_trades.json"))
        self.capital = capital
        self.trades: list[Trade] = []
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            self.trades = [Trade(**t) for t in raw.get("trades", [])]
            self.capital = raw.get("capital", self.capital)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(
                {"capital": self.capital, "trades": [asdict(t) for t in self.trades]},
                indent=2,
            ),
            encoding="utf-8",
        )

    # ------------------------------------------------------------------ #
    def open_trade(
        self, symbol: str, rule: str, side: str, entry: float, stop: float,
        target: float, qty: int, paper: bool = True, note: str = "",
    ) -> Trade:
        trade = Trade(
            id=f"{symbol}-{len(self.trades) + 1:04d}",
            symbol=symbol, rule=rule, side=side,
            opened_at=datetime.now().astimezone().isoformat(timespec="seconds"),
            entry=entry, stop=stop, target=target, qty=qty, paper=paper, note=note,
        )
        self.trades.append(trade)
        self.save()
        return trade

    def close_trade(
        self, trade_id: str, exit_price: float, reason: str = "manual",
        model: CostModel | None = None, delivery: bool = False,
    ) -> Trade:
        trade = self.get(trade_id)
        if trade is None:
            raise KeyError(f"no trade {trade_id!r}")
        if not trade.is_open:
            raise ValueError(f"{trade_id} is already closed")

        model = model or CostModel()
        trade.exit = exit_price
        trade.exit_reason = reason
        trade.closed_at = datetime.now().astimezone().isoformat(timespec="seconds")
        # Charge full costs even on paper. A paper record that ignores them
        # measures a strategy you cannot actually trade.
        trade.costs = model.round_trip(trade.entry, exit_price, trade.qty, delivery)["total"]
        self.save()
        return trade

    def get(self, trade_id: str) -> Trade | None:
        return next((t for t in self.trades if t.id == trade_id), None)

    def open_trades(self) -> list[Trade]:
        return [t for t in self.trades if t.is_open]

    def closed_trades(self) -> list[Trade]:
        return [t for t in self.trades if not t.is_open]

    # ------------------------------------------------------------------ #
    def stats(self, rule: str | None = None) -> Stats:
        closed = [t for t in self.closed_trades() if rule is None or t.rule == rule]
        n = len(closed)
        if n == 0:
            nan = float("nan")
            return Stats(
                n_closed=0, n_open=len(self.open_trades()), wins=0, losses=0,
                win_rate=nan, win_rate_lo=nan, win_rate_hi=nan,
                avg_win_r=nan, avg_loss_r=nan, expectancy_r=nan,
                total_pnl=0.0, total_costs=0.0, best_r=nan, worst_r=nan,
                max_consecutive_losses=0,
            )

        rs = np.array([t.r_multiple() for t in closed], dtype="float64")
        wins, losses = rs[rs > 0], rs[rs <= 0]
        wr = len(wins) / n
        lo, hi = wilson_interval(len(wins), n)

        streak = best_streak = 0
        for r in rs:
            streak = streak + 1 if r <= 0 else 0
            best_streak = max(best_streak, streak)

        return Stats(
            n_closed=n,
            n_open=len(self.open_trades()),
            wins=int(len(wins)),
            losses=int(len(losses)),
            win_rate=wr,
            win_rate_lo=lo,
            win_rate_hi=hi,
            avg_win_r=float(wins.mean()) if wins.size else float("nan"),
            avg_loss_r=float(losses.mean()) if losses.size else float("nan"),
            expectancy_r=float(rs.mean()),
            total_pnl=float(sum(t.pnl() for t in closed)),
            total_costs=float(sum(t.costs for t in closed)),
            best_r=float(rs.max()),
            worst_r=float(rs.min()),
            max_consecutive_losses=best_streak,
        )

    def sources(self) -> list[str]:
        """Distinct signal sources in the journal.

        The ``rule`` field is deliberately free-text. It holds a built-in rule
        name, but it just as happily holds "tipsProviderX" or "telegram_channel" --
        which makes this journal an audit tool for anyone else's recommendations,
        scored by exactly the same barriers as our own.
        """
        return sorted({t.rule for t in self.closed_trades()})

    def compare_sources(self, breakeven: float = 0.42) -> list[tuple[str, Stats, str]]:
        """Rank every signal source by expectancy, with an evidence verdict."""
        rows = []
        for src in self.sources():
            st = self.stats(src)
            if st.win_rate_lo > breakeven:
                verdict = "real edge"
            elif st.win_rate_hi < breakeven:
                verdict = "NO edge"
            else:
                verdict = f"unproven ({st.n_closed} trades)"
            rows.append((src, st, verdict))
        return sorted(rows, key=lambda r: r[1].expectancy_r, reverse=True)

    def export_csv(self, path: Path | str) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow([
                "id", "symbol", "rule", "side", "opened_at", "entry", "stop",
                "target", "qty", "closed_at", "exit", "exit_reason", "costs",
                "pnl", "r_multiple", "paper",
            ])
            for t in self.trades:
                writer.writerow([
                    t.id, t.symbol, t.rule, t.side, t.opened_at, t.entry, t.stop,
                    t.target, t.qty, t.closed_at, t.exit, t.exit_reason,
                    round(t.costs, 2), round(t.pnl(), 2),
                    round(t.r_multiple(), 3) if not t.is_open else "", t.paper,
                ])
        return path


def wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% confidence interval for a win rate.

    Wilson rather than the textbook normal approximation, which misbehaves badly
    at the small samples that matter here -- and small samples are the whole
    point. After 10 trades the interval is so wide it tells you to keep going;
    that *is* the finding.
    """
    if n == 0:
        return (float("nan"), float("nan"))
    p = successes / n
    denom = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / denom
    margin = z * np.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denom
    return (max(0.0, centre - margin), min(1.0, centre + margin))


def trades_needed_for_confidence(
    win_rate: float = 0.55, breakeven: float = 0.42, z: float = 1.96
) -> int:
    """How many trades before the interval clears the break-even line.

    Answers "when do I actually know?" -- usually a larger number than people
    expect, and worth knowing before rather than after.
    """
    for n in range(10, 5001):
        lo, _ = wilson_interval(int(round(win_rate * n)), n, z)
        if lo > breakeven:
            return n
    return -1
