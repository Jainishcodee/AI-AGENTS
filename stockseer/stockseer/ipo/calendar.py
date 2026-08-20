"""IPO application alerts -- one per issue, on its closing day.

Deliberately narrow. Earlier versions also announced openings and "closes
tomorrow", which meant three or four buzzes per issue for a decision you make
once. An alert stream you skim is an alert stream that fails on the day it
matters, so everything except the closing day was removed.

**Why the closing day is the right day.** Allotment in the retail category is a
computerised lottery: every valid application is one entry regardless of when it
was submitted, so applying early buys you nothing. Applying on the last day buys
you information -- by then NSE has published how many times the book is covered,
so you decide with real demand figures in front of you. The only cost is
congestion risk near the UPI mandate cut-off, which is why the alert fires in
the morning rather than at 4pm.

**SME issues are excluded by default.** Their minimum application runs to roughly
a lakh, so they are not reachable on a small account, and an alert you cannot act
on is noise.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date

from ..notify import hub
from .registry import IPO, Subscription, past_issues, subscription, upcoming_issues

log = logging.getLogger(__name__)

CUTOFF_NOTE = "Apply before the 5 PM UPI mandate cut-off."


@dataclass
class CalendarEvent:
    ipo: IPO
    kind: str            # "closes_today"
    urgency: str
    subs: Subscription | None = None


def _all_known(refresh: bool = False) -> list[IPO]:
    """Open issues plus recently-priced ones, de-duplicated by symbol.

    Neither endpoint alone is complete: `upcoming` drops an issue once bidding
    closes, while `past_issues` carries it with its listing date.
    """
    seen: dict[str, IPO] = {}
    for ipo in upcoming_issues(refresh) + past_issues(refresh):
        seen.setdefault(ipo.symbol, ipo)
    return list(seen.values())


def scan(today: date | None = None, refresh: bool = False,
         include_sme: bool = False, with_subs: bool = True) -> list[CalendarEvent]:
    """Issues whose bidding closes today."""
    today = today or date.today()
    events: list[CalendarEvent] = []

    for ipo in _all_known(refresh):
        if ipo.is_sme and not include_sme:
            continue
        if not ipo.ipo_end or date.fromisoformat(ipo.ipo_end) != today:
            continue
        subs = subscription(ipo.symbol) if with_subs else None
        events.append(CalendarEvent(ipo, "closes_today", "critical", subs))

    events.sort(key=lambda e: e.ipo.symbol)
    return events


def _message(ev: CalendarEvent) -> tuple[str, str]:
    """Short by design: name, price, demand, deadline. Nothing else."""
    i = ev.ipo
    band = i.price_range or (f"Rs.{i.issue_price}" if i.issue_price else "price TBA")

    lines = [i.company, band]
    if ev.subs:
        lines.append(ev.subs.summary)
    lines.append(CUTOFF_NOTE)
    return f"LAST DAY: {i.symbol}", "\n".join(lines)


def notify_today(today: date | None = None, refresh: bool = True,
                 include_sme: bool = False) -> list:
    """Scan and queue alerts. Safe to run repeatedly -- deduped per day."""
    today = today or date.today()
    pushed = []
    for ev in scan(today, refresh, include_sme):
        title, body = _message(ev)
        n = hub().alert(
            kind="ipo_closes_today", urgency=ev.urgency, title=title, body=body,
            symbol=ev.ipo.symbol,
            dedupe_key=f"closes_today:{ev.ipo.symbol}:{today.isoformat()}",
            company=ev.ipo.company, price_range=ev.ipo.price_range,
            issue_price=ev.ipo.issue_price, ipo_end=ev.ipo.ipo_end,
            retail_x=ev.subs.retail_x if ev.subs else None,
            qib_x=ev.subs.qib_x if ev.subs else None,
            nii_x=ev.subs.nii_x if ev.subs else None,
        )
        if n:
            pushed.append(n)
    return pushed


def print_calendar(today: date | None = None, refresh: bool = False,
                   include_sme: bool = False) -> None:
    today = today or date.today()
    events = scan(today, refresh, include_sme)
    bar = "=" * 68

    print(f"\n{bar}")
    print(f" CLOSING TODAY  --  {today.isoformat()}")
    print(bar)

    if not events:
        print("\n No IPO closes today. Nothing to apply for.\n")
        return

    for ev in events:
        i = ev.ipo
        band = i.price_range or (f"Rs.{i.issue_price}" if i.issue_price else "TBA")
        print(f"\n  {i.symbol:<14}{band}")
        print(f"    {i.company[:56]}")
        if ev.subs:
            print(f"    {ev.subs.summary}")
            if ev.subs.updated:
                print(f"    {ev.subs.updated}")
        print(f"    {CUTOFF_NOTE}")

    print(f"\n{bar}\n")
