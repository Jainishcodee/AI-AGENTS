"""The listing-morning alert sequence.

These encode the decisions the study forced, so a later "improvement" cannot
quietly undo them:

  * no buy alert on the opening print (53% of listings peak there and fade)
  * a buy alert only after it holds above the open
  * warnings fire *before* a level, not on it
  * every buy alert carries a price, a stop, a target and a rupee amount
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from stockseer.ipo.registry import IPO
from stockseer.ipo.watcher import ListingWatcher, WatchConfig
from stockseer.notify import NotificationHub


@pytest.fixture
def ipo() -> IPO:
    return IPO(symbol="TESTCO", company="Test Company Limited",
               issue_price=100.0, listing_date="2026-08-14",
               price_range="Rs.95 to Rs.100", security_type="EQ")


@pytest.fixture
def watcher(ipo, tmp_path, monkeypatch):
    cfg = WatchConfig(capital=40_000, confirm_minutes=5, target_pct=0.035,
                      stop_pct=0.030, near_pct=0.008)
    w = ListingWatcher(ipo, feed=None, config=cfg)
    w._hub = NotificationHub(tmp_path / "n.json")
    return w


def kinds(w) -> list[str]:
    return [n.kind for n in w._hub.items]


def last(w, kind: str):
    return next((n for n in reversed(w._hub.items) if n.kind == kind), None)


def _age(w, minutes: int) -> None:
    """Pretend the confirmation window has elapsed."""
    w.state.opened_at = datetime.now() - timedelta(minutes=minutes)
    w.state.history = [(datetime.now() - timedelta(minutes=minutes - i), p)
                       for i, (_, p) in enumerate(w.state.history)]


# --------------------------------------------------------------------------- #
def test_opening_print_reports_but_does_not_say_buy(watcher):
    watcher.on_tick(120.0)
    assert kinds(watcher) == ["ipo_listed"]
    body = last(watcher, "ipo_listed").body
    assert "DO NOT BUY YET" in body
    assert watcher.state.position is None


def test_no_buy_while_it_fades_from_the_open(watcher):
    """The 53% case: opens high, drifts down. Must never produce a buy."""
    watcher.on_tick(120.0)
    for p in (119.0, 118.0, 117.5, 116.0):
        watcher.on_tick(p)
    _age(watcher, 6)
    watcher.on_tick(115.0)
    assert "ipo_buy" not in kinds(watcher)
    assert watcher.state.position is None


def test_buy_fires_once_it_holds_above_the_open(watcher):
    watcher.on_tick(120.0)
    for p in (120.5, 121.0, 120.8, 121.5):
        watcher.on_tick(p)
    _age(watcher, 6)
    watcher.on_tick(122.0)

    assert "ipo_buy" in kinds(watcher)
    pos = watcher.state.position
    assert pos is not None
    assert pos.entry == pytest.approx(122.0)
    assert pos.target == pytest.approx(122.0 * 1.035)
    assert pos.stop == pytest.approx(122.0 * 0.970)
    assert pos.qty == int(40_000 // 122.0)


def test_buy_alert_states_price_target_stop_and_rupees(watcher):
    watcher.on_tick(100.0)
    for p in (100.5, 101.0, 101.2):
        watcher.on_tick(p)
    _age(watcher, 6)
    watcher.on_tick(102.0)

    n = last(watcher, "ipo_buy")
    assert n is not None and n.urgency == "critical"
    assert "BUY" in n.body and "TARGET" in n.body and "STOP" in n.body
    assert n.data["qty"] == int(40_000 // 102.0)
    assert n.data["target_rupees"] > 0
    assert n.data["stop_rupees"] < 0
    # A three-second buzz, not a tick.
    assert sum(n.vibration) >= 2000


def _enter(w, open_px=100.0, entry=102.0):
    w.on_tick(open_px)
    for p in (open_px + 0.5, open_px + 1.0, open_px + 1.2):
        w.on_tick(p)
    _age(w, 6)
    w.on_tick(entry)
    return w.state.position


# --------------------------------------------------------------------------- #
def test_warns_before_the_target_not_on_it(watcher):
    pos = _enter(watcher)
    watcher.on_tick(pos.target * 0.995)          # inside the 0.8% warn band
    assert "ipo_near_target" in kinds(watcher)
    assert "ipo_exit" not in kinds(watcher), "warned, but must not have exited"


def test_warns_before_the_stop_not_on_it(watcher):
    pos = _enter(watcher)
    watcher.on_tick(pos.stop * 1.005)
    assert "ipo_near_stop" in kinds(watcher)
    assert "ipo_exit" not in kinds(watcher)


def test_target_hit_closes_the_position(watcher):
    pos = _enter(watcher)
    watcher.on_tick(pos.target * 1.001)
    n = last(watcher, "ipo_exit")
    assert n is not None and "TARGET HIT" in n.title
    assert watcher.state.position.closed
    assert n.data["pnl"] > 0


def test_stop_hit_closes_the_position(watcher):
    pos = _enter(watcher)
    watcher.on_tick(pos.stop * 0.999)
    n = last(watcher, "ipo_exit")
    assert n is not None and "STOP HIT" in n.title
    assert n.data["pnl"] < 0


def test_trailing_stop_protects_a_gain_that_never_reached_target(watcher):
    """The winner-turned-loser case the trail exists for.

    Up 2% (past the 1.5% arm, short of the 3.5% target), then it fades. Without
    a trail this rides all the way down to the stop and gives back the lot.
    """
    pos = _enter(watcher)
    watcher.on_tick(pos.entry * 1.02)            # peak; trail now armed
    for mult in (1.015, 1.010, 1.005, 1.0019):   # walks down through the floor
        watcher.on_tick(pos.entry * mult)

    n = last(watcher, "ipo_exit")
    assert n is not None and "TRAILING" in n.title
    assert n.data["pnl"] > 0, "an armed trail must not hand back a loss"


def test_a_gap_through_the_trail_reports_the_real_fill(watcher):
    """If it gaps past the level you fill below it -- say so, do not pretend.

    Reporting the trigger price instead of the traded price would quietly
    overstate every result the journal ever shows.
    """
    pos = _enter(watcher)
    watcher.on_tick(pos.entry * 1.02)
    watcher.on_tick(pos.entry * 0.99)            # one tick straight through
    n = last(watcher, "ipo_exit")
    assert n is not None
    assert n.data["price"] == pytest.approx(pos.entry * 0.99)
    assert n.data["pnl"] < 0


def test_trail_stays_asleep_on_a_trivial_wiggle(watcher):
    """A 0.5% blip must not arm the trail and eject you on noise."""
    pos = _enter(watcher)
    watcher.on_tick(pos.entry * 1.005)
    watcher.on_tick(pos.entry * 0.995)
    assert "ipo_exit" not in kinds(watcher)


def test_each_alert_fires_once(watcher):
    pos = _enter(watcher)
    for _ in range(5):
        watcher.on_tick(pos.target * 0.995)
    assert kinds(watcher).count("ipo_near_target") == 1


def test_no_further_alerts_after_the_exit(watcher):
    pos = _enter(watcher)
    watcher.on_tick(pos.stop * 0.99)
    before = len(watcher._hub.items)
    for p in (pos.target, pos.target * 1.1, pos.stop * 0.5):
        watcher.on_tick(p)
    assert len(watcher._hub.items) == before


def test_session_close_squares_off_an_open_position(watcher):
    _enter(watcher)
    watcher.on_tick(103.0)
    watcher.session_over()
    n = last(watcher, "ipo_exit")
    assert n is not None and "SESSION CLOSING" in n.title


def test_price_above_capital_produces_no_position(ipo, tmp_path):
    """A Rs.5,000 share on Rs.4,000 of capital cannot be bought."""
    w = ListingWatcher(ipo, feed=None, config=WatchConfig(capital=4_000))
    w._hub = NotificationHub(tmp_path / "n.json")
    w.on_tick(5_000.0)
    for p in (5_010.0, 5_020.0, 5_030.0):
        w.on_tick(p)
    _age(w, 6)
    w.on_tick(5_040.0)
    assert "ipo_buy" not in kinds(w)
    assert w.state.position is None


def test_every_alert_buzzes_for_at_least_two_seconds(watcher):
    """A market alert competes with a pocket; a 200ms tick loses."""
    _enter(watcher)
    watcher.on_tick(watcher.state.position.target * 1.01)
    assert watcher._hub.items
    for n in watcher._hub.items:
        assert sum(n.vibration) >= 2000, f"{n.kind} buzzes for {sum(n.vibration)}ms"
