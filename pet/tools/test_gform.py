"""Form reading, filling and the record-then-replay round trip.

    python tools/test_gform.py

Runs headless against a local fixture with the same ARIA structure Google
emits. Nothing is ever submitted to anything real.

The assertions that matter are the ones about a form that has CHANGED since
you taught it: a renamed option or a deleted question must be reported, never
guessed at or silently dropped.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config                                    # noqa: E402
from skills import gform                         # noqa: E402

FIXTURE = (Path(__file__).parent / "fixtures" / "fake_form.html").as_uri()

ANSWERS = {
    "What is your name?": "Yash",
    "Why do you want this role?": "I build AI assistants and want to ship more.",
    "Which year are you in?": "Final year",
    "Which languages do you know?": ["Python", "Dart"],
    "Preferred start date": "Immediately",
}

fails: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{'  — ' + detail if detail else ''}")
    if not ok:
        fails.append(label)


def main() -> int:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=config.BROWSER_PATH,
                                    headless=True)
        page = browser.new_page()
        page.goto(FIXTURE)

        print("reading the form")
        qs = gform.read_questions(page)
        check("found every question", len(qs) == 5, f"{len(qs)} found")
        for q in qs:
            print(f"      {q}")
        kinds = {q.title: q.kind for q in qs}
        check("text question typed right",
              kinds.get("What is your name?") == "text")
        check("paragraph typed right",
              kinds.get("Why do you want this role?") == "paragraph")
        check("radio typed right", kinds.get("Which year are you in?") == "radio")
        check("checkbox typed right",
              kinds.get("Which languages do you know?") == "checkbox")
        check("dropdown typed right", kinds.get("Preferred start date") == "dropdown")
        check("required flag read", next(
            q.required for q in qs if q.title == "What is your name?"))
        check("optional not marked required", not next(
            q.required for q in qs if q.title == "Preferred start date"))

        print("\nreplaying a recorded recipe")
        filled, skipped = gform.fill(page, ANSWERS)
        check("filled everything", len(filled) == 5, f"filled={len(filled)}")
        check("skipped nothing", not skipped, str(skipped))

        print("\nreading it back (this is how recording works)")
        got = gform.read_answers(page)
        for title, want in ANSWERS.items():
            check(f"round-trips: {title[:34]}", got.get(title) == want,
                  f"got {got.get(title)!r}")

        print("\nnothing was submitted")
        check("submit not triggered",
              page.evaluate("window.__submitted === undefined"))

        print("\nform changed since you taught it — must report, not guess")
        page.goto(FIXTURE)
        # The option got renamed, and a whole question was removed.
        page.evaluate("""
            document.querySelector('[role="radio"][aria-label="Final year"]')
                    .setAttribute('aria-label', 'Fourth year');
            document.querySelectorAll('[role="listitem"]')[1].remove();
        """)
        filled, skipped = gform.fill(page, ANSWERS)
        check("still filled what it could", len(filled) == 3, f"filled={filled}")
        check("reported the renamed option",
              any("Final year" in s for s in skipped), str(skipped))
        check("reported the deleted question",
              any("Why do you want" in s for s in skipped), str(skipped))
        check("guessed at nothing",
              gform.read_answers(page).get("Which year are you in?") is None,
              "no radio should be set")

        print("\nsubmit works when actually asked")
        page.goto(FIXTURE)
        check("submit clicked", gform.submit(page))
        check("form registered it", page.evaluate("window.__submitted === true"))

        browser.close()

    print("\nOK" if not fails else f"\n{len(fails)} FAILED: {fails}")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
