"""What one IPO application is actually worth, and how to place it.

The listing-gain study measures the payoff **given an allotment**: mainboard
issues opened +14.4% on average, +9.1% at the median, over 150 listings. That
is the number the alert quoted, and on its own it is misleading, because it
never touches the probability of getting any shares at all.

Multiply the two and the picture inverts. On a 170x-subscribed issue the odds
are 1 in 171, so blocking Rs.15,000 for five days returns an expected Rs.6 --
about 2% a year on committed capital, worse than a savings account. On a
3x-subscribed issue the same Rs.15,000 expects Rs.365. **The exciting IPOs are
the bad ones**, and no amount of enthusiasm changes the arithmetic.

Two mechanics from SEBI's ICDR regulations drive everything here:

**Allotment is a lottery, not a queue.** An oversubscribed retail book is
allotted by computerised draw, minimum lot to as many applicants as possible.
There is no discretion and no preference for larger bids.

**Above a threshold, extra lots buy nothing.** While there are enough shares to
give every applicant one lot, surplus is distributed proportionately and bidding
more genuinely helps. Once demand passes that point it becomes a single-lot
draw, and one application is one entry whether you bid one lot or thirteen.
Past that line, additional lots are dead capital -- and the money is strictly
better spent as a second application on a different PAN.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

log = logging.getLogger(__name__)

# Retail is a lottery for a single lot once demand passes roughly this level.
# The true threshold depends on how many applicants bid more than one lot,
# which is never published, so this is the conservative reading: any retail
# oversubscription at all should be treated as a draw.
LOTTERY_THRESHOLD = 1.0


def accounts() -> int:
    """How many PANs are available to apply with.

    Each PAN is one independent entry in the draw, which makes this the largest
    single lever on allotment odds -- far larger than anything about *which*
    IPO you pick. The same PAN applying twice gets every one of its
    applications rejected, so this counts people, not demat accounts.
    """
    from ..config import setting

    try:
        return max(1, int(setting("IPO_ACCOUNTS") or 1))
    except (TypeError, ValueError):
        return 1


@dataclass
class Application:
    """The economics of applying to one issue."""

    odds: float | None            # P(allotment) for a single application
    lot_amount: float | None      # rupees blocked per application
    expected_gain: float          # payoff given allotment, as a fraction
    n_accounts: int = 1

    @property
    def ev_per_application(self) -> float | None:
        """Expected rupees from one application, before it is placed."""
        if self.odds is None or not self.lot_amount:
            return None
        return self.odds * self.lot_amount * self.expected_gain

    @property
    def ev_total(self) -> float | None:
        """Expected rupees across every account you can apply from."""
        ev = self.ev_per_application
        return None if ev is None else ev * self.n_accounts

    @property
    def capital_blocked(self) -> float | None:
        """Rupees tied up until allotment, across all accounts."""
        if not self.lot_amount:
            return None
        return self.lot_amount * self.n_accounts

    @property
    def return_on_capital(self) -> float | None:
        """EV as a fraction of the money you must block to earn it.

        The honest denominator. Funds sit under a UPI mandate for roughly five
        days whether or not shares arrive, so this is the number comparable to
        a deposit rate -- and the one that reveals a 170x issue as a poor use
        of Rs.15,000.
        """
        ev, cap = self.ev_total, self.capital_blocked
        if ev is None or not cap:
            return None
        return ev / cap

    @property
    def is_lottery(self) -> bool:
        """True when extra lots stop helping and only extra PANs do."""
        return self.odds is not None and self.odds < 1.0


def evaluate(subs, terms, expected_gain: float,
             n_accounts: int | None = None) -> Application | None:
    """Build the economics from a live subscription and issue terms."""
    if subs is None:
        return None
    return Application(
        odds=subs.odds,
        lot_amount=getattr(terms, "lot_amount", None) if terms else None,
        expected_gain=expected_gain,
        n_accounts=accounts() if n_accounts is None else n_accounts,
    )


def describe(app: Application) -> list[str]:
    """Alert lines stating the economics, without telling anyone what to do.

    Deliberately verdict-free. "Expected value Rs.6" and "Rs.365" are so far
    apart that a label would add nothing a reader cannot see, and a SKIP the
    reader disagrees with is how an alert stream stops being trusted.
    """
    out: list[str] = []
    ev = app.ev_per_application
    if ev is None:
        return out

    out.append(f"Expected value: about Rs.{ev:,.0f} per application")
    if app.n_accounts > 1 and app.ev_total is not None:
        out.append(f"Across {app.n_accounts} accounts: about "
                   f"Rs.{app.ev_total:,.0f}")

    roc = app.return_on_capital
    if roc is not None and app.capital_blocked:
        out.append(f"That is {roc * 100:.2f}% on the Rs.{app.capital_blocked:,.0f} "
                   f"blocked for about 5 days")

    if app.is_lottery:
        out.append("Oversubscribed, so allotment is a draw: one lot per PAN is "
                   "all that counts -- extra lots do not improve your odds.")
    return out
