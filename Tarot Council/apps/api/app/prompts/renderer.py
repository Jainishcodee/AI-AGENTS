"""Prompt rendering. Turns (program, stage, state) into strings and nothing else."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined

TEMPLATE_DIR = Path(__file__).parent / "templates"


@lru_cache(maxsize=1)
def _env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )
    env.filters["tojson"] = lambda v: json.dumps(v, ensure_ascii=False)
    return env


@lru_cache(maxsize=1)
def constitution() -> str:
    return _env().get_template("constitution.jinja").render().strip()


def render(template: str, **ctx: Any) -> str:
    return _env().get_template(template).render(**ctx).strip()


def system_prompt(program: Any) -> str:
    return render("system.jinja", constitution=constitution(), program=program)
