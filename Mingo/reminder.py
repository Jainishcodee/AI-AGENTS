"""Emails you every N hours to do Microsoft Rewards on your MAIN account by
hand (Mingo only auto-runs the spare one). Sends from your Gmail to your Gmail
using a Gmail App Password — see .env.example.
"""
import smtplib
import time
from email.message import EmailMessage

import config

_BODY = (
    "Hey — Mingo here.\n\n"
    "Time to knock out the Bing / Microsoft Rewards stuff on your MAIN account. "
    "Mingo only auto-runs the spare account, so this one's on you. ~5 minutes:\n"
    "  - ~30 Bing searches on desktop\n"
    "  - ~20 searches on your phone\n"
    "  - the Daily Set cards at https://rewards.bing.com/\n\n"
    "- Mingo"
)


def send_reminder() -> None:
    if not (config.SMTP_EMAIL and config.SMTP_APP_PASSWORD and config.REMINDER_TO):
        print("[reminder] SMTP not configured in .env — skipping email.")
        return
    msg = EmailMessage()
    msg["Subject"] = "Mingo: do Microsoft Rewards on your MAIN account"
    msg["From"] = config.SMTP_EMAIL
    msg["To"] = config.REMINDER_TO
    msg.set_content(_BODY)
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=20) as s:
            s.login(config.SMTP_EMAIL, config.SMTP_APP_PASSWORD)
            s.send_message(msg)
        print(f"[reminder] sent to {config.REMINDER_TO}")
    except Exception as e:  # noqa: BLE001
        print(f"[reminder] failed to send: {e}")


def run_reminder_loop() -> None:
    interval_s = max(0.05, config.REMINDER_INTERVAL_HOURS) * 3600
    if config.SEND_REMINDER_ON_START:
        send_reminder()
    while True:
        time.sleep(interval_s)
        send_reminder()


if __name__ == "__main__":
    send_reminder()
