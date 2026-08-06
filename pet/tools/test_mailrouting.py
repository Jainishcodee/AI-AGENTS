"""Parsing for the mail commands. No dialogs, no sending.

    python tools/test_mailrouting.py

The negative cases carry the weight: a sentence that isn't a mail instruction
must return None so it falls through to the rest of the router, rather than
being half-understood as one.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.commander import (parse_fill, parse_mail, parse_open,  # noqa: E402
                            parse_write)

fails: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{'  — ' + detail if detail else ''}")
    if not ok:
        fails.append(label)


def main() -> int:
    print("parse_mail()")
    for text, want in [
        ("mail cold outreach to priya@acme.com", ("cold outreach", "priya@acme.com")),
        ("email cold outreach to priya@acme.com", ("cold outreach", "priya@acme.com")),
        ("send intro to a.b-c@sub.domain.co.in", ("intro", "a.b-c@sub.domain.co.in")),
        ("mail 'follow up' to x@y.com", ("follow up", "x@y.com")),
        # A template name containing "to" must not split in the wrong place —
        # hence rsplit, not split.
        ("mail intro to founders to x@y.com", ("intro to founders", "x@y.com")),
        ("mail cold outreach", None),          # no recipient
        ("open brave", None),
        ("fill internship form", None),
        ("what's the weather", None),
    ]:
        got = parse_mail(text)
        check(f"{text!r}", got == want, f"got {got!r}")

    print("\nparse_write()")
    for text, want in [
        ("template cold outreach", "cold outreach"),
        ("write template cold outreach", "cold outreach"),
        ("new template intro", "intro"),
        ("edit template intro", "intro"),
        ("open brave", None),
        ("mail intro to x@y.com", None),
    ]:
        got = parse_write(text)
        check(f"{text!r}", got == want, f"got {got!r}")

    print("\nthe commands still don't collide")
    check("'mail x to y' isn't an open", parse_open("mail x to y@z.com") is None)
    check("'mail x to y' isn't a fill", parse_fill("mail x to y@z.com") is None)
    check("'open brave' isn't mail", parse_mail("open brave") is None)
    # "submit" is a FILL verb; it must not be eaten by the mail router first.
    check("'submit the form' isn't mail", parse_mail("submit the form") is None)
    check("'submit the form' is a fill", parse_fill("submit the form") == "form")

    print("\nOK" if not fails else f"\n{len(fails)} FAILED: {fails}")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
