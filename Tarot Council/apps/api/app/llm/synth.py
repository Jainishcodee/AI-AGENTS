"""Generic Pydantic instance synthesiser, used by the mock provider.

Given any model class, produce a dict that satisfies its schema — respecting
numeric bounds, enum choices, minimum list lengths, and self-referential models.
Knows nothing about artifacts; kind-specific invariant fixups are injected by the
caller so this module stays domain-free.
"""

from __future__ import annotations

from typing import Any, Literal, Union, get_args, get_origin

from annotated_types import Ge, Gt, Le, Lt, MinLen
from pydantic import BaseModel
from pydantic.fields import FieldInfo

_NoneType = type(None)


def synthesize(model: type[BaseModel], *, seed: str = "mock") -> dict[str, Any]:
    return _build_model(model, seed=seed, path=(), depth=0)


def _build_model(
    model: type[BaseModel], *, seed: str, path: tuple[type, ...], depth: int
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for name, info in model.model_fields.items():
        out[name] = _build_field(
            info, name=name, seed=seed, path=path + (model,), depth=depth
        )
    return out


def _bounds(info: FieldInfo) -> tuple[float | None, float | None, int]:
    low = high = None
    min_len = 0
    for meta in info.metadata:
        if isinstance(meta, Ge):
            low = float(meta.ge)
        elif isinstance(meta, Gt):
            low = float(meta.gt) + 1
        elif isinstance(meta, Le):
            high = float(meta.le)
        elif isinstance(meta, Lt):
            high = float(meta.lt) - 1
        elif isinstance(meta, MinLen):
            min_len = int(meta.min_length)
    return low, high, min_len


def _build_field(
    info: FieldInfo, *, name: str, seed: str, path: tuple[type, ...], depth: int
) -> Any:
    low, high, min_len = _bounds(info)
    return _build_type(
        info.annotation,
        name=name,
        seed=seed,
        path=path,
        depth=depth,
        low=low,
        high=high,
        min_len=min_len,
    )


def _build_type(
    annotation: Any,
    *,
    name: str,
    seed: str,
    path: tuple[type, ...],
    depth: int,
    low: float | None = None,
    high: float | None = None,
    min_len: int = 0,
) -> Any:
    origin = get_origin(annotation)

    # Optional / Union — take the first non-None branch so required nested shapes
    # still get built rather than collapsing to null.
    if origin is Union:
        branches = [a for a in get_args(annotation) if a is not _NoneType]
        if not branches:
            return None
        return _build_type(
            branches[0], name=name, seed=seed, path=path, depth=depth, low=low, high=high
        )

    if origin is Literal:
        return get_args(annotation)[0]

    if origin in (list, tuple, set):
        args = [a for a in get_args(annotation) if a is not Ellipsis]
        # `tuple[X, ...]` yields (X, Ellipsis) and `tuple[X, Y]` yields two real types.
        # Taking the first after dropping Ellipsis handles the variadic form and degrades
        # sensibly on the fixed-length one. Unpacking directly raised ValueError, which
        # surfaced as an unexplained module abstention the first time an artifact used a
        # tuple field instead of a list.
        inner = args[0] if args else str
        # Stop self-referential recursion (TreeNode.children) by returning an
        # empty list once the inner model is already on the path.
        if isinstance(inner, type) and issubclass(inner, BaseModel) and inner in path:
            return []
        count = max(min_len, 1)
        return [
            _build_type(inner, name=f"{name}_{i}", seed=seed, path=path, depth=depth + 1)
            for i in range(count)
        ]

    if origin is dict:
        return {}

    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        if annotation in path or depth > 6:
            return None
        return _build_model(annotation, seed=seed, path=path, depth=depth + 1)

    if annotation is bool:
        return False
    if annotation is int:
        return int(_numeric(low, high, default=3))
    if annotation is float:
        return _numeric(low, high, default=0.5)
    if annotation is str:
        return f"[{seed}] {name.replace('_', ' ')}"
    return None


def _numeric(low: float | None, high: float | None, *, default: float) -> float:
    if low is not None and high is not None:
        if low <= default <= high:
            return default
        return round(low + (high - low) / 2, 2)
    if low is not None:
        return max(low, default)
    if high is not None:
        return min(high, default)
    return default
