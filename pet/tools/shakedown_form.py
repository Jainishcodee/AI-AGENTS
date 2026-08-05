"""Fill a REAL Google Form, screenshot it, then decline. Submits nothing.

    python tools/shakedown_form.py "<viewform url>" [--submit]

Without --submit this is safe to run against any form: it fills the fields,
saves a screenshot so you can see exactly what the pet typed, then declines at
the approval gate. The point is to prove the gate holds on a real form before
trusting it with one that matters.

--submit sends a real response. Only use it on a form you own and don't mind
polluting.
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtWidgets import QApplication              # noqa: E402

import config                                            # noqa: E402
from skills.webtask import FormTask                      # noqa: E402

ANSWERS = {
    "Wich department": "AI/ML",
    "FUll name": "Umbry Testrun",
    "email address": "umbry.testrun@example.com",
}

events: list[tuple] = []


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--submit", action="store_true",
                    help="actually send a response (real, irreversible)")
    args = ap.parse_args()

    app = QApplication([])
    task = FormTask()
    task.opened.connect(lambda u, q: events.append(("opened", u, q)))
    task.awaiting_approval.connect(lambda n, f, s: events.append(("awaiting", n, f, s)))
    task.done.connect(lambda m: events.append(("done", m)))
    task.failed.connect(lambda m: events.append(("failed", m)))

    print(f"form   : {args.url[:80]}")
    print(f"mode   : {'SUBMIT (real response)' if args.submit else 'fill + decline'}")

    task.replay("shakedown", {"url": args.url, "answers": ANSWERS})

    deadline = time.monotonic() + 180
    seen_await = False
    while time.monotonic() < deadline:
        app.processEvents()
        for e in list(events):
            if e[0] == "awaiting" and not seen_await:
                seen_await = True
                print("\nfilled:")
                for t in e[2]:
                    print(f"   OK   {t}  ->  {ANSWERS.get(t)!r}")
                for s in e[3]:
                    print(f"   SKIP {s}")

                # Look at it before deciding, exactly as you would.
                print(f"\nscreenshot: {task.last_shot or 'unavailable'}")
                task.release(args.submit)
            if e[0] in ("done", "failed"):
                print(f"\n{e[0]}: {e[1]}")
                if not args.submit and "unsubmitted" in str(e[1]).lower():
                    print("\nOK — the gate held, nothing was sent.")
                    return 0
                return 0 if e[0] == "done" else 1
        time.sleep(0.03)

    print("\ntimed out")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
