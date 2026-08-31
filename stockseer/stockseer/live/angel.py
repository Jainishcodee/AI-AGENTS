"""Angel One SmartAPI feed.

**One key is enough.** An earlier version of this file claimed SmartAPI issues
a separate, non-interchangeable key per app type. That was wrong, and it was
wrong twice over: a single Trading API key was measured serving both
``ltpData`` (live quotes) and ``getCandleData`` (historical candles)
successfully. Set ``ANGEL_API_KEY`` and nothing else.

``AG8004 Invalid API Key`` is what misled us. It is not an entitlement error --
it is returned transiently on a perfectly healthy key, typically under rate
limiting, and once for a key that had simply been pasted a character short.
Diagnose it by reading the actual response, never by assuming a missing app.

    ANGEL_API_KEY         your app's API key -- used for everything
    ANGEL_MARKET_KEY      optional override, only if you really do keep
    ANGEL_HISTORICAL_KEY  separate apps; both default to ANGEL_API_KEY

    ANGEL_CLIENT_ID       your client code, e.g. A123456
    ANGEL_PIN             login PIN
    ANGEL_TOTP_SECRET     the base32 secret from Enable TOTP, not the 6-digit code

None of this needs order permissions -- StockSeer never places a trade.
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from .feed import IST, Feed, Quote, _normalise

log = logging.getLogger(__name__)

SCRIP_MASTER_URL = (
    "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
)
CACHE = Path(__file__).resolve().parent.parent.parent / "cache"

INTERVALS = {
    "1m": "ONE_MINUTE", "3m": "THREE_MINUTE", "5m": "FIVE_MINUTE",
    "10m": "TEN_MINUTE", "15m": "FIFTEEN_MINUTE", "30m": "THIRTY_MINUTE",
    "60m": "ONE_HOUR", "1d": "ONE_DAY",
}
MAX_DAYS_PER_CALL = {
    "ONE_MINUTE": 30, "THREE_MINUTE": 60, "FIVE_MINUTE": 100,
    "TEN_MINUTE": 100, "FIFTEEN_MINUTE": 200, "THIRTY_MINUTE": 200,
    "ONE_HOUR": 400, "ONE_DAY": 2000,
}

# Reliance -- the canonical liquid probe symbol.
PROBE = ("NSE", "RELIANCE-EQ", "2885")


def public_ip(timeout: int = 8) -> str:
    """This machine's public IP, as Angel's IP whitelist sees it."""
    import urllib.request

    for url in ("https://api.ipify.org", "https://ifconfig.me/ip"):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as resp:
                ip = resp.read().decode().strip()
                if ip.count(".") == 3:
                    return ip
        except Exception:
            continue
    return ""


def _fix_sdk_public_ip(api) -> str:
    """Work around a bug in smartapi-python.

    ``SmartConnect`` looks up the real public IP, then discards it in a
    ``finally:`` block that hardcodes ``106.193.147.98`` -- a developer's own
    address left in the shipped library (smartConnect.py:71-81). Every user
    therefore sends that same IP in ``X-ClientPublicIP``.

    Harmless until you register a Primary Static IP on the app, at which point
    Angel compares the header against your whitelist, sees a stranger's address,
    and rejects every market-data call with ``AG8004 Invalid API Key`` -- an
    error that says nothing about IPs. Login and getProfile skip the check,
    which is why credentials look fine while all data calls fail.
    """
    ip = public_ip()
    if ip:
        api.clientPublicIp = ip
        log.debug("patched SDK public IP -> %s", ip)
    return ip


def _load_dotenv() -> None:
    """Kept as an alias so existing callers and scripts keep working.

    The implementation lives in `config`, which imports nothing third-party.
    """
    from ..config import load_dotenv

    load_dotenv()


def _why(resp) -> str:
    """Render SmartAPI's own explanation of a refusal.

    SmartAPI answers a rejected call with ``status: False`` plus an errorcode
    and message rather than an exception, so a caller that only checks the
    boolean throws away the one piece of information worth having.
    """
    if not isinstance(resp, dict):
        return f"unexpected response: {str(resp)[:120]}"
    code = resp.get("errorcode") or "?"
    msg = resp.get("message") or "no message"
    return f"{code} {msg}"


class AngelError(RuntimeError):
    pass


class AngelFeed(Feed):
    name = "angel-one"
    delayed_seconds = 0

    def __init__(self, market_key: str, historical_key: str,
                 client_id: str, pin: str, totp_secret: str):
        self._keys = {"market": market_key, "historical": historical_key}
        self._client_id = client_id
        self._pin = pin
        self._totp_secret = totp_secret
        self._sessions: dict[str, object] = {}
        self._scrips: pd.DataFrame | None = None
        self._entitled: dict[str, bool] = {}
        # Why each probe failed, kept verbatim. Guessing at the cause is what
        # produced two rounds of chasing app types that were never the problem.
        self._probe_error: dict[str, str] = {}

    # ------------------------------------------------------------------ #
    # Sessions -- one per distinct API key
    # ------------------------------------------------------------------ #
    def _session(self, capability: str):
        key = self._keys[capability]
        if key in self._sessions:
            return self._sessions[key]

        from SmartApi import SmartConnect

        import pyotp

        api = SmartConnect(api_key=key)
        _fix_sdk_public_ip(api)
        last = None
        for attempt in range(3):
            code = pyotp.TOTP(self._totp_secret).now()
            res = api.generateSession(self._client_id, self._pin, code)
            if res and res.get("status"):
                self._sessions[key] = api
                log.info("Angel One session established for %s (%s)",
                         self._client_id, capability)
                return api
            last = (res or {}).get("message", "unknown error")
            # A TOTP can be rejected as replayed when two logins land in the same
            # 30s window; waiting for the next one costs less than failing.
            if "totp" in str(last).lower() and attempt < 2:
                time.sleep(31)
                continue
            break
        raise AngelError(f"login failed ({capability}): {last}")

    def check_entitlements(self, attempts: int = 3, pause: float = 2.0) -> dict[str, bool]:
        """Probe what each key can actually reach.

        Retried, because SmartAPI intermittently returns ``AG8004`` on a healthy
        key -- a rate limit or a momentary blip. Treating one bad probe as
        permanent silently downgrades the whole session to 15-minute delayed
        Yahoo data, and you find out on listing morning when the prices you are
        acting on are a quarter of an hour stale.
        """
        out: dict[str, bool] = {}
        delay = pause
        for attempt in range(attempts):
            self._probe_error.clear()      # keep only the final attempt's cause
            out = self._probe_once()
            if all(out.values()):
                break
            if attempt < attempts - 1:
                # Backs off rather than repeating at a fixed interval, because
                # the usual cause is rate limiting and three probes two seconds
                # apart is itself a burst.
                log.info("probe %s (%s); retrying in %.0fs", out,
                         self._probe_error or "no detail", delay)
                time.sleep(delay)
                delay *= 2
        self._entitled = out
        return out

    def _probe_once(self) -> dict[str, bool]:
        exch, tsym, token = PROBE
        out = {}
        try:
            r = self._session("market").ltpData(exch, tsym, token)
            out["market"] = bool(r and r.get("status"))
            if not out["market"]:
                self._probe_error["market"] = _why(r)
        except Exception as exc:
            log.debug("market probe failed: %s", exc)
            self._probe_error["market"] = f"{type(exc).__name__}: {exc}"
            out["market"] = False
        try:
            end = datetime.now()
            r = self._session("historical").getCandleData({
                "exchange": exch, "symboltoken": token, "interval": "FIVE_MINUTE",
                "fromdate": (end - timedelta(days=3)).strftime("%Y-%m-%d %H:%M"),
                "todate": end.strftime("%Y-%m-%d %H:%M"),
            })
            out["historical"] = bool(r and r.get("status"))
            if not out["historical"]:
                self._probe_error["historical"] = _why(r)
        except Exception as exc:
            log.debug("historical probe failed: %s", exc)
            self._probe_error["historical"] = f"{type(exc).__name__}: {exc}"
            out["historical"] = False
        return out

    @classmethod
    def from_env(cls, require: tuple[str, ...] = ("market", "historical")) -> AngelFeed:
        _load_dotenv()
        base = os.environ.get("ANGEL_API_KEY", "")
        market = os.environ.get("ANGEL_MARKET_KEY") or base
        hist = os.environ.get("ANGEL_HISTORICAL_KEY") or base

        missing = [k for k in ("ANGEL_CLIENT_ID", "ANGEL_PIN", "ANGEL_TOTP_SECRET")
                   if not os.environ.get(k)]
        if not (market or hist):
            missing.append("ANGEL_API_KEY")
        if missing:
            raise AngelError(f"missing credentials: {', '.join(missing)}")

        feed = cls(market, hist, os.environ["ANGEL_CLIENT_ID"],
                   os.environ["ANGEL_PIN"], os.environ["ANGEL_TOTP_SECRET"])
        ent = feed.check_entitlements()
        lacking = [c for c in require if not ent.get(c)]
        if lacking:
            # Report what the API actually said. The previous message named a
            # cause -- "these keys lack entitlement, go and create the matching
            # app" -- that the evidence never supported, and acting on it meant
            # hunting for app types that do not gate anything. A single key was
            # measured serving both endpoints.
            why = "; ".join(f"{c}: {feed._probe_error.get(c, 'no detail')}"
                            for c in lacking)
            raise AngelError(
                f"login succeeded but {', '.join(lacking)} did not respond -- {why}. "
                f"AG8004 here usually means rate limiting rather than a bad key, "
                f"so retry before changing anything. Verify the key is complete "
                f"(a truncated key produces the same error) and confirm it works "
                f"at https://smartapi.angelone.in/."
            )
        return feed

    def describe(self) -> str:
        ent = self._entitled or {}
        live = [k for k, v in ent.items() if v]
        return f"{self.name} (real-time; {', '.join(live) or 'no'} data)"

    # ------------------------------------------------------------------ #
    # Symbol resolution
    # ------------------------------------------------------------------ #
    def _scrip_master(self, refresh: bool = False) -> pd.DataFrame:
        """The instrument master, cached for a day.

        Angel identifies instruments by numeric token, not ticker, so every
        lookup goes through this ~5MB file. A stock listing today only appears
        after the file refreshes -- hence ``refresh`` for IPO mornings.
        """
        if self._scrips is not None and not refresh:
            return self._scrips

        CACHE.mkdir(parents=True, exist_ok=True)
        path = CACHE / "angel_scrip_master.json"
        stale = not path.exists() or (time.time() - path.stat().st_mtime) > 86_400
        if stale or refresh:
            import urllib.request

            log.info("downloading Angel One scrip master")
            with urllib.request.urlopen(SCRIP_MASTER_URL, timeout=90) as resp:
                path.write_bytes(resp.read())

        self._scrips = pd.DataFrame(json.loads(path.read_text(encoding="utf-8")))
        return self._scrips

    def resolve(self, symbol: str, exchange: str = "NSE",
                refresh: bool = False) -> tuple[str, str, str]:
        """Map a ticker to (exchange, tradingsymbol, symboltoken)."""
        base = symbol.upper().replace(".NS", "").replace(".BO", "")
        if symbol.upper().endswith(".BO"):
            exchange = "BSE"

        df = self._scrip_master(refresh)
        cand = df[(df["exch_seg"] == exchange) & (df["symbol"] == f"{base}-EQ")]
        if cand.empty:
            cand = df[(df["exch_seg"] == exchange) & (df["name"] == base)]
        if cand.empty and not refresh:
            # Probably listed today; the cached master predates it.
            return self.resolve(symbol, exchange, refresh=True)
        if cand.empty:
            raise AngelError(f"{symbol!r} not found in the {exchange} scrip master")
        row = cand.iloc[0]
        return exchange, str(row["symbol"]), str(row["token"])

    # ------------------------------------------------------------------ #
    # Data
    # ------------------------------------------------------------------ #
    def history(self, symbol: str, interval: str = "5m", days: int = 30) -> pd.DataFrame:
        ang_interval = INTERVALS.get(interval)
        if ang_interval is None:
            raise ValueError(f"unsupported interval {interval!r}; use {sorted(INTERVALS)}")

        exchange, _, token = self.resolve(symbol)
        api = self._session("historical")
        chunk = MAX_DAYS_PER_CALL[ang_interval]
        end = datetime.now()
        frames, remaining = [], days

        # Long windows must be paged; the API rejects an oversized span outright.
        while remaining > 0:
            span = min(chunk, remaining)
            start = end - timedelta(days=span)
            resp = api.getCandleData({
                "exchange": exchange, "symboltoken": token, "interval": ang_interval,
                "fromdate": start.strftime("%Y-%m-%d %H:%M"),
                "todate": end.strftime("%Y-%m-%d %H:%M"),
            })
            if not (resp and resp.get("status")):
                raise AngelError(f"candles for {symbol}: {(resp or {}).get('message')}")
            if resp.get("data"):
                frames.append(pd.DataFrame(
                    resp["data"],
                    columns=["at", "Open", "High", "Low", "Close", "Volume"],
                ))
            remaining -= span
            end = start
            time.sleep(0.35)          # SmartAPI historical limit is 3 req/s

        if not frames:
            raise AngelError(f"no {interval} candles returned for {symbol}")

        df = pd.concat(frames, ignore_index=True)
        df["at"] = pd.to_datetime(df["at"], format="ISO8601", utc=True).dt.tz_convert(IST)
        return _normalise(df.set_index("at").sort_index())

    def quote(self, symbol: str) -> Quote:
        exchange, tsym, token = self.resolve(symbol)
        resp = self._session("market").ltpData(exchange, tsym, token)
        data = (resp or {}).get("data")
        if not data:
            raise AngelError(f"no LTP for {symbol}: {(resp or {}).get('message')}")

        ltp = float(data["ltp"])
        close = float(data.get("close") or 0.0)
        return Quote(
            symbol=symbol, price=ltp, at=datetime.now().astimezone(),
            change_pct=(ltp / close - 1.0) if close else None,
            delayed_seconds=0,
        )

    def logout(self) -> None:
        for api in self._sessions.values():
            try:
                api.terminateSession(self._client_id)
            except Exception as exc:
                log.debug("logout failed: %s", exc)
