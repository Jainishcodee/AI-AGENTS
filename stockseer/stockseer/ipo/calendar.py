"""IPO application calendar -- never miss the window that actually pays.

The listing-morning study found a coin flip. The allotment study found
**+13.5% mean, +7.3% median, positive 69% of the time** on mainboard issues.
The edge is in *applying*, and the only way to lose it is to forget.

So this is the higher-value half of the IPO tooling, and it is also the easier
half: the dates are published in advance by NSE, so nothing has to be predicted.

Alerts fired per issue:
  - opens today          (info)     -- the window is open
  - closes tomorrow      (act)      -- last full day to decide
  - CLOSES TODAY         (critical) -- apply before the cut-off or lose the chance
  - lists tomorrow       (info)     -- so the listing watcher can arm
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta

from ..notify import hub
from .registry import IPO, past_issues, upcoming_issues

log = logging.getLogger(__name__)

# UPI mandate cut-off on the closing day. Applications after this are rejected
# by the exchange, so "closes today" needs to fire in the morning, not at 5pm.
CUTOFF_TEXT = "UPI mandate cut-off is usually 5:00 PM on the closing day"


@dataclass
class CalendarEvent:
    ipo: IPO
    kind: str
    urgency: str
    days_away: int


def _all_known(refresh: bool = False) -> list[IPO]:
    """Upcoming issues plus recently-priced ones, de-duplicated by symbol.

    Neither endpoint alone is complete: `upcoming` drops an issue once bidding
    closes, while `past_issues` carries it with its listing date. Merging keeps
    an IPO visible from announcement through listing.
    """
    seen: dict[str, IPO] = {}
    for ipo in upcoming_issues(refresh) + past_issues(refresh):
        seen.setdefault(ipo.symbol, ipo)
    return list(seen.values())


def scan(today: date | None = None, refresh: bool = False,
         mainboard_only: bool = False) -> list[CalendarEvent]:
    """Everything worth a notification today."""
    today = today or date.today()
    events: list[CalendarEvent] = []

    for ipo in _all_known(refresh):
        if mainboard_only and ipo.is_sme:
            continue
        start = date.fromisoformat(ipo.ipo_start) if ipo.ipo_start else None
        end = date.fromisoformat(ipo.ipo_end) if ipo.ipo_end else None
        listing = ipo.listing_day()

        if end == today:
            events.append(CalendarEvent(ipo, "closes_today", "critical", 0))
        elif end == today + timedelta(days=1):
            events.append(CalendarEvent(ipo, "closes_tomorrow", "act", 1))
        elif start == today:
            events.append(CalendarEvent(ipo, "opens_today", "info", 0))
        elif start and today < start <= today + timedelta(days=2):
            events.append(CalendarEvent(ipo, "opens_soon", "info",
                                        (start - today).days))

        if listing == today + timedelta(days=1):
            events.append(CalendarEvent(ipo, "lists_tomorrow", "info", 1))

    order = {"critical": 0, "act": 1, "info": 2}
    events.sort(key=lambda e: (order[e.urgency], e.ipo.symbol))
    return events


def _message(ev: CalendarEvent) -> tuple[str, str]:
    ipo, i = ev, ev.ipo
    band = i.price_range or (f"Rs.{i.issue_price}" if i.issue_price else "price TBA")
    tag = "SME" if i.is_sme else "Mainboard"

    if ev.kind == "closes_today":
        return (f"LAST DAY: {i.symbol}",
                f"{i.company}\n{tag} · {band}\n"
                f"Bidding closes TODAY. {CUTOFF_TEXT}.\n"
                f"Historically mainboard allotments list +13.5% on average "
                f"(median +7.3%, positive 69% of the time).")
    if ev.kind == "closes_tomorrow":
        return (f"Closes tomorrow: {i.symbol}",
                f"{i.company}\n{tag} · {band}\n"
                f"Last full day to apply is tomorrow ({i.ipo_end}).")
    if ev.kind == "opens_today":
        return (f"IPO open: {i.symbol}",
                f"{i.company}\n{tag} · {band}\n"
                f"Bidding is open now, closes {i.ipo_end}.")
    if ev.kind == "opens_soon":
        return (f"Opens in {ev.days_away}d: {i.symbol}",
                f"{i.company}\n{tag} · {band}\nBidding opens {i.ipo_start}.")
    if ev.kind == "lists_tomorrow":
        return (f"Lists tomorrow: {i.symbol}",
                f"{i.company}\n{tag} · issue Rs.{i.issue_price}\n"
                f"Listing {i.listing_date}. The watcher will arm at 09:55.\n"
                f"Note: buying at the listing open is a coin flip "
                f"(50% win rate, n=38) -- the edge was in the allotment.")
    return (f"{i.symbol}", i.company)


def notify_today(today: date | None = None, refresh: bool = True,
                 mainboard_only: bool = False) -> list:
    """Scan and push notifications. Safe to run repeatedly -- deduped per day."""
    today = today or date.today()
    events = scan(today, refresh, mainboard_only)
    pushed = []
    for ev in events:
        title, body = _message(ev)
        n = hub().alert(
            kind=f"ipo_{ev.kind}", urgency=ev.urgency, title=title, body=body,
            symbol=ev.ipo.symbol,
            dedupe_key=f"{ev.kind}:{ev.ipo.symbol}:{today.isoformat()}",
            company=ev.ipo.company, price_range=ev.ipo.price_range,
            is_sme=ev.ipo.is_sme, issue_price=ev.ipo.issue_price,
            ipo_end=ev.ipo.ipo_end, listing_date=ev.ipo.listing_date,
        )
        if n:
            pushed.append(n)
    return pushed


def print_calendar(today: date | None = None, refresh: bool = False,
                   mainboard_only: bool = False) -> None:
    today = today or date.today()
    events = scan(today, refresh, mainboard_only)
    bar = "=" * 74

    print(f"\n{bar}")
    print(f" IPO CALENDAR  --  {today.isoformat()}")
    print(bar)
    if not events:
        print("\n Nothing opening, closing, or listing in the next couple of days.\n")
        return

    marks = {"critical": "!!", "act": " !", "info": "  "}
    for ev in events:
        i = ev.ipo
        band = i.price_range or (f"Rs.{i.issue_price}" if i.issue_price else "TBA")
        label = ev.kind.replace("_", " ")
        print(f"\n {marks[ev.urgency]} {i.symbol:<14}{label:<18}"
              f"{'SME' if i.is_sme else 'MAIN':<6}{band}")
        print(f"      {i.company[:60]}")
        if ev.kind == "closes_today":
            print(f"      -> apply today. {CUTOFF_TEXT}.")
        elif i.ipo_end:
            print(f"      -> bidding {i.ipo_start} to {i.ipo_end}")

    print(f"\n{bar}")
    print(" Allotment is the edge: mainboard issue->listing averaged +13.5%,")
    print(" median +7.3%, positive 69% of the time across 176 IPOs.")
    print(bar + "\n")
