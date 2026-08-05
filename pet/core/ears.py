"""Offline voice input.

No cloud speech API — Mingo's recognizer needs the internet, which defeats the
point. This captures with PyAudio, decides where an utterance starts and ends
with a plain energy gate, and transcribes with faster-whisper on the CPU.

Why no Vosk wake-word stage: it would be one more dependency and model download
to save CPU we aren't short of. Whisper only runs when you actually speak, and
an utterance costs well under a second. If the machine ever feels the load,
that's the first thing to add.

Everything below runs on a daemon thread and talks to the pet through Qt
signals, which are delivered on the UI thread automatically.
"""
import difflib
import struct
import threading
import time

from PySide6.QtCore import QObject, Signal

import config

RATE = 16000
CHUNK = 480                      # 30ms frames
CALIBRATE_SEC = 1.0

_PUNCT = str.maketrans("", "", ".,!?;:'\"-")

# Whisper mishears a name it has never been told. These are the spellings it
# actually produces; anything else is caught by the fuzzy pass.
WAKE_ALIASES = {
    "jarvis": {"jarvis", "jervis", "javis", "jarvez", "jarvis's", "service",
               "harvest", "charvis", "jar vis", "drivers"},
}


# Devices that exist but never carry your voice. Windows will happily hand you
# a virtual audio cable as "the default input", and then the pet sits there
# hearing pure silence forever with no error to show for it.
VIRTUAL_HINTS = ("voice.ai", "voiceai", "cable", "virtual", "stereo mix",
                 "sound mapper", "vb-audio", "voicemeeter", "wave microphone",
                 "what u hear", "loopback")


def _norm(s: str) -> str:
    return " ".join(s.lower().translate(_PUNCT).split())


def pick_input_device(pa) -> tuple[int | None, str]:
    """Choose a microphone that's plausibly real. Returns (index, name).

    MIC_INDEX in .env always wins. Otherwise prefer the first input that
    doesn't look like a virtual cable, and only fall back to the system
    default if everything looks virtual.
    """
    if config.MIC_INDEX >= 0:
        try:
            return config.MIC_INDEX, pa.get_device_info_by_index(config.MIC_INDEX)["name"]
        except Exception:  # noqa: BLE001 - bad index in .env shouldn't be fatal
            print(f"[ears] MIC_INDEX={config.MIC_INDEX} is not a valid device")

    for i in range(pa.get_device_count()):
        try:
            d = pa.get_device_info_by_index(i)
        except Exception:  # noqa: BLE001
            continue
        if int(d.get("maxInputChannels", 0)) < 1:
            continue
        if any(h in str(d["name"]).lower() for h in VIRTUAL_HINTS):
            continue
        return i, str(d["name"])

    try:
        return None, str(pa.get_default_input_device_info()["name"])
    except Exception:  # noqa: BLE001
        return None, "system default"


class Ears(QObject):
    ready = Signal(bool, str)        # loaded?, message
    wake = Signal()                  # wake word heard on its own
    heard = Signal(str)              # an instruction for the pet
    listening = Signal(bool)         # currently capturing an utterance

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._model = None
        self._muted = False
        self._hint: str | None = None
        self.wake_word = _norm(config.WAKE_WORD)
        self._aliases = WAKE_ALIASES.get(self.wake_word, set()) | {self.wake_word}

    # ---------- lifecycle ----------

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="ears", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def set_muted(self, muted: bool) -> None:
        """Stop acting on speech without tearing down the model."""
        self._muted = muted

    def _vocab_hint(self) -> str:
        """Words Whisper should expect, as a fake preceding sentence.

        Built from what you've actually taught the pet plus the app names on
        this machine — the exact vocabulary that was coming back wrong. Kept
        short: a long prompt costs accuracy rather than adding it.
        """
        if self._hint is not None:
            return self._hint

        words: list[str] = []
        try:
            from core.recipes import book
            words += list(book.known_apps())[:8]      # things you really ask for
        except Exception:  # noqa: BLE001
            pass
        try:
            from skills import apps
            words += [a.name for a in apps.index()[:40] if len(a.name) < 18]
        except Exception:  # noqa: BLE001
            pass

        seen, picked, budget = set(), [], 180
        for w in words:
            k = w.lower()
            if k in seen:
                continue
            seen.add(k)
            if budget - len(w) - 2 < 0:
                break
            budget -= len(w) + 2
            picked.append(w)

        wake = config.WAKE_WORD.capitalize()
        self._hint = (f"{wake}, open Brave. {wake}, launch Notepad. "
                      f"Apps: {', '.join(picked)}.") if picked else \
                     f"{wake}, open Brave. {wake}, launch Notepad."
        return self._hint

    # ---------- wake word ----------

    def _match_wake(self, text: str) -> str | None:
        """Remainder after the wake word, '' if it was said alone, None if absent."""
        words = _norm(text).split()
        for i, w in enumerate(words[:3]):        # only ever leads an utterance
            hit = w in self._aliases or any(
                difflib.SequenceMatcher(None, w, a).ratio() >= 0.72
                for a in self._aliases)
            if hit:
                return " ".join(words[i + 1:])
            # "jar vis" — the name split across two tokens
            if i + 1 < len(words):
                pair = w + words[i + 1]
                if difflib.SequenceMatcher(None, pair, self.wake_word).ratio() >= 0.8:
                    return " ".join(words[i + 2:])
        return None

    # ---------- the loop ----------

    def _run(self) -> None:
        try:
            import numpy as np
            import pyaudio
            from faster_whisper import WhisperModel
        except ImportError as e:
            self.ready.emit(False, f"voice needs a package that's missing: {e.name}")
            return

        try:
            # int8 on CPU: the GPU's 4GB is already holding phi4-mini.
            self._model = WhisperModel(config.WHISPER_MODEL,
                                       device=config.WHISPER_DEVICE,
                                       compute_type="int8")
        except Exception as e:  # noqa: BLE001 - first run also downloads the model
            self.ready.emit(False, f"couldn't load speech model: {e}")
            return

        pa = pyaudio.PyAudio()
        idx, mic_name = pick_input_device(pa)
        try:
            stream = pa.open(format=pyaudio.paInt16, channels=1, rate=RATE,
                             input=True, frames_per_buffer=CHUNK,
                             input_device_index=idx)
        except Exception as e:  # noqa: BLE001
            pa.terminate()
            self.ready.emit(False, f"couldn't open the microphone: {e}")
            return
        print(f"[ears] mic: [{idx if idx is not None else 'default'}] {mic_name}")

        def rms(buf: bytes) -> float:
            vals = struct.unpack(f"{len(buf) // 2}h", buf)
            return (sum(v * v for v in vals) / len(vals)) ** 0.5

        # Measure the room, then treat anything clearly louder as speech.
        floor, n = 0.0, 0
        deadline = time.monotonic() + CALIBRATE_SEC
        while time.monotonic() < deadline and not self._stop.is_set():
            floor += rms(stream.read(CHUNK, exception_on_overflow=False))
            n += 1
        floor = (floor / max(1, n)) or 30.0
        threshold = max(floor * config.VAD_SENSITIVITY, floor + 120)

        # A floor this low means the device is delivering digital silence — a
        # muted mic or a virtual cable. Say so, rather than listening forever
        # to nothing and looking broken.
        if floor < 2.0:
            self.ready.emit(False, f"the mic ({mic_name}) is silent — "
                                   f"check it isn't muted, or set MIC_INDEX in .env")
            print(f"[ears] noise floor {floor:.1f} — device appears to be silent")
        else:
            self.ready.emit(True, f'listening for "{self.wake_word}"')
        print(f"[ears] noise floor {floor:.0f}, speech above {threshold:.0f}")

        awaiting_followup_until = 0.0

        while not self._stop.is_set():
            try:
                frame = stream.read(CHUNK, exception_on_overflow=False)
            except OSError:
                time.sleep(0.1)
                continue

            if rms(frame) < threshold:
                continue

            # --- capture one utterance ---
            self.listening.emit(True)
            frames = [frame]
            quiet_for = 0.0
            started = time.monotonic()
            while not self._stop.is_set():
                try:
                    f = stream.read(CHUNK, exception_on_overflow=False)
                except OSError:
                    break
                frames.append(f)
                quiet_for = 0.0 if rms(f) >= threshold else quiet_for + CHUNK / RATE
                if quiet_for >= config.VAD_SILENCE_SEC:
                    break
                if time.monotonic() - started >= config.VAD_MAX_SEC:
                    break
            self.listening.emit(False)

            secs = len(frames) * CHUNK / RATE
            if secs < config.VAD_MIN_SEC or self._muted:
                continue

            audio = (np.frombuffer(b"".join(frames), dtype=np.int16)
                     .astype(np.float32) / 32768.0)
            try:
                # beam_size 5 and a vocabulary hint, because the wake word lands
                # but the instruction after it comes back mangled. Whisper
                # guesses badly at app names it has no reason to expect; naming
                # them up front is the cheapest accuracy win available.
                segments, _ = self._model.transcribe(
                    audio, language="en", beam_size=5, vad_filter=True,
                    initial_prompt=self._vocab_hint())
                text = " ".join(s.text for s in segments).strip()
            except Exception as e:  # noqa: BLE001
                print(f"[ears] transcribe failed: {e}")
                continue
            if not text:
                continue
            print(f"[ears] heard: {text!r}")

            rest = self._match_wake(text)

            # Already woken and waiting for the actual instruction.
            if rest is None and time.monotonic() < awaiting_followup_until:
                awaiting_followup_until = 0.0
                self.heard.emit(_norm(text))
                continue

            if rest is None:
                continue                      # not addressed to the pet — ignore

            if rest:
                awaiting_followup_until = 0.0
                self.heard.emit(rest)
            else:
                awaiting_followup_until = time.monotonic() + config.FOLLOWUP_SEC
                self.wake.emit()

        stream.stop_stream()
        stream.close()
        pa.terminate()