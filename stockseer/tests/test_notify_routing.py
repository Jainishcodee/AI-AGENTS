"""One event, one buzz.

With both transports live, a naive fan-out delivers every alert twice: once
through Jarvis's poll, once through ntfy. Two buzzes for one event is how
notifications get swiped away unread, which then loses the one that mattered.
"""

from __future__ import annotations

import pytest

from stockseer.notify import NotificationHub, Notification


@pytest.fixture
def hub(tmp_path, monkeypatch):
    h = NotificationHub(tmp_path / "n.json")
    sent: list[str] = []
    monkeypatch.setattr("stockseer.push.configured", lambda: True)
    monkeypatch.setattr("stockseer.push.push_notification",
                        lambda n: sent.append(n.title) or True)
    h._sent = sent          # type: ignore[attr-defined]
    return h


def _alert(h, title="x"):
    return h.push(Notification(kind="test", urgency="act", title=title, body="b"))


def test_pushes_when_nothing_is_polling(hub):
    """PC asleep, Jarvis closed — ntfy is the only way through."""
    _alert(hub, "no client")
    assert hub._sent == ["no client"]


def test_does_not_push_while_jarvis_is_polling(hub):
    hub.note_poll()
    _alert(hub, "jarvis is here")
    assert hub._sent == [], "Jarvis is collecting; ntfy would double-buzz"


def test_resumes_pushing_once_jarvis_goes_quiet(hub, monkeypatch):
    """Phone locked or app killed mid-session: delivery must fail over."""
    hub.note_poll()
    _alert(hub, "while polling")
    assert hub._sent == []

    # Two minutes later, no further polls.
    base = hub._last_poll
    monkeypatch.setattr("stockseer.notify._now", lambda: base + 120.0)
    _alert(hub, "after silence")
    assert hub._sent == ["after silence"]


def test_poll_window_tolerates_one_dropped_request(hub, monkeypatch):
    """A single missed poll must not cause a duplicate buzz."""
    hub.note_poll()
    base = hub._last_poll
    monkeypatch.setattr("stockseer.notify._now", lambda: base + 45.0)
    _alert(hub, "one poll missed")
    assert hub._sent == []


def test_a_pushed_alert_is_recorded_but_no_longer_owed(hub):
    """The queue is the record; the transport is just delivery.

    Once ntfy has delivered an alert it must drop out of `pending`, or Jarvis
    re-buzzes for it on its next connect -- possibly days later, for an event
    that is long over.
    """
    _alert(hub, "kept")
    assert [n.title for n in hub.items] == ["kept"]
    assert hub.items[0].pushed is True
    assert hub.pending() == [], "ntfy already delivered it"


def test_an_undelivered_alert_is_still_owed(hub, monkeypatch):
    """If the push fails, Jarvis must still get its chance."""
    monkeypatch.setattr("stockseer.push.push_notification", lambda n: False)
    _alert(hub, "push failed")
    assert hub.items[0].pushed is False
    assert [n.title for n in hub.pending()] == ["push failed"]


def test_stale_alerts_are_not_replayed(hub, monkeypatch):
    """A market alert from two days ago is not news."""
    monkeypatch.setattr("stockseer.push.configured", lambda: False)
    n = _alert(hub, "old news")
    n.created_at = "2020-01-01T09:00:00+05:30"
    assert hub.pending() == []
    assert hub.pending(max_age_hours=24 * 365 * 20)


def test_push_failure_never_loses_the_alert(tmp_path, monkeypatch):
    monkeypatch.setattr("stockseer.push.configured", lambda: True)

    def boom(_):
        raise RuntimeError("relay down")

    monkeypatch.setattr("stockseer.push.push_notification", boom)
    h = NotificationHub(tmp_path / "n.json")
    h.push(Notification(kind="test", urgency="act", title="survives", body="b"))
    assert [n.title for n in h.items] == ["survives"]


def test_dedupe_still_applies_across_transports(hub):
    a = hub.push(Notification(kind="t", urgency="act", title="one", body="b"),
                 dedupe_key="k")
    b = hub.push(Notification(kind="t", urgency="act", title="two", body="b"),
                 dedupe_key="k")
    assert a is not None and b is None
    assert hub._sent == ["one"], "the suppressed duplicate must not be pushed"
