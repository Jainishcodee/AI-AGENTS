"""Text-to-speech on a worker thread.

pyttsx3's runAndWait() blocks, which would freeze the pet's animation if we
called it on the Qt thread. So everything goes through a queue consumed by one
daemon thread. Same fresh-engine-per-utterance trick as Mingo — reusing a
pyttsx3 engine across calls hangs on Windows SAPI5.
"""
import queue
import threading

import config

_q: "queue.Queue[str | None]" = queue.Queue()
_worker: threading.Thread | None = None


def _run() -> None:
    while True:
        text = _q.get()
        if text is None:
            return
        try:
            import pyttsx3
            engine = pyttsx3.init()
            engine.setProperty("rate", config.TTS_RATE)
            engine.say(text)
            engine.runAndWait()
            engine.stop()
        except Exception as e:  # noqa: BLE001 - voice is a nice-to-have, never fatal
            print(f"(text-to-speech unavailable: {e})")


def start() -> None:
    global _worker
    if _worker is None:
        _worker = threading.Thread(target=_run, name="tts", daemon=True)
        _worker.start()


def speak(text: str) -> None:
    print(f"[{config.PET_NAME}] {text}")
    if not config.SPEAK:
        return
    start()
    # If the pet is already mid-sentence, drop the backlog rather than queueing
    # a monologue — a nag that arrives four minutes late is just noise.
    while not _q.empty():
        try:
            _q.get_nowait()
        except queue.Empty:
            break
    _q.put(text)


def stop() -> None:
    if _worker is not None:
        _q.put(None)
