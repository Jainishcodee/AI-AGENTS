"""Cold mail: rendering, the refusals, and the approval gate.

    python tools/test_mail.py

Sends nothing. A fake transport captures the message instead of SMTP, which is
what lets us assert the interesting thing: that declining at the gate results
in NO message being handed to the transport at all.

Most of these assertions are negative on purpose. Sending is irreversible, so
what matters is what the pet refuses to do.
"""
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("SMTP_EMAIL", "test@example.com")
os.environ.setdefault("SMTP_APP_PASSWORD", "not-a-real-password")
os.environ.setdefault("MAIL_FROM_NAME", "Yash")

from PySide6.QtWidgets import QApplication              # noqa: E402

import config                                            # noqa: E402
from core.recipes import RecipeBook                      # noqa: E402
from skills import mail                                  # noqa: E402

TEMPLATE = {
    "subject": "{role} at {company}",
    "body": ("Hi {name},\n\nI came across the {role} opening at {company} and "
             "wanted to reach out.\n\nBest,\nYash"),
}

fails: list[str] = []
sent: list = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{'  — ' + detail if detail else ''}")
    if not ok:
        fails.append(label)


def main() -> int:
    app = QApplication([])
    tmp = Path(tempfile.mkdtemp())
    mail.LOG = tmp / "sent_mail.jsonl"          # never touch the real log

    print("finding the blanks")
    ph = mail.placeholders(TEMPLATE["body"])
    check("found placeholders in order", ph == ["name", "role", "company"], str(ph))

    print("\nrendering a complete one")
    draft, problems = mail.render(TEMPLATE, {
        "to": "someone@company.com", "name": "Priya",
        "role": "ML Engineer", "company": "Acme"})
    check("no problems", not problems, str(problems))
    check("subject filled", draft and draft.subject == "ML Engineer at Acme",
          draft.subject if draft else "")
    check("body filled", draft and "Hi Priya," in draft.body)
    check("no stray braces left", draft and "{" not in draft.body + draft.subject)

    print("\nrefusals (this is the point of the whole module)")
    _, p = mail.render(TEMPLATE, {"to": "someone@company.com",
                                  "name": "Priya", "role": "ML Engineer"})
    check("refuses an unfilled placeholder", any("company" in x for x in p), str(p))

    d, p = mail.render(TEMPLATE, {"to": "someone@company.com", "name": "Priya",
                                  "role": "ML Engineer", "company": "   "})
    check("whitespace is not 'filled in'", d is None and any("company" in x for x in p),
          str(p))

    _, p = mail.render(TEMPLATE, {"to": "yash at gmail", "name": "P",
                                  "role": "R", "company": "C"})
    check("refuses a malformed address", any("email address" in x for x in p), str(p))

    _, p = mail.render(TEMPLATE, {"to": "", "name": "P", "role": "R", "company": "C"})
    check("refuses no recipient", any("recipient" in x for x in p), str(p))

    print("\nthe approval gate")
    for approve in (False, True):
        sent.clear()
        task = mail.MailTask()
        task.transport = sent.append                 # capture instead of send
        events: list = []
        task.awaiting_approval.connect(lambda n, d: events.append(("await", n, d)))
        task.done.connect(lambda m: events.append(("done", m)))
        task.failed.connect(lambda m: events.append(("failed", m)))

        task.compose("outreach", TEMPLATE, {
            "to": "someone@company.com", "name": "Priya",
            "role": "ML Engineer", "company": "Acme"})

        deadline, released, outcome = time.monotonic() + 20, False, None
        while time.monotonic() < deadline and outcome is None:
            app.processEvents()
            for e in list(events):
                if e[0] == "await" and not released:
                    released = True
                    task.release(approve)
                elif e[0] in ("done", "failed"):
                    outcome = e
            time.sleep(0.02)

        word = "approving" if approve else "declining"
        check(f"{word}: reached the gate first", released)
        check(f"{word}: sent {len(sent)} message(s)",
              len(sent) == (1 if approve else 0), str(outcome))

    print("\ndaily limit")
    saved = config.MAIL_DAILY_LIMIT
    config.MAIL_DAILY_LIMIT = 1                      # one is already logged above
    try:
        mail.send(mail.Draft(to="a@b.com", subject="s", body="b",
                             from_email="test@example.com"), transport=sent.append)
        check("stops at the daily limit", False, "it sent anyway")
    except RuntimeError as e:
        check("stops at the daily limit", "limit" in str(e), str(e))
    finally:
        config.MAIL_DAILY_LIMIT = saved

    print("\nrecipe book")
    book = RecipeBook(tmp / "recipes.json")
    book.learn_mail("cold outreach", TEMPLATE["subject"], TEMPLATE["body"])
    check("template persists", book.mail_for("cold outreach") is not None)
    check("survives reload",
          RecipeBook(tmp / "recipes.json").mail_for("COLD  Outreach") is not None)

    print("\nOK" if not fails else f"\n{len(fails)} FAILED: {fails}")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
