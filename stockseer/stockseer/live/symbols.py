"""Symbol search across NSE, BSE and global exchanges.

Two sources, deliberately layered:

* **Yahoo's search endpoint** -- free, no key, returns real company names and the
  exact ``.NS`` / ``.BO`` symbols our data layer already speaks. Primary, because
  a user searching "reliance" means the company, not a ticker they memorised.
* **Angel One's public scrip master** -- a 151k-instrument dump that needs no
  credentials. Offline fallback and the authoritative list of what actually
  trades: 2,439 NSE equities and 12,711 BSE.

The local index only knows tickers (the scrip master's ``name`` field for
equities is just the symbol again), so it degrades from "search by company" to
"search by ticker" when offline. That is a real limitation, not a hidden one.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.parse
import urllib.request
from functools import lru_cache
from pathlib import Path

log = logging.getLogger(__name__)

CACHE = Path(__file__).resolve().parent.parent.parent / "cache"
SCRIP_URL = (
    "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
)
YAHOO_URL = (
    "https://query1.finance.yahoo.com/v1/finance/search"
    "?q={q}&quotesCount={n}&newsCount=0&enableFuzzyQuery=true"
)
UA = "Mozilla/5.0 (compatible; StockSeer/0.1)"

# Indices are not equities and do not appear in the scrip master in a usable
# form, so they are curated. These are the ones an Indian user actually wants.
INDICES = [
    ("^NSEI", "NIFTY 50", "NSE"),
    ("^NSEBANK", "NIFTY BANK", "NSE"),
    ("^CNXIT", "NIFTY IT", "NSE"),
    ("^CNXAUTO", "NIFTY AUTO", "NSE"),
    ("^CNXPHARMA", "NIFTY PHARMA", "NSE"),
    ("^CNXFMCG", "NIFTY FMCG", "NSE"),
    ("^CNXMETAL", "NIFTY METAL", "NSE"),
    ("^NSMIDCP", "NIFTY MIDCAP 100", "NSE"),
    ("^BSESN", "S&P BSE SENSEX", "BSE"),
    ("^GSPC", "S&P 500", "US"),
    ("^IXIC", "NASDAQ COMPOSITE", "US"),
    ("^DJI", "DOW JONES", "US"),
    ("^FTSE", "FTSE 100", "UK"),
    ("^N225", "NIKKEI 225", "JP"),
]

_YAHOO_CACHE: dict[str, tuple[float, list[dict]]] = {}
_CACHE_TTL = 900.0


# --------------------------------------------------------------------------- #
# Local index (offline)
# --------------------------------------------------------------------------- #
def _scrip_master(refresh: bool = False) -> list[dict]:
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / "angel_scrip_master.json"
    stale = not path.exists() or (time.time() - path.stat().st_mtime) > 86_400
    if stale or refresh:
        log.info("downloading scrip master")
        req = urllib.request.Request(SCRIP_URL, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=90) as resp:
            path.write_bytes(resp.read())
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def local_index() -> list[dict]:
    """Every tradable NSE/BSE equity, mapped to the symbol yfinance expects."""
    out = [{"symbol": s, "name": n, "exchange": e, "type": "INDEX"}
           for s, n, e in INDICES]
    try:
        rows = _scrip_master()
    except Exception as exc:
        log.warning("scrip master unavailable (%s); indices only", exc)
        return out

    seen = {r["symbol"] for r in out}
    for r in rows:
        seg, sym = r.get("exch_seg"), str(r.get("symbol", ""))
        if seg == "NSE" and sym.endswith("-EQ"):
            base, suffix = sym[:-3], ".NS"
        elif seg == "BSE" and r.get("instrumenttype", "") in ("", "EQ"):
            base, suffix = sym.replace("-EQ", ""), ".BO"
        else:
            continue
        full = f"{base}{suffix}"
        if full in seen:
            continue
        seen.add(full)
        out.append({"symbol": full, "name": str(r.get("name") or base),
                    "exchange": seg, "type": "EQUITY"})
    log.info("local symbol index: %d entries", len(out))
    return out


def _rank(entry: dict, q: str) -> int:
    """Lower is better. Exact ticker beats prefix beats substring."""
    sym = entry["symbol"].upper()
    base = sym.split(".")[0].lstrip("^")
    name = entry["name"].upper()
    if base == q or sym == q:
        return 0
    if base.startswith(q):
        return 1
    if name.startswith(q):
        return 2
    if q in base:
        return 3
    if q in name:
        return 4
    return 9


def search_local(query: str, limit: int = 20) -> list[dict]:
    q = query.strip().upper()
    if not q:
        return []
    scored = []
    for e in local_index():
        r = _rank(e, q)
        if r < 9:
            scored.append((r, len(e["symbol"]), e))
    scored.sort(key=lambda t: (t[0], t[1]))
    return [e for _, _, e in scored[:limit]]


# --------------------------------------------------------------------------- #
# Yahoo (online, better names, global)
# --------------------------------------------------------------------------- #
def search_yahoo(query: str, limit: int = 12) -> list[dict]:
    q = query.strip()
    if not q:
        return []
    key = f"{q.lower()}|{limit}"
    hit = _YAHOO_CACHE.get(key)
    if hit and (time.time() - hit[0]) < _CACHE_TTL:
        return hit[1]

    req = urllib.request.Request(
        YAHOO_URL.format(q=urllib.parse.quote(q), n=limit),
        headers={"User-Agent": UA},
    )
    with urllib.request.urlopen(req, timeout=12) as resp:
        data = json.load(resp)

    out = []
    for item in data.get("quotes", []):
        sym = item.get("symbol")
        if not sym or item.get("quoteType") not in ("EQUITY", "ETF", "INDEX", "MUTUALFUND"):
            continue
        out.append({
            "symbol": sym,
            "name": item.get("shortname") or item.get("longname") or sym,
            "exchange": item.get("exchange") or "",
            "type": item.get("quoteType"),
        })
    _YAHOO_CACHE[key] = (time.time(), out)
    return out


def search(query: str, limit: int = 20) -> dict:
    """Yahoo first, local index as the offline fallback.

    Indian results are floated to the top: this is an NSE/BSE-first tool, and a
    user typing "TATA" wants Tata Motors on the NSE, not a Frankfurt listing.
    """
    q = query.strip()
    if not q:
        return {"results": [], "source": "none"}

    source = "yahoo"
    try:
        results = search_yahoo(q, limit)
    except Exception as exc:
        log.warning("yahoo search failed (%s); using local index", exc)
        results, source = [], "local"

    if not results:
        results, source = search_local(q, limit), "local"
    else:
        # Backfill with local hits Yahoo missed (delisted, thin, BSE-only names).
        have = {r["symbol"] for r in results}
        results += [e for e in search_local(q, limit) if e["symbol"] not in have]

    qq = q.upper()

    def sort_key(r):
        sym = r["symbol"].upper()
        base = sym.split(".")[0].lstrip("^")
        # Exact ticker wins outright -- searching "AAPL" must surface Apple, not
        # a BSE listing that merely contains those letters.
        exact = 0 if (base == qq or sym == qq) else 1
        prefix = 0 if base.startswith(qq) else 1
        # Only then prefer home exchanges: this is an NSE/BSE-first tool.
        india = (0 if (sym.endswith(".NS") or sym.startswith("^NSE")) else
                 1 if sym.endswith(".BO") else 2)
        return (exact, prefix, india, len(sym))

    results.sort(key=sort_key)
    return {"results": results[:limit], "source": source}
