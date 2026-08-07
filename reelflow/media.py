"""Stage 6: fetch a cover image for every card, and drop cards whose reel is gone.

Thumbnails only -- the reel itself stays on Instagram and opens there, which
keeps the APK small and avoids shipping other people's video around.

This is also the only stage that touches every card's URL, so it doubles as the
liveness check: Instagram takes reels down for copyright and creators delete
them, and a card that opens to a dead page is worse than no card. Ids that come
back clearly gone are written to data/unavailable.json for pack.py to exclude.

  python media.py
"""
import argparse
import subprocess
import time
from pathlib import Path

from common import DATA, load_json, write_json

THUMBS = Path(r"g:\AI AGENTS\Jarvis\assets\thumbs")

# yt-dlp text that means the post itself is gone -- taken down, deleted, or made
# private. Matching is deliberately narrow: a card is only discarded on one of
# these, and anything unrecognised keeps its card and just loses the cover.
GONE = (
    "empty media response",
    "post not available",
    "http error 404",
    "content isn't available",
    "has been removed",
    "page not found",
    "video unavailable",
    "this post is unavailable",
)

# Photo carousels have no video stream to pull a cover frame from. Not a dead
# reel -- the card is fine, it just ships without art.
CAROUSEL = "no video formats found"


def classify(err):
    """gone / carousel / unknown. Unknown never costs a card."""
    e = err.lower()
    if any(p in e for p in GONE):
        return "gone"
    if CAROUSEL in e:
        return "carousel"
    return "unknown"


def fetch(url, item_id, force=False):
    """-> ("ok"|"cached", "") or ("fail", stderr)."""
    out = THUMBS / f"{item_id}.jpg"
    if out.exists() and not force:
        return "cached", ""
    cmd = ["yt-dlp", "-q", "--no-warnings", "--socket-timeout", "30", "--retries", "2",
           "--skip-download", "--write-thumbnail", "--convert-thumbnails", "jpg",
           "-o", str(THUMBS / f"{item_id}.%(ext)s"), url]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if out.exists():
            return "ok", ""
        return "fail", (p.stderr or p.stdout).strip()
    except subprocess.TimeoutExpired:
        return "fail", "timeout"
    except Exception as e:
        return "fail", str(e)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--sleep", type=float, default=0.5,
                    help="pacing between fetches, to stay under IG's rate limit")
    args = ap.parse_args()

    THUMBS.mkdir(parents=True, exist_ok=True)
    cards = [c for c in load_json(DATA / "distilled.json")
             if c["kind"] in ("task", "fact") and not c.get("error")]
    print(f"{len(cards)} cards to cover\n")

    stats = {"ok": 0, "cached": 0, "gone": 0, "carousel": 0, "unknown": 0}
    dead, t0 = [], time.time()
    for n, c in enumerate(cards, 1):
        st, err = fetch(c["url"], c["id"], args.force)
        if st in ("ok", "cached"):
            stats[st] += 1
            continue
        verdict = classify(err)
        stats[verdict] += 1
        if verdict == "gone":
            dead.append({"id": c["id"], "url": c["url"], "reason": err[:200]})
        if verdict == "unknown" and stats["unknown"] <= 5:
            print(f"  [{n}/{len(cards)}] {c['id']}: {err[:110]}")
        if args.sleep:
            time.sleep(args.sleep)

    # A platform-wide change (Instagram re-walling anonymous access, or this box
    # getting rate-limited) looks exactly like every reel being dead at once.
    # Refuse to act on that automatically -- losing most of the deck to a
    # transient outage is far worse than shipping a few stale cards.
    attempted = len(cards)
    if dead and len(dead) > attempted * 0.25:
        print(f"\n!! {len(dead)}/{attempted} cards look unavailable -- too many to trust.")
        print("   Treating this as an Instagram-side problem, not real takedowns.")
        print("   Nothing discarded. Re-run when the network/rate limit settles.")
        dead = []

    write_json(DATA / "unavailable.json", dead)

    got = len(list(THUMBS.glob("*.jpg")))
    print(f"\n{time.time() - t0:.0f}s  {stats}")
    print(f"{got} thumbnails in {THUMBS}")
    print(f"{len(dead)} dead reels -> {DATA / 'unavailable.json'} (pack.py drops these)")
    if not got:
        print("\nNothing downloaded at all -- check yt-dlp works on a reel URL by hand.")
    else:
        print("Now re-run: python pack.py")


if __name__ == "__main__":
    main()
