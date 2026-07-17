"""Patch pilot CSV with recovered transcripts + analyze caption vs transcript."""
import csv, re
from pathlib import Path

PILOT = Path(r"g:\AI AGENTS\pilot")
TXT = PILOT / "transcripts"
CSV_IN = PILOT / "pilot_results.csv"

# Load existing CSV
rows = list(csv.DictReader(open(CSV_IN, encoding="utf-8")))

# Recover transcripts from .txt files on disk
recovered = 0
for r in rows:
    txt = TXT / f"{r['id']}.txt"
    if txt.exists():
        content = txt.read_text(encoding="utf-8").strip()
        if content and not r.get("transcript"):
            r["transcript"] = content
            r["transcript_len"] = len(content)
            recovered += 1
        elif content:
            # always prefer full file content over CSV-truncated value
            r["transcript"] = content
            r["transcript_len"] = len(content)

# Write patched CSV (transcripts full, not truncated)
with open(CSV_IN, "w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=rows[0].keys())
    w.writeheader()
    w.writerows(rows)

# ---- Analysis ----
dl_ok = [r for r in rows if r["dl"] in ("ok", "cached")]
tx = [r for r in dl_ok if r.get("transcript")]
meaningful = [r for r in tx if len(r["transcript"]) > 30]  # actual narration, not "you" / empty

# Reels with short captions where transcript saved the day
short_cap = [r for r in rows if len(r["caption"]) < 50]
short_cap_got_tx = [r for r in short_cap if len(r.get("transcript", "")) > 30]

# Languages
from collections import Counter
langs = Counter(r["lang"] for r in tx if r["lang"])

print("=" * 60)
print("PATCHED PILOT RESULTS")
print("=" * 60)
print(f"Download success:                {len(dl_ok)}/50")
print(f"Transcribed (any text):          {len(tx)}/50")
print(f"Transcribed (>30 chars, useful): {len(meaningful)}/50")
print(f"Languages: {dict(langs)}")
print(f"\nReels with short/empty captions: {len(short_cap)}")
print(f"  ...of those, useful transcript: {len(short_cap_got_tx)}")

# Show 3 cases where transcript ADDS information
print("\n" + "=" * 60)
print("WHERE TRANSCRIPTS ADDED REAL CONTENT (caption was thin):")
print("=" * 60)
shown = 0
for r in sorted(rows, key=lambda x: (len(x["caption"]), -len(x.get("transcript", ""))) ):
    if shown >= 5: break
    if len(r.get("transcript", "")) > 100 and len(r["caption"]) < 100:
        print(f"\n@{r['owner']}  ({r['id']})")
        print(f"  CAPTION ({len(r['caption'])} chars): {r['caption'][:120]!r}")
        print(f"  TRANSCRIPT ({len(r['transcript'])} chars): {r['transcript'][:200]!r}")
        shown += 1

print("\n" + "=" * 60)
print("CSV patched -> " + str(CSV_IN))
