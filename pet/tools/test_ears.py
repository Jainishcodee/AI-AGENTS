"""Check the voice chain without needing anyone to talk to the pet.

    python tools/test_ears.py

Speaks test phrases with the offline Windows voice, saves them to WAV, and
feeds them back through the same Whisper model the pet uses. That exercises
transcription and wake-word extraction end to end.

Honest caveat: synthesised speech is cleaner than a real person in a real room,
so this proves the plumbing works, not that it will hear *you* reliably. The
mic-level check at the end is the part that says something about your setup.
"""
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["VOICE_INPUT"] = "false"        # don't start the real listener

import config                                          # noqa: E402
from core.commander import parse_open                  # noqa: E402
from core.ears import Ears                             # noqa: E402

PHRASES = [
    ("Jarvis, open Brave.",              "open brave"),
    ("Jarvis open notepad please.",      "open notepad"),
    ("Jarvis.",                          ""),           # wake word alone
    ("What time is the meeting?",        None),         # not addressed to it
]

fails: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{'  — ' + detail if detail else ''}")
    if not ok:
        fails.append(label)


def say_to_wav(text: str, path: Path) -> bool:
    import pyttsx3
    engine = pyttsx3.init()
    engine.setProperty("rate", 165)
    engine.save_to_file(text, str(path))
    engine.runAndWait()
    engine.stop()
    for _ in range(30):                    # SAPI writes the file asynchronously
        if path.exists() and path.stat().st_size > 2000:
            return True
        time.sleep(0.1)
    return False


def main() -> int:
    print("wake word :", config.WAKE_WORD)
    print("model     :", config.WHISPER_MODEL, f"({config.WHISPER_DEVICE}, int8)")

    print("\nloading whisper (first run downloads it)...")
    t0 = time.monotonic()
    try:
        from faster_whisper import WhisperModel
        model = WhisperModel(config.WHISPER_MODEL,
                             device=config.WHISPER_DEVICE, compute_type="int8")
    except Exception as e:  # noqa: BLE001
        print(f"  FAIL  couldn't load the model: {e}")
        return 1
    print(f"  loaded in {time.monotonic() - t0:.1f}s")

    ears = Ears()          # constructed only for its wake-word matcher
    tmp = Path(tempfile.mkdtemp())

    print("\ntranscription + wake word")
    for phrase, want in PHRASES:
        wav = tmp / (phrase[:12].replace(" ", "_").replace(",", "") + ".wav")
        if not say_to_wav(phrase, wav):
            check(f"{phrase!r}", False, "TTS produced no audio")
            continue

        t0 = time.monotonic()
        segments, _ = model.transcribe(str(wav), language="en", beam_size=1)
        text = " ".join(s.text for s in segments).strip()
        secs = time.monotonic() - t0

        rest = ears._match_wake(text)
        got = "(not addressed)" if rest is None else (rest or "(wake only)")

        # Compare what it ROUTES to, not the raw remainder — "open notepad
        # please" and "open notepad" are the same instruction, and parse_open
        # is what decides that.
        if want is None:
            ok = rest is None
        elif want == "":
            ok = rest == ""
        else:
            ok = rest is not None and parse_open(rest) == parse_open(want)

        check(f"{phrase!r}", ok, f"heard {text!r} -> {got}  ({secs:.1f}s)")

    print("\nmicrophone")
    try:
        import pyaudio

        from core.ears import pick_input_device
        pa = pyaudio.PyAudio()
        idx, name = pick_input_device(pa)          # same choice the pet makes
        stream = pa.open(format=pyaudio.paInt16, channels=1, rate=16000,
                         input=True, frames_per_buffer=480,
                         input_device_index=idx)
        import struct
        peak = 0.0
        for _ in range(60):                        # ~1.8s of room tone
            buf = stream.read(480, exception_on_overflow=False)
            vals = struct.unpack(f"{len(buf) // 2}h", buf)
            peak = max(peak, (sum(v * v for v in vals) / len(vals)) ** 0.5)
        stream.close()
        pa.terminate()
        # A real room is never digitally silent. Near-zero means a muted mic or
        # a virtual cable, and that's a failure — the pet would hear nothing.
        check(f"mic carries sound ({name})", peak >= 2,
              f"room level peaked at {peak:.0f}")
        if peak < 2:
            print("\n        That device delivers silence. Available inputs:")
            for i in range(pa.get_device_count()):
                d = pa.get_device_info_by_index(i)
                if int(d.get("maxInputChannels", 0)) >= 1:
                    print(f"          MIC_INDEX={i}  {d['name']}")
            print("        Put the right one in .env as MIC_INDEX.")
    except Exception as e:  # noqa: BLE001
        check("mic opens", False, str(e))

    print("\nOK" if not fails else f"\n{len(fails)} FAILED: {fails}")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
