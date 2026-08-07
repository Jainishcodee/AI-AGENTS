"""Calibration and learning.

The one place where recorded outcomes turn into something that changes future
reasoning. Split deliberately:

    grader.py   an LLM judges what happened, blind to any stated confidence
    scoring.py  pure arithmetic over those judgements — Brier, hit rate, execution
    priors.py   rule-based patterns with counts computed in Python, never phrased
                by a model

Nothing here alters a program. Priors reach a module as citable memory it may argue
with (ADR-018).
"""

from . import priors, scoring
from .grader import GradingFailed, grade

__all__ = ["GradingFailed", "grade", "priors", "scoring"]
