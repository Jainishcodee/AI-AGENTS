"""A shared-secret gate, for when the API stops being a localhost toy.

Until now there was none, which was defensible while the only client was a browser on the
same machine. It stops being defensible the moment a phone reaches this over a tunnel:
every route is unauthenticated, and the corpus behind them is the most personal thing this
project holds — what you were deciding, what you feared, what you were avoiding.

**Opt-in, not opt-out.** With `COUNCIL_TOKEN` unset the gate is inert and localhost keeps
working with no configuration. Requiring a token by default would mean the first thing
anybody does is turn it off, and a security control people routinely disable is worse than
an honest absence of one.

Deliberately not OAuth, JWTs or users. There is one user and one device; a shared secret in
a header is the whole threat model, and anything more would be machinery protecting a
single-tenant SQLite file.
"""

from __future__ import annotations

import hmac

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from ..core.logging import get_logger

log = get_logger(__name__)

HEADER = "X-Council-Token"

OPEN_PATHS: frozenset[str] = frozenset({"/health", "/docs", "/openapi.json", "/redoc"})
"""Reachable without the token.

`/health` is open on purpose: a tunnel or a phone needs to answer "is the PC up?" before
it has any business asking for decisions, and the answer leaks nothing.
"""


class TokenMiddleware(BaseHTTPMiddleware):
    """Reject anything without the shared secret, when one is configured."""

    def __init__(self, app, token: str | None) -> None:
        super().__init__(app)
        self._token = (token or "").strip()
        if self._token:
            log.info("API token required (header: %s)", HEADER)

    async def dispatch(self, request: Request, call_next):
        if not self._token:
            return await call_next(request)
        if request.method == "OPTIONS" or request.url.path in OPEN_PATHS:
            # CORS preflight carries no custom headers by definition, so gating it would
            # break the browser client without adding any protection.
            return await call_next(request)

        supplied = request.headers.get(HEADER, "")
        # Constant-time: a plain `!=` leaks the secret's prefix through timing, which is
        # cheap to avoid and embarrassing to explain.
        if not hmac.compare_digest(supplied, self._token):
            return JSONResponse(
                status_code=401,
                content={"detail": f"missing or invalid {HEADER}"},
            )
        return await call_next(request)
