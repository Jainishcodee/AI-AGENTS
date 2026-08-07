"""Stage 5: distilled cards -> the JSON pack the Jarvis app ships with.

Drops the skips, drops the fields only the pipeline cares about, and writes
straight into the app's assets folder. This is the whole contract between the
Python side and the Flutter side -- nothing else crosses.

  python pack.py                 # full run  (data/distilled.json)
  python pack.py --sample        # proof set (data/distilled_sample.json)
"""
import argparse
from pathlib import Path

from common import DATA, load_json, write_json

APP_ASSET = r"g:\AI AGENTS\Jarvis\assets\deck.json"
THUMBS = Path(r"g:\AI AGENTS\Jarvis\assets\thumbs")

KEEP = ["id", "kind", "title", "summary", "domain", "tags", "url", "collection",
        "owner_user", "evidence", "confidence", "steps", "effort", "horizon",
        "recurrence", "claim", "why", "applicability"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", action="store_true")
    ap.add_argument("--out", default=APP_ASSET)
    args = ap.parse_args()

    src = DATA / ("distilled_sample.json" if args.sample else "distilled.json")
    cards = [c for c in load_json(src) if c["kind"] in ("task", "fact")]

    # Reels Instagram has taken down (copyright) or the creator deleted. media.py
    # finds them while fetching covers; a card that opens to a dead page is worse
    # than no card, so they never reach the app.
    dead_path = DATA / "unavailable.json"
    dead = {d["id"] for d in load_json(dead_path)} if dead_path.exists() else set()
    if dead:
        cards = [c for c in cards if c["id"] not in dead]

    # An error row is a failed API call, not a verdict -- shipping it would put
    # "ERROR: ..." on a card. distill.py retries these on its next run.
    cards = [c for c in cards if not c.get("error")]

    out = []
    for c in cards:
        card = {k: c[k] for k in KEEP if k in c and c[k] not in (None, "", [])}
        # The model sometimes answers "None" as a literal string rather than omitting.
        if str(card.get("applicability", "")).lower() == "none":
            card.pop("applicability")
        card.setdefault("tags", [])
        if card["kind"] == "task":
            card.setdefault("steps", [])
            card.setdefault("horizon", "short_term")
            card.setdefault("recurrence", "once")
        # Only claim a thumbnail that actually exists, so the app can trust the
        # field instead of probing the asset bundle at runtime.
        if (THUMBS / f"{c['id']}.jpg").exists():
            card["thumb"] = f"assets/thumbs/{c['id']}.jpg"
        out.append(card)

    write_json(args.out, out)
    tasks = sum(1 for c in out if c["kind"] == "task")
    thumbs = sum(1 for c in out if "thumb" in c)
    horizons = {}
    for c in out:
        if c["kind"] == "task":
            horizons[c["horizon"]] = horizons.get(c["horizon"], 0) + 1
    print(f"{len(out)} cards  ({tasks} task / {len(out) - tasks} fact)"
          + (f"  [{len(dead)} dropped as unavailable]" if dead else ""))
    print(f"horizons: {horizons}")
    print(f"thumbnails: {thumbs}/{len(out)}"
          + ("  (run media.py --cookies brave)" if thumbs == 0 else ""))
    print(f"-> {args.out}")


if __name__ == "__main__":
    main()
