"""Opening Windows apps.

The pet's first real task. Two lookups, in order:

1. The recipe book — something you've already taught it. Exact, instant.
2. The Start Menu index — fuzzy matched, and only acted on when the match is
   *clearly* the best one.

If neither is confident, the pet does not pick the closest guess and hope.
It asks you, and records your answer so it never has to ask again.
"""
import difflib
import os
from dataclasses import dataclass
from pathlib import Path

from core.recipes import book

START_MENUS = [
    Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
    Path(os.environ.get("PROGRAMDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
]

# Shortcuts that are not "an app you'd ask to open".
NOISE = ("uninstall", "readme", "read me", "help", "documentation", "release notes",
         "website", "home page", "homepage", "manual", "license", "support",
         "報告", "modify", "repair")

# A few things that have no Start Menu shortcut but you'd still ask for.
BUILTINS = {
    "file explorer": "explorer.exe",
    "explorer": "explorer.exe",
    "settings": "ms-settings:",
    "task manager": "taskmgr.exe",
    "control panel": "control.exe",
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "command prompt": "cmd.exe",
    "terminal": "wt.exe",
}

# Below this, "closest match" is meaningless and the pet must ask.
MIN_SCORE = 0.60
# A match this good, with clear daylight to the runner-up, can just be opened.
CONFIDENT_SCORE = 0.82
CLEAR_MARGIN = 0.08


@dataclass(frozen=True)
class AppEntry:
    name: str
    target: str          # .lnk / .url / .exe / shell URI

    def launch(self) -> None:
        os.startfile(self.target)   # noqa: S606 - ShellExecute, Windows only


_index: list[AppEntry] | None = None


def index(refresh: bool = False) -> list[AppEntry]:
    """All launchable apps, deduped by name. Cached — scanning is ~200 files."""
    global _index
    if _index is not None and not refresh:
        return _index

    seen: dict[str, AppEntry] = {}
    for root in START_MENUS:
        if not root.is_dir():
            continue
        for pattern in ("*.lnk", "*.url"):
            for f in root.rglob(pattern):
                name = f.stem.strip()
                low = name.lower()
                if not name or any(n in low for n in NOISE):
                    continue
                seen.setdefault(low, AppEntry(name, str(f)))

    for name, target in BUILTINS.items():
        seen.setdefault(name, AppEntry(name.title(), target))

    _index = sorted(seen.values(), key=lambda a: a.name.lower())
    return _index


def _score(query: str, name: str) -> float:
    q, n = query.lower().strip(), name.lower().strip()
    if not q:
        return 0.0
    if q == n:
        return 1.0
    if n.startswith(q):
        return 0.94
    # Whole-word hit beats a mid-string coincidence ("code" in "Barcode").
    if q in n.split() or f" {q} " in f" {n} ":
        return 0.88
    if q in n:
        return 0.80
    return difflib.SequenceMatcher(None, q, n).ratio()


@dataclass
class Match:
    """What the pet found. `confident` is the only thing that grants it
    permission to act without asking."""
    query: str
    confident: AppEntry | None
    candidates: list[AppEntry]
    taught: bool = False        # came straight from the recipe book


def find(query: str) -> Match:
    query = query.strip()

    taught = book.app_for(query)
    if taught:
        name = Path(taught).stem if taught.endswith((".lnk", ".url")) else taught
        return Match(query, AppEntry(name, taught), [], taught=True)

    scored = sorted(((_score(query, a.name), a) for a in index()),
                    key=lambda p: p[0], reverse=True)
    if not scored:
        return Match(query, None, [])

    best_score, best = scored[0]
    runner_up = scored[1][0] if len(scored) > 1 else 0.0

    confident = (best if best_score >= CONFIDENT_SCORE
                 and best_score - runner_up >= CLEAR_MARGIN else None)

    candidates = [a for s, a in scored if s >= MIN_SCORE][:8]
    if not candidates:
        candidates = [a for _, a in scored[:8]]      # give the picker something
    return Match(query, confident, candidates)


def remember(query: str, entry: AppEntry) -> None:
    """Teach the pet, after you've picked. Next time it's a dict lookup."""
    book.learn_app(query, entry.target)
