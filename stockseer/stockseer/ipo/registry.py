"""IPO registry, sourced from NSE's own public endpoints.

NSE publishes both a past-issues archive (~1,400 entries with issue price and
listing date) and an upcoming-issues list. No key, no scraping, no paid feed --
it is the exchange's own data.

The endpoints require a session cookie obtained by first hitting the homepage;
without it they return 401. That is NSE's bot-deterrent, not an access
restriction, and one homepage fetch per session satisfies it.

**Mainboard and SME issues are kept separate throughout.** They behave like
different asset classes: SME issues are thinly traded, have far wider listing
swings, and a strategy measured on one says nothing about the other.
"""

from __future__ import annotations

import http.cookiejar
import json
import logging
import re
import time
import urllib.request
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path

log = logging.getLogger(__name__)

CACHE = Path(__file__).resolve().parent.parent.parent / "cache"
BASE = "https://www.nseindia.com"
PAST = "/api/public-past-issues"
UPCOMING = "/api/all-upcoming-issues?category=ipo"
CACHE_TTL = 6 * 3600

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": f"{BASE}/market-data/all-upcoming-issues-ipo",
}


@dataclass
class IPO:
    symbol: str                  # NSE symbol, e.g. ARDEE
    company: str
    issue_price: float | None
    listing_date: str | None     # ISO date, or None if not yet listed
    price_range: str = ""
    security_type: str = "EQ"    # EQ = mainboard, SME = small/medium platform
    ipo_start: str | None = None
    ipo_end: str | None = None

    @property
    def yf_symbol(self) -> str:
        return f"{self.symbol}.NS"

    @property
    def is_sme(self) -> bool:
        return self.security_type.upper() == "SME"

    @property
    def listed(self) -> bool:
        return bool(self.listing_date)

    def listing_day(self) -> date | None:
        return date.fromisoformat(self.listing_date) if self.listing_date else None


# --------------------------------------------------------------------------- #
def _opener():
    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    op.addheaders = list(HEADERS.items())
    op.open(BASE, timeout=25).read()      # seeds the session cookie
    return op


def _fetch(path: str) -> list[dict]:
    op = _opener()
    with op.open(BASE + path, timeout=30) as resp:
        data = json.load(resp)
    return data if isinstance(data, list) else data.get("data", [])


def _cached(name: str, path: str, refresh: bool = False) -> list[dict]:
    CACHE.mkdir(parents=True, exist_ok=True)
    fp = CACHE / f"nse_{name}.json"
    fresh = fp.exists() and (time.time() - fp.stat().st_mtime) < CACHE_TTL
    if fresh and not refresh:
        return json.loads(fp.read_text(encoding="utf-8"))
    try:
        rows = _fetch(path)
        fp.write_text(json.dumps(rows), encoding="utf-8")
        return rows
    except Exception as exc:
        if fp.exists():
            log.warning("NSE %s unavailable (%s); using cached copy", name, exc)
            return json.loads(fp.read_text(encoding="utf-8"))
        raise


def _parse_date(raw: str | None) -> str | None:
    """NSE mixes '12-AUG-2026' and '12-Aug-2026'; '-' means not yet listed."""
    if not raw or raw.strip() in ("-", ""):
        return None
    for fmt in ("%d-%b-%Y", "%d-%B-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw.strip(), fmt).date().isoformat()
        except ValueError:
            continue
    log.debug("unparsed listing date %r", raw)
    return None


def _parse_price(raw) -> float | None:
    if raw is None:
        return None
    s = str(raw).replace(",", "").strip()
    if s in ("-", ""):
        return None
    m = re.search(r"\d+(?:\.\d+)?", s)
    return float(m.group()) if m else None


def _to_ipo(row: dict) -> IPO | None:
    """Normalise a row from either NSE endpoint.

    The two endpoints do not agree on field names: past-issues uses
    ``ipoStartDate`` / ``company``, while upcoming-issues uses
    ``issueStartDate`` / ``companyName``. Reading only one set silently yields
    IPOs with no dates -- which looks like an empty calendar rather than a bug.
    """
    symbol = (row.get("symbol") or "").strip().upper()
    if not symbol:
        return None

    raw_price = row.get("issuePrice")
    price_range = (row.get("priceRange") or "").strip()
    # On upcoming issues `issuePrice` carries the band ("Rs.92 to Rs.97"); once
    # priced it becomes a single number and priceRange holds the band.
    if not price_range and isinstance(raw_price, str) and " to " in raw_price:
        price_range = raw_price.strip()

    return IPO(
        symbol=symbol,
        company=(row.get("company") or row.get("companyName") or symbol).strip(),
        issue_price=_parse_price(raw_price),
        listing_date=_parse_date(row.get("listingDate")),
        price_range=price_range,
        security_type=(row.get("securityType") or "EQ").strip().upper(),
        ipo_start=_parse_date(row.get("ipoStartDate") or row.get("issueStartDate")),
        ipo_end=_parse_date(row.get("ipoEndDate") or row.get("issueEndDate")),
    )


# --------------------------------------------------------------------------- #
def past_issues(refresh: bool = False, mainboard_only: bool = False) -> list[IPO]:
    """Historical IPOs, newest first. Only those with a real issue price."""
    out = []
    for row in _cached("past_issues", PAST, refresh):
        ipo = _to_ipo(row)
        if ipo and ipo.issue_price and (not mainboard_only or not ipo.is_sme):
            out.append(ipo)
    out.sort(key=lambda i: i.listing_date or "", reverse=True)
    return out


def upcoming_issues(refresh: bool = False) -> list[IPO]:
    """Open and announced issues -- what you can still apply for."""
    rows = _cached("upcoming_issues", UPCOMING, refresh)
    return [i for i in (_to_ipo(r) for r in rows) if i]


def listing_today(when: date | None = None, refresh: bool = False) -> list[IPO]:
    """IPOs listing on a given day -- the ones the watcher should arm for."""
    when = when or date.today()
    return [i for i in past_issues(refresh) if i.listing_day() == when]


def upcoming_listings(days: int = 14, refresh: bool = False) -> list[IPO]:
    """Already-priced issues whose listing date is in the near future."""
    today = date.today()
    out = []
    for ipo in past_issues(refresh):
        d = ipo.listing_day()
        if d and today <= d <= date.fromordinal(today.toordinal() + days):
            out.append(ipo)
    return sorted(out, key=lambda i: i.listing_date or "")


def refresh_registry() -> dict[str, int]:
    past = past_issues(refresh=True)
    upcoming = upcoming_issues(refresh=True)
    return {
        "past": len(past),
        "mainboard": sum(1 for i in past if not i.is_sme),
        "sme": sum(1 for i in past if i.is_sme),
        "upcoming": len(upcoming),
    }


def find(symbol: str) -> IPO | None:
    s = symbol.upper().replace(".NS", "")
    return next((i for i in past_issues() if i.symbol == s), None)


def to_dict(ipo: IPO) -> dict:
    return {**asdict(ipo), "yf_symbol": ipo.yf_symbol, "is_sme": ipo.is_sme}


# --------------------------------------------------------------------------- #
# Live subscription (how many times the book is covered)
# --------------------------------------------------------------------------- #
SUBSCRIPTION = "/api/ipo-active-category?symbol={symbol}"


@dataclass
class Subscription:
    """Official NSE demand figures, published live while bidding is open.

    Preferred over grey-market premium: GMP is an unregulated rumour quoted by
    dealers with a position, while this is the exchange reporting how many
    times the book is actually covered.
    """

    symbol: str
    retail_x: float | None
    qib_x: float | None
    nii_x: float | None
    updated: str = ""

    @property
    def summary(self) -> str:
        parts = []
        if self.retail_x is not None:
            parts.append(f"Retail {self.retail_x:.1f}x")
        if self.qib_x is not None:
            parts.append(f"QIB {self.qib_x:.1f}x")
        if self.nii_x is not None:
            parts.append(f"NII {self.nii_x:.1f}x")
        return "  ".join(parts) or "no bids yet"


def _as_float(val) -> float | None:
    try:
        f = float(str(val).strip())
        return f if f == f else None
    except (TypeError, ValueError):
        return None


def subscription(symbol: str) -> Subscription | None:
    """Fetch live demand for one open issue. Returns None if unavailable."""
    try:
        op = _opener()
        raw = op.open(BASE + SUBSCRIPTION.format(symbol=symbol.upper()),
                      timeout=25).read().decode("utf-8", "replace")
        data = json.loads(raw)
    except Exception as exc:
        log.info("%s: subscription unavailable (%s)", symbol, exc)
        return None

    rows = data.get("dataList") or []
    out = {"retail": None, "qib": None, "nii": None}
    for row in rows:
        cat = str(row.get("category", "")).lower()
        times = _as_float(row.get("noOfTotalMeant"))
        if times is None:
            continue
        # Match only the top-level rows; the sub-rows (1(a), 2.1 ...) break
        # the totals down and would otherwise overwrite them.
        sr = str(row.get("srNo", "")).strip()
        if sr == "3" and "retail" in cat:
            out["retail"] = times
        elif sr == "1" and "qualified institutional" in cat:
            out["qib"] = times
        elif sr == "2" and "non institutional" in cat:
            out["nii"] = times

    if all(v is None for v in out.values()):
        return None
    return Subscription(symbol=symbol.upper(), retail_x=out["retail"],
                        qib_x=out["qib"], nii_x=out["nii"],
                        updated=str(data.get("updateTime", "")))
