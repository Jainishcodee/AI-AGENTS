"""Concrete providers: Gemini, OpenRouter, Ollama, and a deterministic mock.

Each returns raw text; validation is the caller's job. Retry and concurrency
control live in `registry.py` so the policy is uniform across providers.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from typing import Any

import httpx
from pydantic import BaseModel

from ..core.errors import ProviderError
from ..core.logging import get_logger
from .base import LLMRequest, LLMResponse
from .jsonio import schema_hint
from .synth import synthesize

log = get_logger(__name__)

JSON_INSTRUCTION = (
    "Return ONLY a single JSON object matching this shape. No prose, no code "
    "fence, no commentary. Every required field must be present.\n\n"
    "SHAPE:\n{shape}"
)

RETRYABLE_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}


def _compose_user(request: LLMRequest) -> str:
    if request.json_model is None:
        return request.user
    shape = JSON_INSTRUCTION.format(shape=schema_hint(request.json_model))
    return f"{request.user}\n\n---\n{shape}"


class _HttpProvider:
    name = "http"

    def __init__(self, *, timeout: float) -> None:
        self._client = httpx.AsyncClient(timeout=timeout)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _post(self, url: str, *, json_body: dict, headers: dict) -> dict:
        try:
            resp = await self._client.post(url, json=json_body, headers=headers)
        except httpx.TimeoutException as exc:
            raise ProviderError(self.name, f"timeout: {exc}", retryable=True) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(self.name, f"transport: {exc}", retryable=True) from exc

        if resp.status_code >= 400:
            detail = resp.text[:400]
            raise ProviderError(
                self.name,
                f"HTTP {resp.status_code}: {detail}",
                retryable=resp.status_code in RETRYABLE_STATUS,
            )
        try:
            return resp.json()
        except json.JSONDecodeError as exc:
            raise ProviderError(self.name, "non-JSON response body", retryable=True) from exc


class GeminiProvider(_HttpProvider):
    name = "gemini"
    BASE = "https://generativelanguage.googleapis.com/v1beta/models"

    def __init__(self, api_key: str, *, timeout: float) -> None:
        super().__init__(timeout=timeout)
        self._key = api_key

    async def complete(self, request: LLMRequest, model: str) -> LLMResponse:
        generation: dict[str, Any] = {
            "temperature": request.temperature,
            "maxOutputTokens": request.max_tokens,
        }
        if request.json_model is not None:
            # Schema goes in the prompt, not responseSchema: Gemini's schema subset
            # rejects $ref/$defs and these models are deeply nested.
            generation["responseMimeType"] = "application/json"

        body = {
            "contents": [{"role": "user", "parts": [{"text": _compose_user(request)}]}],
            "generationConfig": generation,
        }
        if request.system:
            body["systemInstruction"] = {"parts": [{"text": request.system}]}

        started = time.perf_counter()
        data = await self._post(
            f"{self.BASE}/{model}:generateContent?key={self._key}",
            json_body=body,
            headers={"content-type": "application/json"},
        )
        elapsed = int((time.perf_counter() - started) * 1000)

        candidates = data.get("candidates") or []
        if not candidates:
            blocked = (data.get("promptFeedback") or {}).get("blockReason")
            raise ProviderError(
                self.name,
                f"no candidates (blockReason={blocked})",
                retryable=blocked is None,
            )
        candidate = candidates[0]
        finish = candidate.get("finishReason", "")
        parts = (candidate.get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts)
        if not text.strip():
            # 2.5 models spend output budget on thinking; an empty body with
            # MAX_TOKENS means raise the budget, and is worth retrying once.
            raise ProviderError(
                self.name, f"empty completion (finishReason={finish})", retryable=True
            )

        usage = data.get("usageMetadata") or {}
        return LLMResponse(
            text=text,
            provider=self.name,
            model=model,
            input_tokens=usage.get("promptTokenCount", 0),
            output_tokens=usage.get("candidatesTokenCount", 0),
            latency_ms=elapsed,
            finish_reason=finish,
        )


class OpenRouterProvider(_HttpProvider):
    name = "openrouter"
    URL = "https://openrouter.ai/api/v1/chat/completions"

    def __init__(self, api_key: str, *, timeout: float) -> None:
        super().__init__(timeout=timeout)
        self._key = api_key

    async def complete(self, request: LLMRequest, model: str) -> LLMResponse:
        messages = []
        if request.system:
            messages.append({"role": "system", "content": request.system})
        messages.append({"role": "user", "content": _compose_user(request)})

        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        if request.json_model is not None:
            body["response_format"] = {"type": "json_object"}

        started = time.perf_counter()
        data = await self._post(
            self.URL,
            json_body=body,
            headers={
                "authorization": f"Bearer {self._key}",
                "content-type": "application/json",
                "x-title": "Cognitive OS",
            },
        )
        elapsed = int((time.perf_counter() - started) * 1000)

        choices = data.get("choices") or []
        if not choices:
            raise ProviderError(self.name, f"no choices: {str(data)[:200]}", retryable=True)
        message = choices[0].get("message") or {}
        text = message.get("content") or ""
        if not text.strip():
            raise ProviderError(self.name, "empty completion", retryable=True)
        usage = data.get("usage") or {}
        return LLMResponse(
            text=text,
            provider=self.name,
            model=model,
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
            latency_ms=elapsed,
            finish_reason=choices[0].get("finish_reason", ""),
        )


class OllamaProvider(_HttpProvider):
    name = "ollama"

    def __init__(self, host: str, *, timeout: float) -> None:
        super().__init__(timeout=timeout)
        self._host = host.rstrip("/")

    async def complete(self, request: LLMRequest, model: str) -> LLMResponse:
        messages = []
        if request.system:
            messages.append({"role": "system", "content": request.system})
        messages.append({"role": "user", "content": _compose_user(request)})

        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": request.temperature},
        }
        if request.json_model is not None:
            body["format"] = "json"

        started = time.perf_counter()
        data = await self._post(
            f"{self._host}/api/chat", json_body=body, headers={"content-type": "application/json"}
        )
        elapsed = int((time.perf_counter() - started) * 1000)
        text = ((data.get("message") or {}).get("content")) or ""
        if not text.strip():
            raise ProviderError(self.name, "empty completion", retryable=True)
        return LLMResponse(
            text=text,
            provider=self.name,
            model=model,
            input_tokens=data.get("prompt_eval_count", 0),
            output_tokens=data.get("eval_count", 0),
            latency_ms=elapsed,
            finish_reason=data.get("done_reason", ""),
        )


def _scoped(prompt: str, stage_id: str) -> str:
    """Narrow a batched prompt to one stage's own instructions, keeping the shared header.

    A batched call asks for several stages in one response, each under a numbered heading
    ending `under the key \\`<stage_id>\\``. A fixup reading the whole prompt sees *every*
    stage's declared shape and picks the first — which for two authored tables in one batch
    meant the second table was filled with the first one's columns and then correctly
    rejected by its own invariant.

    Everything before the first heading is shared context (question, priors, memory) and is
    always kept. If the heading is not found, the full prompt is returned: degrading to the
    old behaviour beats returning nothing.
    """
    marker = f"under the key `{stage_id}`"
    position = prompt.find(marker)
    if position == -1:
        return prompt

    heading = re.compile(r"^\s*\d+\.\s.+?—\s*produce ", re.M)
    starts = [m.start() for m in heading.finditer(prompt)]
    if not starts:
        return prompt

    shared = prompt[: starts[0]]
    mine = max((s for s in starts if s <= position), default=starts[0])
    following = [s for s in starts if s > mine]
    return shared + prompt[mine : following[0] if following else len(prompt)]


class MockProvider:
    """Deterministic fake model.

    Synthesises a schema-valid instance of `request.json_model`, then applies any
    registered fixup for that model so invariants (probability sums, tag quotas,
    profile completeness) also hold. This is what makes the whole pipeline runnable
    with no key and no network — and what makes the invariant suite exercisable in
    CI.

    Fixups are injected rather than imported so this module stays free of any
    artifact knowledge.
    """

    name = "mock"

    def __init__(
        self,
        fixups: dict[str, Callable[[dict[str, Any], str], dict[str, Any]]] | None = None,
    ) -> None:
        self._fixups = fixups or {}

    def _apply(
        self, model: type[BaseModel], data: dict[str, Any], prompt: str
    ) -> dict[str, Any]:
        """Apply the fixup for this model, or recurse into a batch wrapper.

        A batched stage call asks for an object keyed by stage id whose values are
        artifact models. Recursing by field annotation handles that without the
        provider knowing anything about stages or artifacts.
        """
        fixup = self._fixups.get(model.__name__)
        if fixup is not None:
            return fixup(data, prompt)
        for name, info in model.model_fields.items():
            annotation = info.annotation
            if (
                isinstance(annotation, type)
                and issubclass(annotation, BaseModel)
                and isinstance(data.get(name), dict)
            ):
                data[name] = self._apply(annotation, data[name], _scoped(prompt, name))
                # Append each fixed sibling as a synthetic prior block so a later
                # stage in the same batch can read what an earlier one produced —
                # exactly as it would across separate calls.
                prompt += (
                    f'\n<prior stage="{name}" kind="{annotation.__name__}">\n'
                    f"{json.dumps(data[name])}\n</prior>"
                )
        return data

    async def complete(self, request: LLMRequest, model: str) -> LLMResponse:
        if request.json_model is None:
            return LLMResponse(
                text=f"[mock] {request.tag or 'completion'}",
                provider=self.name,
                model=model,
            )
        data = self._apply(
            request.json_model, synthesize(request.json_model, seed="mock"), request.user
        )
        text = json.dumps(data)
        return LLMResponse(
            text=text,
            provider=self.name,
            model=model,
            input_tokens=len(request.user) // 4,
            output_tokens=len(text) // 4,
            latency_ms=1,
        )

    async def aclose(self) -> None:
        return None
