"""`doctor` — one command that says what is wrong (Phase 6).

Every failure this reports has already cost somebody an evening: a key that was never
set, a store two migrations behind, a route pointing at a model the free tier does not
serve. Each surfaces late and badly — mid-deliberation, after the first calls have
already been spent — and the error you see names the symptom rather than the cause.

The rule here is that a check must be **cheap and offline**. Nothing in this module makes
a network call or spends a token: a diagnostic you hesitate to run because it costs quota
is a diagnostic nobody runs. That means it cannot tell you a key is *rejected*, only that
it is absent — and it says so rather than implying more confidence than it has.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Literal

from .core.config import Settings
from .core.errors import ProgramInvalid
from .programs import loader

Status = Literal["ok", "warn", "fail"]

NOT_ON_FREE_TIER: frozenset[str] = frozenset({"gemini-2.5-pro"})
"""Models that exist but are not served on the free tier.

Routing at one of these fails on the *first* call with an error that reads like a quota
problem, which sends people to the wrong fix entirely (ADR-020).
"""

KNOWN_PROVIDERS: frozenset[str] = frozenset({"gemini", "openrouter", "ollama", "mock"})


@dataclass(slots=True)
class Check:
    name: str
    status: Status
    detail: str
    fix: str = ""

    @property
    def ok(self) -> bool:
        return self.status == "ok"


@dataclass(slots=True)
class Report:
    checks: list[Check] = field(default_factory=list)

    @property
    def failures(self) -> list[Check]:
        return [c for c in self.checks if c.status == "fail"]

    @property
    def warnings(self) -> list[Check]:
        return [c for c in self.checks if c.status == "warn"]

    @property
    def healthy(self) -> bool:
        return not self.failures

    def summary(self) -> str:
        if self.failures:
            return f"{len(self.failures)} problem(s) will stop a deliberation"
        if self.warnings:
            return f"ready, with {len(self.warnings)} thing(s) worth knowing"
        return "ready"


def _key_for(provider: str, settings: Settings) -> str | None:
    return {
        "gemini": settings.gemini_api_key,
        "openrouter": settings.openrouter_api_key,
    }.get(provider)


def _routes(settings: Settings) -> dict[str, str]:
    return {
        "intake": settings.route_intake,
        "reasoning": settings.route_reasoning,
        "synthesis": settings.route_synthesis,
    }


def check_routes(settings: Settings) -> list[Check]:
    """Every configured route names a known provider, with a key, on a servable model."""
    out: list[Check] = []
    seen_missing: set[str] = set()

    for role, route in _routes(settings).items():
        provider, _, model = route.partition(":")
        if provider not in KNOWN_PROVIDERS:
            out.append(
                Check(
                    f"route:{role}",
                    "fail",
                    f"'{route}' names unknown provider '{provider}'",
                    f"Known: {', '.join(sorted(KNOWN_PROVIDERS))}",
                )
            )
            continue

        if provider in ("gemini", "openrouter") and not _key_for(provider, settings):
            # Reported once per provider, not once per role: three identical lines for
            # one missing key reads as three problems.
            if provider not in seen_missing:
                seen_missing.add(provider)
                out.append(
                    Check(
                        f"key:{provider}",
                        "fail",
                        f"{provider.upper()}_API_KEY is not set, but {role} routes to it",
                        "Put it in .env at the repo root. `--provider mock` needs no key.",
                    )
                )
        if model in NOT_ON_FREE_TIER:
            out.append(
                Check(
                    f"route:{role}",
                    "warn",
                    f"'{model}' is not served on the free tier",
                    "The first call fails with what looks like a quota error. Use "
                    "gemini-2.5-flash unless you are on a paid key.",
                )
            )

    if not any(c.status != "ok" for c in out):
        out.append(
            Check("routes", "ok", ", ".join(f"{r}={v}" for r, v in _routes(settings).items()))
        )
    return out


def check_programs() -> Check:
    """The six built-ins load and pass all ten rules. This is fatal at boot, so check early."""
    try:
        programs = loader.programs()
        presets = loader.presets()
    except ProgramInvalid as exc:
        return Check("programs", "fail", str(exc), "A built-in program is malformed.")
    return Check(
        "programs", "ok", f"{len(programs)} modules, {len(presets)} presets, all rules pass"
    )


def check_store(settings: Settings) -> list[Check]:
    """Store reachable, and at the schema version this build expects.

    An unmigrated store is the nastiest failure here because it half-works: older tables
    are still readable, so the break arrives later, on whichever feature needs the new
    column, looking like a bug in that feature.
    """
    from .memory.sqlite_store import SCHEMA_VERSION

    if settings.store == "memory":
        return [
            Check(
                "store",
                "warn",
                "store=memory — nothing is persisted",
                "Set COUNCIL_STORE=sqlite in .env, or the corpus cannot accumulate.",
            )
        ]

    if settings.store == "file":
        return [
            Check(
                "store",
                "warn",
                "store=file — the legacy JSON store (ADR-024)",
                "Set COUNCIL_STORE=sqlite and run `app.cli migrate` to import it.",
            )
        ]

    path = Path(settings.store_dir) / "cognitive-os.sqlite3"
    if not path.exists():
        return [
            Check(
                "store",
                "warn",
                f"no database at {path.name} yet",
                "Created on first use. `app.cli migrate` imports legacy JSON history.",
            )
        ]

    try:
        conn = sqlite3.connect(path)
        try:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
        finally:
            conn.close()
    except sqlite3.Error as exc:
        return [Check("store", "fail", f"cannot open {path.name}: {exc}", "")]

    if version < SCHEMA_VERSION:
        return [
            Check(
                "store",
                "fail",
                f"schema v{version}, this build expects v{SCHEMA_VERSION}",
                "Migrations run on open; if this persists the file is not ours.",
            )
        ]
    if version > SCHEMA_VERSION:
        return [
            Check(
                "store",
                "fail",
                f"schema v{version} is newer than this build's v{SCHEMA_VERSION}",
                "Update the code rather than the database.",
            )
        ]
    return [Check("store", "ok", f"sqlite v{version} at {path.name}")]


def check_pacing(settings: Settings) -> Check:
    """`max_rpm` is what actually decides whether a run finishes (ADR-020)."""
    if settings.max_rpm <= 0:
        return Check(
            "pacing",
            "warn",
            "COUNCIL_MAX_RPM=0 — unpaced",
            "Right for mock or a paid key. On a free tier this trips 429s immediately.",
        )
    if settings.max_rpm > 15:
        return Check(
            "pacing",
            "warn",
            f"COUNCIL_MAX_RPM={settings.max_rpm} is above any free tier",
            "Free Gemini serves roughly 5-10 req/min; too high means 429s and backoff.",
        )
    return Check(
        "pacing", "ok", f"{settings.max_rpm} req/min, {settings.max_concurrency} concurrent"
    )


async def check_corpus(store) -> list[Check]:
    """What the learning loop actually has to work with.

    Reported because an empty corpus is not a *fault* — it is the honest state of a new
    install, and it is also the single thing blocking every outstanding measurement in the
    roadmap. Saying so plainly beats letting somebody wonder why `scores` is empty.
    """
    try:
        cards = await store.list_cards(limit=500)
    except Exception as exc:  # noqa: BLE001 - a diagnostic must survive a broken store
        return [Check("corpus", "fail", f"cannot read cards: {exc}", "")]

    today = date.today()
    resolved = [c for c in cards if c.resolution is not None]
    due = [c for c in cards if c.status(today) == "due"]

    out = [
        Check(
            "corpus",
            "ok" if resolved else "warn",
            f"{len(cards)} decision(s), {len(resolved)} resolved",
            ""
            if resolved
            else "Calibration, priors and replay are all downstream of resolved cards. "
            "Nothing learns until one is closed.",
        )
    ]
    if due:
        out.append(
            Check(
                "due",
                "warn",
                f"{len(due)} decision(s) due for a check-in",
                "`app.cli checkin` walks them; `app.cli calendar` puts them on your phone.",
            )
        )
    else:
        out.append(Check("due", "ok", "nothing due today"))
    return out


def check_voice() -> Check:
    """Optional dependency, reported so its absence is a fact rather than a surprise."""
    try:
        import edge_tts  # noqa: F401
    except ImportError:
        return Check(
            "voice",
            "warn",
            "edge-tts not installed — `brief --speak` produces no audio",
            "pip install edge-tts (free, no key). The script is produced regardless.",
        )
    return Check("voice", "ok", "edge-tts available")


async def run(settings: Settings, store) -> Report:
    """Every check, in the order they would bite you."""
    report = Report()
    report.checks.append(check_programs())
    report.checks.extend(check_routes(settings))
    report.checks.extend(check_store(settings))
    report.checks.append(check_pacing(settings))
    report.checks.extend(await check_corpus(store))
    report.checks.append(check_voice())
    return report
