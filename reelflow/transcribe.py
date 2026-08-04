"""Stage 2: transcribe the thin-caption reels.

Only items flagged needs_transcript get audio pulled -- a rich caption already
carries enough for distillation, so spending 30s of CPU on it buys nothing.

Reuses the May pilot's audio/transcript cache (same shortcode filenames), and
broadens the yt-dlp format selector to `bestaudio/best`, which fixes the
"Requested format is not available" failures the pilot hit on older reels.

  python transcribe.py            # every thin-caption item
  python transcribe.py --sample 20  # stratified 20-item proof set
"""
import argparse
import json
import random
import subprocess
import time
from pathlib import Path

from common import AUDIO, DATA, TRANSCRIPTS, load_json, write_json

PILOT_AUDIO = Path(r"g:\AI AGENTS\pilot\audio")
PILOT_TXT = Path(r"g:\AI AGENTS\pilot\transcripts")


def download(url, item_id, cookies=None):
    target = AUDIO / f"{item_id}.wav"
    if target.exists():
        return "cached"
    cached = PILOT_AUDIO / f"{item_id}.wav"
    if cached.exists():
        target.write_bytes(cached.read_bytes())
        return "cached-pilot"
    cmd = ["yt-dlp", "-q", "--no-warnings", "--socket-timeout", "30", "--retries", "2",
           "-f", "bestaudio/best",
           "--extract-audio", "--audio-format", "wav", "--audio-quality", "0",
           "-o", str(AUDIO / f"{item_id}.%(ext)s")]
    # Instagram stopped serving media to logged-out clients around mid-2026,
    # so anonymous downloads that worked in the May pilot now return an empty
    # media response. A logged-in session is required.
    if cookies:
        cmd += (["--cookies", cookies] if cookies.endswith(".txt")
                else ["--cookies-from-browser", cookies])
    cmd.append(url)
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        return "ok" if target.exists() else f"fail: {(p.stderr or p.stdout)[:100].strip()}"
    except subprocess.TimeoutExpired:
        return "fail: timeout"
    except Exception as e:
        return f"fail: {e}"


def pick_sample(items, n, seed=42):
    """Stratified: keep the thin/rich ratio of the full set so the proof run
    exercises both the transcript path and the caption-only path."""
    thin = [i for i in items if i["needs_transcript"]]
    rich = [i for i in items if not i["needs_transcript"]]
    n_thin = max(1, round(n * len(thin) / len(items))) if items else 0
    n_thin = min(n_thin, len(thin))
    n_rich = min(n - n_thin, len(rich))
    rng = random.Random(seed)
    return rng.sample(thin, n_thin) + rng.sample(rich, n_rich)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=0)
    ap.add_argument("--model", default="small")
    ap.add_argument("--cookies", default=None,
                    help="browser name (brave/edge/chrome/firefox) or a cookies.txt path")
    ap.add_argument("--from-skips", default=None, metavar="DISTILLED_JSON",
                    help="only fetch reels a distill pass marked skip_reason=needs_video")
    args = ap.parse_args()

    AUDIO.mkdir(parents=True, exist_ok=True)
    TRANSCRIPTS.mkdir(parents=True, exist_ok=True)

    items = load_json(DATA / "items.json")
    by_id = {i["id"]: i for i in items}

    if args.from_skips:
        # Pass 2. Caption length turned out to be a poor predictor -- a 500-char
        # caption is often pure hook. Trust the distiller's own verdict instead:
        # it read the caption and said the content is in the video.
        cards = load_json(args.from_skips)
        want = {c["id"] for c in cards if c.get("skip_reason") == "needs_video"}
        todo = [i for i in items if i["id"] in want]
        print(f"Pass 2: {len(todo)} reels the distiller flagged as needs_video\n")
    else:
        if args.sample:
            sample = pick_sample(items, args.sample)
            write_json(DATA / "sample.json", [i["id"] for i in sample])
            scope = sample
            print(f"Proof sample: {len(scope)} items "
                  f"({sum(1 for i in scope if i['needs_transcript'])} thin-caption)")
        else:
            scope = items
        todo = [i for i in scope if i["needs_transcript"]]
        print(f"Need transcription: {len(todo)}\n")

    # -- download --
    t0 = time.time()
    stats = {}
    for n, it in enumerate(todo, 1):
        st = download(it["url"], it["id"], args.cookies)
        it["dl"] = st
        stats[st.split(":")[0]] = stats.get(st.split(":")[0], 0) + 1
        if st.startswith("fail"):
            print(f"  [{n}/{len(todo)}] {it['id']}: {st}")
    print(f"Download: {time.time() - t0:.0f}s  {stats}\n")

    # -- transcribe --
    pending = [i for i in todo
               if i.get("dl", "").startswith(("ok", "cached"))
               and not (TRANSCRIPTS / f"{i['id']}.txt").exists()]
    # adopt any transcript the pilot already produced
    for it in todo:
        dst = TRANSCRIPTS / f"{it['id']}.txt"
        src = PILOT_TXT / f"{it['id']}.txt"
        if not dst.exists() and src.exists():
            dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
            pending = [p for p in pending if p["id"] != it["id"]]

    if pending:
        print(f"Loading Whisper '{args.model}' on CPU...")
        from faster_whisper import WhisperModel
        model = WhisperModel(args.model, device="cpu", compute_type="int8")
        t0 = time.time()
        for n, it in enumerate(pending, 1):
            try:
                segs, info = model.transcribe(str(AUDIO / f"{it['id']}.wav"),
                                              beam_size=1, vad_filter=True)
                text = " ".join(s.text.strip() for s in segs).strip()
                (TRANSCRIPTS / f"{it['id']}.txt").write_text(text, encoding="utf-8")
                by_id[it["id"]]["lang"] = info.language
                print(f"  [{n}/{len(pending)}] {it['id']} [{info.language}] {text[:70]}")
            except Exception as e:
                print(f"  [{n}/{len(pending)}] {it['id']}: FAIL {e}")
        print(f"Transcribe: {time.time() - t0:.0f}s")

    # -- fold transcripts back into items.json --
    got = 0
    for it in items:
        f = TRANSCRIPTS / f"{it['id']}.txt"
        if f.exists():
            it["transcript"] = f.read_text(encoding="utf-8").strip()
            if len(it["transcript"]) > 30:
                got += 1
    write_json(DATA / "items.json", items)
    print(f"\nUseful transcripts (>30 chars): {got}")


if __name__ == "__main__":
    main()
