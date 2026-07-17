"""Microphone diagnostic for Mingo.

    python mic_test.py          # list devices, then record from the system default
    python mic_test.py 2        # record from device index 2

Find an index that actually transcribes what you say, then put it in your .env:
    MIC_INDEX=2
"""
import sys

import speech_recognition as sr


def main() -> None:
    print("Microphones detected:")
    names = sr.Microphone.list_microphone_names()
    for i, name in enumerate(names):
        print(f"  [{i}] {name}")
    if not names:
        print("  (none! PyAudio can't see any input device — check Windows sound settings)")
        return

    idx = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].lstrip("-").isdigit() else None
    print(f"\nUsing device: {idx if idx is not None else 'system default'}")

    r = sr.Recognizer()
    r.dynamic_energy_threshold = True
    try:
        with sr.Microphone(device_index=idx) as src:
            print("Calibrating (stay quiet ~1s)...")
            r.adjust_for_ambient_noise(src, duration=1.0)
            print(f"energy_threshold = {r.energy_threshold:.0f}")
            print(">>> SPEAK NOW (you have ~5 seconds) <<<")
            try:
                audio = r.listen(src, timeout=5, phrase_time_limit=5)
            except sr.WaitTimeoutError:
                print("\nHeard NOTHING. Likely: wrong device index, mic muted, or no mic "
                      "permission for Python/terminal. Try another index from the list above.")
                return
    except Exception as e:  # noqa: BLE001
        print(f"\nCouldn't open that device: {e}")
        return

    print("Got audio. Transcribing via Google...")
    try:
        text = r.recognize_google(audio)
        print(f"\n  YOU SAID: {text!r}\n")
        print(f"This device works. Put  MIC_INDEX={idx if idx is not None else ''}  in your .env")
    except sr.UnknownValueError:
        print("Audio was captured but Google couldn't transcribe it — speak louder/clearer, "
              "or this device is picking up the wrong source.")
    except sr.RequestError as e:
        print(f"Speech service error (internet/firewall?): {e}")


if __name__ == "__main__":
    main()
