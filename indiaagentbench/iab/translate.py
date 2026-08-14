"""Generate conditions C2-C5 from the C1 English task set.

Only `user_goal` is translated. task_id, verify and checkpoints are copied
byte-for-byte, so every condition shares one answer key and the comparison
measures language form and nothing else.

**The override layer is the important part.** Machine translation is a draft,
not a deliverable -- unvalidated MT is the single most likely reason for this
work to be dismissed by a reviewer. So a human correction written to
`tasks/overrides/<domain>_<condition>.json` always wins over the model draft and
survives regeneration. The validation report tracks which turns are still
drafts, and that count needs to reach zero before publication.

    python -m iab.translate --condition C2 --domain rail
    python -m iab.translate --all
    python -m iab.translate --all --drafts-only    # skip anything already fixed
"""
import argparse
import json
import re

from .budget import Rotator
from .common import TASKS, load_json, write_json

CACHE = TASKS / ".cache"
OVERRIDES = TASKS / "overrides"

CONDITIONS = {
    "C2": {"lang": "hi", "script": "Deva", "mixed": False,
           "label": "Hindi in Devanagari script"},
    "C3": {"lang": "hi", "script": "Latn", "mixed": True,
           "label": "romanized Hindi-English code-mixed (Hinglish)"},
    "C4": {"lang": "ta", "script": "Taml", "mixed": False,
           "label": "Tamil in Tamil script"},
    "C5": {"lang": "ta", "script": "Latn", "mixed": True,
           "label": "romanized Tamil-English code-mixed (Tanglish)"},
}

# Translation quality is not an experimental variable, so unlike evaluation this
# may rotate across different models freely -- whichever has quota is fine.
TRANSLATORS = [
    ("gemini", None, "GEMINI_API_KEY", "gemini-2.5-flash"),
    ("gemini", None, "GEMINI_API_KEY", "gemini-3.5-flash"),
    ("gemini", None, "GEMINI_API_KEY", "gemini-3.1-flash-lite"),
]

NATIVE = """\
Rewrite the following customer message in {label}.

This is a real person phoning a helpline, so keep the register conversational
and natural. Do not sound like a translation.

Hard rules:
- Keep every number exactly as it appears. A number written in digits (PNRs,
  mobile numbers, amounts, dates) must stay in the same digits, and must not be
  converted to another numeral system. A number written out in words must stay
  in words -- do not turn "twelve thousand" into 12000, or "three" into 3.
- Keep every person's name, place name and scheme name. Write names in the
  target script.
- Preserve every fact and every request. Do not add information, do not remove
  any, and do not answer the request.
- Output only the rewritten message. No preamble, no quotes, no notes.

Message:
{text}"""

MIXED = """\
Rewrite the following customer message as {label}, written in Latin script.

This must read like a real bilingual Indian speaker typing on a phone -- roughly
half the words in {lang_name} and half in English, switching mid-sentence the
way people actually do. Everyday English words (cancel, ticket, refund, apply,
scheme, income, student) normally stay in English. Do NOT produce pure {lang_name}
transliterated word-for-word, and do NOT produce plain English.

Hard rules:
- Latin script only. No {script_name} characters anywhere.
- Keep every number exactly as it appears. Digits stay as the same digits;
  numbers written out in words stay in words -- do not turn "twelve thousand"
  into 12000, or "three" into 3.
- Keep every person's name, place name and scheme name, romanized.
- Preserve every fact and every request. Do not add information, do not remove
  any, and do not answer the request.
- Output only the rewritten message. No preamble, no quotes, no notes.

Message:
{text}"""

LANG_NAME = {"hi": "Hindi", "ta": "Tamil"}
SCRIPT_NAME = {"hi": "Devanagari", "ta": "Tamil"}


def prompt_for(condition, text):
    c = CONDITIONS[condition]
    if c["mixed"]:
        return MIXED.format(label=c["label"], text=text,
                            lang_name=LANG_NAME[c["lang"]],
                            script_name=SCRIPT_NAME[c["lang"]])
    return NATIVE.format(label=c["label"], text=text)


def clean(text):
    """Strip the wrapper models add despite being told not to."""
    t = (text or "").strip()
    t = re.sub(r"^(here is|here's|sure[,!]?)[^:]*:\s*", "", t, flags=re.I)
    if len(t) > 1 and t[0] == t[-1] and t[0] in "\"'“‘":
        t = t[1:-1].strip()
    return t.strip()


def cache_path(domain, condition):
    return CACHE / f"{domain}_{condition}.json"


def load_map(path):
    try:
        return load_json(path)
    except (FileNotFoundError, ValueError):
        return {}


def translate(domain, condition, rotator, only_missing=True):
    src = load_json(TASKS / f"{domain}_C1.json")
    cache = load_map(cache_path(domain, condition))
    overrides = load_map(OVERRIDES / f"{domain}_{condition}.json")

    out, made = [], 0
    for t in src:
        tid = t["task_id"]
        text = overrides.get(tid) or cache.get(tid)
        source = "human" if tid in overrides else "draft"

        if not text:
            if not only_missing:
                pass
            reply = rotator.chat("You are a careful translator.",
                                 [{"role": "user",
                                   "content": prompt_for(condition, t["user_goal"])}],
                                 [])
            text = clean(reply["text"])
            cache[tid] = text
            # Persist after every draft, not at the end. A crash mid-run
            # otherwise throws away calls already paid for out of a small
            # daily allowance -- which is exactly what happened the first time.
            write_json(cache_path(domain, condition), cache)
            made += 1
            print(f"    drafted {tid}")

        c = CONDITIONS[condition]
        out.append({**t,
                    "condition": condition,
                    "lang": c["lang"],
                    "script": c["script"],
                    "source": source,
                    "user_goal": text,
                    "user_goal_en": t["user_goal"]})

    write_json(cache_path(domain, condition), cache)
    write_json(TASKS / f"{domain}_{condition}.json", out)
    human = sum(1 for t in out if t["source"] == "human")
    print(f"  {domain}/{condition}: {len(out)} tasks "
          f"({made} newly drafted, {human} human-approved)")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--condition", choices=sorted(CONDITIONS))
    ap.add_argument("--domain", choices=["rail", "schemes"])
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()

    conds = [args.condition] if args.condition else sorted(CONDITIONS)
    doms = [args.domain] if args.domain else ["rail", "schemes"]
    if not (args.all or args.condition or args.domain):
        ap.error("pass --all, or narrow with --condition / --domain")

    rotator = Rotator("translator", TRANSLATORS)
    for d in doms:
        for c in conds:
            translate(d, c, rotator)

    print("\nNext: python -m iab.validate_conditions")


if __name__ == "__main__":
    main()
