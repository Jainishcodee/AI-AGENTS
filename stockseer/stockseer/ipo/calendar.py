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
from .registry import (IPO, Subscription, issue_terms, past_issues,
                       subscription, upcoming_issues)

log = logging.getLogger(__name__)

CUTOFF_NOTE = "Apply before the 5 PM UPI mandate cut-off."


@dataclass
class CalendarEvent:
    ipo: IPO
    kind: str            # "closes_today"
    urgency: str
    subs: Subscription | None = None
    terms: object | None = None      # IssueTerms: bid lot, cut-off


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
        # Allow-list rather than "not SME": the security-type field carries 28
        # values, and bonds, NCDs and InvITs are not IPOs you can apply to.
        if not include_sme and not ipo.is_mainboard:
            continue
        if not ipo.ipo_end or date.fromisoformat(ipo.ipo_end) != today:
            continue
        subs = subscription(ipo.symbol) if with_subs else None
        terms = issue_terms(ipo.symbol) if with_subs else None
        events.append(
            CalendarEvent(ipo, "closes_today", "critical", subs, terms))

    events.sort(key=lambda e: e.ipo.symbol)
    return events


# Kept as a last-resort default only. The live figure comes from
# study.load_base_rate(), which the study writes after each run -- a literal
# here went stale the moment new issues listed, and for months the alert quoted
# +7.3% of 176 while the measured numbers had moved to +9.1% of 150.
MEDIAN_LISTING_GAIN = 0.0914


def _message(ev: CalendarEvent) -> tuple[str, str]:
    """Plain words only. The reader has minutes and a phone screen.

    Leads with the odds rather than the subscription multiple, because "1 in
    19" is the number you decide on and "18.7x" is the number you would have
    to convert first.
    """
    i = ev.ipo
    band = i.price_range or (f"Rs.{i.issue_price}" if i.issue_price else "price TBA")

    lines = [i.company, band]
    t = ev.terms
    if t is not None and getattr(t, "lot_amount", None):
        lines.append(f"1 lot = {t.lot_shares} shares = about "
                     f"Rs.{t.lot_amount:,.0f}")
    lines.append("")

    if ev.subs and ev.subs.retail_x is not None:
        lines.append(f"Filled {ev.subs.retail_x:.1f}x by retail")
        lines.append(f"Your chance: {ev.subs.odds_text}")
        # QIB and NII have their own reserved pools and change nothing for a
        # retail applicant, so they appear as context, not as a headline.
        big = []
        if ev.subs.qib_x is not None:
            big.append(f"institutions {ev.subs.qib_x:.1f}x")
        if ev.subs.nii_x is not None:
            big.append(f"wealthy investors {ev.subs.nii_x:.1f}x")
        if big:
            lines.append("Demand elsewhere: " + ", ".join(big))
    else:
        lines.append("Subscription figures not published yet.")

    # What the application is actually worth, which is the base rate multiplied
    # by the odds sitting two lines above it. Quoting the base rate alone
    # overstates a heavily-subscribed issue by more than a hundredfold.
    from .apply import describe, evaluate
    from .study import load_base_rate

    rate = load_base_rate()
    app = evaluate(ev.subs, ev.terms, rate["median"])
    if app is not None:
        econ = describe(app)
        if econ:
            lines.append("")
            lines.extend(econ)

    lines.append("")
    lines.append(f"If allotted, past IPOs listed "
                 f"{rate['median'] * 100:+.1f}% (median of {rate['n']}).")
    cutoff = getattr(ev.terms, "cutoff", "") if ev.terms else ""
    lines.append(f"Apply before {cutoff} today." if cutoff else CUTOFF_NOTE)
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
            print(f"    chance of allotment: {ev.subs.odds_text}")
            if ev.subs.updated:
                print(f"    {ev.subs.updated}")
        print(f"    {CUTOFF_NOTE}")

    print(f"\n{bar}\n")


def heartbeat(today: date | None = None, weekday: int = 0,
              force: bool = False, include_sme: bool = False):
    """Weekly "still watching" digest, so silence is never ambiguous.

    A quiet alert stream has two possible meanings -- nothing was due, or the
    job died -- and from the phone they look identical. That ambiguity is how
    Friday passed without anyone noticing whether the pipeline had run.

    Emitted on one weekday only (Monday by default). Stateless on purpose:
    GitHub runners keep nothing between runs, so "days since the last alert"
    cannot be tracked there, while "is it Monday" always works.
    """
    today = today or date.today()
    if not force and today.weekday() != weekday:
        return None

    issues = [i for i in upcoming_issues(refresh=False)
              if i.ipo_end and (include_sme or not i.is_sme)]
    issues.sort(key=lambda i: i.ipo_end or "")

    if issues:
        nxt = issues[0]
        days = (date.fromisoformat(nxt.ipo_end) - today).days
        when = ("closes TODAY" if days == 0 else
                "closes tomorrow" if days == 1 else f"closes in {days} days")
        lines = [f"Watching {len(issues)} open issue(s).",
                 f"Next: {nxt.symbol} {when} ({nxt.ipo_end})"]
        for i in issues[1:4]:
            lines.append(f"  {i.symbol} -> {i.ipo_end}")
    else:
        lines = ["No IPOs open right now.", "Nothing to apply for this week."]

    return hub().alert(
        kind="ipo_heartbeat", urgency="info",
        title="IPO watch is running",
        body="\n".join(lines),
        dedupe_key=f"heartbeat:{today.isoformat()}",
        open_issues=len(issues),
    )
