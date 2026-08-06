"""Cold mail: templates you teach once, filled in and held for your approval.

Deliberately template-driven rather than model-written. A cold email is a
thing you send to a real person under your own name — the wording should be
yours, decided once when you're thinking clearly, not improvised per-send by a
3B model. The pet fills in the blanks and shows you the result.

Two hard refusals, both because the failure is unrecoverable:

* an unfilled placeholder — "Hi {name}," going out is worse than not sending
* an address that isn't a plausible email

Nothing here sends without an explicit approval; see MailTask.
"""
import json
import re
import smtplib
import ssl
import threading
from dataclasses import dataclass
from datetime import date, datetime
from email.message import EmailMessage
from email.utils import formataddr, parseaddr
from pathlib import Path
from string import Formatter

from PySide6.QtCore import QObject, Signal

import config

LOG = Path(config.ROOT) / "sent_mail.jsonl"

# Deliberately loose: the point is to catch "yash at gmail" and empty strings,
# not to adjudicate RFC 5322.
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[a-zA-Z]{2,}$")


@dataclass
class Draft:
    to: str
    subject: str
    body: str
    from_email: str = ""
    from_name: str = ""

    def preview(self) -> str:
        who = formataddr((self.from_name, self.from_email)) if self.from_email else "(unset)"
        return (f"From:    {who}\n"
                f"To:      {self.to}\n"
                f"Subject: {self.subject}\n\n{self.body}")


def placeholders(template: str) -> list[str]:
    """Every {field} in the template, in order, deduped."""
    seen, out = set(), []
    for _, field, _, _ in Formatter().parse(template):
        if field and field not in seen:
            seen.add(field)
            out.append(field)
    return out


def render(template: dict, values: dict) -> tuple[Draft | None, list[str]]:
    """Fill a taught template. Returns (draft, problems).

    A draft is only returned when every placeholder is filled and the address
    looks real — otherwise the problems list says exactly what's missing and
    nothing is produced to accidentally send.
    """
    subject_t = template.get("subject", "")
    body_t = template.get("body", "")
    to = str(values.get("to", "")).strip()

    problems = []
    if not to:
        problems.append("no recipient")
    elif not EMAIL_RE.match(to):
        problems.append(f"{to!r} doesn't look like an email address")

    needed = set(placeholders(subject_t)) | set(placeholders(body_t))
    missing = sorted(f for f in needed if not str(values.get(f, "")).strip())
    for f in missing:
        problems.append(f"nothing to put in {{{f}}}")

    if problems:
        return None, problems

    safe = {f: str(values.get(f, "")) for f in needed}
    return Draft(
        to=to,
        subject=subject_t.format(**safe),
        body=body_t.format(**safe),
        from_email=config.SMTP_EMAIL,
        from_name=config.MAIL_FROM_NAME or "",
    ), []


def sent_today() -> int:
    if not LOG.exists():
        return 0
    today = date.today().isoformat()
    n = 0
    try:
        for line in LOG.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    if json.loads(line).get("at", "").startswith(today):
                        n += 1
                except json.JSONDecodeError:
                    continue
    except OSError:
        return 0
    return n


def _record(draft: Draft) -> None:
    entry = {"at": datetime.now().isoformat(timespec="seconds"),
             "to": draft.to, "subject": draft.subject}
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def build_message(draft: Draft) -> EmailMessage:
    msg = EmailMessage()
    msg["To"] = draft.to
    msg["Subject"] = draft.subject
    msg["From"] = (formataddr((draft.from_name, draft.from_email))
                   if draft.from_name else draft.from_email)
    msg.set_content(draft.body)
    return msg


def send(draft: Draft, transport=None) -> None:
    """Actually send. Only ever called after you've approved the draft.

    `transport` exists so tests can prove the approval gate without a real
    mailbox on the other end.
    """
    ok, why = config.mail_ready()
    if not ok:
        raise RuntimeError(why)
    if not EMAIL_RE.match(draft.to):
        raise ValueError(f"refusing to send to {draft.to!r}")
    if sent_today() >= config.MAIL_DAILY_LIMIT:
        raise RuntimeError(f"daily limit of {config.MAIL_DAILY_LIMIT} already sent")

    msg = build_message(draft)
    if transport is not None:
        transport(msg)
    else:
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=30) as s:
            s.starttls(context=ssl.create_default_context())
            s.login(config.SMTP_EMAIL, config.SMTP_APP_PASSWORD)
            s.send_message(msg)
    _record(draft)


class MailTask(QObject):
    """Same shape as FormTask: draft, show, wait for a click, then act."""

    awaiting_approval = Signal(str, object)   # name, Draft
    done = Signal(str)
    failed = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._gate = threading.Event()
        self._approved = False
        self._busy = False
        self.transport = None                 # tests inject; None = real SMTP

    @property
    def busy(self) -> bool:
        return self._busy

    def release(self, approved: bool = True) -> None:
        self._approved = approved
        self._gate.set()

    def compose(self, name: str, template: dict, values: dict) -> None:
        if self._busy:
            self.failed.emit("I'm already in the middle of an email.")
            return
        draft, problems = render(template, values)
        if draft is None:
            # Refuse loudly and specifically. "Couldn't send" teaches nothing.
            self.failed.emit("can't send that — " + "; ".join(problems))
            return

        self._busy = True
        self._gate.clear()
        threading.Thread(target=self._run, args=(name, draft),
                         name="mailtask", daemon=True).start()

    def _run(self, name: str, draft: Draft) -> None:
        try:
            self.awaiting_approval.emit(name, draft)
            self._gate.wait()
            if not self._approved:
                outcome = ("done", "not sent.")
            else:
                send(draft, transport=self.transport)
                outcome = ("done", f"sent to {draft.to}.")
        except Exception as e:  # noqa: BLE001 - a bad mailbox must not kill the pet
            outcome = ("failed", f"{type(e).__name__}: {str(e)[:140]}")

        self._busy = False
        {"done": self.done, "failed": self.failed}[outcome[0]].emit(outcome[1])
