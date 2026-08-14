"""Script detection and code-mixing measurement.

Two jobs, both quality gates on the non-English conditions:

- **Purity.** A single word must not splice Devanagari into Tamil. Hand-written
  transliteration produces exactly this kind of error (four of the twelve seed
  aliases had it), and a native speaker reviewing a published dataset would
  spot it immediately.
- **Density.** C3 and C5 are supposed to be roughly 50 percent code-mixed. A
  "romanized Hinglish" turn that is actually 100 percent Hindi in Latin letters
  is a different linguistic object and would silently change what the condition
  measures. Density is therefore measured, not assumed.
"""
import re
import unicodedata

RANGES = {
    "Deva": (0x0900, 0x097F),
    "Taml": (0x0B80, 0x0BFF),
    "Beng": (0x0980, 0x09FF),
    "Telu": (0x0C00, 0x0C7F),
    "Knda": (0x0C80, 0x0CFF),
    "Mlym": (0x0D00, 0x0D7F),
    "Guru": (0x0A00, 0x0A7F),
    "Gujr": (0x0A80, 0x0AFF),
}

WORD = re.compile(r"[^\s\.,;:!\?\-\(\)\"']+")


def char_script(ch):
    o = ord(ch)
    for name, (lo, hi) in RANGES.items():
        if lo <= o <= hi:
            return name
    if ch.isascii() and ch.isalpha():
        return "Latn"
    return None


def scripts_in(text):
    return {s for s in (char_script(c) for c in text) if s}


def mixed_script_words(text):
    """Words that draw on more than one script -- almost always an error."""
    bad = []
    for w in WORD.findall(text):
        s = scripts_in(w)
        # digits and punctuation carry no script; Latin+Indic inside ONE word
        # is the failure we care about
        if len(s) > 1:
            bad.append((w, sorted(s)))
    return bad


def is_native_script(text, script):
    """Text is predominantly in `script`, with no foreign Indic contamination."""
    s = scripts_in(text)
    others = s - {script, "Latn"}
    return script in s and not others


def latin_ratio(text):
    """Fraction of word tokens written in Latin script.

    The code-mixing density proxy for C3/C5. Tokens that are pure digits are
    ignored -- a PNR is not a language choice.
    """
    words = [w for w in WORD.findall(text) if not w.isdigit()]
    if not words:
        return 0.0
    latin = sum(1 for w in words if scripts_in(w) == {"Latn"})
    return latin / len(words)


def digits_in(text):
    """Every digit run, in order. Used to prove entities survived translation."""
    return re.findall(r"\d+", unicodedata.normalize("NFKC", text))
