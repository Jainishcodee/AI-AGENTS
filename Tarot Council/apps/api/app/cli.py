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
from functools import lru_cache

from .core.config import get_settings
from .core.errors import CognitiveOSError
from .core.logging import setup_logging
from .council import Council
from .learning import divergence, priors
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
    "migrate",
    "projects",
    "replay",
    "divergence",
    "resume",
    "brief",
)


GLOBAL_FLAGS: dict[str, bool] = {
    "--provider": True,
    "--json": False,
    "--quiet": False,
    "--no-persist": False,
    "-h": False,
    "--help": False,
}
"""Flags accepted *before* the subcommand, mapped to whether they take a value.

The single source of truth for where an implied `ask` gets inserted, which is why the
values below are read from here rather than hand-listed twice. `tests/test_cli_parsing.py`
asserts this agrees with the parser.
"""


def build_parser() -> argparse.ArgumentParser:
    """Extracted from `parse_args` so the flag table above can be checked against it."""
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
    ask.add_argument(
        "--project",
        default=None,
        dest="project_id",
        help="Group under an ongoing situation, and prefer its memories on recall.",
    )

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

    projects = sub.add_parser("projects", help="Ongoing situations decisions belong to.")
    projects.add_argument(
        "--new", default=None, metavar="NAME", help="Create a project with this name."
    )
    projects.add_argument("--brief", default="", help="What the situation is.")
    projects.add_argument("--close", default=None, metavar="ID", help="Close a project.")

    replay = sub.add_parser(
        "replay",
        help="Re-decide a resolved card against today's programs and score it against "
        "what actually happened.",
    )
    replay.add_argument("card_id")

    divergence_cmd = sub.add_parser(
        "divergence",
        help="Measure whether the modules actually reason differently, or merely sound "
        "different.",
    )
    divergence_cmd.add_argument(
        "--live",
        action="store_true",
        help="Also run the decision battery. Costs real calls and minutes; without this "
        "only the spec-level checks run.",
    )
    divergence_cmd.add_argument(
        "--limit", type=int, default=None, help="Use only the first N battery decisions."
    )
    divergence_cmd.add_argument("--depth", choices=("quick", "standard", "deep"), default="standard")
    divergence_cmd.add_argument("--preset", default="full")

    resume_cmd = sub.add_parser(
        "resume",
        help="Continue a deliberation that stopped part-way, reusing what it already paid "
        "for. With no id, lists what is resumable.",
    )
    resume_cmd.add_argument("deliberation_id", nargs="?", default=None)
    resume_cmd.add_argument(
        "--discard", action="store_true", help="Throw the checkpoint away instead."
    )

    brief = sub.add_parser(
        "brief",
        help="A ~90-second spoken briefing of a decision: the recommendation, and each "
        "dissenting module in its own voice.",
    )
    brief.add_argument("deliberation_id")
    brief.add_argument(
        "--speak", action="store_true", help="Also synthesise audio (needs edge-tts)."
    )
    brief.add_argument("--out", default=None, help="Where to write the audio.")

    migrate = sub.add_parser(
        "migrate", help="Import legacy JSON-file history into the SQLite store."
    )
    migrate.add_argument(
        "--from-dir",
        default=None,
        dest="from_dir",
        help="The var/ directory holding deliberations/, cards/ and memories.json. "
        "Defaults to the configured store directory.",
    )

    return parser


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    args = list(sys.argv[1:] if argv is None else argv)
    return build_parser().parse_args(_insert_default_command(args))


@lru_cache(maxsize=1)
def _value_taking_flags() -> frozenset[str]:
    """Every option, on any parser, that consumes the token after it.

    Needed so a global-looking token that is really somebody's *value* is not hoisted:
    `--notes "--quiet"` must keep `--quiet` as the note.
    """
    parser = build_parser()
    found: set[str] = set()

    def collect(target: argparse.ArgumentParser) -> None:
        for action in target._actions:  # noqa: SLF001 - no public enumeration exists
            if action.option_strings and action.nargs != 0:
                found.update(action.option_strings)

    collect(parser)
    for action in parser._actions:  # noqa: SLF001
        if isinstance(action, argparse._SubParsersAction):  # noqa: SLF001
            for subparser in action.choices.values():
                collect(subparser)
    return frozenset(found)


def _insert_default_command(args: list[str]) -> list[str]:
    """Normalise argv into `<global flags> <command> <command args>`.

    Two things are being fixed, both of which broke the *documented* invocation:

    - `app.cli "question"` has no subcommand, so `ask` is implied. It must land after the
      global flags and their values, or `--provider mock` looks like the subcommand `mock`.
    - argparse requires global flags to precede the subcommand, but nobody types in that
      order. `--provider mock --depth quick --quiet "…?"` mixes a global flag, one of
      `ask`'s flags, and another global flag. So global flags are **hoisted** to the front
      rather than merely skipped, and order stops mattering.

    An earlier version skipped every flag rather than only global ones, which put `ask`
    after `--depth` and had argparse reject `--depth` at the top level.
    """
    value_flags = _value_taking_flags()
    head: list[str] = []
    tail: list[str] = []
    index = 0

    while index < len(args):
        token = args[index]
        base = token.split("=", 1)[0]
        inline_value = "=" in token and base != token

        if base in GLOBAL_FLAGS:
            head.append(token)
            if GLOBAL_FLAGS[base] and not inline_value and index + 1 < len(args):
                head.append(args[index + 1])
                index += 1
        else:
            tail.append(token)
            # Consume this flag's value here so it can never be mistaken for a global
            # flag on a later pass.
            if base in value_flags and not inline_value and index + 1 < len(args):
                tail.append(args[index + 1])
                index += 1
        index += 1

    if tail and tail[0] not in COMMANDS:
        tail.insert(0, "ask")
    return [*head, *tail]


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
            "migrate": _cmd_migrate,
            "projects": _cmd_projects,
            "replay": _cmd_replay,
            "divergence": _cmd_divergence,
            "resume": _cmd_resume,
            "brief": _cmd_brief,
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


async def _cmd_projects(council: Council, args: argparse.Namespace) -> int:
    if args.new:
        project = await council.create_project(args.new, args.brief)
        print(_c(f"{project.id}  {project.name}", BOLD))
        print(_wrap(f'Use it with: app.cli ask --project {project.id} "..."'))
        return 0

    if args.close:
        try:
            closed = await council.close_project(args.close)
        except KeyError:
            print(f"no such project: {args.close}", file=sys.stderr)
            return 1
        print(_wrap(f"closed {closed.id} ({closed.name})"))
        return 0

    found = await council.store.list_projects()
    if args.json:
        print(json.dumps([p.model_dump(mode="json") for p in found], indent=2, default=str))
        return 0
    if not found:
        print(
            _wrap(
                'No projects. Create one with: app.cli projects --new "Job hunt". '
                "Decisions in the same project share memories, which stops unrelated "
                "ones bleeding into each other."
            )
        )
        return 0
    cards = await council.store.list_cards(limit=500)
    for project in found:
        mine = [c for c in cards if c.project_id == project.id]
        state = "open" if project.open else "closed"
        print(f"{GLYPH['dot']} {_c(project.id, BOLD)}  {state:<7}{len(mine):>3} decisions  {project.name}")
        if project.brief:
            print(_c(_wrap(project.brief, indent="    "), DIM))
    print()
    return 0


async def _cmd_replay(council: Council, args: argparse.Namespace) -> int:
    """Re-decide a resolved card and compare against what actually happened."""
    try:
        result = await council.replay(args.card_id)
    except KeyError:
        print(f"no such card: {args.card_id}", file=sys.stderr)
        return 1
    except CognitiveOSError as exc:
        print(f"{exc}", file=sys.stderr)
        return 1

    if args.json:
        print(result.model_dump_json(indent=2))
        return 0

    print()
    print(RULE)
    print(_c(f"replay of card {result.card_id}", BOLD))
    print(RULE)
    print(
        _wrap(
            f"withheld from the replay: {result.excluded_memories} memories and "
            f"{result.excluded_priors} priors derived from this card. Without that it "
            "would be reading its own answer."
        )
    )
    print()
    print(_c(f"  {'module':<14}{'then':<10}{'now':<10}", BOLD))
    for module in result.modules:
        then = module.then_verdict or "—"
        now = module.now_verdict or "—"
        mark = "" if not module.moved else ("  changed")
        print(f"  {module.module:<14}{then:<10}{now:<10}{_c(mark, DIM)}")
    print()
    print(
        _wrap(
            f"{result.improved} module(s) did better, {result.regressed} worse, on a "
            "decision whose outcome is already known."
        )
    )
    changed = result.versions_changed
    if changed:
        detail = ", ".join(f"{m} v{then}→v{now}" for m, (then, now) in sorted(changed.items()))
        print(_wrap(f"Program versions moved ({detail}), so this measures your change."))
    else:
        print(
            _c(
                _wrap(
                    "No program version changed, so any difference above is model "
                    "variance, not a change you made. Bump a module's `version` and "
                    "replay again to measure an edit."
                ),
                DIM,
            )
        )
    print()
    return 0


async def _cmd_brief(council: Council, args: argparse.Namespace) -> int:
    """Print (and optionally speak) a listenable briefing.

    The script is produced whether or not a speech engine is installed — it is the half
    that carries the thinking, and a missing optional dependency should degrade the
    feature rather than break the command.
    """
    from pathlib import Path

    from .voice import briefing as voice

    found = await council.store.get_deliberation(args.deliberation_id)
    if found is None:
        print(f"no such deliberation: {args.deliberation_id}", file=sys.stderr)
        return 1
    try:
        script = voice.build(found)
    except ValueError as exc:
        print(f"{exc}", file=sys.stderr)
        return 1

    if args.json:
        print(
            json.dumps(
                {
                    "deliberation_id": script.deliberation_id,
                    "estimated_seconds": script.estimated_seconds,
                    "lines": [
                        {"module": l.module, "voice": l.voice, "text": l.text}
                        for l in script.lines
                    ],
                },
                indent=2,
            )
        )
        return 0

    print()
    print(RULE)
    print(_c(f"briefing · about {script.estimated_seconds} seconds", BOLD))
    print(RULE)
    for line in script.lines:
        who = "" if line.module == "narrator" else f"{line.module}: "
        print(_wrap(f"{who}{line.text}"))
    print()

    if not args.speak:
        print(_c(_wrap("Add --speak to hear it. Needs `pip install edge-tts` (free)."), DIM))
        return 0

    if not voice.engine_available():
        print(
            _wrap(
                "No speech engine installed. `pip install edge-tts` — it is free and needs "
                "no key. The script above is unaffected."
            ),
            file=sys.stderr,
        )
        return 1

    out_dir = Path(args.out) if args.out else get_settings().store_dir / "briefings"
    audio = await voice.synthesise(script, out_dir)
    if audio is None:
        print(_wrap("Synthesis failed; the script above is still good."), file=sys.stderr)
        return 1
    print(_wrap(f"audio: {audio}"))
    return 0


async def _cmd_resume(council: Council, args: argparse.Namespace) -> int:
    """List or continue unfinished deliberations."""
    if args.discard and args.deliberation_id:
        await council.discard(args.deliberation_id)
        print(_wrap(f"discarded the checkpoint for {args.deliberation_id}"))
        return 0

    if not args.deliberation_id:
        pending = await council.resumable()
        if args.json:
            print(json.dumps([c.model_dump(mode="json") for c in pending], indent=2, default=str))
            return 0
        if not pending:
            print(_wrap("Nothing unfinished. Every deliberation ran to completion."))
            return 0
        print(_c("unfinished deliberations", BOLD))
        for checkpoint in pending:
            print(
                f"{GLYPH['arrow']} {_c(checkpoint.deliberation_id, BOLD)}  "
                f"{_clip(checkpoint.request.question, 52)}"
            )
            print(_c(_wrap(checkpoint.describe(), indent="    "), DIM))
            if checkpoint.failure:
                print(_c(_wrap(f"stopped because: {checkpoint.failure[:120]}", indent="    "), DIM))
        print()
        print(_c(_wrap("Continue one with: app.cli resume <id>"), DIM))
        return 0

    result: Deliberation | None = None
    try:
        async for event in council.resume(args.deliberation_id):
            if event.type == "done":
                result = Deliberation.model_validate(event.payload["deliberation"])
            elif event.type == "error":
                level = "warning" if event.payload.get("recoverable") else "error"
                print(_c(f"[{level}] {event.payload.get('message')}", DIM), file=sys.stderr)
            elif not args.quiet:
                _progress(event)
    except KeyError:
        print(f"nothing to resume for {args.deliberation_id}", file=sys.stderr)
        return 1
    except CognitiveOSError as exc:
        print(f"{exc}", file=sys.stderr)
        return 1

    if result is None:
        print("the resumed run did not finish either", file=sys.stderr)
        return 1
    if args.json:
        print(result.model_dump_json(indent=2))
    else:
        _report(result)
    return 0


async def _cmd_divergence(council: Council, args: argparse.Namespace) -> int:
    """Is this six algorithms or six voices?

    The structural half is free and always runs. The live half is opt-in because it runs
    the whole battery — on a free tier that is minutes of wall clock and real quota.
    """
    structure = divergence.structural()
    live = None
    if args.live:
        items = divergence.battery(args.limit)
        print(
            _c(
                f"running {len(items)} battery decisions at {args.depth} depth "
                f"({args.preset})… this costs real calls",
                DIM,
            ),
            file=sys.stderr,
        )
        live = await divergence.measure(
            council, limit=args.limit, depth=args.depth, preset=args.preset
        )

    if args.json:
        print(
            json.dumps(
                {
                    "structural": structure.model_dump(mode="json"),
                    "live": live.model_dump(mode="json") if live else None,
                },
                indent=2,
            )
        )
        return 0 if structure.ok and (live is None or not live.failing) else 1

    print()
    print(_c("REPRESENTATION — what each module produces that nothing else does", BOLD))
    for module in structure.modules:
        mark = GLYPH["ok"] if module.distinct else GLYPH["gone"]
        print(f"  {mark} {module.module:<14}{len(module.unique_artifacts)} unique")
        print(_c(_wrap(", ".join(module.unique_artifacts), indent="      "), DIM))

    shared = {k: v for k, v in structure.artifact_owners.items() if len(v) > 1}
    print()
    if shared:
        print(_c("artifact kinds produced by more than one module", BOLD))
        for kind, owners in shared.items():
            print(_wrap(f"{kind}: {', '.join(owners)}"))
    else:
        print(_wrap("No artifact kind is produced by two modules — representations are distinct."))

    print()
    print(_c("CRITIQUE TOPOLOGY", BOLD))
    for module in structure.modules:
        print(
            f"  {module.module:<14}critiques {len(module.critiques)}, "
            f"critiqued by {len(module.critiqued_by)}, "
            f"{module.biases_detected_elsewhere} of its biases watched elsewhere"
        )

    if structure.problems:
        print()
        print(_c("STRUCTURAL PROBLEMS", BOLD))
        for problem in structure.problems:
            print(_wrap(f"{GLYPH['gone']} {problem}"))

    if live is None:
        print()
        print(
            _c(
                _wrap(
                    "Spec-level checks only. Whether the modules actually reach different "
                    "conclusions needs real runs: add --live (and expect it to take a "
                    "while on a free key)."
                ),
                DIM,
            )
        )
        return 0 if structure.ok else 1

    print()
    print(_c(f"BEHAVIOUR over {len(live.battery)} decisions", BOLD))
    print(
        _c(
            f"  {'module':<14}{'dissents':>9}{'named':>7}{'crits':>7}{'accepted':>10}{'overlap':>9}",
            BOLD,
        )
    )
    for module in live.modules:
        overlap = (
            f"{module.stance_similarity:.2f}" if module.stance_similarity is not None else "—"
        )
        mark = " " if module.passes else GLYPH["gone"]
        print(
            f"{mark} {module.module:<14}{module.dissents:>9}{module.disagreements:>7}"
            f"{module.critiques_raised:>7}{module.critiques_accepted:>10}{overlap:>9}"
        )

    print()
    if live.mean_stance_similarity is not None:
        verdict = (
            "distinct conclusions"
            if live.mean_stance_similarity <= 0.6
            else "SUSPICIOUSLY SIMILAR — the modules may have collapsed into one voice"
        )
        print(_wrap(f"mean pairwise stance overlap: {live.mean_stance_similarity:.2f} — {verdict}"))
    for note in live.notes:
        print(_c(_wrap(note), DIM))

    if live.failing:
        print()
        print(_c("MODULES THAT DID NOT EARN THEIR PLACE", BOLD))
        for module in live.modules:
            for problem in module.problems:
                print(_wrap(f"{module.module}: {problem}"))

    print()
    return 0 if structure.ok and not live.failing else 1


async def _cmd_migrate(council: Council, args: argparse.Namespace) -> int:
    """Bring legacy JSON history into SQLite.

    Idempotent — every write is an upsert on id — so running it twice is safe and
    running it after new decisions have been recorded does not clobber them.
    """
    from pathlib import Path

    from .memory.sqlite_store import SQLiteStore
    from .memory.store import FileStore

    target = council.store
    if not isinstance(target, SQLiteStore):
        print(
            _wrap(
                "The active store is not SQLite, so there is nothing to migrate into. "
                "Set COUNCIL_STORE=sqlite and run this again."
            ),
            file=sys.stderr,
        )
        return 1

    source_dir = Path(args.from_dir) if args.from_dir else get_settings().store_dir
    if not (source_dir / "cards").is_dir() and not (source_dir / "deliberations").is_dir():
        print(_wrap(f"No JSON history found under {source_dir}. Nothing to do."))
        return 0

    counts = await target.import_from(FileStore(source_dir))
    if args.json:
        print(json.dumps(counts, indent=2))
        return 0
    print(
        _wrap(
            f"Imported {counts['deliberations']} deliberations, {counts['cards']} cards "
            f"and {counts['memories']} memories from {source_dir}."
        )
    )
    print(_c(_wrap("The JSON files are left untouched; delete them once you are happy."), DIM))
    return 0


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
        project_id=args.project_id,
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
