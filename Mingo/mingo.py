"""Mingo — voice-activated Microsoft Rewards helper.

Say "Mingo" and it drives Microsoft Edge through the Bing Rewards searches +
daily activities on your SPARE account, then speaks the result. In the
background it emails you every few hours to do your MAIN account by hand.

WARNING: Automating Microsoft Rewards violates Microsoft's Terms of Service and
can get the account suspended / points voided. This is pointed at a throwaway
account on purpose. No CAPTCHA solving, no anti-detection trickery. Use at your
own risk.

Run:  python mingo.py
Quit: Ctrl+C
"""
import threading

import config
from reminder import run_reminder_loop
from rewards_bot import run_rewards
from voice import listen_for_wake_word, speak

_busy = threading.Lock()


def _on_wake() -> None:
    if not _busy.acquire(blocking=False):
        speak("I'm already on it.")
        return
    try:
        speak("On it. Running Microsoft Rewards on the spare account — give me a few minutes.")
        report = run_rewards()
        speak(report.spoken())
    except Exception as e:  # noqa: BLE001
        print(f"run failed: {e}")
        speak("Something went wrong during the run — check the terminal.")
    finally:
        _busy.release()


def main() -> None:
    print("=" * 60)
    print("  Mingo — Microsoft Rewards helper")
    print("  (spare account = automated, main account = email reminders)")
    print("=" * 60)
    threading.Thread(target=run_reminder_loop, daemon=True).start()
    speak(f'Mingo is ready. Say "{config.WAKE_WORD}" to start.')
    try:
        listen_for_wake_word(config.WAKE_WORD, _on_wake)
    except KeyboardInterrupt:
        print("\nBye.")


if __name__ == "__main__":
    main()
