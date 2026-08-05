"""The full teach-then-replay cycle, including the approval gate.

    python tools/test_webtask.py

Runs headless against the local fixture and submits nothing to anything real.
Exercises the worker-thread handshake, so a deadlock or a signal that never
arrives shows up here rather than with a browser window open on your desk.

The assertion that matters most: declining the approval must leave the form
UNSUBMITTED. That gate is the last thing standing between a recipe and a real
irreversible action.
"""
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["BROWSER_HEADLESS"] = "true"

from PySide6.QtWidgets import QApplication              # noqa: E402

import config                                            # noqa: E402
from core.recipes import RecipeBook                      # noqa: E402
from skills.webtask import FormTask, today               # noqa: E402

FIXTURE = (Path(__file__).parent / "fixtures" / "fake_form.html").as_uri()

events: list[tuple] = []
fails: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{'  — ' + detail if detail else ''}")
    if not ok:
        fails.append(label)


def pump(app, want: str, task: FormTask, release: bool | None = None,
         timeout: float = 90.0):
    """Wait for a named signal, optionally releasing the gate when it arrives."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        for e in events:
            if e[0] == want:
                if release is not None:
                    task.release(release)
                return e
            if e[0] == "failed":
                return e
        time.sleep(0.02)
    return None


def main() -> int:
    app = QApplication([])
    task = FormTask()
    task.opened.connect(lambda u, q: events.append(("opened", u, q)))
    task.recorded.connect(lambda n, a: events.append(("recorded", n, a)))
    task.awaiting_approval.connect(
        lambda n, f, s: events.append(("awaiting", n, f, s)))
    task.done.connect(lambda m: events.append(("done", m)))
    task.failed.connect(lambda m: events.append(("failed", m)))

    print(f"browser: {Path(config.BROWSER_PATH).name} (headless)")
    tmp = Path(tempfile.mkdtemp())
    book = RecipeBook(tmp / "recipes.json")

    # --- teach it ---
    print("\nrecording: the form arrives already filled, standing in for you")
    events.clear()
    task.record("internship form", FIXTURE + "#prefill")

    ev = pump(app, "opened", task, release=True)
    check("form opened and read", ev is not None and ev[0] == "opened",
          f"{len(ev[2])} questions" if ev and ev[0] == "opened" else str(ev))

    ev = pump(app, "recorded", task)
    ok = ev is not None and ev[0] == "recorded"
    # Back-to-back sessions must work: the lock has to be released before the
    # result is announced, not after the browser finishes closing.
    check("free to start another form immediately", not task.busy)
    check("read back what was filled", ok, str(ev[1] if ok else ev))
    if not ok:
        print(f"\n{len(fails)} FAILED: {fails}")
        return 1

    answers = ev[2]
    for line in [f"{k}: {v}" for k, v in answers.items()]:
        print(f"      {line}")
    check("captured all five answers", len(answers) == 5, str(len(answers)))
    check("radio captured", answers.get("Which year are you in?") == "Final year")
    check("multi-select captured",
          answers.get("Which languages do you know?") == ["Python", "Dart"])

    book.learn_form("internship form", FIXTURE, answers, today())
    check("recipe persisted", book.form_for("internship form") is not None)
    check("survives a reload",
          RecipeBook(tmp / "recipes.json").form_for("INTERNSHIP FORM") is not None)

    # --- replay, then decline ---
    print("\nreplaying, then saying NO at the approval gate")
    events.clear()
    task.replay("internship form", book.form_for("internship form"))

    ev = pump(app, "awaiting", task, release=False)
    ok = ev is not None and ev[0] == "awaiting"
    check("filled in and stopped for approval", ok,
          f"filled={ev[2]} skipped={ev[3]}" if ok else str(ev))
    if ok:
        check("filled every field", len(ev[2]) == 5, str(ev[2]))
        check("nothing skipped", not ev[3], str(ev[3]))

    ev = pump(app, "done", task)
    check("declining left it UNSUBMITTED",
          ev is not None and "unsubmitted" in str(ev[1]).lower(), str(ev))

    # --- replay, then approve ---
    print("\nreplaying, then approving")
    events.clear()
    task.replay("internship form", book.form_for("internship form"))
    pump(app, "awaiting", task, release=True)
    ev = pump(app, "done", task)
    check("approving submitted it",
          ev is not None and "submitted" in str(ev[1]).lower(), str(ev))

    # --- a recipe that no longer fits ---
    print("\na recipe for a form that changed beyond use")
    events.clear()
    stale = {"url": FIXTURE, "answers": {"A question that never existed": "x"}}
    task.replay("stale form", stale)
    ev = pump(app, "failed", task)
    # Assert the *reason*, not just that something failed — an earlier version
    # of this test passed on "I'm already in the middle of a form", which told
    # us nothing about whether the stale recipe was handled.
    check("refused rather than submitting a blank form",
          ev is not None and ev[0] == "failed" and "changed" in str(ev[1]),
          str(ev))

    print("\nOK" if not fails else f"\n{len(fails)} FAILED: {fails}")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
