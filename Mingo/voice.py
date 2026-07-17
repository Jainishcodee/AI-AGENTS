"""Wake-word listening + text-to-speech for Mingo.

- speak(text): says it out loud via pyttsx3 (offline, Windows SAPI5) and prints it.
- listen_for_wake_word(word, callback): blocks forever, fires callback() whenever
  the wake word (or a close mishear of it) is heard. Uses SpeechRecognition's
  free Google recognizer, which is fine for light personal use. Want a proper
  always-on wake word with no network round-trip? Swap this for pvporcupine later.
"""
import difflib
import time

import config

# Google's recognizer rarely returns "mingo" verbatim — it hears mango / bingo /
# "ming go" / mingle. Treat any of these (or anything fuzzily close) as a hit.
_EXTRA_VARIANTS = {"mingo", "mango", "bingo", "mingle", "ming go", "mein go", "min go", "ningo"}
_FUZZY_THRESHOLD = 0.72


def speak(text: str) -> None:
    print(f"[Mingo] {text}")
    if not config.SPEAK:
        return
    try:
        import pyttsx3
        engine = pyttsx3.init()           # fresh engine each call dodges the
        engine.setProperty("rate", 178)   # "second call hangs" pyttsx3 bug
        engine.say(text)
        engine.runAndWait()
        engine.stop()
    except Exception as e:  # noqa: BLE001 - TTS is a nice-to-have, never fatal
        print(f"(text-to-speech unavailable: {e})")


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

    accept = _EXTRA_VARIANTS | {wake_word}
    for c in candidates:
        if c in accept:
            return True
        if difflib.SequenceMatcher(None, c, wake_word).ratio() >= _FUZZY_THRESHOLD:
            return True
        for v in accept:
            if difflib.SequenceMatcher(None, c, v).ratio() >= _FUZZY_THRESHOLD:
                return True
    return False


def listen_for_wake_word(wake_word: str, on_wake) -> None:
    import speech_recognition as sr

    recognizer = sr.Recognizer()
    recognizer.dynamic_energy_threshold = True
    recognizer.pause_threshold = 0.6

    dev = config.MIC_INDEX
    mic = sr.Microphone(device_index=dev)
    dev_name = sr.Microphone.list_microphone_names()[dev] if dev is not None else "system default"
    with mic as source:
        print(f"Mic: [{dev if dev is not None else 'default'}] {dev_name}")
        print("Calibrating for ambient noise (be quiet ~1s)...")
        recognizer.adjust_for_ambient_noise(source, duration=1.0)
    if config.ENERGY_THRESHOLD is not None:
        recognizer.dynamic_energy_threshold = False
        recognizer.energy_threshold = config.ENERGY_THRESHOLD
    print(f"  energy_threshold = {recognizer.energy_threshold:.0f} "
          f"(if it never hears you, lower it via ENERGY_THRESHOLD in .env)")
    print(f'Listening for "{wake_word}"  (Ctrl+C to quit)')

    idle = 0
    while True:
        try:
            with mic as source:
                audio = recognizer.listen(source, timeout=5, phrase_time_limit=4)
        except sr.WaitTimeoutError:
            idle += 1
            if idle % 6 == 0:
                print('  ...still listening (say the wake word out loud)...')
            continue
        except KeyboardInterrupt:
            raise
        except Exception as e:  # noqa: BLE001
            print(f"  mic error: {e}")
            time.sleep(1)
            continue

        idle = 0
        print("  🎤 got audio — transcribing...")
        try:
            heard = recognizer.recognize_google(audio).lower()
        except sr.UnknownValueError:
            print("  (couldn't make that out — say it louder/clearer)")
            continue
        except sr.RequestError as e:
            print(f"  speech service error: {e} — retrying in 5s")
            time.sleep(5)
            continue

        matched = _matches_wake(heard, wake_word)
        print(f"  heard: {heard!r}{'   <-- WAKE WORD!' if matched else ''}")
        if matched:
            on_wake()
            print(f'Listening for "{wake_word}"...')
