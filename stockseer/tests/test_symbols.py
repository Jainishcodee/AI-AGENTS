"""Symbol search tests.

All offline: the Yahoo leg is stubbed, so the suite never depends on a network
call or on what a live exchange happens to list today.
"""

from __future__ import annotations

import pytest

from stockseer.live import symbols as sym


@pytest.fixture
def fake_index(monkeypatch):
    entries = [
        {"symbol": "^NSEI", "name": "NIFTY 50", "exchange": "NSE", "type": "INDEX"},
        {"symbol": "RELIANCE.NS", "name": "RELIANCE", "exchange": "NSE", "type": "EQUITY"},
        {"symbol": "RELIANCE.BO", "name": "RELIANCE", "exchange": "BSE", "type": "EQUITY"},
        {"symbol": "RELINFRA.NS", "name": "RELINFRA", "exchange": "NSE", "type": "EQUITY"},
        {"symbol": "TCS.NS", "name": "TCS", "exchange": "NSE", "type": "EQUITY"},
        {"symbol": "WSTCSTPAPR.NS", "name": "WSTCSTPAPR", "exchange": "NSE", "type": "EQUITY"},
        {"symbol": "AAPLUSTRAD.BO", "name": "AAPLUSTRAD", "exchange": "BSE", "type": "EQUITY"},
    ]
    monkeypatch.setattr(sym, "local_index", lambda: entries)
    return entries


def _no_network(monkeypatch, results=None):
    if results is None:
        monkeypatch.setattr(sym, "search_yahoo",
                            lambda q, n=12: (_ for _ in ()).throw(OSError("offline")))
    else:
        monkeypatch.setattr(sym, "search_yahoo", lambda q, n=12: results)


# --------------------------------------------------------------------------- #
def test_exact_ticker_outranks_a_substring_match(fake_index, monkeypatch):
    """Searching AAPL must not surface a BSE listing that merely contains it."""
    _no_network(monkeypatch, [
        {"symbol": "AAPLUSTRAD.BO", "name": "AAPLUSTRAD", "exchange": "BSE", "type": "EQUITY"},
        {"symbol": "AAPL", "name": "Apple Inc.", "exchange": "NMS", "type": "EQUITY"},
    ])
    out = sym.search("AAPL", 5)["results"]
    assert out[0]["symbol"] == "AAPL"


def test_nse_preferred_over_bse_when_neither_is_more_exact(fake_index, monkeypatch):
    _no_network(monkeypatch, [
        {"symbol": "RELIANCE.BO", "name": "RELIANCE", "exchange": "BSE", "type": "EQUITY"},
        {"symbol": "RELIANCE.NS", "name": "RELIANCE INDUSTRIES", "exchange": "NSI", "type": "EQUITY"},
    ])
    out = sym.search("RELIANCE", 5)["results"]
    assert out[0]["symbol"] == "RELIANCE.NS"
    assert out[1]["symbol"] == "RELIANCE.BO"


def test_prefix_beats_substring(fake_index, monkeypatch):
    _no_network(monkeypatch)
    out = sym.search("TCS", 5)["results"]
    assert out[0]["symbol"] == "TCS.NS"
    syms = [r["symbol"] for r in out]
    assert syms.index("TCS.NS") < syms.index("WSTCSTPAPR.NS")


def test_falls_back_to_local_when_yahoo_is_down(fake_index, monkeypatch):
    _no_network(monkeypatch)
    d = sym.search("RELIANCE", 5)
    assert d["source"] == "local"
    assert any(r["symbol"] == "RELIANCE.NS" for r in d["results"])


def test_local_results_backfill_what_yahoo_missed(fake_index, monkeypatch):
    """A thin or BSE-only name absent from Yahoo must still be reachable."""
    _no_network(monkeypatch, [
        {"symbol": "RELIANCE.NS", "name": "RELIANCE INDUSTRIES", "exchange": "NSI", "type": "EQUITY"},
    ])
    out = [r["symbol"] for r in sym.search("RELIANCE", 10)["results"]]
    assert "RELIANCE.NS" in out
    assert "RELIANCE.BO" in out, "local index should backfill"
    assert len(out) == len(set(out)), "no duplicates across sources"


def test_indices_are_searchable(fake_index, monkeypatch):
    _no_network(monkeypatch)
    assert sym.search("^NSEI", 5)["results"][0]["symbol"] == "^NSEI"
    assert any(r["symbol"] == "^NSEI" for r in sym.search("NSEI", 5)["results"])


def test_empty_query_returns_nothing(fake_index, monkeypatch):
    _no_network(monkeypatch)
    for q in ("", "   "):
        assert sym.search(q)["results"] == []


def test_limit_is_respected(fake_index, monkeypatch):
    _no_network(monkeypatch)
    assert len(sym.search("R", 2)["results"]) <= 2


def test_search_is_case_insensitive(fake_index, monkeypatch):
    _no_network(monkeypatch)
    lower = [r["symbol"] for r in sym.search("reliance", 5)["results"]]
    upper = [r["symbol"] for r in sym.search("RELIANCE", 5)["results"]]
    assert lower == upper


def test_curated_index_list_is_well_formed():
    """The hardcoded index list must not drift into a broken shape."""
    for entry in sym.INDICES:
        assert len(entry) == 3
        assert entry[0].startswith("^")
        assert entry[1] and entry[2]
