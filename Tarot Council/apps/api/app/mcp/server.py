"""MCP server — Cognitive OS as a tool other agents can consult.

Speaks the Model Context Protocol over stdio using nothing but the standard library:
MCP is JSON-RPC 2.0 over newline-delimited JSON, and implementing the four methods we
need is ~150 lines against a dependency that would pin us to one SDK's release cycle.

Design choice worth naming: the tools exposed here are **deliberately not** a mirror
of the HTTP API. An agent calling this wants an answer and the dissent, not a 40k-token
transcript — so `consult` returns the recommendation, the disagreements, the minority
opinions and the council's own blind spot, and hands back a `deliberation_id` for
anything deeper. Returning everything would blow the caller's context and bury the part
that matters.

    python -m app.mcp                      # stdio, for an MCP client
    python -m app.mcp --provider mock      # no key, no network
"""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

from ..core.config import get_settings
from ..core.errors import CognitiveOSError
from ..core.logging import get_logger, setup_logging
from ..council import Council
from ..engine.planner import call_estimate
from ..learning import priors as priors_module
from ..programs import loader
from ..schemas.cards import Resolution
from ..schemas.council import DeliberationRequest

log = get_logger(__name__)

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "cognitive-os", "version": "0.1.0"}

# Kept small on purpose. Every tool here is one an agent can act on; the full
# transcript is available by id for the rare case that wants it.
TOOLS: list[dict[str, Any]] = [
    {
        "name": "consult",
        "description": (
            "Put a real decision to a council of six reasoning engines that each run a "
            "different algorithm (evidence and probability; asymmetry and tempo; power "
            "and incentives; human psychology; constraint and efficiency; values and "
            "regret). Returns one recommendation plus the disagreements and minority "
            "opinions, so you can see what the council was divided on rather than only "
            "what it concluded. Use for decisions with tradeoffs, not for factual "
            "lookups. Include constraints and the people involved — the modules will "
            "not invent them, and will say so if they are missing."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "The decision, in the asker's own words.",
                },
                "context": {
                    "type": "string",
                    "description": "Constraints, actors, money, deadlines, what has been tried.",
                },
                "preset": {
                    "type": "string",
                    "enum": [
                        "full",
                        "strategy",
                        "people",
                        "execution",
                        "life",
                        *(f"solo:{m}" for m in sorted(loader.programs())),
                    ],
                    "description": (
                        "Which engines run. `strategy` for power and moves, `people` for "
                        "relationships, `execution` for effort, `life` for irreversible "
                        "personal decisions, `full` for all six."
                    ),
                },
                "depth": {
                    "type": "string",
                    "enum": ["quick", "standard", "deep"],
                    "description": (
                        "quick skips the debate round (~9 calls). standard adds critique "
                        "and revision (~26). deep runs every stage separately (~56) and "
                        "is minutes of wall clock."
                    ),
                },
            },
            "required": ["question"],
        },
    },
    {
        "name": "list_modules",
        "description": (
            "The reasoning engines available, what each is forced to produce before it "
            "may conclude, and its known failure modes."
        ),
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_deliberation",
        "description": (
            "The full transcript of a past deliberation by id: every module's stage "
            "artifacts, the critiques between them, and the synthesis. Large — fetch "
            "only when the summary from `consult` is not enough."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"deliberation_id": {"type": "string"}},
            "required": ["deliberation_id"],
        },
    },
    {
        "name": "record_outcome",
        "description": (
            "Record what actually happened for a past decision, and score every engine "
            "against what it said. This is what makes the council improve — without it "
            "nothing here learns anything, because there is no ground truth about a "
            "decision except the outcome."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "card_id": {"type": "string"},
                "chose": {
                    "type": "string",
                    "description": "What was actually done — free text, not one of the options.",
                },
                "outcome": {"type": "string", "description": "What happened as a result."},
                "surprises": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Anything that happened which nobody predicted.",
                },
            },
            "required": ["card_id", "chose", "outcome"],
        },
    },
    {
        "name": "track_record",
        "description": (
            "How each engine has actually performed for this user: hit rate, calibration "
            "(stated confidence vs. what happened), and how often its advice was taken. "
            "Withheld below 8 resolved decisions, because a figure over three is not a "
            "measurement."
        ),
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "pending_checkins",
        "description": (
            "Decisions whose predicted-outcome date has arrived and which are waiting for "
            "someone to record what happened."
        ),
        "inputSchema": {"type": "object", "properties": {}},
    },
]


class MCPServer:
    def __init__(self, council: Council) -> None:
        self._council = council

    # ------------------------------------------------------------- dispatch --

    async def handle(self, message: dict[str, Any]) -> dict[str, Any] | None:
        method = message.get("method")
        request_id = message.get("id")
        params = message.get("params") or {}

        # Notifications have no id and must never be answered.
        if request_id is None:
            return None

        try:
            if method == "initialize":
                result: Any = {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {"tools": {}},
                    "serverInfo": SERVER_INFO,
                }
            elif method == "tools/list":
                result = {"tools": TOOLS}
            elif method == "tools/call":
                result = await self._call(params.get("name", ""), params.get("arguments") or {})
            elif method == "ping":
                result = {}
            else:
                return _error(request_id, -32601, f"unknown method: {method}")
        except CognitiveOSError as exc:
            return _error(request_id, -32000, str(exc))
        except Exception as exc:  # noqa: BLE001 - a bad call must not kill the server
            log.exception("tool call failed")
            return _error(request_id, -32603, f"internal error: {exc}")

        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    async def _call(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        handler = {
            "consult": self._consult,
            "list_modules": self._list_modules,
            "get_deliberation": self._get_deliberation,
            "record_outcome": self._record_outcome,
            "track_record": self._track_record,
            "pending_checkins": self._pending_checkins,
        }.get(name)
        if handler is None:
            return _tool_error(f"unknown tool: {name}")
        return await handler(args)

    # ---------------------------------------------------------------- tools --

    async def _consult(self, args: dict[str, Any]) -> dict[str, Any]:
        question = (args.get("question") or "").strip()
        if len(question) < 8:
            return _tool_error("`question` must describe an actual decision.")

        result = await self._council.run(
            DeliberationRequest(
                question=question,
                preset=args.get("preset"),
                depth=args.get("depth"),
                context_notes=args.get("context") or "",
            )
        )
        synthesis = result.synthesis
        if synthesis is None:
            return _tool_error("the council did not reach a synthesis")

        cards = await self._council.store.list_cards(limit=1)
        card_id = cards[0].id if cards and cards[0].deliberation_id == result.id else None

        # Deliberately a summary. An agent needs the answer and the dissent; the
        # transcript is 40k tokens and available by id.
        payload = {
            "deliberation_id": result.id,
            "card_id": card_id,
            "recommendation": synthesis.recommendation.model_dump(),
            "confidence": synthesis.confidence.model_dump(),
            "wrong_if": synthesis.confidence.falsifier,
            "disagreements": [
                {
                    "issue": d.issue,
                    "positions": {p.module: p.position for p in d.positions},
                    "what_would_resolve_it": d.what_would_resolve_it,
                }
                for d in synthesis.disagreements
            ],
            "minority_opinions": [m.model_dump() for m in synthesis.minority_opinions],
            "what_no_module_examined": synthesis.council_blind_spot,
            "find_out_first": synthesis.information_to_gather,
            "expected_outcome": synthesis.expected_outcome.model_dump(),
            "abstained": [r.module for r in result.runs if r.abstained],
            "per_module": {
                r.module: {
                    "stance": r.conclusion.stance,
                    "confidence": r.conclusion.confidence.score,
                    "wrong_if": r.conclusion.confidence.falsifier,
                }
                for r in result.runs
                if r.conclusion
            },
            "usage": {"calls": result.usage.calls},
        }
        if synthesis.ethical_veto_response:
            payload["ethical_veto_response"] = synthesis.ethical_veto_response
        return _ok(payload)

    async def _list_modules(self, _args: dict[str, Any]) -> dict[str, Any]:
        return _ok(
            [
                {
                    "id": program.id,
                    "name": program.skin.name,
                    "summary": program.summary.strip(),
                    "produces": [s.produces for s in program.stages if not s.terminal],
                    "known_failure_modes": [b.description for b in program.biases],
                    "holds_ethical_veto": program.veto_enabled,
                    "calls": {
                        depth: call_estimate(program, depth)
                        for depth in ("quick", "standard", "deep")
                    },
                }
                for program in loader.programs().values()
            ]
        )

    async def _get_deliberation(self, args: dict[str, Any]) -> dict[str, Any]:
        found = await self._council.store.get_deliberation(args.get("deliberation_id", ""))
        if found is None:
            return _tool_error("no such deliberation")
        return _ok(found.model_dump(mode="json"))

    async def _record_outcome(self, args: dict[str, Any]) -> dict[str, Any]:
        from datetime import date

        try:
            card = await self._council.resolve(
                args["card_id"],
                Resolution(
                    chose=args["chose"],
                    actual_outcome=args["outcome"],
                    happened_at=date.today(),
                    surprises=args.get("surprises") or [],
                ),
            )
        except KeyError:
            return _tool_error("no such card")

        scoring = card.scoring
        return _ok(
            {
                "card_id": card.id,
                "prediction_met": scoring.expected_outcome_met if scoring else "ungraded",
                "chose_something_no_module_proposed": (
                    not scoring.chose_was_proposed if scoring else None
                ),
                "verdicts": {
                    v.module: {
                        "verdict": v.verdict,
                        "you_acted_on_it": v.followed,
                        "its_falsifier_fired": v.falsifier_fired,
                        "why": v.justification,
                    }
                    for v in (scoring.module_verdicts if scoring else [])
                },
                "nobody_predicted": scoring.unpredicted if scoring else [],
            }
        )

    async def _track_record(self, _args: dict[str, Any]) -> dict[str, Any]:
        computed = await self._council.store.scores()
        shown = [s for s in computed if s.displayable]
        cards = await self._council.store.list_cards(limit=500)
        return _ok(
            {
                "scores": [
                    {
                        "module": s.module,
                        "domain": s.domain,
                        "n": s.n,
                        "hit_rate": s.hit_rate,
                        "overconfidence": s.overconfidence,
                        "brier": s.brier,
                        "execution_rate": s.execution_rate,
                    }
                    for s in shown
                ],
                "withheld_for_small_sample": len(computed) - len(shown),
                "note": (
                    "Nothing is reported below 8 resolved decisions. An accuracy figure "
                    "over three decisions is not a measurement."
                ),
                "learned_patterns": {
                    module: [p.pattern for p in items]
                    for module, items in priors_module.build(cards).items()
                },
            }
        )

    async def _pending_checkins(self, _args: dict[str, Any]) -> dict[str, Any]:
        due = await self._council.store.list_cards(limit=50, status="due")
        return _ok(
            [
                {
                    "card_id": card.id,
                    "question": card.question,
                    "predicted": card.expected_outcome.statement if card.expected_outcome else None,
                    "was_due": str(card.expected_outcome.check_on) if card.expected_outcome else None,
                }
                for card in due
            ]
        )


# ------------------------------------------------------------------ framing --


def _ok(payload: Any) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": json.dumps(payload, indent=2, default=str)}],
        "isError": False,
    }


def _tool_error(message: str) -> dict[str, Any]:
    """A tool-level failure, not a protocol one.

    Reported inside a successful JSON-RPC result with `isError`, which is what lets the
    calling model read the message and try something else rather than seeing a
    transport fault.
    """
    return {"content": [{"type": "text", "text": message}], "isError": True}


def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


# -------------------------------------------------------------------- stdio --


async def serve(council: Council) -> None:
    """Read newline-delimited JSON-RPC from stdin, write responses to stdout.

    stdin is read on a worker thread rather than through `loop.connect_read_pipe`:
    that call is unreliable for stdin on Windows and outright unsupported on the
    selector event loop, and a stdio server handles a handful of messages a second at
    most, so a blocking `readline` in an executor costs nothing and works everywhere.

    stdout is the protocol channel and must carry nothing else — all logging goes to
    stderr, which is why `setup_logging` writes there.
    """
    server = MCPServer(council)
    loop = asyncio.get_running_loop()

    while True:
        line = await loop.run_in_executor(None, sys.stdin.readline)
        if not line:  # EOF: the client closed the pipe
            break
        text = line.strip()
        if not text:
            continue
        try:
            message = json.loads(text)
        except json.JSONDecodeError as exc:
            _write(_error(None, -32700, f"parse error: {exc}"))
            continue

        response = await server.handle(message)
        if response is not None:
            _write(response)


def _write(payload: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, default=str) + "\n")
    sys.stdout.flush()


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    provider = None
    if "--provider" in args:
        provider = args[args.index("--provider") + 1]

    settings = get_settings()
    setup_logging(settings.log_level)
    council = Council(settings, force_provider=provider)

    async def run() -> None:
        try:
            await serve(council)
        finally:
            await council.aclose()

    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        return 130
    return 0
