"""Turns what you typed into something the pet does.

No model involved. Phase 2 puts a local LLM *in front* of this to handle
free-form speech, but the routing itself stays plain code — an instruction the
pet can't parse must fail loudly, not get guessed at.
"""
import os
from pathlib import Path

from PySide6.QtCore import QObject, QPoint

import config
from core import brain
from core.brain import Brain
from core.events import bus
from core.recipes import book
from shell.ask import (Approval, CommandBar, Compose, Confirm, FillIn,
                       MailApproval, Picker, Waiting)
from skills import apps, mail
from skills.webtask import FormTask, today

OPEN_VERBS = ("open", "launch", "start", "run", "fire up", "boot up", "boot")
FILL_VERBS = ("fill out", "fill in", "fill", "do the", "do my", "submit")
TEACH_VERBS = ("teach", "learn", "remember")
FILLER_PREFIX = ("the", "my", "up")
FILLER_SUFFIX = ("for me", "please", "now", "app", "application")


def parse_open(text: str) -> str | None:
    """'launch up my brave please' -> 'brave'. None if it isn't an open request."""
    t = " ".join(text.lower().split())
    for verb in sorted(OPEN_VERBS, key=len, reverse=True):
        if t == verb:
            return ""                      # "open" with no target
        if t.startswith(verb + " "):
            t = t[len(verb) + 1:]
            break
    else:
        return None

    changed = True
    while changed:
        changed = False
        for w in FILLER_PREFIX:
            if t.startswith(w + " "):
                t, changed = t[len(w) + 1:], True
        for w in FILLER_SUFFIX:
            if t.endswith(" " + w):
                t, changed = t[:-(len(w) + 1)], True
    return t.strip()


def parse_fill(text: str) -> str | None:
    """'fill out my internship form' -> 'internship form'."""
    t = " ".join(text.lower().split())
    for verb in sorted(FILL_VERBS, key=len, reverse=True):
        if t.startswith(verb + " "):
            t = t[len(verb) + 1:]
            break
    else:
        return None
    for w in ("the", "my", "a"):
        if t.startswith(w + " "):
            t = t[len(w) + 1:]
    for w in ("for me", "please", "now"):
        if t.endswith(" " + w):
            t = t[:-(len(w) + 1)]
    return t.strip()


def parse_mail(text: str) -> tuple[str, str] | None:
    """'mail cold outreach to priya@acme.com' -> ('cold outreach', 'priya@acme.com').

    The address must be typed, never dictated — a misheard character sends your
    email to a stranger.
    """
    t = " ".join(text.split())
    low = t.lower()
    for verb in ("email", "mail", "send"):
        if low.startswith(verb + " "):
            t = t[len(verb) + 1:]
            break
    else:
        return None

    parts = t.rsplit(" to ", 1)
    if len(parts) != 2:
        return None
    name, to = parts[0].strip(" '\""), parts[1].strip(" '\"<>")
    return (name, to) if name and to else None


def parse_write(text: str) -> str | None:
    """'write template cold outreach' / 'new template x' -> the template name."""
    t = " ".join(text.split())
    low = t.lower()
    for verb in ("write template", "new template", "compose template",
                 "edit template", "template"):
        if low.startswith(verb + " "):
            return t[len(verb) + 1:].strip(" '\"")
    return None


def parse_teach(text: str) -> tuple[str, str] | None:
    """'teach internship form https://…' -> (name, url).

    The URL is required and must be typed — dictating one never ends well.
    """
    t = " ".join(text.split())
    low = t.lower()
    for verb in sorted(TEACH_VERBS, key=len, reverse=True):
        if low.startswith(verb + " "):
            t = t[len(verb) + 1:]
            break
    else:
        return None

    parts = t.split()
    urls = [w for w in parts if w.startswith(("http://", "https://"))]
    if not urls:
        return None
    url = urls[0]
    name = " ".join(w for w in parts if w != url).strip(" '\"")
    return (name, url) if name else None


class Commander(QObject):
    def __init__(self, window) -> None:
        super().__init__(window)
        self._window = window
        self._asked = ""
        self._form_name = ""
        self._pending_url = ""
        self._brain = Brain()
        self._brain.parsed.connect(self._on_parsed)

        self._task = FormTask(self)
        self._task.opened.connect(self._on_form_opened)
        self._task.recorded.connect(self._on_form_recorded)
        self._task.awaiting_approval.connect(self._on_form_awaiting)
        self._task.done.connect(lambda m: bus.say_here.emit(m, "happy"))
        self._task.failed.connect(lambda m: bus.say_here.emit(m, "alert"))

        self._mail = mail.MailTask(self)
        self._mail.awaiting_approval.connect(self._on_mail_awaiting)
        self._mail.done.connect(lambda m: bus.say_here.emit(m, "happy"))
        self._mail.failed.connect(lambda m: bus.say_here.emit(m, "alert"))

        bus.command.connect(self.prompt)

    def _anchor(self) -> QPoint:
        w = self._window
        return QPoint(int(w.x() + w.width() / 2), int(w.y() + w.height() * 0.35))

    def prompt(self) -> None:
        text = CommandBar.ask(self._anchor(), self._window)
        if text:
            self.handle(text)

    def handle(self, text: str) -> None:
        """Plain parsing first — it's instant and cannot invent anything.

        Only when that fails do we wake the model, and whatever it concludes
        needs a click before it happens.
        """
        target = parse_open(text)
        if target is not None:
            if target:
                self.open_app(target)
            else:
                bus.say_here.emit("open what?", "think")
            return

        taught = parse_teach(text)
        if taught is not None:
            self.teach_form(*taught)
            return

        tmpl = parse_write(text)
        if tmpl:
            self.write_template(tmpl)
            return

        addressed = parse_mail(text)
        if addressed is not None:
            self.send_mail(*addressed)
            return

        form = parse_fill(text)
        if form is not None:
            if form:
                self.fill_form(form)
            else:
                bus.say_here.emit("fill what?", "think")
            return

        if not brain.available():
            bus.say_here.emit(
                'try "open brave", or "fill <form name>".', "think")
            return

        self._asked = text
        bus.say_here.emit("thinking…", "think")
        self._brain.parse_async(text)

    def _on_parsed(self, text: str, intent) -> None:
        if intent is None:
            bus.say_here.emit("couldn't reach my local brain just now.", "alert")
            return

        if not intent.actionable:
            # Deliberately blunt. The model's "chat"/"question" answers are not
            # something the pet can carry out, and pretending otherwise is how
            # you end up with invented tasks.
            bus.say_here.emit("I heard you, but that's not something I can do yet.",
                              "think")
            return

        if config.CONFIRM_MODEL_ACTIONS:
            proposal = f"Open {intent.target}?"
            if not Confirm.ask(text, proposal, self._anchor(), self._window):
                bus.say_here.emit("okay, dropped it.", "happy")
                return
        self.open_app(intent.target)

    # --- web forms ---

    def teach_form(self, name: str, url: str) -> None:
        bus.say_here.emit(f"opening {name} — fill it in and I'll watch.", "think")
        self._form_name = name
        self._pending_url = url          # needed when the recording comes back
        self._task.record(name, url)

    def fill_form(self, name: str) -> None:
        recipe = book.form_for(name)
        if recipe is None:
            # Never guess at a form. Teaching one needs a URL, which has to be
            # typed rather than dictated.
            known = ", ".join(book.known_forms()) or "none yet"
            bus.say_here.emit(
                f"I've not been taught \"{name}\". Teach me with: "
                f"teach {name} <url>.  I know: {known}", "think")
            return
        self._form_name = name
        bus.say_here.emit(f"filling {name} — I'll stop before submitting.", "think")
        self._task.replay(name, recipe)

    def _on_form_opened(self, url: str, questions) -> None:
        name = self._form_name
        ok = Waiting.show_for(name, questions, self._anchor(), self._window)
        self._task.release(ok)

    def _on_form_recorded(self, name: str, answers: dict) -> None:
        book.learn_form(name, self._pending_url or "", answers, today())
        bus.say_here.emit(f"learned {name} — {len(answers)} answers. "
                          f'Say "fill {name}" next time.', "happy")

    def _on_form_awaiting(self, name: str, filled, skipped) -> None:
        ok = Approval.ask(name, filled, skipped, self._anchor(), self._window)
        self._task.release(ok)

    # --- cold mail ---

    def write_template(self, name: str) -> None:
        existing = book.mail_for(name)
        written = Compose.ask(name, self._anchor(), existing, self._window)
        if written is None:
            bus.say_here.emit("left it as it was.", "happy")
            return
        subject, body = written
        book.learn_mail(name, subject, body)
        blanks = sorted(set(mail.placeholders(subject)) | set(mail.placeholders(body)))
        bus.say_here.emit(
            f"saved \"{name}\"" + (f" — I'll ask you for {', '.join(blanks)}."
                                   if blanks else "."), "happy")

    def send_mail(self, name: str, to: str) -> None:
        template = book.mail_for(name)
        if template is None:
            known = ", ".join(book.known_mail()) or "none yet"
            bus.say_here.emit(
                f"no template called \"{name}\". Write one with: "
                f"template {name}.  I know: {known}", "think")
            return

        ready, why = config.mail_ready()
        if not ready:
            # Say this before asking you to fill in blanks, not after.
            bus.say_here.emit(why, "alert")
            return

        blanks = sorted((set(mail.placeholders(template.get("subject", "")))
                         | set(mail.placeholders(template.get("body", ""))))
                        - {"to"})
        values = FillIn.ask(f"Sending “{name}” to {to}", blanks,
                            self._anchor(), self._window)
        if values is None:
            bus.say_here.emit("okay, dropped it.", "happy")
            return

        values["to"] = to
        self._mail.compose(name, template, values)

    def _on_mail_awaiting(self, name: str, draft) -> None:
        ok = MailApproval.ask(draft, self._anchor(), self._window)
        self._mail.release(ok)

    # --- voice ---

    def on_wake(self) -> None:
        bus.say_here.emit("yes?", "happy")

    def on_heard(self, text: str) -> None:
        if text.strip():
            self.handle(text)

    # --- the app-opening skill ---

    def open_app(self, query: str) -> None:
        match = apps.find(query)

        if match.confident is not None:
            self._launch(match.confident, learned=match.taught)
            return

        # Never guess. Ask, and remember the answer.
        bus.say_here.emit(f"I don't know \"{query}\" yet — show me which one.", "think")
        options = [(a.name, a.target) for a in match.candidates]
        chosen = Picker.choose(f"Which one is \"{query}\"?", options,
                               self._anchor(), self._window)
        if chosen is None:
            bus.say_here.emit("okay, skipped.", "happy")
            return

        target, remember = chosen
        entry = apps.AppEntry(Path(target).stem if target.endswith((".lnk", ".url"))
                              else target, target)
        if remember:
            apps.remember(query, entry)
        self._launch(entry, learned=remember, taught_now=remember)

    def _launch(self, entry: apps.AppEntry, learned: bool,
                taught_now: bool = False) -> None:
        try:
            entry.launch()
        except OSError as e:
            # A stale recipe (app uninstalled/moved) must not stick around
            # silently failing forever.
            bus.say_here.emit(f"couldn't open {entry.name} — {e.strerror or e}.", "alert")
            return

        if taught_now:
            bus.say_here.emit(f"got it — {entry.name}. I'll remember.", "happy")
        elif learned:
            bus.say_here.emit(f"opening {entry.name}.", "happy")
        else:
            bus.say_here.emit(f"opening {entry.name}.", "happy")
