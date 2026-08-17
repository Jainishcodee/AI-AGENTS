"""The council as something you listen to.

The temptation is to treat this as text-to-speech: pipe the deliberation into a voice and
ship it. That produces twenty minutes of audio nobody finishes. Six full analyses are a
*reading* artefact — they are tables, graphs and cited rows, and none of that survives
being read aloud.

So voice is a **summarisation** problem first. A briefing is the part that is genuinely
better heard than read:

    the recommendation · what would make it wrong · then each dissenting module,
    in its own voice, saying what it would do instead and when it would be right

That is about ninety seconds, it is the shape of a real conversation, and the dissent is
what makes it worth hearing rather than a notification read out. If you want the tables,
open the trace.

Synthesis is free: `edge-tts` is a pip package against Microsoft's public endpoint — no
key, no card, and a genuinely large voice inventory, which is what lets six modules sound
like six people. ElevenLabs is better and costs money, so it is a config swap rather than
the default. If no engine is installed the script is still produced, because the script is
the useful half and it is fully testable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from ..core.logging import get_logger
from ..programs import loader
from ..schemas.council import Deliberation

log = get_logger(__name__)

# Distinct enough to be told apart with eyes closed, which is the only requirement that
# matters. Assigned per module rather than per skin so dropping the LOTM layer (ADR-016)
# does not silently reassign anyone's voice.
VOICES: dict[str, str] = {
    "narrator": "en-GB-RyanNeural",
    "analyst": "en-GB-ThomasNeural",
    "tactician": "en-US-GuyNeural",
    "strategist": "en-GB-RyanNeural",
    "psychologist": "en-GB-SoniaNeural",
    "optimizer": "en-AU-WilliamNeural",
    "ethicist": "en-GB-LibbyNeural",
}
FALLBACK_VOICE = "en-GB-RyanNeural"

MAX_DISSENTS = 3
"""Beyond three, a briefing stops being listenable. The rest are in the transcript."""


@dataclass(slots=True)
class Line:
    """One spoken line, with the voice that should say it."""

    module: str
    voice: str
    text: str

    @property
    def words(self) -> int:
        return len(self.text.split())


@dataclass(slots=True)
class Briefing:
    deliberation_id: str
    lines: list[Line]

    @property
    def script(self) -> str:
        return "\n\n".join(f"[{line.module}] {line.text}" for line in self.lines)

    @property
    def words(self) -> int:
        return sum(line.words for line in self.lines)

    @property
    def estimated_seconds(self) -> int:
        # ~155 wpm is a normal narration pace; the figure exists so the UI can say
        # "about ninety seconds" before spending anything on synthesis.
        return round(self.words / 155 * 60)


def build(deliberation: Deliberation) -> Briefing:
    """Turn a finished deliberation into something worth listening to."""
    synthesis = deliberation.synthesis
    if synthesis is None:
        raise ValueError("a deliberation with no synthesis has nothing to brief")

    programs = loader.programs()
    lines: list[Line] = []

    def say(module: str, text: str) -> None:
        cleaned = _speakable(text)
        if cleaned:
            lines.append(Line(module=module, voice=VOICES.get(module, FALLBACK_VOICE), text=cleaned))

    say("narrator", f"On the question: {deliberation.question}")
    say("narrator", f"The council's recommendation is this. {synthesis.recommendation.action}")
    say("narrator", f"Start with: {synthesis.recommendation.first_action}")

    if synthesis.recommendation.do_not:
        say("narrator", "Do not: " + _list(synthesis.recommendation.do_not))

    say(
        "narrator",
        f"Confidence is {round(synthesis.confidence.score * 100)} percent. "
        f"This recommendation is wrong if {synthesis.confidence.falsifier}",
    )

    # The dissent is the reason to listen rather than read a notification, so each one
    # gets the dissenting module's own voice.
    dissents = synthesis.minority_opinions[:MAX_DISSENTS]
    if dissents:
        say("narrator", "Not everyone agrees.")
        for minority in dissents:
            skin = programs[minority.module].skin.name if minority.module in programs else minority.module
            say(minority.module, f"{skin} disagrees. {minority.position}")
            say(minority.module, f"That would be the right call if {minority.when_it_would_be_right}")
        if len(synthesis.minority_opinions) > MAX_DISSENTS:
            say(
                "narrator",
                f"There are {len(synthesis.minority_opinions) - MAX_DISSENTS} further "
                "dissenting views in the transcript.",
            )

    if synthesis.ethical_veto_response:
        say("ethicist", "There is an ethical objection on the record.")
        say("narrator", synthesis.ethical_veto_response)

    say("narrator", f"What no module examined: {synthesis.council_blind_spot}")

    if synthesis.information_to_gather:
        say("narrator", f"Find out first: {synthesis.information_to_gather[0]}")

    # `_speakable` only guarantees punctuation at the *end* of what it is given, so an
    # interior boundary has to be closed here or the two sentences run together — "about
    # the next 90 days Check back in 90 days" is what that sounds like.
    say(
        "narrator",
        f"The prediction on record: {_speakable(synthesis.expected_outcome.statement)} "
        f"Check back in {synthesis.expected_outcome.check_in_days} days.",
    )

    return Briefing(deliberation_id=deliberation.id, lines=lines)


async def synthesise(briefing: Briefing, out_dir: Path) -> Path | None:
    """Render the briefing to a single audio file, if an engine is available.

    Returns `None` when nothing is installed. Deliberately not an error: the script is the
    valuable half and it is produced regardless, so a missing optional dependency
    degrades the feature instead of breaking the command.
    """
    try:
        import edge_tts  # type: ignore[import-not-found]
    except ImportError:
        log.info("edge-tts is not installed; briefing script produced without audio")
        return None

    out_dir.mkdir(parents=True, exist_ok=True)
    parts: list[Path] = []

    for index, line in enumerate(briefing.lines):
        part = out_dir / f"{briefing.deliberation_id}-{index:02d}.mp3"
        try:
            await edge_tts.Communicate(line.text, line.voice).save(str(part))
        except Exception as exc:  # noqa: BLE001 - a network TTS endpoint can simply fail
            log.warning("could not synthesise line %d: %s", index, exc)
            # Leave nothing half-written behind. Returning here with the earlier parts
            # still on disk litters the output directory with fragments of a briefing
            # nobody can play, and the caller has already been told this failed.
            for orphan in parts:
                orphan.unlink(missing_ok=True)
            return None
        parts.append(part)

    combined = out_dir / f"{briefing.deliberation_id}.mp3"
    if not _concatenate(parts, combined):
        # The join is byte-wise and needs no tools, so a failure here is the filesystem
        # (full disk, permissions), not a missing dependency. The separate parts are still
        # playable in order, which beats failing outright.
        log.info("could not write the joined file; leaving %d separate parts", len(parts))
        return parts[0] if parts else None

    for part in parts:
        part.unlink(missing_ok=True)
    return combined


def _concatenate(parts: list[Path], target: Path) -> bool:
    """MP3 frames concatenate byte-wise, so this needs no dependency at all.

    ffmpeg would be tidier about metadata, but requiring it to hear a briefing is a poor
    trade — players handle a naive join fine.
    """
    if not parts:
        return False
    try:
        with target.open("wb") as out:
            for part in parts:
                out.write(part.read_bytes())
        return True
    except OSError as exc:
        log.warning("could not join audio parts: %s", exc)
        return False


def engine_available() -> bool:
    try:
        import edge_tts  # noqa: F401
    except ImportError:
        return False
    return True


_MARKUP = re.compile(r"[`*_#\[\]]+")
_WHITESPACE = re.compile(r"\s+")
# `module/stage/Kind#row` and the parenthesised form. Matched with the `#` still present,
# which is why this has to run *before* markup stripping — `_MARKUP` removes `#` and `_`,
# and a citation with those gone is unrecognisable and unspeakable.
_ROW_REF = re.compile(r"\(?\b[a-z][a-z_]*/[a-z][\w.-]*/[A-Za-z]\w*(?:#[\w.-]+)?\)?")


def _speakable(text: str) -> str:
    """Strip what only makes sense on a page.

    Row ids, markdown and bracketed asides are precise in the trace and noise out loud —
    "analyst slash evidence slash EvidenceLedger hash e one" is not a sentence anyone
    wants read to them.
    """
    cleaned = _ROW_REF.sub("", text or "")
    cleaned = _MARKUP.sub("", cleaned)
    cleaned = _WHITESPACE.sub(" ", cleaned).strip()
    cleaned = re.sub(r"\s+([.,;:!?])", r"\1", cleaned)
    if cleaned and cleaned[-1] not in ".!?":
        cleaned += "."
    return cleaned


def _list(items: list[str]) -> str:
    speakable = [_speakable(item).rstrip(".") for item in items if item.strip()]
    if not speakable:
        return ""
    if len(speakable) == 1:
        return f"{speakable[0]}."
    return "; ".join(speakable[:-1]) + f"; and {speakable[-1]}."
