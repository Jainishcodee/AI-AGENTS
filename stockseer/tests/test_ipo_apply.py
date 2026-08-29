"""The allotment arithmetic, and the classification bugs that fed it.

These tests exist because the alert was quoting a payoff without its
probability, which made a 170x-subscribed issue look like a +9% opportunity
when it was worth about six rupees.
"""

import pytest

from stockseer.ipo.apply import (Application, describe, evaluate,
                                 expected_gain_for)
from stockseer.ipo.registry import IPO, IssueTerms, Subscription, _to_ipo


# --------------------------------------------------------------------------- #
# Expected value
# --------------------------------------------------------------------------- #
def test_ev_collapses_on_a_heavily_subscribed_issue():
    """HTEL: 170.6x retail, a Rs.15,000 lot, +9.14% median gain -> about Rs.8.

    The number the alert used to omit. Worked by hand:
    (1/170.6) * 15000 * 0.0914 = 8.03
    """
    app = Application(odds=1 / 170.6, lot_amount=15_000.0,
                      expected_gain=0.0914, n_accounts=1)
    assert app.ev_per_application == pytest.approx(8.03, abs=0.05)
    # Blocking Rs.15,000 for five days for this is well under a deposit rate.
    assert app.return_on_capital < 0.001


def test_expected_gain_rises_with_subscription():
    """Measured over 382 listings: rho = +0.49 between subscription and gain.

    The first version of this module applied one global median to every issue.
    That is wrong at both ends, and the bottom end matters most -- it turned a
    negative-expectancy issue into an apparent opportunity.
    """
    quiet, _ = expected_gain_for(2.0, 0.0914)
    mid, _ = expected_gain_for(13.0, 0.0914)
    hot, _ = expected_gain_for(170.6, 0.0914)
    assert quiet < 0 < mid < hot
    assert hot > 0.25          # heavily subscribed issues opened ~+38%


def test_barely_subscribed_issues_have_negative_expected_value():
    """"Everyone who applies gets shares" is a warning, not an opportunity.

    Below ~3.5x the median listing gain is negative and only 43% rise, so good
    odds of an allotment are odds on a loss.
    """
    app = evaluate(Subscription(symbol="Q", retail_x=2.1, qib_x=3.2, nii_x=4.2),
                   IssueTerms(symbol="Q", lot_shares=180, price_high=83.0),
                   0.0914)
    assert app.ev_per_application < 0
    assert any("-Rs." in ln for ln in describe(app))


def test_ev_per_rupee_is_roughly_flat_across_hot_issues():
    """The payoff rises about as fast as the odds fall above ~3.5x.

    This is why "avoid the hyped ones" was wrong: choosing between a 13x and a
    170x issue barely changes what a rupee expects.
    """
    def roc(x):
        app = evaluate(Subscription(symbol="X", retail_x=x, qib_x=x, nii_x=x),
                       IssueTerms(symbol="X", lot_shares=100, price_high=150.0),
                       0.0914)
        return app.return_on_capital

    hot, mid = roc(170.6), roc(13.0)
    assert 0 < hot and 0 < mid
    assert 0.1 < hot / mid < 10       # same order of magnitude, not 50x apart


def test_undersubscribed_issue_allots_to_everyone():
    """Odds cap at 1.0 -- you cannot be more than certain of an allotment."""
    subs = Subscription(symbol="X", retail_x=0.4, qib_x=1.0, nii_x=0.5)
    assert subs.odds == 1.0
    app = Application(odds=subs.odds, lot_amount=15_000.0, expected_gain=0.0914)
    assert app.ev_per_application == pytest.approx(1371.0, abs=1.0)
    assert not app.is_lottery


def test_accounts_multiply_ev_and_capital_together():
    """Three PANs treble the expected value and treble the money committed.

    Return on capital must therefore be unchanged -- extra accounts buy more
    entries, not a better rate. Getting this wrong would make family accounts
    look like free money.
    """
    one = Application(odds=1 / 13.0, lot_amount=14_820.0,
                      expected_gain=0.0914, n_accounts=1)
    three = Application(odds=1 / 13.0, lot_amount=14_820.0,
                        expected_gain=0.0914, n_accounts=3)
    assert three.ev_total == pytest.approx(3 * one.ev_total)
    assert three.capital_blocked == pytest.approx(3 * one.capital_blocked)
    assert three.return_on_capital == pytest.approx(one.return_on_capital)


def test_missing_inputs_yield_no_claim_rather_than_a_wrong_one():
    """No subscription or no lot size means no EV, not an EV of zero."""
    assert evaluate(None, None, 0.0914) is None
    subs = Subscription(symbol="X", retail_x=None, qib_x=None, nii_x=None)
    app = evaluate(subs, None, 0.0914)
    assert app is not None and app.ev_per_application is None
    assert describe(app) == []


def test_lottery_note_appears_only_when_oversubscribed():
    """Bidding extra lots helps below 1x and is dead capital above it."""
    over = Application(odds=1 / 25.0, lot_amount=15_000.0, expected_gain=0.0914)
    under = Application(odds=1.0, lot_amount=15_000.0, expected_gain=0.0914)
    assert any("one lot per PAN" in ln for ln in describe(over))
    assert not any("one lot per PAN" in ln for ln in describe(under))


def test_describe_states_economics_without_a_verdict():
    """The alert reports the number and leaves the judgement to the reader."""
    app = Application(odds=1 / 170.6, lot_amount=15_000.0, expected_gain=0.0914)
    text = " ".join(describe(app)).lower()
    assert "expected value" in text
    for verdict in ("skip", "avoid", "worth it", "recommend", "don't apply"):
        assert verdict not in text


# --------------------------------------------------------------------------- #
# Classification -- the two bugs that corrupted the base rate
# --------------------------------------------------------------------------- #
def test_upcoming_issues_report_their_series_not_a_default():
    """The upcoming feed says `series`; reading only `securityType` hid SME.

    ASHUTOSH and SHANTIINOR are both SME and were being alerted on despite SME
    being excluded by default, because every upcoming issue silently fell back
    to EQ.
    """
    sme = _to_ipo({"symbol": "ASHUTOSH", "companyName": "Ashutosh Fibre Limited",
                   "issuePrice": "Rs.87 to Rs.92", "series": "SME"})
    assert sme.is_sme and not sme.is_mainboard

    eq = _to_ipo({"symbol": "LUMINO", "companyName": "Lumino Industries",
                  "issuePrice": "Rs.78 to Rs.82", "series": "EQ"})
    assert eq.is_mainboard and not eq.is_sme


def test_past_issues_still_read_security_type():
    """The other feed uses `securityType`; both must keep working."""
    ipo = _to_ipo({"symbol": "GAJA", "company": "Gaja Alternative",
                   "issuePrice": "160", "securityType": "EQ"})
    assert ipo.is_mainboard


@pytest.mark.parametrize("code", ["BE", "DEBT", "N0", "IV", "RR", "NZ", "Z9"])
def test_non_equity_instruments_are_not_mainboard_ipos(code):
    """`not is_sme` swept bonds, NCDs and InvITs into the mainboard bucket.

    130 of 569 supposedly-mainboard past issues were these. They list flat and
    dragged the measured allotment gain down.
    """
    ipo = IPO(symbol="X", company="Some Debenture", issue_price=100.0,
              listing_date="2024-01-01", security_type=code)
    assert not ipo.is_mainboard
    assert not ipo.is_sme          # and so the old test let it through


def test_message_carries_the_expected_value(monkeypatch):
    """End to end: the rendered alert states EV and the one-lot rule."""
    monkeypatch.setenv("IPO_ACCOUNTS", "3")
    from stockseer.ipo.calendar import CalendarEvent, _message

    ipo = IPO(symbol="SYMBIOTEC", company="Symbiotec Pharmalab Limited",
              issue_price=988.0, listing_date=None,
              price_range="Rs.938 to Rs.988", security_type="EQ",
              ipo_end="2026-08-27")
    ev = CalendarEvent(
        ipo, "closes_today", "critical",
        Subscription(symbol="SYMBIOTEC", retail_x=12.96, qib_x=172.0, nii_x=73.6),
        IssueTerms(symbol="SYMBIOTEC", lot_shares=15, price_high=988.0),
    )
    title, body = _message(ev)
    assert title == "LAST DAY: SYMBIOTEC"
    assert "Expected value" in body
    assert "one lot per PAN" in body
    assert "1 in 13" in body
