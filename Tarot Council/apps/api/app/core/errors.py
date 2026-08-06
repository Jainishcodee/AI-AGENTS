"""Error taxonomy.

The distinction that matters: `ProgramInvalid` is a *developer* error raised at
load time and refuses to let the server start. `ArtifactInvalid` is an expected
runtime condition that drives the repair pass, and only becomes an abstention
after the repair also fails.
"""

from __future__ import annotations


class CognitiveOSError(Exception):
    """Base class."""


class ProgramInvalid(CognitiveOSError):
    """A module program or preset violates a loader rule (SPEC-FORMAT.md §rules).

    Raised at import time, never during a deliberation.
    """


class ArtifactInvalid(CognitiveOSError):
    """A stage produced output failing schema or invariant validation.

    Carries the validator complaints verbatim so the repair prompt can show the
    model exactly what was wrong.
    """

    def __init__(self, kind: str, problems: list[str], raw: str | None = None) -> None:
        self.kind = kind
        self.problems = problems
        self.raw = raw
        super().__init__(f"{kind}: " + "; ".join(problems))


class ProviderError(CognitiveOSError):
    """An LLM provider failed after exhausting retries."""

    def __init__(self, provider: str, message: str, *, retryable: bool = False) -> None:
        self.provider = provider
        self.retryable = retryable
        super().__init__(f"{provider}: {message}")


class ModuleAbstained(CognitiveOSError):
    """A module could not complete its program.

    Never fails the council — the synthesiser is told who is missing and why.
    """

    def __init__(self, module: str, stage_id: str, reason: str) -> None:
        self.module = module
        self.stage_id = stage_id
        self.reason = reason
        super().__init__(f"{module} abstained at {stage_id}: {reason}")
