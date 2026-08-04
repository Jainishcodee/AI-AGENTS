"""Shared helpers for the reelflow pipeline (IG saved items -> Jarvis cards)."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
AUDIO = DATA / "audio"
TRANSCRIPTS = DATA / "transcripts"

# Fresh export dropped in the workspace (2026-08-01); the Downloads copy from
# May is kept as a fallback only because the pilot's audio cache is keyed to it.
_EXPORTS = [
    Path(r"g:\AI AGENTS\your_instagram_activity\saved"),
    Path(r"C:\Users\Jainish\Downloads\instagram-jainish._07-2026-05-19-vUO25keT"
         r"\your_instagram_activity\saved"),
]
IG_EXPORT = next((p for p in _EXPORTS if (p / "saved_collections.json").exists()),
                 _EXPORTS[0])

# A caption shorter than this can't carry a task or a fact on its own, so the
# reel has to be transcribed for distillation to have anything to work with.
THIN_CAPTION = 100


def fix(s):
    """Instagram exports mojibake: real UTF-8 bytes escaped as latin-1. Undo it."""
    if not isinstance(s, str):
        return s
    try:
        return s.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s


def shortcode(url):
    """/p/DCCc9w3MDuG/ or /reel/XYZ/ -> DCCc9w3MDuG. Used as the stable item id."""
    m = re.search(r"/(?:p|reel|tv)/([A-Za-z0-9_-]+)", url or "")
    return m.group(1) if m else ""


def extract_media(label_values):
    """Pull one reel/post record out of a label_values list."""
    rec = {"url": "", "caption": "", "title": "", "hashtags": [],
           "owner_user": "", "owner_name": ""}
    for e in label_values:
        if "label" in e:
            lab, val = e.get("label"), fix(e.get("value", ""))
            if lab == "URL" and not rec["url"]:
                rec["url"] = val
            elif lab == "Caption" and not rec["caption"]:
                rec["caption"] = val
            elif lab == "Title" and not rec["title"]:
                rec["title"] = val
        elif "dict" in e:
            title = e.get("title", "")
            if title == "Hashtags":
                for h in e["dict"]:
                    for kv in h.get("dict", []):
                        if kv.get("label") == "Name":
                            rec["hashtags"].append(fix(kv.get("value", "")))
            elif title == "Owner":
                for o in e["dict"]:
                    for kv in o.get("dict", []):
                        l, v = kv.get("label"), fix(kv.get("value", ""))
                        if l == "Username":
                            rec["owner_user"] = v
                        elif l == "Name":
                            rec["owner_name"] = v
    return rec


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json(path, obj):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
