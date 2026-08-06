"""Role-based routing, retry, concurrency, and cross-provider fallback (ADR-005).

Call sites ask for a *role* — `intake`, `reasoning`, `synthesis` — never a model
name. Tuning cost and quality is three environment variables.
"""

from __future__ import annotations

import asyncio
import random
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
        # Free tiers rate-limit per minute and six modules firing at once is the
        # usual trigger, so the cap is deliberately below the module count.
        self._gate = asyncio.Semaphore(settings.max_concurrency)

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

        async with self._gate:
            for attempt in range(1, attempts + 1):
                try:
                    provider = self._provider(route.provider)
                    return await provider.complete(request, route.name)
                except ProviderError as exc:
                    last = exc
                    if not exc.retryable or attempt == attempts:
                        break
                    delay = min(2 ** (attempt - 1), 8) * (0.6 + random.random() * 0.8)
                    log.warning(
                        "%s attempt %d/%d failed (%s); retrying in %.1fs",
                        request.tag or role,
                        attempt,
                        attempts,
                        exc,
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
