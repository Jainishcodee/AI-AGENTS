"""Listing-morning watcher.

Designed around what the 38-listing study actually found, not around the story:

* **53% of listings peak in their opening minute and fade.** So there is no
  "buy at 10:00" alert. The watcher reports the opening print, then waits for
  the stock to *prove* it is holding above it before suggesting an entry.
* **11:00 is not special** -- the drift kept growing until the close. So there
  is no forced 11:00 exit; a trailing stop rides whatever drift shows up.
* **The tail is -20%** (lower circuit). So the stop is mandatory, not optional.
* **The whole thing is a coin flip** (50% win rate, t = 1.02). Every alert
  carries that number, so the decision is made with it in view.

Mainboard IPOs open at 10:00 IST after a special pre-open auction; SME issues
start with the normal 09:15 session.
"""

from __future__ import annotations

import logging
import time as _time
from dataclasses import dataclass, field
from datetime import date, datetime, time

from ..notify import hub
from .registry import IPO, listing_today

log = logging.getLogger(__name__)

BASE_RATE = ("Listing-day base rate: 50% win at 11:00, t=1.02 over 38 listings. "
             "53% of listings peak in their first minute and fade.")


@dataclass
class WatchConfig:
    confirm_minutes: int = 5        # how long it must hold above open to confirm
    stop_pct: float = 0.04          # hard stop below entry
    trail_pct: float = 0.03         # trail once in profit
    take_profit_pct: float = 0.08   # bank a spike this big outright
    poll_seconds: int = 20
    arm_before_minutes: int = 5     # pre-listing heads-up
    session_end: time = time(15, 15)


@dataclass
class WatchState:
    ipo: IPO
    opening_print: float | None = None
    opened_at: datetime | None = None
    entry: float | None = None
    peak: float | None = None
    stopped: bool = False
    booked: bool = False
    history: list[tuple[datetime, float]] = field(default_factory=list)

    @property
    def armed(self) -> bool:
        return self.entry is not None and not (self.stopped or self.booked)


class ListingWatcher:
    """Watches one IPO through its listing session."""

    def __init__(self, ipo: IPO, feed, config: WatchConfig | None = None):
        self.ipo = ipo
        self.feed = feed
        self.cfg = config or WatchConfig()
        self.state = WatchState(ipo=ipo)
        self._hub = hub()

    # ------------------------------------------------------------------ #
    def _price(self) -> float | None:
        try:
            return float(self.feed.quote(self.ipo.yf_symbol).price)
        except Exception as exc:
            log.debug("%s: quote unavailable (%s)", self.ipo.symbol, exc)
            return None

    def arm(self) -> None:
        i = self.ipo
        self._hub.alert(
            kind="ipo_listing_soon", urgency="act",
            title=f"{i.symbol} lists shortly",
            body=(f"{i.company}\nIssue price Rs.{i.issue_price}\n"
                  f"Watching for the opening print.\n\n{BASE_RATE}"),
            symbol=i.symbol,
            dedupe_key=f"arm:{i.symbol}:{date.today().isoformat()}",
            issue_price=i.issue_price,
        )

    def on_open(self, price: float) -> None:
        """First traded price seen. Reports, does not recommend."""
        st = self.state
        st.opening_print = price
        st.opened_at = datetime.now()
        st.peak = price

        gain = (price / self.ipo.issue_price - 1.0) if self.ipo.issue_price else None
        allot = (f"Allotment holders are up {gain * 100:+.1f}% on this print.\n"
                 if gain is not None else "")
        self._hub.alert(
            kind="ipo_listed", urgency="act",
            title=f"{self.ipo.symbol} listed at Rs.{price:,.2f}",
            body=(f"{self.ipo.company}\n{allot}"
                  f"NOT a buy signal yet. Waiting {self.cfg.confirm_minutes} min to see "
                  f"if it holds above the open -- 53% of listings peak in the "
                  f"first minute and fade.\n\n{BASE_RATE}"),
            symbol=self.ipo.symbol,
            dedupe_key=f"listed:{self.ipo.symbol}:{date.today().isoformat()}",
            opening_print=price, issue_price=self.ipo.issue_price,
        )

    def _confirm(self, price: float) -> bool:
        """Has it held above the opening print for the confirmation window?"""
        st = self.state
        if st.opened_at is None or st.opening_print is None:
            return False
        elapsed = (datetime.now() - st.opened_at).total_seconds() / 60.0
        if elapsed < self.cfg.confirm_minutes:
            return False
        recent = [p for t, p in st.history
                  if (datetime.now() - t).total_seconds() <= self.cfg.confirm_minutes * 60]
        return bool(recent) and price > st.opening_print and min(recent) > st.opening_print * 0.995

    def on_confirmed(self, price: float) -> None:
        st = self.state
        st.entry = price
        st.peak = price
        stop = price * (1 - self.cfg.stop_pct)
        self._hub.alert(
            kind="ipo_entry", urgency="critical",
            title=f"{self.ipo.symbol} holding above open - entry window",
            body=(f"Price Rs.{price:,.2f}, held above the Rs.{st.opening_print:,.2f} "
                  f"open for {self.cfg.confirm_minutes} min.\n"
                  f"If you take it: stop Rs.{stop:,.2f} (-{self.cfg.stop_pct * 100:.0f}%), "
                  f"then a {self.cfg.trail_pct * 100:.0f}% trailing stop.\n"
                  f"No fixed 11:00 exit -- the drift kept growing to the close.\n\n"
                  f"{BASE_RATE}"),
            symbol=self.ipo.symbol,
            dedupe_key=f"entry:{self.ipo.symbol}:{date.today().isoformat()}",
            price=price, stop=stop,
        )

    def on_tick(self, price: float) -> None:
        st = self.state
        st.history.append((datetime.now(), price))

        if st.opening_print is None:
            self.on_open(price)
            return
        if st.entry is None:
            if self._confirm(price):
                self.on_confirmed(price)
            return
        if not st.armed:
            return

        st.peak = max(st.peak or price, price)
        gain = price / st.entry - 1.0
        hard_stop = st.entry * (1 - self.cfg.stop_pct)
        trail_stop = st.peak * (1 - self.cfg.trail_pct)

        if gain >= self.cfg.take_profit_pct:
            st.booked = True
            self._fire_exit("TAKE PROFIT", price, gain,
                            f"Up {gain * 100:+.1f}% -- bank it.")
        elif price <= hard_stop:
            st.stopped = True
            self._fire_exit("STOP HIT", price, gain,
                            f"Below the Rs.{hard_stop:,.2f} stop. Exit now.")
        elif st.peak > st.entry and price <= trail_stop:
            st.stopped = True
            self._fire_exit("TRAILING STOP", price, gain,
                            f"Off the Rs.{st.peak:,.2f} high by "
                            f"{self.cfg.trail_pct * 100:.0f}%. Take what is left.")

    def _fire_exit(self, label: str, price: float, gain: float, why: str) -> None:
        self._hub.alert(
            kind="ipo_exit", urgency="critical",
            title=f"{label}: {self.ipo.symbol} at Rs.{price:,.2f}",
            body=f"{why}\nP&L from entry: {gain * 100:+.2f}%",
            symbol=self.ipo.symbol,
            dedupe_key=f"exit:{self.ipo.symbol}:{date.today().isoformat()}",
            price=price, gain=gain,
        )

    def session_over(self) -> None:
        st = self.state
        if st.armed and st.entry:
            price = st.history[-1][1] if st.history else st.entry
            self._fire_exit("SESSION CLOSING", price, price / st.entry - 1.0,
                            "Square off before the close if this was intraday.")


def run(symbols: list[str] | None = None, feed=None, config: WatchConfig | None = None,
        once: bool = False) -> None:
    """Watch every IPO listing today (or the given symbols)."""
    from ..live.feed import get_feed

    cfg = config or WatchConfig()
    feed = feed or get_feed()

    ipos = listing_today()
    if symbols:
        wanted = {s.upper().replace(".NS", "") for s in symbols}
        from .registry import find
        ipos = [i for i in (find(s) for s in wanted) if i] or ipos

    if not ipos:
        print(" No IPO lists today. Nothing to watch.")
        print(" (The calendar command shows what is coming up.)")
        return

    watchers = [ListingWatcher(i, feed, cfg) for i in ipos]
    print(f"\n Watching {len(watchers)} listing(s): "
          f"{', '.join(w.ipo.symbol for w in watchers)}")
    print(f" feed: {feed.describe()}")
    print(f" stop {cfg.stop_pct * 100:.0f}%  trail {cfg.trail_pct * 100:.0f}%  "
          f"take-profit {cfg.take_profit_pct * 100:.0f}%\n")
    for w in watchers:
        w.arm()

    while True:
        now = datetime.now()
        for w in watchers:
            price = w._price()
            if price is None:
                continue
            w.on_tick(price)
            st = w.state
            tag = ("waiting" if st.entry is None else
                   "done" if not st.armed else
                   f"in @ {st.entry:,.2f}, now {price:,.2f} "
                   f"({price / st.entry - 1:+.2%})")
            print(f" [{now:%H:%M:%S}] {w.ipo.symbol:<12} {price:>10,.2f}  {tag}")

        if now.time() >= cfg.session_end:
            for w in watchers:
                w.session_over()
            print(" session over.")
            return
        if once:
            return
        _time.sleep(cfg.poll_seconds)
