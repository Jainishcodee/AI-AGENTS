"""Check app matching against the real Start Menu. Launches nothing.

    python tools/test_apps.py

The important assertion is the negative one: a query the pet isn't sure about
must come back NOT confident, so it asks instead of opening the wrong thing.
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.commander import parse_open              # noqa: E402
from core.recipes import RecipeBook                # noqa: E402
from skills import apps                            # noqa: E402

fails: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{'  — ' + detail if detail else ''}")
    if not ok:
        fails.append(label)


def main() -> int:
    idx = apps.index()
    print(f"indexed {len(idx)} apps\n")

    print("parse_open()")
    for text, want in [
        ("open brave", "brave"),
        ("launch up my brave please", "brave"),
        ("start vs code", "vs code"),
        ("fire up the terminal now", "terminal"),
        ("run notepad app", "notepad"),
        ("open", ""),
        ("what's the weather", None),
        ("drink water", None),
    ]:
        got = parse_open(text)
        check(f"{text!r} -> {want!r}", got == want, f"got {got!r}")

    print("\nmatching")
    m = apps.find("brave")
    check("'brave' is confident", m.confident is not None,
          m.confident.name if m.confident else f"candidates={[a.name for a in m.candidates]}")
    if m.confident:
        check("'brave' resolves to brave", "brave" in m.confident.target.lower(),
              m.confident.target)

    m = apps.find("notepad")
    check("'notepad' is confident", m.confident is not None)

    # The whole point of the never-guess rule: nonsense must NOT resolve.
    m = apps.find("zzqqxx nonsense app")
    check("nonsense is NOT confident", m.confident is None,
          m.confident.name if m.confident else "asks instead")

    m = apps.find("my browser")
    check("vague 'my browser' is NOT confident", m.confident is None,
          m.confident.name if m.confident else "asks instead")

    print("\nteaching (never-guess -> learned)")
    with tempfile.TemporaryDirectory() as td:
        b = RecipeBook(Path(td) / "recipes.json")
        b.learn_app("my browser", r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe")
        check("recipe persists", b.app_for("my browser") is not None)
        check("lookup is case/space insensitive",
              RecipeBook(Path(td) / "recipes.json").app_for("  MY   Browser ") is not None)
        b.forget_app("my browser")
        check("forget works", b.app_for("my browser") is None)

    print("\nsample of what it found:")
    for a in idx[:8]:
        print(f"   {a.name}")

    print("\nOK" if not fails else f"\n{len(fails)} FAILED: {fails}")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
