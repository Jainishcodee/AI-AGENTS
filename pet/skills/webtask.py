"""Teaching the pet a web form, and replaying it afterwards.

Two flows, both ending at you:

  record  — opens the form in Brave and steps back. YOU fill it in. The pet
            reads back what you put and stores it. Nothing is submitted.
  replay  — fills in what you taught it, then stops and shows you the form.
            It submits only after you click approve.

Playwright's sync API belongs to the thread that created it, so an entire
session lives on one worker thread and talks to the pet over Qt signals.
The handshake back the other way — "I've filled it in", "yes, submit" — is a
threading.Event the worker blocks on.
"""
import threading
from datetime import date

from PySide6.QtCore import QObject, Signal

import config
from skills import gform


class FormTask(QObject):
    # url, list[Question] — the form is open and waiting for you
    opened = Signal(str, object)
    # name, answers — what the pet read back off the form you filled
    recorded = Signal(str, object)
    # name, filled titles, skipped reasons — filled in, awaiting your approval
    awaiting_approval = Signal(str, object, object)
    # a human-readable outcome
    done = Signal(str)
    failed = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._gate = threading.Event()
        self._approved = False
        self._busy = False

    @property
    def busy(self) -> bool:
        return self._busy

    # ---------- called from the UI thread ----------

    def release(self, approved: bool = True) -> None:
        """Unblock the worker: 'I've filled it in' or 'yes, submit'."""
        self._approved = approved
        self._gate.set()

    def record(self, name: str, url: str) -> None:
        self._spawn(self._record, name, url)

    def replay(self, name: str, recipe: dict) -> None:
        self._spawn(self._replay, name, recipe)

    def _spawn(self, fn, *args) -> None:
        if self._busy:
            self.failed.emit("I'm already in the middle of a form.")
            return
        self._busy = True
        self._gate.clear()
        threading.Thread(target=self._guard, args=(fn, *args),
                         name="webtask", daemon=True).start()

    def _guard(self, fn, *args) -> None:
        """Run a session, then release the lock *before* announcing the result.

        The workers return their outcome rather than emitting it, because a
        signal is queued to the UI thread and would otherwise arrive while this
        thread is still closing the browser — so asking for a second form the
        moment the first finished got you "I'm already in the middle of a form".
        """
        try:
            outcome = fn(*args)
        except Exception as e:  # noqa: BLE001 - a browser crash must not kill the pet
            outcome = ("failed", f"{type(e).__name__}: {str(e)[:120]}")

        self._busy = False                      # browser is shut by now
        if not outcome:
            return
        kind, payload = outcome[0], outcome[1:]
        {"recorded": self.recorded, "done": self.done,
         "failed": self.failed}[kind].emit(*payload)

    # ---------- worker thread ----------

    def _browser(self, p):
        """Brave, with its own profile so it never fights the window you use."""
        if not config.BROWSER_PATH:
            raise RuntimeError("no browser found — set BROWSER_PATH in .env")
        return p.chromium.launch_persistent_context(
            user_data_dir=config.BROWSER_PROFILE,
            executable_path=config.BROWSER_PATH,
            headless=config.BROWSER_HEADLESS,
            args=["--no-first-run", "--no-default-browser-check"],
        )

    def _record(self, name: str, url: str) -> tuple:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            ctx = self._browser(p)
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=45_000)
                questions = gform.read_questions(page)
                if not questions:
                    return ("failed", "that doesn't look like a form I can read.")

                self.opened.emit(url, questions)
                self._gate.wait()                 # you fill it in
                if not self._approved:
                    return ("done", "okay, forgot about it.")

                answers = gform.read_answers(page)
                if not answers:
                    # Recording an empty form would store a useless recipe that
                    # silently does nothing on replay.
                    return ("failed", "the form's still blank — nothing to learn.")
                return ("recorded", name, answers)
            finally:
                ctx.close()

    def _replay(self, name: str, recipe: dict) -> tuple:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            ctx = self._browser(p)
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            try:
                page.goto(recipe["url"], wait_until="domcontentloaded",
                          timeout=45_000)
                filled, skipped = gform.fill(page, recipe.get("answers", {}))
                if not filled:
                    return ("failed",
                            "couldn't fill anything — the form has changed.")

                self.awaiting_approval.emit(name, filled, skipped)
                self._gate.wait()                 # you look at it and decide
                if not self._approved:
                    return ("done", "left it unsubmitted.")

                if gform.submit(page):
                    page.wait_for_timeout(2500)   # let the response page land
                    return ("done", f"submitted {name}.")
                return ("failed", "couldn't find the submit button.")
            finally:
                ctx.close()


def today() -> str:
    return date.today().isoformat()
