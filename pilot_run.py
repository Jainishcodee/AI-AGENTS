"""Pilot: download + transcribe 50 random reels from saved set, compare to captions."""
import json, random, subprocess, time, csv, sys
from pathlib import Path

SAVED = Path(r"C:\Users\Jainish\Downloads\instagram-jainish._07-2026-05-19-vUO25keT\your_instagram_activity\saved")
PILOT = Path(r"g:\AI AGENTS\pilot")
AUDIO = PILOT / "audio"
TXT = PILOT / "transcripts"
AUDIO.mkdir(parents=True, exist_ok=True)
TXT.mkdir(parents=True, exist_ok=True)

# ---- fix mojibake ----
def fix(s):
    if not isinstance(s, str): return s
    try: return s.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError): return s

def extract(lvs):
    rec = {"url": "", "caption": "", "owner": ""}
    for e in lvs:
        if "label" in e:
            v = fix(e.get("value", ""))
            if e["label"] == "URL" and not rec["url"]: rec["url"] = v
            elif e["label"] == "Caption" and not rec["caption"]: rec["caption"] = v
        elif e.get("title") == "Owner":
            for o in e["dict"]:
                for kv in o.get("dict", []):
                    if kv.get("label") == "Username":
                        rec["owner"] = fix(kv.get("value", ""))
    return rec

# ---- collect unique URLs + captions ----
pool = {}
for it in json.load(open(SAVED / "saved_posts.json", encoding="utf-8")):
    r = extract(it.get("label_values", []))
    if r["url"] and r["url"] not in pool: pool[r["url"]] = r
for coll in json.load(open(SAVED / "saved_collections.json", encoding="utf-8")):
    for e in coll.get("label_values", []):
        if e.get("title") == "Media":
            for m in e["dict"]:
                r = extract(m.get("dict", []))
                if r["url"] and r["url"] not in pool: pool[r["url"]] = r

# only true reels (skip /p/ photo posts since transcription only makes sense for video)
reels = [r for r in pool.values() if "/reel/" in r["url"]]
print(f"Total unique reels available: {len(reels)}")

random.seed(42)
sample = random.sample(reels, 50)
print(f"Sampled {len(sample)} reels\n")

# ---- download phase ----
def download(url, out_id):
    target = AUDIO / f"{out_id}.wav"
    if target.exists(): return "cached"
    cmd = ["yt-dlp", "-q", "--no-warnings", "--socket-timeout", "30", "--retries", "2",
           "-f", "bestaudio[ext=m4a]/bestaudio",
           "--extract-audio", "--audio-format", "wav", "--audio-quality", "0",
           "-o", str(AUDIO / f"{out_id}.%(ext)s"), url]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        return "ok" if target.exists() else f"fail: {(p.stderr or p.stdout)[:120]}"
    except subprocess.TimeoutExpired:
        return "fail: timeout"
    except Exception as e:
        return f"fail: {e}"

reel_id = lambda u: u.rstrip("/").rsplit("/", 1)[-1]
results = []
t0 = time.time()
for i, r in enumerate(sample, 1):
    rid = reel_id(r["url"])
    status = download(r["url"], rid)
    if i % 5 == 0 or status.startswith("fail"):
        print(f"[{i}/50] {rid}: {status}")
    results.append({**r, "id": rid, "dl": status})
print(f"\nDownload phase: {time.time()-t0:.0f}s")
ok = sum(1 for r in results if r["dl"] in ("ok", "cached"))
print(f"Downloaded: {ok}/50\n")

# ---- transcribe phase ----
print("Loading Whisper 'small' model (first run downloads ~500MB)...")
from faster_whisper import WhisperModel
model = WhisperModel("small", device="cpu", compute_type="int8")
print("Model loaded.\n")

t0 = time.time()
for i, r in enumerate(results, 1):
    if r["dl"] not in ("ok", "cached"):
        r["transcript"] = ""; r["lang"] = ""; r["dur"] = 0
        continue
    wav = AUDIO / f"{r['id']}.wav"
    txt_file = TXT / f"{r['id']}.txt"
    if txt_file.exists():
        r["transcript"] = txt_file.read_text(encoding="utf-8")
        r["lang"] = ""; r["dur"] = 0
        continue
    try:
        segs, info = model.transcribe(str(wav), beam_size=1, vad_filter=True)
        text = " ".join(s.text.strip() for s in segs).strip()
        r["transcript"] = text
        r["lang"] = info.language
        r["dur"] = round(info.duration, 1)
        txt_file.write_text(text, encoding="utf-8")
        print(f"[{i}/50] {r['id']} [{info.language} {info.duration:.0f}s] {text[:80]}")
    except Exception as e:
        r["transcript"] = ""; r["lang"] = ""; r["dur"] = 0
        print(f"[{i}/50] {r['id']}: transcribe-fail {e}")

print(f"\nTranscribe phase: {time.time()-t0:.0f}s")

# ---- write CSV report ----
out = PILOT / "pilot_results.csv"
with open(out, "w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["id", "url", "owner", "dl", "lang", "dur",
                                       "caption_len", "transcript_len",
                                       "caption", "transcript"])
    w.writeheader()
    for r in results:
        w.writerow({
            "id": r["id"], "url": r["url"], "owner": r["owner"], "dl": r["dl"],
            "lang": r.get("lang", ""), "dur": r.get("dur", 0),
            "caption_len": len(r["caption"]), "transcript_len": len(r.get("transcript", "")),
            "caption": r["caption"][:500], "transcript": r.get("transcript", "")[:1500],
        })
print(f"\nCSV -> {out}")

# ---- summary ----
dl_ok = [r for r in results if r["dl"] in ("ok", "cached")]
tx_ok = [r for r in dl_ok if r.get("transcript")]
empty_caption = sum(1 for r in results if len(r["caption"]) < 20)
empty_caption_tx_ok = sum(1 for r in results if len(r["caption"]) < 20 and r.get("transcript"))
from collections import Counter
langs = Counter(r["lang"] for r in tx_ok if r.get("lang"))
print(f"\n=== PILOT RESULTS ===")
print(f"Download success:   {len(dl_ok)}/50")
print(f"Transcribe success: {len(tx_ok)}/50")
print(f"Reels w/ short or empty caption: {empty_caption} (of those, transcripts recovered: {empty_caption_tx_ok})")
print(f"Languages detected: {dict(langs)}")
