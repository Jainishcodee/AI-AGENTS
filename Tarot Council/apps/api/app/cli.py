"""Terminal client, so the engine is usable before any UI exists.

    python -m app.cli --provider mock "Should I quit my internship?"
    python -m app.cli --preset strategy --depth standard "..."
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from .core.config import get_settings
from .core.errors import CognitiveOSError
from .core.logging import setup_logging
from .council import Council
from .memory.store import InMemoryStore
from .programs import loader
from .schemas.council import Deliberation, DeliberationRequest

DIM = "\033[2m"
BOLD = "\033[1m"
RESET = "\033[0m"
RULE = "─" * 78


def _supports_colour() -> bool:
    return sys.stdout.isatty()


def _c(text: str, code: str) -> str:
    return f"{code}{text}{RESET}" if _supports_colour() else text


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="app.cli", description="Run a council deliberation from the terminal."
    )
    parser.add_argument("question", help="The decision to deliberate on.")
    parser.add_argument(
        "--preset",
        default=None,
        help="full | strategy | people | execution | life | solo:<module>",
    )
    parser.add_argument("--depth", choices=("quick", "standard", "deep"), default=None)
    parser.add_argument(
        "--provider",
        default=None,
        help="Override routing entirely. `mock` needs no key and no network.",
    )
    parser.add_argument(
        "--notes", default="", help="Extra context: constraints, actors, values."
    )
    parser.add_argument("--json", action="store_true", help="Print the raw result as JSON.")
    parser.add_argument("--quiet", action="store_true", help="Suppress progress lines.")
    parser.add_argument(
        "--no-persist", action="store_true", help="Do not write anything to disk."
    )
    return parser.parse_args(argv)


async def _run(args: argparse.Namespace) -> int:
    settings = get_settings()
    setup_logging("WARNING" if args.quiet else settings.log_level)

    council = Council(
        settings,
        store=InMemoryStore() if args.no_persist else None,
        force_provider=args.provider,
    )
    request = DeliberationRequest(
        question=args.question,
        preset=args.preset,
        depth=args.depth,
        context_notes=args.notes,
    )

    result: Deliberation | None = None
    try:
        async for event in council.deliberate(request):
            if event.type == "done":
                result = Deliberation.model_validate(event.payload["deliberation"])
            elif event.type == "error":
                level = "warning" if event.payload.get("recoverable") else "error"
                print(_c(f"[{level}] {event.payload.get('message')}", DIM), file=sys.stderr)
            elif not args.quiet:
                _progress(event)
    finally:
        await council.aclose()

    if result is None:
        print("no result produced", file=sys.stderr)
        return 1

    if args.json:
        print(result.model_dump_json(indent=2))
    else:
        _report(result)
    return 0


def _progress(event) -> None:
    p = event.payload
    if event.type == "stage_started":
        print(_c(f"\n▸ {p.get('label', p.get('phase'))}", BOLD), file=sys.stderr)
    elif event.type == "artifact_complete":
        print(
            _c(f"  ✓ {p['module']:<13} {p['stage_id']:<16} {p['artifact']['kind']}", DIM),
            file=sys.stderr,
        )
    elif event.type == "artifact_invalid":
        tail = " → repairing" if p.get("repairing") else " → abstaining"
        print(
            _c(f"  ! {p['module']:<13} {p['stage_id']:<16} {p['problems'][0][:70]}{tail}", DIM),
            file=sys.stderr,
        )
    elif event.type == "module_abstained":
        print(_c(f"  ✗ {p['module']} abstained: {p.get('reason', '')[:80]}", DIM), file=sys.stderr)
    elif event.type == "critique_complete":
        print(_c(f"  ⚔ {p['module']:<13} {len(p['critiques'])} critiques", DIM), file=sys.stderr)
    elif event.type == "revision_complete":
        r = p["revision"]
        print(
            _c(
                f"  ↻ {r['module']:<13} {r['delta'][:60]} "
                f"(confidence {r['confidence']['score']})",
                DIM,
            ),
            file=sys.stderr,
        )


def _wrap(text: str, indent: str = "  ", width: int = 76) -> str:
    import textwrap

    return "\n".join(
        textwrap.fill(line, width=width, initial_indent=indent, subsequent_indent=indent)
        for line in (text or "").splitlines()
        or [""]
    )


def _report(d: Deliberation) -> None:
    programs = loader.programs()
    print()
    print(RULE)
    print(_c(d.question, BOLD))
    print(_c(f"{d.preset} · {d.depth} · {d.usage.calls} calls · {d.id}", DIM))
    print(RULE)

    for run in d.runs:
        program = programs.get(run.module)
        skin = program.skin.name if program else run.module
        header = f"\n{skin} ({run.module}) — {run.role}"
        print(_c(header, BOLD))
        if run.abstained:
            print(_wrap(f"abstained at {run.abstained_at}: {run.abstain_reason}"))
            continue
        for artifact in run.artifacts:
            if artifact.kind == "Conclusion":
                continue
            print(_c(f"  · {artifact.title or artifact.stage_id} → {artifact.kind}", DIM))
        if run.conclusion:
            c = run.conclusion
            print()
            print(_wrap(f"STANCE  {c.stance}"))
            print(_wrap(f"FIRST   {c.first_action}"))
            print(_wrap(f"WHY     {c.reasoning}"))
            print(_wrap(f"CONF    {c.confidence.score} — {c.confidence.basis}"))
            print(_wrap(f"FLIPS IF {c.confidence.falsifier}"))
            if c.ethical_veto:
                print(_wrap(f"VETO    {c.veto_grounds}"))

    if d.critiques:
        print(_c("\n\nDEBATE", BOLD))
        for critique in d.critiques:
            ref = ""
            if critique.target_ref:
                ref = f" [{critique.target_ref.kind}"
                ref += f"#{critique.target_ref.row_id}]" if critique.target_ref.row_id else "]"
            print(
                _wrap(
                    f"{critique.critic} → {critique.target}{ref} "
                    f"({critique.kind}/{critique.severity}): {critique.statement}"
                )
            )

    s = d.synthesis
    if s is None:
        print(_c("\n\nNo synthesis was produced.", BOLD))
        return

    print(_c("\n\nSYNTHESIS", BOLD))
    print(_wrap(s.debate_summary))

    if s.consensus:
        print(_c("\nCONSENSUS", BOLD))
        for point in s.consensus:
            print(_wrap(f"· {point.point} ({', '.join(point.modules)})"))

    if s.disagreements:
        print(_c("\nDISAGREEMENTS", BOLD))
        for disagreement in s.disagreements:
            print(_wrap(f"· {disagreement.issue}"))
            for position in disagreement.positions:
                print(_wrap(f"  {position.module}: {position.position}", indent="    "))
            print(_wrap(f"  resolves if: {disagreement.what_would_resolve_it}", indent="    "))

    if s.blind_spots_fired:
        print(_c("\nBIASES THAT FIRED", BOLD))
        for fired in s.blind_spots_fired:
            mark = "corrected" if fired.corrected else "uncorrected"
            print(_wrap(f"· {fired.module}/{fired.bias_id} ({mark}): {fired.evidence}"))

    print(_c("\nWHAT THE COUNCIL DID NOT EXAMINE", BOLD))
    print(_wrap(s.council_blind_spot))

    print(_c("\nRECOMMENDATION", BOLD))
    print(_wrap(s.recommendation.action))
    print(_wrap(f"FIRST   {s.recommendation.first_action}"))
    if s.recommendation.timeline:
        print(_wrap(f"WHEN    {s.recommendation.timeline}"))
    for item in s.recommendation.do_not:
        print(_wrap(f"DO NOT  {item}"))
    for item in s.recommendation.conditions:
        print(_wrap(f"ONLY IF {item}"))
    print(_wrap(f"CONF    {s.confidence.score} — {s.confidence.basis}"))
    print(_wrap(f"FLIPS IF {s.confidence.falsifier}"))
    if s.calibration_note:
        print(_wrap(f"NOTE    {s.calibration_note}"))
    if s.ethical_veto_response:
        print(_c("\nVETO RESPONSE", BOLD))
        print(_wrap(s.ethical_veto_response))

    if s.minority_opinions:
        print(_c("\nMINORITY OPINIONS", BOLD))
        for minority in s.minority_opinions:
            print(_wrap(f"· {minority.module}: {minority.position}"))
            print(_wrap(f"  right if: {minority.when_it_would_be_right}", indent="    "))

    if s.alternative_strategy:
        print(_c("\nALTERNATIVE", BOLD))
        print(_wrap(s.alternative_strategy.action))
        print(_wrap(f"switch if: {s.alternative_strategy.trigger}"))

    if s.long_term_prediction:
        print(_c("\nPREDICTION", BOLD))
        for horizon in s.long_term_prediction:
            print(_wrap(f"{horizon.horizon:<5} {horizon.prediction} ({horizon.confidence})"))

    if s.information_to_gather:
        print(_c("\nFIND OUT, IN THIS ORDER", BOLD))
        for index, item in enumerate(s.information_to_gather, start=1):
            print(_wrap(f"{index}. {item}"))

    print(_c("\nEXPECTED OUTCOME", BOLD))
    print(_wrap(f"{s.expected_outcome.statement}"))
    print(_wrap(f"check in {s.expected_outcome.check_in_days} days"))
    print()


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        return asyncio.run(_run(args))
    except KeyboardInterrupt:
        return 130
    except CognitiveOSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
