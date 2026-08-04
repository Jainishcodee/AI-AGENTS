"""Stage 6: fetch a cover image for every card, to bundle with the app.

Thumbnails only -- the reel itself stays on Instagram and opens there, which
keeps the APK small and avoids shipping other people's video around.

Instagram stopped serving media to logged-out clients around mid-2026, so this
needs a session. Close the browser first (it locks the cookie DB), then:

  python media.py --cookies brave
  python media.py --cookies path\\to\\cookies.txt
"""
import argparse
import subprocess
import time
from pathlib import Path

from common import DATA, load_json

THUMBS = Path(r"g:\AI AGENTS\Jarvis\assets\thumbs")


def fetch(url, item_id, cookies, force=False):
    out = THUMBS / f"{item_id}.jpg"
    if out.exists() and not force:
        return "cached"
    cmd = ["yt-dlp", "-q", "--no-warnings", "--socket-timeout", "30", "--retries", "2",
           "--skip-download", "--write-thumbnail", "--convert-thumbnails", "jpg",
           "-o", str(THUMBS / f"{item_id}.%(ext)s")]
    if cookies:
        cmd += (["--cookies", cookies] if cookies.endswith(".txt")
                else ["--cookies-from-browser", cookies])
    cmd.append(url)
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if out.exists():
            return "ok"
        return f"fail: {(p.stderr or p.stdout)[:90].strip()}"
    except subprocess.TimeoutExpired:
        return "fail: timeout"
    except Exception as e:
        return f"fail: {e}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cookies", default=None,
                    help="browser name (brave/edge/chrome/firefox) or a cookies.txt path")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    THUMBS.mkdir(parents=True, exist_ok=True)
    cards = [c for c in load_json(DATA / "distilled.json")
             if c["kind"] in ("task", "fact")]
    print(f"{len(cards)} cards to cover\n")

    stats, t0 = {}, time.time()
    for n, c in enumerate(cards, 1):
        st = fetch(c["url"], c["id"], args.cookies, args.force)
        key = st.split(":")[0]
        stats[key] = stats.get(key, 0) + 1
        if st.startswith("fail") and stats[key] <= 3:
            print(f"  [{n}/{len(cards)}] {c['id']}: {st}")

    got = len(list(THUMBS.glob("*.jpg")))
    print(f"\n{time.time() - t0:.0f}s  {stats}")
    print(f"{got} thumbnails in {THUMBS}")
    if not got:
        print("\nNothing downloaded. Instagram needs a logged-in session -- "
              "close your browser fully and pass --cookies brave.")
    else:
        print("Now re-run: python pack.py")


if __name__ == "__main__":
    main()
