"""Shared vocabulary. Imported by every other schema module."""

from __future__ import annotations

from typing import Any, Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, model_validator

_MISSING = object()

# Module ids are plain strings, not a Literal, because Phase 5 lets users author
# modules. `BUILTIN_MODULES` is for display ordering and defaults only — the
# engine never branches on it.
ModuleId = str
StageId = str

BUILTIN_MODULES: tuple[ModuleId, ...] = (
    "analyst",
    "tactician",
    "strategist",
    "psychologist",
    "optimizer",
    "ethicist",
)

Reversibility = Literal["reversible", "costly", "one_way"]
EvidenceStatus = Literal["given", "inferred", "assumed", "speculative", "unknown"]
SourceQuality = Literal["measured", "reported", "estimated", "guessed"]
CostToResolve = Literal["free", "cheap", "expensive", "impossible"]
OptionTag = Literal[
    "obvious", "inverse", "free", "reckless", "reframes", "conventional", "hybrid"
]
EdgeKind = Literal[
    "reports_to",
    "depends_on",
    "owes",
    "allied_with",
    "competes_with",
    "can_veto",
    "informs",
    "gatekeeps",
]
WasteVerdict = Literal["keep", "cut", "automate", "delegate", "defer"]
ValueSource = Literal["stated_by_user", "inferred_from_user", "conventional"]
CritiqueKind = Literal[
    "unsupported",
    "missing_factor",
    "wrong_frame",
    "overweighted",
    "bias_fired",
    "boundary_violation",
    "strong_agreement",
]
Verdict = Literal["right", "wrong", "partial", "untested"]
MemoryKind = Literal[
    "fact", "opportunity", "power_structure", "emotional", "workflow", "promise"
]

DO_NOTHING_ID = "do_nothing"


class Strict(BaseModel):
    """Base for everything crossing the LLM boundary.

    `extra="ignore"` rather than `forbid`: models routinely add a helpful extra
    key, and failing validation for that would burn a repair call on something
    harmless. Missing and malformed fields still fail, which is what matters.
    """

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    @model_validator(mode="before")
    @classmethod
    def _null_means_absent(cls, data: Any) -> Any:
        """Treat an explicit `null` as "not supplied" for non-nullable optionals.

        Models emit `"calibration_note": null` for "nothing to say here" constantly.
        Failing validation for that, and spending a repair call on it, is the wrong
        trade: the field has a default and the intent is unambiguous. Fields that are
        genuinely `X | None` keep their null.
        """
        if not isinstance(data, dict):
            return data
        cleaned: dict[str, Any] | None = None
        for name, field in cls.model_fields.items():
            if data.get(name, _MISSING) is not None or field.is_required():
                continue
            annotation = field.annotation
            if type(None) in get_args(annotation):
                continue  # declared nullable — null is meaningful
            if cleaned is None:
                cleaned = dict(data)
            cleaned[name] = field.get_default(call_default_factory=True)
        return cleaned if cleaned is not None else data


class Confidence(Strict):
    """Confidence with a falsifier (ADR-010).

    `falsifier` is the single observation that would flip the stance. Without it a
    confidence number is decoration.
    """

    score: float = Field(ge=0.0, le=1.0)
    basis: str
    falsifier: str


class ArtifactRowRef(Strict):
    """A pointer into an artifact, used by critiques and trace edges."""

    module: ModuleId
    stage_id: StageId
    kind: str
    row_id: str | None = None


class Usage(BaseModel):
    """Token accounting, summed across a deliberation."""

    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    repairs: int = 0
    by_model: dict[str, int] = Field(default_factory=dict)

    def add(
        self,
        *,
        model: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        repair: bool = False,
    ) -> None:
        self.calls += 1
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        if repair:
            self.repairs += 1
        self.by_model[model] = self.by_model.get(model, 0) + 1

    def merge(self, other: "Usage") -> None:
        self.calls += other.calls
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.repairs += other.repairs
        for model, n in other.by_model.items():
            self.by_model[model] = self.by_model.get(model, 0) + n
