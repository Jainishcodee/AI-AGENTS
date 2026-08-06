"""Getting reliable JSON out of a model that is not obliged to give you any.

Why not native structured output: Gemini's `responseSchema` does not accept
`$ref`/`$defs`, and the artifact models are deeply nested. Flattening the domain
model to fit one vendor's JSON-mode subset is the wrong trade, so instead the
request asks for `application/json`, embeds a compact schema in the prompt, and
validates with Pydantic on return. The repair pass lives in the engine, which is
the only layer that also knows the invariants.
"""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, ValidationError

_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def schema_hint(model: type[BaseModel]) -> str:
    """A compact, LLM-readable rendering of the model's JSON schema.

    `model_json_schema()` with `$defs` inlined and bookkeeping keys dropped. Models
    follow a terse tree far better than they follow raw JSON Schema, and the token
    saving is meaningful when this ships on every stage call.
    """
    schema = model.model_json_schema()
    defs = schema.pop("$defs", {})
    return _render(schema, defs, indent=0).rstrip()


def _resolve(node: dict[str, Any], defs: dict[str, Any]) -> dict[str, Any]:
    ref = node.get("$ref")
    if not ref:
        return node
    name = ref.rsplit("/", 1)[-1]
    resolved = dict(defs.get(name, {}))
    resolved.pop("title", None)
    return resolved


def _type_label(node: dict[str, Any], defs: dict[str, Any]) -> str:
    node = _resolve(node, defs)
    if "enum" in node:
        return " | ".join(json.dumps(v) for v in node["enum"])
    if "const" in node:
        return json.dumps(node["const"])
    if "anyOf" in node:
        parts = [_type_label(o, defs) for o in node["anyOf"] if o.get("type") != "null"]
        label = " | ".join(dict.fromkeys(parts)) or "any"
        return f"{label} | null" if any(o.get("type") == "null" for o in node["anyOf"]) else label
    t = node.get("type")
    if t == "array":
        return f"[{_type_label(node.get('items', {}), defs)}]"
    if t == "object" and "properties" not in node:
        return "object"
    return {"string": "string", "integer": "int", "number": "float", "boolean": "bool"}.get(
        t, t or "any"
    )


def _constraints(node: dict[str, Any]) -> str:
    bits = []
    for key, label in (
        ("minimum", ">="),
        ("maximum", "<="),
        ("exclusiveMinimum", ">"),
        ("exclusiveMaximum", "<"),
        ("minItems", "min items"),
        ("minLength", "min len"),
        ("maxLength", "max len"),
    ):
        if key in node:
            bits.append(f"{label} {node[key]}")
    return f"  ({', '.join(bits)})" if bits else ""


def _render(node: dict[str, Any], defs: dict[str, Any], indent: int) -> str:
    node = _resolve(node, defs)
    pad = "  " * indent
    props = node.get("properties")
    if not props:
        return ""
    required = set(node.get("required", []))
    lines: list[str] = []
    for name, prop in props.items():
        prop_r = _resolve(prop, defs)
        label = _type_label(prop, defs)
        opt = "" if name in required else "?"
        desc = prop_r.get("description", "")
        note = f"   // {desc.splitlines()[0]}" if desc else ""
        lines.append(f"{pad}{name}{opt}: {label}{_constraints(prop_r)}{note}")

        # Recurse into nested objects and arrays of objects so the model sees the
        # whole shape rather than an opaque type name.
        nested = prop_r
        if prop_r.get("type") == "array":
            nested = _resolve(prop_r.get("items", {}), defs)
        elif "anyOf" in prop_r:
            for opt_node in prop_r["anyOf"]:
                candidate = _resolve(opt_node, defs)
                if candidate.get("properties"):
                    nested = candidate
                    break
        if nested.get("properties") and indent < 4:
            body = _render(nested, defs, indent + 1)
            if body:
                lines.append(body.rstrip())
    return "\n".join(lines)


def extract_json(text: str) -> Any:
    """Pull the first JSON value out of a model response.

    Handles fenced blocks, leading prose, and trailing commentary — all of which
    happen often enough that failing on them would waste repair calls.
    """
    if not text or not text.strip():
        raise ValueError("empty response")

    candidates: list[str] = []
    fenced = _FENCE.search(text)
    if fenced:
        candidates.append(fenced.group(1))
    candidates.append(text.strip())

    for candidate in candidates:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass
        sliced = _slice_balanced(candidate)
        if sliced is not None:
            try:
                return json.loads(sliced)
            except json.JSONDecodeError:
                continue
    raise ValueError("response contained no parseable JSON object")


def _slice_balanced(text: str) -> str | None:
    """Extract the outermost balanced {...} or [...], ignoring braces in strings."""
    start = min(
        (i for i in (text.find("{"), text.find("[")) if i != -1),
        default=-1,
    )
    if start == -1:
        return None
    opener = text[start]
    closer = "}" if opener == "{" else "]"
    depth = 0
    in_string = False
    escaped = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def format_validation_error(exc: ValidationError) -> list[str]:
    """Turn Pydantic's error list into complaints a model can act on."""
    problems = []
    for err in exc.errors()[:12]:
        loc = ".".join(str(p) for p in err["loc"]) or "(root)"
        problems.append(f"{loc}: {err['msg']}")
    return problems
