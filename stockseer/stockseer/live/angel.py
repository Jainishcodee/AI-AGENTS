"""Angel One SmartAPI feed.

Free, real-time, and it needs four secrets in the environment (or a ``.env``
beside the repo root):

    ANGEL_API_KEY      from https://smartapi.angelone.in/ -- create a "Market
                       Feed" app, which has no order permissions at all
    ANGEL_CLIENT_ID    your Angel One client code, e.g. A123456
    ANGEL_PIN          your login PIN
    ANGEL_TOTP_SECRET  the base32 secret shown when you enable TOTP, not the
                       6-digit code -- the code is generated fresh each login

Use a market-feed app rather than a trading app. This system never needs to place
an order, so it should not hold the ability to.
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

# SmartAPI interval names, keyed by the interval strings the rest of the app uses.
INTERVALS = {
    "1m": "ONE_MINUTE", "3m": "THREE_MINUTE", "5m": "FIVE_MINUTE",
    "10m": "TEN_MINUTE", "15m": "FIFTEEN_MINUTE", "30m": "THIRTY_MINUTE",
    "60m": "ONE_HOUR", "1d": "ONE_DAY",
}

# getCandleData caps the span per request; smaller intervals get shorter windows.
MAX_DAYS_PER_CALL = {
    "ONE_MINUTE": 30, "THREE_MINUTE": 60, "FIVE_MINUTE": 100,
    "TEN_MINUTE": 100, "FIFTEEN_MINUTE": 200, "THIRTY_MINUTE": 200,
    "ONE_HOUR": 400, "ONE_DAY": 2000,
}


def _load_dotenv() -> None:
    """Minimal .env reader -- avoids a dependency for four variables.

    Searches the repo root, the package directory, and the working directory,
    because "which folder does .env go in" is a guess everyone gets wrong once
    and the failure mode is an unhelpful "missing credentials".
    """
    here = Path(__file__).resolve()
    candidates = (
        here.parents[2] / ".env",      # repo root:      stockseer/.env
        here.parents[1] / ".env",      # package dir:    stockseer/stockseer/.env
        here.parents[0] / ".env",      # live/ dir
        Path.cwd() / ".env",
    )
    for candidate in candidates:
        if not candidate.exists():
            continue
        log.debug("loading credentials from %s", candidate)
        for line in candidate.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip().strip("\"'"))


class AngelFeed(Feed):
    name = "angel-one"
    delayed_seconds = 0

    def __init__(self, api_key: str, client_id: str, pin: str, totp_secret: str):
        from SmartApi import SmartConnect

        import pyotp

        self._api_key = api_key
        self._client_id = client_id
        self.api = SmartConnect(api_key=api_key)
        totp = pyotp.TOTP(totp_secret).now()
        session = self.api.generateSession(client_id, pin, totp)

        if not session or not session.get("status"):
            msg = (session or {}).get("message", "unknown error")
            raise RuntimeError(f"Angel One login failed: {msg}")

        self._jwt = session["data"]["jwtToken"]
        self._feed_token = self.api.getfeedToken()
        self._scrips: pd.DataFrame | None = None
        log.info("Angel One session established for %s", client_id)

    @classmethod
    def from_env(cls) -> AngelFeed:
        _load_dotenv()
        needed = ("ANGEL_API_KEY", "ANGEL_CLIENT_ID", "ANGEL_PIN", "ANGEL_TOTP_SECRET")
        missing = [k for k in needed if not os.environ.get(k)]
        if missing:
            raise RuntimeError(f"missing credentials: {', '.join(missing)}")
        return cls(
            api_key=os.environ["ANGEL_API_KEY"],
            client_id=os.environ["ANGEL_CLIENT_ID"],
            pin=os.environ["ANGEL_PIN"],
            totp_secret=os.environ["ANGEL_TOTP_SECRET"],
        )

    # ------------------------------------------------------------------ #
    # Symbol resolution
    # ------------------------------------------------------------------ #
    def _scrip_master(self) -> pd.DataFrame:
        """The instrument master, cached for a day.

        Angel identifies instruments by numeric token, not ticker, so every
        lookup goes through this ~5MB file.
        """
        if self._scrips is not None:
            return self._scrips

        CACHE.mkdir(parents=True, exist_ok=True)
        path = CACHE / "angel_scrip_master.json"
        stale = (
            not path.exists()
            or (time.time() - path.stat().st_mtime) > 86_400
        )
        if stale:
            import urllib.request

            log.info("downloading Angel One scrip master")
            with urllib.request.urlopen(SCRIP_MASTER_URL, timeout=60) as resp:
                path.write_bytes(resp.read())

        rows = json.loads(path.read_text(encoding="utf-8"))
        df = pd.DataFrame(rows)
        self._scrips = df
        return df

    def resolve(self, symbol: str, exchange: str = "NSE") -> tuple[str, str]:
        """Map a ticker to (exchange, symboltoken).

        Accepts ``RELIANCE``, ``RELIANCE.NS`` or ``RELIANCE-EQ``.
        """
        base = symbol.upper().replace(".NS", "").replace(".BO", "")
        if symbol.upper().endswith(".BO"):
            exchange = "BSE"

        df = self._scrip_master()
        cand = df[(df["exch_seg"] == exchange) & (df["symbol"] == f"{base}-EQ")]
        if cand.empty:
            cand = df[(df["exch_seg"] == exchange) & (df["name"] == base)]
        if cand.empty:
            raise ValueError(
                f"{symbol!r} not found in the Angel One scrip master for {exchange}"
            )
        return exchange, str(cand.iloc[0]["token"])

    # ------------------------------------------------------------------ #
    # Data
    # ------------------------------------------------------------------ #
    def history(self, symbol: str, interval: str = "5m", days: int = 30) -> pd.DataFrame:
        ang_interval = INTERVALS.get(interval)
        if ang_interval is None:
            raise ValueError(f"unsupported interval {interval!r}; use {sorted(INTERVALS)}")

        exchange, token = self.resolve(symbol)
        chunk = MAX_DAYS_PER_CALL[ang_interval]
        end = datetime.now()
        frames = []
        remaining = days

        # Long windows must be paged; the API rejects an oversized span outright.
        while remaining > 0:
            span = min(chunk, remaining)
            start = end - timedelta(days=span)
            resp = self.api.getCandleData({
                "exchange": exchange,
                "symboltoken": token,
                "interval": ang_interval,
                "fromdate": start.strftime("%Y-%m-%d %H:%M"),
                "todate": end.strftime("%Y-%m-%d %H:%M"),
            })
            data = (resp or {}).get("data") or []
            if data:
                frames.append(pd.DataFrame(
                    data, columns=["at", "Open", "High", "Low", "Close", "Volume"]
                ))
            remaining -= span
            end = start
            time.sleep(0.35)  # SmartAPI rate limit is 3 req/s on historical

        if not frames:
            raise ValueError(f"Angel One returned no {interval} candles for {symbol}")

        df = pd.concat(frames, ignore_index=True)
        df["at"] = pd.to_datetime(df["at"], format="ISO8601", utc=True).dt.tz_convert(IST)
        df = df.set_index("at").sort_index()
        return _normalise(df)

    def quote(self, symbol: str) -> Quote:
        exchange, token = self.resolve(symbol)
        resp = self.api.ltpData(exchange, symbol.upper().replace(".NS", "") + "-EQ", token)
        data = (resp or {}).get("data")
        if not data:
            raise RuntimeError(f"no LTP for {symbol}: {(resp or {}).get('message')}")

        ltp = float(data["ltp"])
        close = float(data.get("close") or 0.0)
        return Quote(
            symbol=symbol,
            price=ltp,
            at=datetime.now().astimezone(),
            change_pct=(ltp / close - 1.0) if close else None,
            delayed_seconds=0,
        )

    def logout(self) -> None:
        try:
            self.api.terminateSession(self._client_id)
        except Exception as exc:
            log.debug("logout failed: %s", exc)
