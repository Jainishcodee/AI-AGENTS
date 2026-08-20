"""Price alerts: tell me when this gets cheap enough to buy.

Deliberately dumb. There is no prediction here and no attempt at one -- you
name a level, and it tells you when the market reaches it. Everything measured
in this project says the direction cannot be forecast, so the honest tool is
one that watches a level you chose rather than inventing one for you.

Three ways to say "low", because people mean different things by it:

  --below 200        an absolute price
  --drop 10          10% below its recent high
  --under-avg 5      5% below its 50-day average

A watch fires once, then disarms. A level that re-alerts every day it is
breached is how you learn to ignore the alert that mattered.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path

log = logging.getLogger(__name__)

STORE = Path(__file__).resolve().parent.parent / "artifacts" / "watchlist.json"


@dataclass
class Watch:
    ticker: str
    kind: str                       # "below" | "drop" | "under_avg"
    value: float
    note: str = ""
    created: str = ""
    triggered_on: str | None = None
    last_price: float | None = None
    id: str = ""

    def __post_init__(self):
        self.created = self.created or date.today().isoformat()
        self.id = self.id or f"{self.ticker.replace('.NS', '')}-{self.kind}-{self.value:g}"

    @property
    def armed(self) -> bool:
        return self.triggered_on is None

    def describe(self) -> str:
        if self.kind == "below":
            return f"below Rs.{self.value:,.2f}"
        if self.kind == "drop":
            return f"{self.value:g}% below its recent high"
        return f"{self.value:g}% below its 50-day average"


@dataclass
class Trigger:
    watch: Watch
    price: float
    level: float
    context: str = ""
    extra: dict = field(default_factory=dict)


class Watchlist:
    def __init__(self, path: Path | str | None = None):
        self.path = Path(path or STORE)
        self.items: list[Watch] = []
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            self.items = [Watch(**w) for w in
                          json.loads(self.path.read_text(encoding="utf-8"))]
        except (json.JSONDecodeError, TypeError) as exc:
            log.warning("watchlist unreadable (%s); starting empty", exc)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps([asdict(w) for w in self.items], indent=2), encoding="utf-8")

    def add(self, ticker: str, kind: str, value: float, note: str = "") -> Watch:
        w = Watch(ticker=ticker.upper(), kind=kind, value=value, note=note)
        self.items = [x for x in self.items if x.id != w.id]     # replace, not stack
        self.items.append(w)
        self.save()
        return w

    def remove(self, watch_id: str) -> bool:
        before = len(self.items)
        self.items = [w for w in self.items if w.id != watch_id]
        self.save()
        return len(self.items) < before

    def rearm(self, watch_id: str) -> bool:
        for w in self.items:
            if w.id == watch_id:
                w.triggered_on = None
                self.save()
                return True
        return False

    # ------------------------------------------------------------------ #
    def check(self, fire: bool = True) -> list[Trigger]:
        """Price every armed watch and return the ones that have hit."""
        from .data import load_prices_live

        hits: list[Trigger] = []
        for w in self.items:
            if not w.armed:
                continue
            try:
                px = load_prices_live(w.ticker, start="2023-01-01", min_rows=60)
            except Exception as exc:
                log.warning("%s: %s", w.ticker, exc)
                continue

            c = px["Close"]
            price = float(c.iloc[-1])
            w.last_price = price

            if w.kind == "below":
                level = w.value
                ctx = ""
            elif w.kind == "drop":
                high = float(c.tail(252).max())
                level = high * (1 - w.value / 100.0)
                ctx = f"52-week high Rs.{high:,.2f}"
            else:
                avg = float(c.rolling(50).mean().iloc[-1])
                level = avg * (1 - w.value / 100.0)
                ctx = f"50-day average Rs.{avg:,.2f}"

            if price <= level:
                hits.append(Trigger(w, price, level, ctx,
                                    {"from_high": float(price / c.tail(252).max() - 1)}))
                if fire:
                    w.triggered_on = datetime.now().astimezone().isoformat(
                        timespec="seconds")

        self.save()
        return hits


def notify(triggers: list[Trigger]) -> list:
    """Push each hit once. Silence when nothing has reached its level."""
    from .notify import hub

    pushed = []
    for t in triggers:
        w = t.watch
        name = w.ticker.replace(".NS", "")
        extra = f"\n{t.context}" if t.context else ""
        note = f"\n{w.note}" if w.note else ""
        n = hub().alert(
            kind="price_target", urgency="act",
            title=f"{name} hit Rs.{t.price:,.2f}",
            body=(f"Your level: {w.describe()} (Rs.{t.level:,.2f}){extra}\n"
                  f"Now {t.extra.get('from_high', 0) * 100:+.1f}% from its "
                  f"52-week high.{note}\n\n"
                  f"This is the price you asked to be told about. It is not a "
                  f"signal that it will rise."),
            symbol=w.ticker,
            dedupe_key=f"watch:{w.id}:{date.today().isoformat()}",
            price=t.price, level=t.level,
        )
        if n:
            pushed.append(n)
    return pushed
