"""Parsing for the form commands. No browser, no dialogs, nothing launched.

    python tools/test_formrouting.py
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["SPEAK"] = "false"
os.environ["VOICE_INPUT"] = "false"

from core.commander import parse_fill, parse_open, parse_teach   # noqa: E402

fails: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{'  — ' + detail if detail else ''}")
    if not ok:
        fails.append(label)


def main() -> int:
    print("parse_fill()")
    for text, want in [
        ("fill out my internship form", "internship form"),
        ("fill in the leave request", "leave request"),
        ("fill internship form please", "internship form"),
        ("submit the daily log for me", "daily log"),
        ("fill", None),
        ("open brave", None),
        ("what's the weather", None),
    ]:
        got = parse_fill(text)
        check(f"{text!r} -> {want!r}", got == want, f"got {got!r}")

    print("\nparse_teach()")
    for text, want in [
        ("teach internship form https://forms.gle/abc",
         ("internship form", "https://forms.gle/abc")),
        ("learn daily log https://docs.google.com/forms/d/e/x/viewform",
         ("daily log", "https://docs.google.com/forms/d/e/x/viewform")),
        # A URL is mandatory: without one there's nothing to open, and the pet
        # must not go hunting for a form it thinks you meant.
        ("teach internship form", None),
        ("teach https://forms.gle/abc", None),      # no name either
        ("open brave", None),
    ]:
        got = parse_teach(text)
        check(f"{text!r} -> {want!r}", got == want, f"got {got!r}")

    print("\nthe verbs don't collide")
    check("'fill' is not an open command", parse_open("fill my form") is None)
    check("'open' is not a fill command", parse_fill("open brave") is None)
    check("'teach' is not a fill command", parse_fill("teach x https://y") is None)

    print("\nOK" if not fails else f"\n{len(fails)} FAILED: {fails}")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
