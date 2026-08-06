"""Cognitive OS — reasoning core.

Dependency direction, defended by tests:
    api → council → {engine, programs, prompts, memory, trace} → llm → schemas → core

`engine/` must never import `programs/`: the moment it does, it stops being an
interpreter and becomes a hardcoded pipeline.
"""

__version__ = "0.1.0"
