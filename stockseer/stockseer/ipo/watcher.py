"""Listing-morning watcher: live tracking from the opening print to the exit.

The alert sequence, and why each step is where it is:

  1. ARM        ~5 min before listing. Heads-up, nothing to do yet.
  2. LISTED     first traded price. Reports it. **Not a buy signal** -- 53% of
                listings peak in their opening minute and fade, so acting here
                is buying the high half the time.
  3. BUY        only once it has held above the opening print for
                `confirm_minutes`. Carries the buy price, the stop, the target,
                the quantity your capital affords, and the rupee gain at target.
  4. NEARING    price is closing on the target, or on the stop. Fires *before*
                the level so there is time to act rather than read about it.
  5. EXIT       target hit, stop hit, trailing stop, or the session ending.

Every level is derived from the 38-listing study rather than round numbers:
average best gain before 11:00 was +3.35%, average worst dip -2.80%. Those two
numbers being so close is exactly why this is a coin flip, and the alerts say so.
"""

from __future__ import annotations

import logging
import time as _time
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from ..notify import hub
from .registry import IPO, listing_today

log = logging.getLogger(__name__)

BASE_RATE = ("Base rate: 50% win at 11:00 over 38 listings (t=1.02). "
             "53% peak in minute one and fade. This is a coin flip with a "
             "small positive tilt -- size it accordingly.")


@dataclass
class WatchConfig:
    capital: float = 40_000.0       # used to quote quantity and rupee amounts
    confirm_minutes: int = 5        # hold above the open this long before a buy alert
    target_pct: float = 0.035       # ~ the measured average best exit (+3.35%)
    stop_pct: float = 0.030         # just past the measured average dip (-2.80%)
    trail_arm_pct: float = 0.015    # profit at which the trailing stop wakes up
    trail_pct: float = 0.025        # give-back allowed from the high
    breakeven_buffer: float = 0.002  # floor for an armed trail; covers costs
    near_pct: float = 0.008         # warn this far from a level
    poll_seconds: int = 10          # live tracking cadence once a position is on
    idle_poll_seconds: int = 20     # before entry
    session_end: time = time(15, 15)
    listing_time: time = time(10, 0)   # when a mainboard IPO starts trading
    late_grace_minutes: int = 15       # past this, the open has been and gone


@dataclass
class Position:
    entry: float
    stop: float
    target: float
    qty: int
    opened_at: datetime
    peak: float = 0.0
    closed: bool = False
    warned_target: bool = False
    warned_stop: bool = False

    def gain(self, price: float) -> float:
        return price / self.entry - 1.0

    def rupees(self, price: float) -> float:
        return (price - self.entry) * self.qty


@dataclass
class WatchState:
    ipo: IPO
    opening_print: float | None = None
    opened_at: datetime | None = None
    position: Position | None = None
    history: list[tuple[datetime, float]] = field(default_factory=list)

    @property
    def live(self) -> bool:
        return self.position is not None and not self.position.closed


class ListingWatcher:
    """Watches one IPO from its opening print through to an exit."""

    def __init__(self, ipo: IPO, feed, config: WatchConfig | None = None):
        self.ipo = ipo
        self.feed = feed
        self.cfg = config or WatchConfig()
        self.state = WatchState(ipo=ipo)
        self._hub = hub()
        self._regime_cache: dict | None = None

    # ------------------------------------------------------------------ #
    def price(self) -> float | None:
        try:
            return float(self.feed.quote(self.ipo.yf_symbol).price)
        except Exception as exc:
            log.debug("%s: quote unavailable (%s)", self.ipo.symbol, exc)
            return None

    def _key(self, tag: str) -> str:
        return f"{tag}:{self.ipo.symbol}:{date.today().isoformat()}"

    def _regime(self) -> dict:
        """Market conditions at alert time, recorded for a future study.

        Cached per session: the listing sequence fires several alerts within
        an hour and the regime does not meaningfully move between them.
        """
        if self._regime_cache is None:
            from ..regime import as_payload

            self._regime_cache = as_payload()
        return self._regime_cache

    # ------------------------------------------------------------ 1. arm
    def arm(self, late: bool = False) -> None:
        i = self.ipo
        # Saying "lists shortly" at 14:20 is worse than saying nothing: it reads
        # as "you still have time" for an event that finished hours earlier.
        if late:
            title = f"{i.symbol} already listed - watch started late"
            body = (f"{i.company}\nIssue price Rs.{i.issue_price}\n"
                    f"The open was missed, so there is no entry signal coming. "
                    f"If you hold an allotment, check the price yourself and "
                    f"decide on exit.\n\n{BASE_RATE}")
        else:
            title = f"{i.symbol} lists shortly"
            body = (f"{i.company}\nIssue price Rs.{i.issue_price}\n"
                    f"Watching for the opening print. Keep Jarvis open for live "
                    f"tracking.\n\n{BASE_RATE}")
        self._hub.alert(
            kind="ipo_listing_soon", urgency="act",
            title=title, body=body,
            symbol=i.symbol, dedupe_key=self._key("arm"),
            issue_price=i.issue_price,
            regime=self._regime(),
        )

    # --------------------------------------------------------- 2. listed
    def _on_listed(self, price: float) -> None:
        st = self.state
        st.opening_print = price
        st.opened_at = datetime.now()

        gain = (price / self.ipo.issue_price - 1.0) if self.ipo.issue_price else None
        allot = (f"Allotment holders are up {gain * 100:+.1f}%.\n"
                 if gain is not None else "")
        self._hub.alert(
            kind="ipo_listed", urgency="act",
            title=f"{self.ipo.symbol} listed at Rs.{price:,.2f}",
            body=(f"{self.ipo.company}\n{allot}"
                  f"DO NOT BUY YET. Watching {self.cfg.confirm_minutes} min to see "
                  f"if it holds above Rs.{price:,.2f} -- more than half of "
                  f"listings peak right now and fall.\n\n"
                  f"You will get a separate alert with a buy price if it holds."),
            symbol=self.ipo.symbol, dedupe_key=self._key("listed"),
            opening_print=price, issue_price=self.ipo.issue_price,
            regime=self._regime(),
        )

    def _held_above_open(self, price: float) -> bool:
        st = self.state
        if st.opened_at is None or st.opening_print is None:
            return False
        if (datetime.now() - st.opened_at).total_seconds() < self.cfg.confirm_minutes * 60:
            return False
        window = [p for t, p in st.history
                  if (datetime.now() - t).total_seconds() <= self.cfg.confirm_minutes * 60]
        # Must be above the open now *and* never have broken meaningfully below
        # it during the window -- a dip and recovery is not "holding".
        return bool(window) and price > st.opening_print \
            and min(window) >= st.opening_print * 0.995

    # ------------------------------------------------------------ 3. buy
    def _on_buy(self, price: float) -> None:
        cfg = self.cfg
        qty = max(int(cfg.capital // price), 0)
        if qty == 0:
            log.warning("%s at Rs.%.2f exceeds capital Rs.%.0f",
                        self.ipo.symbol, price, cfg.capital)
            return

        target = price * (1 + cfg.target_pct)
        stop = price * (1 - cfg.stop_pct)
        pos = Position(entry=price, stop=stop, target=target, qty=qty,
                       opened_at=datetime.now(), peak=price)
        self.state.position = pos

        gain_rs = (target - price) * qty
        loss_rs = (price - stop) * qty
        self._hub.alert(
            kind="ipo_buy", urgency="critical",
            title=f"BUY {self.ipo.symbol} at Rs.{price:,.2f}",
            body=(f"Held above the Rs.{self.state.opening_print:,.2f} open for "
                  f"{cfg.confirm_minutes} min.\n\n"
                  f"BUY    Rs.{price:,.2f}   x {qty} sh  = Rs.{price * qty:,.0f}\n"
                  f"TARGET Rs.{target:,.2f}   +{cfg.target_pct * 100:.1f}%  "
                  f"= +Rs.{gain_rs:,.0f}\n"
                  f"STOP   Rs.{stop:,.2f}   -{cfg.stop_pct * 100:.1f}%  "
                  f"= -Rs.{loss_rs:,.0f}\n\n"
                  f"I will buzz before it reaches either. {BASE_RATE}"),
            symbol=self.ipo.symbol, dedupe_key=self._key("buy"),
            entry=price, target=target, stop=stop, qty=qty,
            target_rupees=gain_rs, stop_rupees=-loss_rs,
            regime=self._regime(),
        )

    # -------------------------------------------------------- 4. nearing
    def _check_warnings(self, price: float) -> None:
        pos, cfg = self.state.position, self.cfg
        if pos is None or pos.closed:
            return

        near_target = pos.target * (1 - cfg.near_pct)
        near_stop = pos.stop * (1 + cfg.near_pct)

        if not pos.warned_target and price >= near_target:
            pos.warned_target = True
            self._hub.alert(
                kind="ipo_near_target", urgency="critical",
                title=f"{self.ipo.symbol} nearing target - Rs.{price:,.2f}",
                body=(f"Almost at Rs.{pos.target:,.2f}.\n"
                      f"Unrealised: +Rs.{pos.rupees(price):,.0f} "
                      f"({pos.gain(price) * 100:+.2f}%)\n\n"
                      f"Get ready to sell. I will buzz again if it tags the "
                      f"target or falls back."),
                symbol=self.ipo.symbol, dedupe_key=self._key("near_target"),
                price=price, target=pos.target,
            )
        elif not pos.warned_stop and price <= near_stop:
            pos.warned_stop = True
            self._hub.alert(
                kind="ipo_near_stop", urgency="critical",
                title=f"{self.ipo.symbol} falling - Rs.{price:,.2f}",
                body=(f"Closing on the Rs.{pos.stop:,.2f} stop.\n"
                      f"Unrealised: Rs.{pos.rupees(price):,.0f} "
                      f"({pos.gain(price) * 100:+.2f}%)\n\n"
                      f"Decide now. If it tags the stop I will buzz to exit."),
                symbol=self.ipo.symbol, dedupe_key=self._key("near_stop"),
                price=price, stop=pos.stop,
            )

    # ----------------------------------------------------------- 5. exit
    def _exit(self, label: str, price: float, why: str) -> None:
        pos = self.state.position
        if pos is None:
            return
        pos.closed = True
        self._hub.alert(
            kind="ipo_exit", urgency="critical",
            title=f"{label}: SELL {self.ipo.symbol} at Rs.{price:,.2f}",
            body=(f"{why}\n\n"
                  f"Entry Rs.{pos.entry:,.2f} -> Rs.{price:,.2f}\n"
                  f"P&L   Rs.{pos.rupees(price):,.0f} "
                  f"({pos.gain(price) * 100:+.2f}%) on {pos.qty} shares"),
            symbol=self.ipo.symbol, dedupe_key=self._key(f"exit_{label}"),
            price=price, pnl=pos.rupees(price), gain=pos.gain(price),
        )

    # ------------------------------------------------------------- loop
    def on_tick(self, price: float) -> None:
        st, cfg = self.state, self.cfg
        st.history.append((datetime.now(), price))

        if st.opening_print is None:
            self._on_listed(price)
            return
        if st.position is None:
            if self._held_above_open(price):
                self._on_buy(price)
            return
        if not st.live:
            return

        pos = st.position
        pos.peak = max(pos.peak, price)
        self._check_warnings(price)

        if price >= pos.target:
            self._exit("TARGET HIT", price,
                       f"Reached Rs.{pos.target:,.2f}. Book it.")
        elif price <= pos.stop:
            self._exit("STOP HIT", price,
                       f"Broke Rs.{pos.stop:,.2f}. Exit -- this is the "
                       f"-20% circuit tail the strategy has to respect.")
        # Arms on any real profit, not on the target -- a target hit exits above,
        # so gating the trail on the target would make it unreachable and let a
        # +3% winner slide all the way back to the stop.
        #
        # Floored at breakeven-plus-costs: once you have been up 1.5%, a plain
        # 2.5% give-back would still hand you a loss, which is the exact outcome
        # a trailing stop exists to prevent.
        elif pos.peak >= pos.entry * (1 + cfg.trail_arm_pct):
            trail_at = max(pos.peak * (1 - cfg.trail_pct),
                           pos.entry * (1 + cfg.breakeven_buffer))
            if price <= trail_at:
                self._exit("TRAILING STOP", price,
                           f"Was up to Rs.{pos.peak:,.2f}, now back to "
                           f"Rs.{trail_at:,.2f}. Take the gain rather than "
                           f"riding it down to the stop.")

    def session_over(self) -> None:
        if self.state.live and self.state.history:
            self._exit("SESSION CLOSING", self.state.history[-1][1],
                       "Square off before the close if this was intraday.")

    def line(self, price: float) -> str:
        st = self.state
        if st.opening_print is None:
            return "waiting for the opening print"
        if st.position is None:
            held = (datetime.now() - st.opened_at).total_seconds() / 60
            return f"open {st.opening_print:,.2f}, {held:.0f}m - watching"
        p = st.position
        state = "CLOSED" if p.closed else "LIVE"
        return (f"{state} in @ {p.entry:,.2f}  now {price:,.2f}  "
                f"{p.gain(price) * 100:+.2f}%  Rs.{p.rupees(price):,.0f}  "
                f"[stop {p.stop:,.2f} / tgt {p.target:,.2f}]")


def run(symbols: list[str] | None = None, feed=None, config: WatchConfig | None = None,
        once: bool = False) -> None:
    """Watch every IPO listing today (or the given symbols)."""
    from ..live.feed import get_feed
    from .registry import find

    cfg = config or WatchConfig()
    feed = feed or get_feed()

    ipos = listing_today()
    if symbols:
        picked = [find(s.strip()) for s in symbols]
        ipos = [i for i in picked if i] or ipos
    if not ipos:
        print(" No IPO lists today, and no --symbols given.")
        print(" `stockseer ipo calendar` shows what is coming up.")
        return

    watchers = [ListingWatcher(i, feed, cfg) for i in ipos]
    print(f"\n Watching {len(watchers)}: {', '.join(w.ipo.symbol for w in watchers)}")
    print(f" feed {feed.describe()} | capital Rs.{cfg.capital:,.0f}")
    print(f" target +{cfg.target_pct * 100:.1f}%  stop -{cfg.stop_pct * 100:.1f}%  "
          f"warn {cfg.near_pct * 100:.1f}% early\n")

    # Two conditions that make the whole session worthless, and both used to
    # pass in silence. A run that begins after the open still announced "lists
    # shortly" and a run on delayed prices looked identical to a live one.
    now = datetime.now()
    deadline = (datetime.combine(now.date(), cfg.listing_time)
                + timedelta(minutes=cfg.late_grace_minutes))
    late = now > deadline
    delayed = getattr(feed, "delayed_seconds", 0) > 60

    if late or delayed:
        problems = []
        if late:
            problems.append(
                f"This watcher started at {now:%H:%M}, after the "
                f"{cfg.listing_time:%H:%M} open. The opening print and the "
                f"first minutes of trading were missed.")
        if delayed:
            problems.append(
                f"Prices come from {feed.describe()}, not a live feed. "
                f"Do not trade the numbers in these alerts.")
        hub().alert(
            kind="ipo_listing_soon", urgency="act",
            title=f"Listing watch degraded: {', '.join(w.ipo.symbol for w in watchers)}",
            body="\n\n".join(problems) + "\n\nCheck your broker directly.",
            dedupe_key=f"watch_degraded:{now.date().isoformat()}",
        )
        print(f" WARNING: degraded session -- {' '.join(problems)}\n")

    for w in watchers:
        w.arm(late=late)

    while True:
        now = datetime.now()
        any_live = False
        for w in watchers:
            price = w.price()
            if price is None:
                continue
            w.on_tick(price)
            any_live = any_live or w.state.live
            print(f" [{now:%H:%M:%S}] {w.ipo.symbol:<12}{price:>10,.2f}  {w.line(price)}")

        if now.time() >= cfg.session_end:
            for w in watchers:
                w.session_over()
            print(" session over.")
            return
        if once:
            return
        # Tighten the loop once real money is on the line.
        _time.sleep(cfg.poll_seconds if any_live else cfg.idle_poll_seconds)
