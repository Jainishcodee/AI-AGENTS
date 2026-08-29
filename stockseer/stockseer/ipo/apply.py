"""What one IPO application is actually worth, and how to place it.

The listing-gain study measures the payoff **given an allotment**: mainboard
issues opened +14.4% on average, +9.1% at the median, over 150 listings. That
is the number the alert quoted, and on its own it is misleading, because it
never touches the probability of getting any shares at all.

The obvious correction -- multiply by 1/subscription -- is also wrong, and it
was tried first. It assumes the payoff is the same whatever the demand. It is
not. Over 382 mainboard listings, subscription and listing gain correlate at
**rho = +0.49, p < 0.0001**:

    subscription      median gain    win rate    EV per lakh blocked
    under 1.3x              0.00%         43%                      0
    1.3x -  3.5x           -0.82%         43%                   -367
    3.5x -  9.3x           +6.11%         67%                    963
    9.3x - 22.9x          +12.38%         72%                    837
    over 22.9x            +38.24%         87%                    876

Two things follow, and both are the opposite of the intuition:

**Heavy subscription is not a penalty.** The gain rises almost exactly as fast
as the odds fall, so expected value per rupee is roughly flat above 3.5x.
Choosing between a 10x issue and a 170x issue barely matters.

**The quiet issues are the dangerous ones.** Below about 3.5x the median gain
is negative and only 43% list up. "Not yet full -- everyone who applies should
get shares" reads like an opportunity and is the one case with genuinely
negative expected value.

So the payoff term is looked up by subscription level rather than assumed.

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
    expected_gain: float          # payoff given allotment, at THIS subscription
    n_accounts: int = 1
    win_rate: float = float("nan")   # share of issues at this level that rose

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


def expected_gain_for(retail_x: float | None, fallback: float) -> tuple[float, float]:
    """Median listing gain and win rate for issues at this subscription level.

    Measured over 382 mainboard listings: subscription and listing gain
    correlate at rho = +0.49 (p < 0.0001). Applying one global median to every
    issue -- which is what the alert did -- is wrong at both ends. It
    understates a 170x issue roughly fourfold, and it turns a barely-subscribed
    issue, whose median gain is actually *negative*, into an apparent
    opportunity. Conditioning changes the sign of the answer, not just its size.
    """
    from .backfill import load_gain_curve

    if retail_x is None:
        return fallback, float("nan")

    chosen = None
    for lo, median_gain, win, _n in load_gain_curve():
        if retail_x >= lo:
            chosen = (median_gain, win)
    return chosen if chosen else (fallback, float("nan"))


def evaluate(subs, terms, expected_gain: float,
             n_accounts: int | None = None) -> Application | None:
    """Build the economics from a live subscription and issue terms.

    `expected_gain` is only a fallback here: the payoff actually used is the
    one measured for this issue's subscription level.
    """
    if subs is None:
        return None
    gain, win = expected_gain_for(subs.retail_x, expected_gain)
    return Application(
        odds=subs.odds,
        lot_amount=getattr(terms, "lot_amount", None) if terms else None,
        expected_gain=gain,
        win_rate=win,
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

    # "-Rs.58", not "Rs.-58". A negative expected value is the single most
    # important thing this block can say, so it must not read as a typo.
    money = lambda v: f"{'-' if v < 0 else ''}Rs.{abs(v):,.0f}"   # noqa: E731

    out.append(f"Expected value: about {money(ev)} per application")
    if app.n_accounts > 1 and app.ev_total is not None:
        out.append(f"Across {app.n_accounts} accounts: about "
                   f"{money(app.ev_total)}")

    roc = app.return_on_capital
    if roc is not None and app.capital_blocked:
        out.append(f"That is {roc * 100:.2f}% on the Rs.{app.capital_blocked:,.0f} "
                   f"blocked for about 5 days")

    # State the payoff actually used, because it is conditioned on this issue's
    # demand rather than being the global average the reader might assume.
    if app.expected_gain == app.expected_gain:                 # not NaN
        line = (f"At this subscription level, past issues listed "
                f"{app.expected_gain * 100:+.1f}%")
        if app.win_rate == app.win_rate:
            line += f" and {app.win_rate * 100:.0f}% rose"
        out.append(line + ".")

    if app.is_lottery:
        out.append("Oversubscribed, so allotment is a draw: one lot per PAN is "
                   "all that counts -- extra lots do not improve your odds.")
    return out
