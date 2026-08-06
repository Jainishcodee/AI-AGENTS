"""Provider-facing contract.

This module knows nothing about councils, modules, or artifacts. It is the piece
most likely to be extracted into a shared package, so the boundary is defended:
the only domain object it accepts is a Pydantic model class describing the shape of
the JSON it should ask for.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from pydantic import BaseModel


@dataclass(slots=True)
class LLMRequest:
    system: str
    user: str
    json_model: type[BaseModel] | None = None
    """When set, the provider requests JSON and the caller validates against this.

    Real providers use it to build a schema hint; the mock provider uses it to
    synthesise a valid instance. Either way the request carries its own contract.
    """
    temperature: float = 0.7
    max_tokens: int = 8192
    tag: str = ""
    """Human label for logs and usage attribution, e.g. `strategist:graph`."""
    extra: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class LLMResponse:
    text: str
    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0
    finish_reason: str = ""

    @property
    def route(self) -> str:
        return f"{self.provider}:{self.model}"


@runtime_checkable
class LLMProvider(Protocol):
    name: str

    async def complete(self, request: LLMRequest, model: str) -> LLMResponse: ...

    async def aclose(self) -> None: ...
