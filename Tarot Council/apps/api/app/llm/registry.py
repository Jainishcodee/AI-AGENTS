"""Role-based routing, retry, concurrency, and cross-provider fallback (ADR-005).

Call sites ask for a *role* — `intake`, `reasoning`, `synthesis` — never a model
name. Tuning cost and quality is three environment variables.
"""

from __future__ import annotations

import asyncio
import random
import time
from collections.abc import Callable
from typing import Any

from ..core.config import ModelRoute, Role, Settings
from ..core.errors import ProviderError
from ..core.logging import get_logger
from .base import LLMProvider, LLMRequest, LLMResponse
from .providers import (
    GeminiProvider,
    MockProvider,
    OllamaProvider,
    OpenRouterProvider,
)

log = get_logger(__name__)

Fixups = dict[str, Callable[[dict[str, Any], str], dict[str, Any]]]

RATE_LIMIT_BASE_DELAY = 12.0
"""429 backoff floor, in seconds.

Free-tier limits are per *minute*, so the usual 1-2-4 second exponential backoff
retries three times inside the same window and fails all three. Waiting a
meaningful fraction of a minute is the only backoff that can succeed.
"""


class _RateLimiter:
    """Sliding-window limiter on requests per minute.

    A semaphore caps how many calls are in flight; it cannot cap how many happen per
    minute, which is what free tiers actually meter. Without this, a 26-call
    deliberation fires 26 requests in ten seconds and most of them 429.
    """

    def __init__(self, per_minute: int) -> None:
        self._per_minute = max(1, per_minute)
        self._times: list[float] = []
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        while True:
            async with self._lock:
                now = time.monotonic()
                self._times = [t for t in self._times if now - t < 60.0]
                if len(self._times) < self._per_minute:
                    self._times.append(now)
                    return
                wait = 60.0 - (now - self._times[0]) + 0.05
            log.debug("rate limit reached, waiting %.1fs", wait)
            await asyncio.sleep(wait)


class Router:
    """Owns the provider instances and the retry policy."""

    def __init__(
        self,
        settings: Settings,
        *,
        fixups: Fixups | None = None,
        force_provider: str | None = None,
    ) -> None:
        self._settings = settings
        self._fixups = fixups or {}
        self._force = force_provider
        self._providers: dict[str, LLMProvider] = {}
        # Two independent limits: how many calls are in flight, and how many per
        # minute. Free tiers meter the second one.
        self._gate = asyncio.Semaphore(settings.max_concurrency)
        self._pace = _RateLimiter(settings.max_rpm) if settings.max_rpm else None

    # ------------------------------------------------------------- providers --

    def _provider(self, name: str) -> LLMProvider:
        if name in self._providers:
            return self._providers[name]
        s = self._settings
        timeout = s.request_timeout_s
        if name == "mock":
            provider: LLMProvider = MockProvider(self._fixups)
        elif name == "gemini":
            if not s.gemini_api_key:
                raise ProviderError("gemini", "GEMINI_API_KEY is not set")
            provider = GeminiProvider(s.gemini_api_key, timeout=timeout)
        elif name == "openrouter":
            if not s.openrouter_api_key:
                raise ProviderError("openrouter", "OPENROUTER_API_KEY is not set")
            provider = OpenRouterProvider(s.openrouter_api_key, timeout=timeout)
        elif name == "ollama":
            provider = OllamaProvider(s.ollama_host, timeout=timeout)
        else:
            raise ProviderError(name, f"unknown provider {name!r}")
        self._providers[name] = provider
        return provider

    def route_for(self, role: Role) -> ModelRoute:
        route = self._settings.route(role)
        if self._force:
            # `--provider mock` overrides routing entirely, including the model
            # name, so a mock run needs no credentials of any kind.
            return ModelRoute(provider=self._force, name=f"{self._force}-{role}")
        return route

    # ----------------------------------------------------------------- calls --

    async def complete(
        self, role: Role, request: LLMRequest, *, override: str | None = None
    ) -> LLMResponse:
        route = ModelRoute.parse(override) if override and not self._force else self.route_for(role)
        attempts = self._settings.max_retries + 1
        last: ProviderError | None = None

        # The mock provider never touches the network, so pacing it would only make
        # the test suite slow.
        paced = self._pace if route.provider != "mock" else None

        async with self._gate:
            for attempt in range(1, attempts + 1):
                if paced is not None:
                    await paced.acquire()
                try:
                    provider = self._provider(route.provider)
                    return await provider.complete(request, route.name)
                except ProviderError as exc:
                    last = exc
                    if not exc.retryable or attempt == attempts:
                        break
                    delay = _backoff(attempt, rate_limited=_is_rate_limit(exc))
                    log.warning(
                        "%s attempt %d/%d failed (%s); retrying in %.0fs",
                        request.tag or role,
                        attempt,
                        attempts,
                        str(exc)[:160],
                        delay,
                    )
                    await asyncio.sleep(delay)

            fallback = self._settings.fallback_route
            if fallback and not self._force and fallback.provider != route.provider:
                log.warning(
                    "%s falling back to %s after %s", request.tag or role, fallback, last
                )
                try:
                    provider = self._provider(fallback.provider)
                    return await provider.complete(request, fallback.name)
                except ProviderError as exc:
                    last = exc

        assert last is not None
        raise last

    async def aclose(self) -> None:
        for provider in self._providers.values():
            await provider.aclose()
        self._providers.clear()


def _is_rate_limit(exc: ProviderError) -> bool:
    text = str(exc)
    return "429" in text or "quota" in text.lower() or "rate limit" in text.lower()


def _backoff(attempt: int, *, rate_limited: bool) -> float:
    if rate_limited:
        # Per-minute quota: back off in tens of seconds, not single digits.
        return min(RATE_LIMIT_BASE_DELAY * attempt, 45.0) * (0.85 + random.random() * 0.3)
    return min(2 ** (attempt - 1), 8) * (0.6 + random.random() * 0.8)
