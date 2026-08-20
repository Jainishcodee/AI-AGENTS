"""Holdings, concentration, and tax-loss harvesting.

Two things this answers that price data alone cannot:

**Where is the real risk?** Eighteen holdings feel diversified. Seven of them in
power and PSU names is one bet sized at seven times, and it falls as one. This
groups positions by theme so the concentration is visible in rupees.

**Which losses are worth realising?** Realised losses offset realised gains, so
selling a position you were going to exit anyway can cut the tax on gains you
already booked. That is the one legitimate way a loss "converts" into money --
not by buying something else and hoping, but through the tax code.

Rates follow the post-July-2024 Indian regime: 20% short-term on equity, 12.5%
long-term above a Rs.1.25 lakh exemption. Verify against your own filing; this
is arithmetic, not tax advice.
"""

from __future__ import annotations

import csv
import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

STORE = Path(__file__).resolve().parent.parent / "artifacts" / "portfolio.json"

STCG_RATE = 0.20        # equity, held under 12 months
LTCG_RATE = 0.125       # equity, held over 12 months
LTCG_EXEMPT = 125_000.0

# Positions that rise and fall together are one bet. Grouping by the story you
# bought rather than by the sector code is what makes the concentration obvious.
THEMES: dict[str, tuple[str, ...]] = {
    "Power / PSU / renewable": ("IREDA", "IRFC", "RPOWER", "RTNPOWER", "SUZLON",
                                "WAAREEENER", "URBANCO", "NTPC", "POWERGRID",
                                "TORNTPOWER", "ADANIGREEN", "COALINDIA"),
    "Recent IPOs": ("GLOTTIS", "E2E", "ORKLAINDIA", "BLUESTONE", "SHIPROCKET",
                    "BLEL", "KFINTECH"),
    "IT services": ("INFY", "TCS", "WIPRO", "HCLTECH", "TECHM"),
    "Banks / financials": ("KOTAKBANK", "JIOFIN", "HDFCBANK", "ICICIBANK",
                           "AXISBANK", "SBIN", "BAJFINANCE"),
    "Consumer": ("GODREJCP", "ITC", "HINDUNILVR", "NESTLEIND", "BRITANNIA"),
    "Energy / commodities": ("GAIL", "ONGC", "IOC", "RELIANCE"),
}


def theme_of(symbol: str) -> str:
    s = symbol.upper().replace(".NS", "").replace(".BO", "")
    for name, members in THEMES.items():
        if s in members:
            return name
    return "Other"


@dataclass
class Holding:
    symbol: str
    qty: int
    avg_price: float
    days_held: int | None = None     # None = assume short-term
    note: str = ""

    @property
    def invested(self) -> float:
        return self.qty * self.avg_price

    @property
    def is_long_term(self) -> bool:
        return bool(self.days_held and self.days_held >= 365)


@dataclass
class Position:
    holding: Holding
    price: float
    theme: str
    value: float
    pnl: float
    pnl_pct: float
    live: bool = True


@dataclass
class Portfolio:
    holdings: list[Holding] = field(default_factory=list)
    realised_gains: float = 0.0      # already booked this financial year

    # ------------------------------------------------------------------ #
    @classmethod
    def load(cls, path: Path | str | None = None) -> "Portfolio":
        p = Path(path or STORE)
        if not p.exists():
            return cls()
        raw = json.loads(p.read_text(encoding="utf-8"))
        return cls(holdings=[Holding(**h) for h in raw.get("holdings", [])],
                   realised_gains=float(raw.get("realised_gains", 0.0)))

    def save(self, path: Path | str | None = None) -> Path:
        p = Path(path or STORE)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(
            {"holdings": [asdict(h) for h in self.holdings],
             "realised_gains": self.realised_gains}, indent=2), encoding="utf-8")
        return p

    def import_csv(self, path: Path | str) -> int:
        """Columns: symbol, qty, avg_price[, days_held]."""
        added = 0
        with Path(path).open(newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                self.holdings.append(Holding(
                    symbol=row["symbol"].strip().upper(),
                    qty=int(float(row["qty"])),
                    avg_price=float(row["avg_price"]),
                    days_held=int(row["days_held"]) if row.get("days_held") else None,
                ))
                added += 1
        return added

    # ------------------------------------------------------------------ #
    def price_all(self) -> list[Position]:
        from .data import load_prices_live

        out = []
        for h in self.holdings:
            sym = h.symbol if "." in h.symbol else f"{h.symbol}.NS"
            price, live = 0.0, True
            try:
                price = float(load_prices_live(sym, start="2024-01-01",
                                               min_rows=20)["Close"].iloc[-1])
            except Exception as exc:
                log.info("%s: no price (%s)", h.symbol, exc)
                live = False
            value = h.qty * price
            pnl = value - h.invested
            out.append(Position(
                holding=h, price=price, theme=theme_of(h.symbol), value=value,
                pnl=pnl, pnl_pct=pnl / h.invested if h.invested else 0.0,
                live=live,
            ))
        return out


# --------------------------------------------------------------------------- #
# Tax-loss harvesting
# --------------------------------------------------------------------------- #
@dataclass
class HarvestPlan:
    realised_gains: float
    tax_before: float
    candidates: list[Position]
    selected: list[Position]
    loss_realised: float
    tax_after: float
    tax_saved: float
    carry_forward: float


def harvest(positions: list[Position], realised_gains: float,
            short_term: bool = True) -> HarvestPlan:
    """Pick losing positions to offset gains already booked this year.

    Losers are taken worst-first, and only until the gains are covered. Selling
    beyond that point saves no tax this year -- the excess merely carries
    forward, so there is no reason to let the tax tail wag a holding decision.
    """
    rate = STCG_RATE if short_term else LTCG_RATE
    taxable = max(0.0, realised_gains - (0.0 if short_term else LTCG_EXEMPT))
    tax_before = taxable * rate

    losers = sorted([p for p in positions if p.pnl < 0 and p.live and p.price > 0],
                    key=lambda p: p.pnl)

    selected: list[Position] = []
    booked = 0.0
    for p in losers:
        if booked >= realised_gains:
            break
        selected.append(p)
        booked += abs(p.pnl)

    offset = min(booked, realised_gains)
    taxable_after = max(0.0, realised_gains - offset
                        - (0.0 if short_term else LTCG_EXEMPT))
    tax_after = taxable_after * rate

    return HarvestPlan(
        realised_gains=realised_gains, tax_before=tax_before,
        candidates=losers, selected=selected, loss_realised=booked,
        tax_after=tax_after, tax_saved=tax_before - tax_after,
        carry_forward=max(0.0, booked - realised_gains),
    )


def print_portfolio(positions: list[Position]) -> None:
    money = lambda v: f"Rs.{v:,.0f}"                                  # noqa: E731
    bar = "=" * 72

    invested = sum(p.holding.invested for p in positions)
    value = sum(p.value for p in positions if p.live)
    pnl = value - sum(p.holding.invested for p in positions if p.live)

    print(f"\n{bar}")
    print(f" PORTFOLIO   {len(positions)} holdings")
    print(bar)
    print(f"  invested {money(invested)}   now {money(value)}   "
          f"P&L {money(pnl)} ({pnl / invested * 100:+.1f}%)")

    themes: dict[str, list[Position]] = {}
    for p in positions:
        themes.setdefault(p.theme, []).append(p)

    print("\n  WHERE YOUR MONEY ACTUALLY IS")
    for name, group in sorted(themes.items(),
                              key=lambda kv: -sum(x.holding.invested for x in kv[1])):
        inv = sum(x.holding.invested for x in group)
        gp = sum(x.pnl for x in group if x.live)
        share = inv / invested * 100 if invested else 0
        flag = "  <- one bet" if share >= 25 and len(group) > 2 else ""
        print(f"    {name:<26}{len(group):>3} stocks  {money(inv):>12}"
              f"  {share:>4.0f}%  {money(gp):>10}{flag}")

    print(f"\n  {'stock':<14}{'qty':>6}{'avg':>10}{'now':>10}"
          f"{'P&L':>12}{'%':>8}")
    print("  " + "-" * 62)
    for p in sorted(positions, key=lambda x: x.pnl):
        px = f"{p.price:,.2f}" if p.live else "-"
        print(f"  {p.holding.symbol:<14}{p.holding.qty:>6}"
              f"{p.holding.avg_price:>10,.2f}{px:>10}"
              f"{money(p.pnl):>12}{p.pnl_pct * 100:>7.1f}%")
    print(f"{bar}\n")


def print_harvest(plan: HarvestPlan, short_term: bool = True) -> None:
    money = lambda v: f"Rs.{v:,.0f}"                                  # noqa: E731
    bar = "=" * 72
    label = "short-term (20%)" if short_term else "long-term (12.5%)"

    print(f"\n{bar}")
    print(f" TAX-LOSS HARVESTING   gains booked this year: "
          f"{money(plan.realised_gains)}")
    print(bar)
    print(f"\n  Tax on those gains as things stand: {money(plan.tax_before)}  ({label})")

    if not plan.selected:
        print("\n  No losing positions available to offset them.\n")
        return

    print(f"\n  SELL THESE TO OFFSET (worst loss first, only as far as needed)")
    print(f"    {'stock':<14}{'qty':>6}{'loss booked':>14}{'running total':>16}")
    print("    " + "-" * 50)
    run = 0.0
    for p in plan.selected:
        run += abs(p.pnl)
        print(f"    {p.holding.symbol:<14}{p.holding.qty:>6}"
              f"{money(abs(p.pnl)):>14}{money(run):>16}")

    print(f"\n  losses realised   {money(plan.loss_realised)}")
    print(f"  tax after         {money(plan.tax_after)}")
    print(f"  TAX SAVED         {money(plan.tax_saved)}")
    if plan.carry_forward > 0:
        print(f"  carried forward   {money(plan.carry_forward)}  "
              f"(usable for up to 8 years)")

    print("\n  THINGS THAT MATTER")
    print("    - This only helps for positions you were willing to exit anyway.")
    print("      Selling a holding you believe in, to save tax, is a bad trade")
    print("      wearing an accountant's hat.")
    print("    - Buying the same stock straight back is fine in India (no")
    print("      wash-sale rule), but you re-pay brokerage and reset the")
    print("      holding period.")
    print("    - Losses must be booked before 31 March to count this year.")
    print(f"{bar}\n")
