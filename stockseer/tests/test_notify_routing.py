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


# --------------------------------------------------------------------------- #
# The freshly-booted-runner bug
# --------------------------------------------------------------------------- #
def test_fresh_hub_has_never_been_polled(tmp_path, monkeypatch):
    """A hub nobody has polled must not claim a client is listening.

    `_now()` is time.monotonic(), which counts seconds since boot on Linux.
    While `_last_poll` started at 0.0, a process running on a machine that had
    been up for less than the 90-second window computed
    `(monotonic() - 0.0) < 90` as True and skipped the ntfy push as redundant.

    That is the normal state of a GitHub Actions runner: the VM boots and the
    job starts under a minute later. The alert was dropped for a Jarvis that
    was not running, the failure reported no cause because no request was
    made, and it looked intermittent because it depended on whether the runner
    was freshly booted or reused.
    """
    import stockseer.notify as N

    for uptime in (0.0, 5.0, 30.0, 60.0, 89.0):
        monkeypatch.setattr(N, "_now", lambda u=uptime: u)
        hub = N.NotificationHub(path=tmp_path / f"n{uptime}.json")
        assert not hub.client_recently_polled(), (
            f"a never-polled hub claimed a live client at uptime {uptime}s; "
            "on a runner this silently drops the push"
        )


def test_note_poll_still_registers_a_live_client(tmp_path, monkeypatch):
    """The fix must not disable genuine Jarvis detection."""
    import stockseer.notify as N

    monkeypatch.setattr(N, "_now", lambda: 42.0)
    hub = N.NotificationHub(path=tmp_path / "n.json")
    assert not hub.client_recently_polled()

    hub.note_poll()
    assert hub.client_recently_polled(), "a real poll should register"

    monkeypatch.setattr(N, "_now", lambda: 42.0 + 91.0)
    assert not hub.client_recently_polled(), "the window should still expire"


def test_runner_conditions_actually_push(tmp_path, monkeypatch):
    """End to end: freshly booted machine, no Jarvis -> the relay is called."""
    import stockseer.notify as N
    from stockseer import push as P

    monkeypatch.setattr(N, "_now", lambda: 12.0)      # 12s since boot
    monkeypatch.setenv("NTFY_TOPIC", "test-topic")
    sent = []
    monkeypatch.setattr(P, "push_notification", lambda n: sent.append(n) or True)

    hub = N.NotificationHub(path=tmp_path / "n.json")
    n = hub.alert(kind="ipo_closes_today", urgency="critical",
                  title="LAST DAY: TEST", body="body", dedupe_key="k")

    assert sent, "the push was skipped on a freshly booted machine"
    assert n.pushed is True
