"""Terminal client, so the whole system is usable before any UI exists.

    python -m app.cli --provider mock "Should I quit my internship?"
    python -m app.cli ask --preset strategy --depth quick "..."

    python -m app.cli cards --status due
    python -m app.cli resolve <card-id> --chose "stayed" --outcome "offer arrived in writing"
    python -m app.cli scores
    python -m app.cli priors

The second group is the learning loop. Deliberating is the cheap half; recording what
actually happened is the half that makes the council yours.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from .core.config import get_settings
from .core.errors import CognitiveOSError
from .core.logging import setup_logging
from .council import Council
from .learning import priors
from .learning.scoring import CHANCE_BRIER
from .memory.store import InMemoryStore
from .programs import loader
from .schemas.cards import MIN_N_FOR_PRIOR, MIN_N_TO_DISPLAY, Resolution
from .schemas.council import Deliberation, DeliberationRequest

DIM = "\033[2m"
BOLD = "\033[1m"
RESET = "\033[0m"


def _force_utf8() -> bool:
    """Windows consoles default to cp1252, which cannot encode the glyphs below.

    Reconfiguring is enough on Python 3.7+; if it fails (a redirected non-UTF-8
    stream) we fall back to ASCII rather than crashing at the last line of output.
    """
    ok = True
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except (AttributeError, ValueError, OSError):
            ok = False
    return ok


UNICODE_OK = _force_utf8()
RULE = ("─" if UNICODE_OK else "-") * 78
GLYPH = {
    "ok": "✓" if UNICODE_OK else "+",
    "bad": "!" ,
    "gone": "✗" if UNICODE_OK else "x",
    "arrow": "▸" if UNICODE_OK else ">",
    "swords": "⚔" if UNICODE_OK else "*",
    "cycle": "↻" if UNICODE_OK else "~",
    "dot": "·" if UNICODE_OK else "-",
    "to": "→" if UNICODE_OK else "->",
}


def _supports_colour() -> bool:
    return sys.stdout.isatty()


def _c(text: str, code: str) -> str:
    return f"{code}{text}{RESET}" if _supports_colour() else text


COMMANDS = (
    "ask",
    "cards",
    "resolve",
    "grade",
    "scores",
    "priors",
    "memories",
    "rerun",
    "refine",
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="app.cli", description="Convene the council, and score it afterwards."
    )
    parser.add_argument(
        "--provider",
        default=None,
        help="Override routing entirely. `mock` needs no key and no network.",
    )
    parser.add_argument("--json", action="store_true", help="Print raw JSON.")
    parser.add_argument("--quiet", action="store_true", help="Suppress progress lines.")
    parser.add_argument(
        "--no-persist", action="store_true", help="Do not write anything to disk."
    )

    sub = parser.add_subparsers(dest="command", required=True)

    ask = sub.add_parser("ask", help="Deliberate on a decision.")
    ask.add_argument("question")
    ask.add_argument(
        "--preset", default=None, help="full | strategy | people | execution | life | solo:<module>"
    )
    ask.add_argument("--depth", choices=("quick", "standard", "deep"), default=None)
    ask.add_argument("--notes", default="", help="Extra context: constraints, actors, values.")

    cards = sub.add_parser("cards", help="List Decision Cards, due ones first.")
    cards.add_argument("--status", choices=("open", "due", "resolved"), default=None)
    cards.add_argument("--limit", type=int, default=30)

    resolve = sub.add_parser(
        "resolve", help="Record what actually happened, and grade every module."
    )
    resolve.add_argument("card_id")
    resolve.add_argument("--chose", required=True, help="What you actually did.")
    resolve.add_argument("--outcome", required=True, help="What happened as a result.")
    resolve.add_argument(
        "--on", default=None, help="When it happened (YYYY-MM-DD). Defaults to today."
    )
    resolve.add_argument(
        "--surprise",
        action="append",
        default=[],
        help="Something nobody predicted. Repeatable.",
    )
    resolve.add_argument("--notes", default="")
    resolve.add_argument("--no-grade", action="store_true", help="Save the outcome only.")

    grade = sub.add_parser("grade", help="Re-run the grader on a resolved card.")
    grade.add_argument("card_id")

    scores = sub.add_parser("scores", help="Per-module calibration.")
    scores.add_argument(
        "--all",
        action="store_true",
        dest="all_n",
        help="Include scores below n=8, which are not yet measurements.",
    )

    sub.add_parser("priors", help="What each module will be told about you next run.")

    memories = sub.add_parser("memories", help="What a module remembers about you.")
    memories.add_argument("module")
    memories.add_argument("--about", default="", help="Query to recall against.")

    rerun = sub.add_parser(
        "rerun", help="Re-run one module from one stage with new facts, then re-synthesise."
    )
    rerun.add_argument("deliberation_id")
    rerun.add_argument("--module", required=True)
    rerun.add_argument("--from-stage", required=True, dest="from_stage")
    rerun.add_argument(
        "--fact", action="append", default=[], dest="facts", help="New information. Repeatable."
    )
    rerun.add_argument("--reason", default="")

    refine = sub.add_parser("refine", help="Answer the open unknowns and deliberate again.")
    refine.add_argument("deliberation_id")
    refine.add_argument(
        "--answer", action="append", default=[], dest="answers", required=True, help="Repeatable."
    )
    refine.add_argument("--reason", default="")

    args = list(sys.argv[1:] if argv is None else argv)
    return parser.parse_args(_insert_default_command(args))


VALUE_FLAGS = {"--provider"}


def _insert_default_command(args: list[str]) -> list[str]:
    """`app.cli "question"` still works, without a subcommand.

    That is the documented form and the one people type. Finding where to insert
    `ask` means skipping global flags *and* their values — `--provider mock` would
    otherwise look like the subcommand `mock`.
    """
    index = 0
    while index < len(args):
        token = args[index]
        if token.startswith("-"):
            index += 2 if token in VALUE_FLAGS and "=" not in token else 1
            continue
        return args if token in COMMANDS else [*args[:index], "ask", *args[index:]]
    return args


async def _run(args: argparse.Namespace) -> int:
    settings = get_settings()
    setup_logging("WARNING" if args.quiet else settings.log_level)

    council = Council(
        settings,
        store=InMemoryStore() if args.no_persist else None,
        force_provider=args.provider,
    )
    try:
        handler = {
            "ask": _cmd_ask,
            "cards": _cmd_cards,
            "resolve": _cmd_resolve,
            "grade": _cmd_grade,
            "scores": _cmd_scores,
            "priors": _cmd_priors,
            "memories": _cmd_memories,
            "rerun": _cmd_rerun,
            "refine": _cmd_refine,
        }[args.command]
        code = await handler(council, args)
        if not args.json:
            await _nudge_due(council, args)
        return code
    finally:
        await council.aclose()


async def _nudge_due(council: Council, args: argparse.Namespace) -> None:
    """One line, once, when a check-in has come up.

    A card schedules its own follow-up when it is written; something still has to
    mention it. Printing it after every command is the cheapest reminder that does not
    need a daemon — and the loop only closes if somebody actually comes back.
    """
    if args.command in ("cards", "resolve", "grade"):
        return
    try:
        due = await council.store.list_cards(limit=5, status="due")
    except Exception:  # noqa: BLE001 - a nudge must never break a command
        return
    if not due:
        return
    print(
        _c(
            f"\n{GLYPH['arrow']} {len(due)} decision(s) due for a check-in "
            f"({', '.join(c.id for c in due[:3])}). "
            "`app.cli cards --status due`",
            DIM,
        ),
        file=sys.stderr,
    )


async def _cmd_memories(council: Council, args: argparse.Namespace) -> int:
    found = await council.store.recall(args.module, args.about, k=20)
    if args.json:
        print(json.dumps([m.model_dump(mode="json") for m in found], indent=2, default=str))
        return 0
    if not found:
        print(
            _wrap(
                f"{args.module} remembers nothing yet"
                + (f" about “{args.about}”." if args.about else ".")
                + " Memories are extracted when a decision resolves."
            )
        )
        return 0
    print(_c(f"{args.module} recalls", BOLD))
    for memory in found:
        print(_wrap(f"{GLYPH['dot']} {memory.content}"))
        print(
            _c(
                _wrap(
                    f"{memory.kind} · salience {memory.salience:.2f} · "
                    f"from card {memory.source_card_id}",
                    indent="    ",
                ),
                DIM,
            )
        )
    print()
    return 0


async def _cmd_rerun(council: Council, args: argparse.Namespace) -> int:
    try:
        derived = await council.rerun_stage(
            args.deliberation_id,
            module=args.module,
            from_stage=args.from_stage,
            facts=args.facts,
            reason=args.reason,
        )
    except KeyError as exc:
        print(f"not found: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(derived.model_dump_json(indent=2))
        return 0
    print(
        _c(
            f"\nre-ran {args.module} from '{args.from_stage}' "
            f"→ new deliberation {derived.id} (derived from {args.deliberation_id})",
            BOLD,
        )
    )
    _report(derived)
    return 0


async def _cmd_refine(council: Council, args: argparse.Namespace) -> int:
    try:
        refined = await council.refine(
            args.deliberation_id, answers=args.answers, reason=args.reason
        )
    except KeyError as exc:
        print(f"not found: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(refined.model_dump_json(indent=2))
        return 0
    print(_c(f"\nrefined → new deliberation {refined.id}", BOLD))
    _report(refined)
    return 0


async def _cmd_ask(council: Council, args: argparse.Namespace) -> int:
    request = DeliberationRequest(
        question=args.question,
        preset=args.preset,
        depth=args.depth,
        context_notes=args.notes,
    )

    result: Deliberation | None = None
    card_id: str | None = None
    async for event in council.deliberate(request):
        if event.type == "done":
            result = Deliberation.model_validate(event.payload["deliberation"])
            card_id = event.payload.get("card_id")
        elif event.type == "card_created":
            card_id = event.payload.get("card_id")
        elif event.type == "error":
            level = "warning" if event.payload.get("recoverable") else "error"
            print(_c(f"[{level}] {event.payload.get('message')}", DIM), file=sys.stderr)
        elif not args.quiet:
            _progress(event)

    if result is None:
        print("no result produced", file=sys.stderr)
        return 1

    if args.json:
        print(result.model_dump_json(indent=2))
    else:
        _report(result)
        if card_id:
            print(_c(f"card {card_id}", BOLD))
            print(
                _wrap(
                    "When you know how this went, close the loop — until then nothing "
                    "here learns anything:"
                )
            )
            print(_wrap(f'python -m app.cli resolve {card_id} --chose "…" --outcome "…"'))
            print()
    return 0


async def _cmd_cards(council: Council, args: argparse.Namespace) -> int:
    from datetime import date as _date

    cards = await council.store.list_cards(args.limit, args.status)
    if args.json:
        print(json.dumps([c.model_dump(mode="json") for c in cards], indent=2, default=str))
        return 0
    if not cards:
        print("no cards yet.")
        return 0

    today = _date.today()
    for card in cards:
        status = card.status(today)
        mark = {"due": GLYPH["arrow"], "resolved": GLYPH["ok"], "open": GLYPH["dot"]}[status]
        due = str(card.expected_outcome.check_on) if card.expected_outcome else ""
        print(
            f"{mark} {_c(card.id, BOLD)}  {status:<9}{due:<12}{_clip(card.question, 58)}"
        )
        if status == "resolved" and card.graded and card.scoring:
            verdicts = " ".join(
                f"{v.module[:4]}:{v.verdict[:1].upper()}" for v in card.scoring.module_verdicts
            )
            print(_c(f"    {verdicts}", DIM))
    print()
    print(_c(f"{len(cards)} cards. Resolve a due one to teach the council something.", DIM))
    return 0


async def _cmd_resolve(council: Council, args: argparse.Namespace) -> int:
    from datetime import date as _date

    happened = _date.fromisoformat(args.on) if args.on else _date.today()
    resolution = Resolution(
        chose=args.chose,
        actual_outcome=args.outcome,
        happened_at=happened,
        surprises=args.surprise,
        notes=args.notes,
    )
    try:
        card = await council.resolve(args.card_id, resolution, grade=not args.no_grade)
    except KeyError:
        print(f"no such card: {args.card_id}", file=sys.stderr)
        return 1

    if args.json:
        print(card.model_dump_json(indent=2))
        return 0
    _report_scoring(card)
    return 0


async def _cmd_grade(council: Council, args: argparse.Namespace) -> int:
    try:
        card = await council.grade(args.card_id)
    except KeyError:
        print(f"no such card: {args.card_id}", file=sys.stderr)
        return 1
    if args.json:
        print(card.model_dump_json(indent=2))
        return 0
    _report_scoring(card)
    return 0


async def _cmd_scores(council: Council, args: argparse.Namespace) -> int:
    computed = await council.store.scores()
    shown = computed if args.all_n else [s for s in computed if s.displayable]

    if args.json:
        print(json.dumps([s.model_dump() for s in shown], indent=2))
        return 0

    if not shown:
        held = len(computed)
        print(
            _wrap(
                f"Nothing to show yet. {held} module/domain combination(s) have data but "
                f"fewer than {MIN_N_TO_DISPLAY} tested decisions, and an accuracy figure "
                "over three decisions is not a measurement. Pass --all to see them anyway."
            )
        )
        return 0

    print(_c(f"{'module':<14}{'domain':<16}{'n':>4}{'hit':>7}{'conf':>7}{'over':>7}{'brier':>8}{'exec':>7}", BOLD))
    for s in sorted(shown, key=lambda x: (x.module, x.domain or "")):
        over = s.overconfidence
        print(
            f"{s.module:<14}{(s.domain or '—'):<16}{s.n:>4}"
            f"{_pct(s.hit_rate):>7}{_pct(s.mean_confidence):>7}"
            f"{(f'{over:+.2f}' if over is not None else '—'):>7}"
            f"{(f'{s.brier:.3f}' if s.brier is not None else '—'):>8}"
            f"{_pct(s.execution_rate):>7}"
        )
    print()
    print(_c(f"brier: lower is better; {CHANCE_BRIER} is what always-50% scores.", DIM))
    print(_c("over: stated confidence minus what happened. Positive = overconfident.", DIM))
    print(_c("exec: share of its advice you actually acted on.", DIM))
    return 0


async def _cmd_priors(council: Council, args: argparse.Namespace) -> int:
    cards = await council.store.list_cards(limit=500)
    built = priors.build(cards)
    if args.json:
        print(json.dumps({k: [p.model_dump() for p in v] for k, v in built.items()}, indent=2))
        return 0
    if not built:
        print(
            _wrap(
                f"No priors yet. Each one needs at least {MIN_N_FOR_PRIOR} graded "
                "decisions, because two data points is an anecdote."
            )
        )
        return 0
    for module, items in sorted(built.items()):
        print(_c(f"\n{module}", BOLD))
        for prior in items:
            print(_wrap(f"{GLYPH['dot']} {prior.pattern}"))
            print(_c(_wrap(f"n={prior.evidence_count} · {', '.join(prior.derived_from[:4])}"), DIM))
    print()
    return 0


def _report_scoring(card) -> None:
    print()
    print(RULE)
    print(_c(_clip(card.question, 76), BOLD))
    print(RULE)
    if card.resolution:
        print(_wrap(f"YOU DID   {card.resolution.chose}"))
        print(_wrap(f"OUTCOME   {card.resolution.actual_outcome}"))
        for surprise in card.resolution.surprises:
            print(_wrap(f"SURPRISE  {surprise}"))

    if not card.scoring:
        print(_wrap("\nNot graded. Run `grade` to score the modules."))
        return

    s = card.scoring
    print()
    print(_c(f"prediction met: {s.expected_outcome_met}", BOLD))
    if not s.chose_was_proposed:
        print(
            _wrap(
                "You did something no module proposed. That is a finding about the "
                "council, not about you — it will be fed back as a prior."
            )
        )
    print()
    for verdict in s.module_verdicts:
        flags = []
        if verdict.followed:
            flags.append("you acted on it")
        if verdict.falsifier_fired:
            flags.append("its falsifier fired")
        if verdict.overridden:
            flags.append("overridden by you")
        suffix = f"  ({', '.join(flags)})" if flags else ""
        print(f"  {verdict.module:<14}{_c(verdict.verdict.upper(), BOLD)}{suffix}")
        print(_c(_wrap(verdict.justification, indent="    "), DIM))
    if s.unpredicted:
        print(_c("\nnobody predicted", BOLD))
        for item in s.unpredicted:
            print(_wrap(f"{GLYPH['dot']} {item}"))
    print()


def _pct(value: float | None) -> str:
    return "—" if value is None else f"{value:.0%}"


def _clip(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else f"{text[: limit - 1]}…"


def _progress(event) -> None:
    p = event.payload
    if event.type == "stage_started":
        print(
            _c(f"\n{GLYPH['arrow']} {p.get('label', p.get('phase'))}", BOLD), file=sys.stderr
        )
    elif event.type == "artifact_complete":
        print(
            _c(f"  {GLYPH['ok']} {p['module']:<13} {p['stage_id']:<16} {p['artifact']['kind']}", DIM),
            file=sys.stderr,
        )
    elif event.type == "artifact_invalid":
        tail = " → repairing" if p.get("repairing") else " → abstaining"
        print(
            _c(f"  ! {p['module']:<13} {p['stage_id']:<16} {p['problems'][0][:70]}{tail}", DIM),
            file=sys.stderr,
        )
    elif event.type == "module_abstained":
        print(_c(f"  {GLYPH['gone']} {p['module']} abstained: {p.get('reason', '')[:80]}", DIM), file=sys.stderr)
    elif event.type == "critique_complete":
        print(_c(f"  {GLYPH['swords']} {p['module']:<13} {len(p['critiques'])} critiques", DIM), file=sys.stderr)
    elif event.type == "revision_complete":
        r = p["revision"]
        print(
            _c(
                f"  {GLYPH['cycle']} {r['module']:<13} {r['delta'][:60]} "
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
            print(_c(f"  {GLYPH['dot']} {artifact.title or artifact.stage_id} {GLYPH['to']} {artifact.kind}", DIM))
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
                    f"{critique.critic} {GLYPH['to']} {critique.target}{ref} "
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
            print(_wrap(f"{GLYPH['dot']} {point.point} ({', '.join(point.modules)})"))

    if s.disagreements:
        print(_c("\nDISAGREEMENTS", BOLD))
        for disagreement in s.disagreements:
            print(_wrap(f"{GLYPH['dot']} {disagreement.issue}"))
            for position in disagreement.positions:
                print(_wrap(f"  {position.module}: {position.position}", indent="    "))
            print(_wrap(f"  resolves if: {disagreement.what_would_resolve_it}", indent="    "))

    if s.blind_spots_fired:
        print(_c("\nBIASES THAT FIRED", BOLD))
        for fired in s.blind_spots_fired:
            mark = "corrected" if fired.corrected else "uncorrected"
            print(_wrap(f"{GLYPH['dot']} {fired.module}/{fired.bias_id} ({mark}): {fired.evidence}"))

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
            print(_wrap(f"{GLYPH['dot']} {minority.module}: {minority.position}"))
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
