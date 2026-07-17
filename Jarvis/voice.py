"""Voice subsystem for Jarvis.

All audio access — microphone AND text-to-speech — happens on a single
dedicated thread. External code (UI clicks, agent callbacks) calls
`voice.say(text)`, which is non-blocking; the request is enqueued and the
voice thread will speak it on its next turn.

This is critical: pyttsx3's SAPI5 driver runs a Windows COM message loop
inside `runAndWait()`. If that runs on the Tk main thread while PyAudio's
`read()` is mid-call on another thread (GIL released), Python crashes hard
with `PyEval_RestoreThread: the GIL must be held`. Single-owner audio fixes it.
"""
from __future__ import annotations

import difflib
import queue
import threading
from typing import Callable, Optional

_JARVIS_VARIANTS = {
    "jarvis", "jervis", "jarvas", "service", "jar bus", "jar this",
    "jarvi", "javis", "your boss",
}
_FUZZY_THRESHOLD = 0.72


def _matches_wake(heard: str, wake_word: str) -> bool:
    heard = heard.lower().strip()
    wake_word = wake_word.lower().strip()
    if not heard:
        return False
    if wake_word in heard:
        return True
    words = heard.replace("-", " ").split()
    candidates = set(words)
    candidates.update(" ".join(words[i:i + 2]) for i in range(len(words) - 1))
    accept = _JARVIS_VARIANTS | {wake_word}
    for c in candidates:
        if c in accept:
            return True
        if difflib.SequenceMatcher(None, c, wake_word).ratio() >= _FUZZY_THRESHOLD:
            return True
        for v in accept:
            if difflib.SequenceMatcher(None, c, v).ratio() >= _FUZZY_THRESHOLD:
                return True
    return False


class Voice:
    """Single-threaded owner of mic + TTS.

    Parameters
    ----------
    command_handler : callable(transcript: str) -> reply: str
        Invoked on the voice thread once a full command has been captured
        after the wake word. The returned string is spoken back.
    on_log : callable(line: str) -> None
        Called with status / transcript lines so the UI can print them.
    on_state : callable(state: str) -> None
        Called with one of: 'listening', 'speaking', 'thinking'.
    """

    def __init__(
        self,
        *,
        mic_index: Optional[int],
        energy_threshold: Optional[int],
        wake_word: str,
        speak_enabled: bool,
        command_handler: Callable[[str], str],
        on_log: Optional[Callable[[str], None]] = None,
        on_state: Optional[Callable[[str], None]] = None,
    ):
        self.mic_index = mic_index
        self.energy_threshold = energy_threshold
        self.wake_word = wake_word.lower()
        self.speak_enabled = speak_enabled
        self.command_handler = command_handler
        self.on_log = on_log or (lambda m: None)
        self.on_state = on_state or (lambda s: None)

        self._q: "queue.Queue[tuple[str, object]]" = queue.Queue()
        self._stop = threading.Event()
        self.mic_name = "?"
        self._thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------ API
    def start(self) -> threading.Thread:
        self._thread = threading.Thread(target=self._run, daemon=True, name="JarvisVoice")
        self._thread.start()
        return self._thread

    def say(self, text: str) -> None:
        """Fire-and-forget: voice thread will speak this between listens."""
        if text:
            self._q.put(("say", text))

    def shutdown(self) -> None:
        self._stop.set()
        self._q.put(("stop", None))

    # --------------------------------------------------------------- thread
    def _run(self) -> None:
        try:
            self._init_audio()
        except Exception as e:  # noqa: BLE001
            self.on_log(f"voice init failed: {e}")
            return

        self._say_now("Jarvis online.")
        self.on_state("listening")

        while not self._stop.is_set():
            # 1. Drain any pending say-requests first
            kind, payload = self._poll_q()
            if kind == "stop":
                return
            if kind == "say":
                self._say_now(payload)  # type: ignore[arg-type]
                continue

            # 2. Otherwise wake-listen
            transcript = self._listen(timeout=4, phrase_time_limit=4)
            if not transcript:
                continue
            if _matches_wake(transcript, self.wake_word):
                self.on_log(f"  heard: {transcript!r}   <-- WAKE")
                self._handle_wake()

    # --------------------------------------------------------------- helpers
    def _init_audio(self) -> None:
        import speech_recognition as sr  # imported lazily for clean error paths
        self._sr = sr

        names = sr.Microphone.list_microphone_names()
        self.mic_name = (
            names[self.mic_index]
            if self.mic_index is not None and self.mic_index < len(names)
            else "system default"
        )
        self.r = sr.Recognizer()
        self.r.dynamic_energy_threshold = True
        self.r.pause_threshold = 0.6
        self.mic = sr.Microphone(device_index=self.mic_index)
        with self.mic as src:
            self.r.adjust_for_ambient_noise(src, duration=1.0)
        if self.energy_threshold is not None:
            self.r.dynamic_energy_threshold = False
            self.r.energy_threshold = self.energy_threshold
        self.on_log(f"Mic: {self.mic_name}  (threshold {self.r.energy_threshold:.0f})")

    def _poll_q(self) -> tuple[str, object]:
        try:
            return self._q.get(timeout=0.05)
        except queue.Empty:
            return ("", None)

    def _handle_wake(self) -> None:
        self.on_state("speaking")
        self._say_now("Yes sir?")
        self.on_state("listening")
        cmd = self._listen(timeout=5, phrase_time_limit=8)
        self.on_log(f"  heard: {cmd!r}")
        self.on_state("thinking")
        try:
            reply = self.command_handler(cmd)
        except Exception as e:  # noqa: BLE001
            self.on_log(f"command handler crashed: {e}")
            reply = f"Sorry sir, something went wrong: {e}"
        if reply:
            self._say_now(reply)
        self.on_state("listening")

    def _listen(self, *, timeout: int, phrase_time_limit: int) -> str:
        try:
            with self.mic as src:
                audio = self.r.listen(src, timeout=timeout, phrase_time_limit=phrase_time_limit)
        except self._sr.WaitTimeoutError:
            return ""
        except Exception as e:  # noqa: BLE001
            self.on_log(f"  mic error: {e}")
            return ""
        try:
            return self.r.recognize_google(audio).lower()
        except self._sr.UnknownValueError:
            return ""
        except self._sr.RequestError as e:
            self.on_log(f"  (speech service error: {e})")
            return ""

    def _say_now(self, text: str) -> None:
        if not text:
            return
        self.on_log(f"[Jarvis] {text}")
        if not self.speak_enabled:
            return
        self.on_state("speaking")
        try:
            import pyttsx3
            # Fresh engine each call dodges the SAPI5 "second call hangs" bug.
            engine = pyttsx3.init()
            engine.setProperty("rate", 178)
            engine.say(text)
            engine.runAndWait()
            engine.stop()
            del engine
        except Exception as e:  # noqa: BLE001
            self.on_log(f"(tts unavailable: {e})")
