# Instagram saved-items -> Excel report. Stdlib + pandas + openpyxl (all free).
import json, re
from collections import Counter, defaultdict
from datetime import datetime, timezone
import pandas as pd

SRC = r"C:\Users\Jainish\Downloads\instagram-jainish._07-2026-05-19-vUO25keT\your_instagram_activity\saved"
OUT = r"g:\AI AGENTS\instagram_saved_report.xlsx"

def fix(s):
    """Instagram exports mojibake: real UTF-8 bytes escaped as latin-1. Undo it."""
    if not isinstance(s, str):
        return s
    try:
        return s.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s

def load(name):
    with open(f"{SRC}\\{name}", encoding="utf-8") as f:
        return json.load(f)

def extract_post(label_values):
    """Pull one reel/post record from a label_values list."""
    rec = {"url": "", "caption": "", "hashtags": [],
           "owner_user": "", "owner_name": "", "owner_link": ""}
    for e in label_values:
        if "label" in e:
            lab, val = e.get("label"), fix(e.get("value", ""))
            if lab == "URL" and not rec["url"]:
                rec["url"] = val
            elif lab == "Caption" and not rec["caption"]:
                rec["caption"] = val
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
                        elif l == "URL":
                            rec["owner_link"] = v
    return rec

# ---- Topic classification (ordered: first strong match wins as "primary") ----
TOPICS = {
    "AI & Coding/Tech": ["ai", "chatgpt", "claude", "gemini", "llm", "coding", "code", "programming",
        "developer", "software", "github", "python", "dsa", "vibecod", "automation", "n8n", "tech",
        "machinelearning", "datascience", "computerscience", "webdev", "openai", "agent", "prompt",
        "aitools", "aivideo", "aiagents", "aiagent", "genai", "generativeai", "aiart", "antigravity"],
    "Career / Jobs / Internships": ["internship", "placement", "resume", "linkedin", "hiring", "job",
        "career", "interview", "faang", "recruiter", "gsoc", "off campus", "offcampus"],
    "Startup / Business": ["startup", "entrepreneur", "founder", "business", "saas", "venturecapital",
        "vc ", "ycombinator", "pitch", "marketing", "branding", "familybusiness"],
    "Finance / Investing": ["finance", "investing", "stock", "mutual fund", "etf", "trading", "wealth",
        "money", "billionaire", "passive income", "demat", "nse", "compounding"],
    "Fitness / Gym": ["gym", "workout", "fitness", "calisthenics", "pushup", "abs", "fatloss",
        "bodybuilding", "forearm", "muscle", "posture"],
    "Skincare / Beauty / Glow-up": ["skincare", "glowup", "glowing", "acne", "glass skin", "haircare",
        "beauty", "makeup", "looksmax", "tanning", "selfcare"],
    "Height / Looksmaxxing": ["height", "growtaller", "taller", "heightmax", "elevate method"],
    "Fashion / Style": ["fashion", "outfit", "menswear", "oldmoney", "style", "ootd", "wardrobe",
        "streetwear", "perfume", "fragrance"],
    "Dating / Relationships": ["dating", "relationship", "rizz", "situationship", "breakup", "girlfriend",
        "boyfriend", "attraction", "flirt", "couple", "masculine", "redpill", "femini"],
    "Self-improvement / Mindset": ["motivation", "mindset", "discipline", "selfimprovement", "habits",
        "growthmindset", "stoic", "productivity", "successmindset", "psychology", "manifest"],
    "Travel": ["travel", "trip", "itinerary", "vacation", "explore the world", "wanderlust", "udaipur",
        "goa", "bali", "vietnam", "japan", "europe", "tourism", "getaway"],
    "Food (incl. Jain)": ["jain food", "recipe", "foodie", "restaurant", "vegetarian", "veg ", "cooking",
        "food", "fries", "candy"],
    "Wedding / Events": ["wedding", "mehendi", "sangeet", "baraat", "shaadi", "bride", "groom", "garba",
        "dakla", "navratri"],
    "Spirituality / Religion": ["jainism", "krishna", "hanuman", "spiritual", "mahadev", "astrology",
        "tarot", "vedanta", "bhagavad", "consciousness", "manifestation", "guruji", "stuti", "mantra"],
    "Study / Education": ["study", "student", "college", "exam", "neet", "jee", "cat", "mba", "iim",
        "scholarship", "education", "studygram"],
    "Anime": ["anime", "animeedit", "manga", "otaku"],
    "Movies / Series": ["movie", "netflix", "series", "cinema", "film", "webseries", "imdb"],
    "Music / Dance": ["song", "music", "dance", "lyrics", "rap", "hiphop", "cover", "singing"],
    "Health / Remedies": ["health", "remedy", "detox", "nutrition", "neuroscience", "testosterone",
        "wellness", "ayurveda", "mudra", "period"],
    "Photography / Editing": ["editing", "lightroom", "presets", "photography", "vlog", "cinematic",
        "pose", "story idea", "story effect", "iphone"],
    "Memes / Funny / Relatable": ["meme", "funny", "relatable", "comedy", "shitpost"],
}

_TOPIC_RX = {t: re.compile(r"\b(" + "|".join(re.escape(k.strip()) for k in kws) + r")\b")
             for t, kws in TOPICS.items()}

def classify(text):
    matched = [t for t, rx in _TOPIC_RX.items() if rx.search(text)]
    return (matched[0] if matched else "Other"), matched

# ---- de-duplicated reel store keyed by URL ----
reels = {}  # url -> dict
def add(rec, ts, source):
    url = rec["url"]
    if not url:
        return
    if url not in reels:
        text = (rec["caption"] + " " + " ".join(rec["hashtags"]) + " " + rec["owner_name"]).lower()
        primary, allt = classify(text)
        reels[url] = {**rec, "ts": ts, "sources": set(),
                      "topic": primary, "all_topics": allt}
    if ts and (reels[url]["ts"] is None or ts < reels[url]["ts"]):
        reels[url]["ts"] = ts
    reels[url]["sources"].add(source)

# posts
posts = load("saved_posts.json")
for item in posts:
    add(extract_post(item.get("label_values", [])), item.get("timestamp"), "Saved Posts")

# collections
collections = load("saved_collections.json")
coll_summary = []
for coll in collections:
    name = ptype = priv = ""; n = 0; upd = None
    for e in coll.get("label_values", []):
        if e.get("label") == "Name":
            name = fix(e.get("value", ""))
        elif e.get("label") == "Type":
            ptype = e.get("value", "")
        elif e.get("label") == "Privacy":
            priv = e.get("value", "")
        elif e.get("label") == "Update time":
            upd = e.get("timestamp_value")
        elif e.get("dict") is not None and e.get("title") == "Media":
            for media in e["dict"]:
                rec = extract_post(media.get("dict", []))
                add(rec, coll.get("timestamp"), f"Collection: {name}")
                if rec["url"]:
                    n += 1
    coll_summary.append({"Collection": name, "Type": ptype, "Privacy": priv,
                         "Items": n,
                         "Last updated": datetime.fromtimestamp(upd).strftime("%Y-%m-%d") if upd else ""})

def dt(ts):
    return datetime.fromtimestamp(ts) if ts else None

# ---- build dataframes ----
rows = []
for r in reels.values():
    d = dt(r["ts"])
    rows.append({
        "Saved date": d.strftime("%Y-%m-%d") if d else "",
        "Month": d.strftime("%Y-%m") if d else "",
        "Topic": r["topic"],
        "All topics": ", ".join(r["all_topics"]),
        "Creator (@)": r["owner_user"],
        "Creator name": r["owner_name"],
        "Caption": (r["caption"][:300] + "…") if len(r["caption"]) > 300 else r["caption"],
        "Hashtags": " ".join("#" + h for h in r["hashtags"]),
        "Saved in": ", ".join(sorted(r["sources"])),
        "URL": r["url"],
    })
df = pd.DataFrame(rows).sort_values("Saved date", ascending=False, na_position="last")

topic_df = (df["Topic"].value_counts().rename_axis("Topic")
            .reset_index(name="Reels"))
creator_df = (df[df["Creator (@)"] != ""]["Creator (@)"].value_counts()
              .rename_axis("Creator (@)").reset_index(name="Reels").head(40))
tag_counter = Counter(h.lower() for r in reels.values() for h in r["hashtags"] if h)
tag_df = pd.DataFrame(tag_counter.most_common(50), columns=["Hashtag", "Times used"])
tag_df["Hashtag"] = "#" + tag_df["Hashtag"]
month_df = (df[df["Month"] != ""]["Month"].value_counts()
            .rename_axis("Month").reset_index(name="Reels").sort_values("Month"))
coll_df = pd.DataFrame(coll_summary).sort_values("Items", ascending=False)

# saved music
music_rows = []
for m in load("saved_music.json"):
    title = artist = ""
    for e in m.get("label_values", []):
        if e.get("label") == "Title":
            title = fix(e.get("value", ""))
        elif e.get("label") == "Artist":
            artist = fix(e.get("value", ""))
    d = dt(m.get("timestamp"))
    music_rows.append({"Saved date": d.strftime("%Y-%m-%d") if d else "",
                       "Track": title, "Artist": artist})
music_df = pd.DataFrame(music_rows)

with pd.ExcelWriter(OUT, engine="openpyxl") as xl:
    df.to_excel(xl, sheet_name="All Saved Reels", index=False)
    topic_df.to_excel(xl, sheet_name="By Topic", index=False)
    creator_df.to_excel(xl, sheet_name="Top Creators", index=False)
    tag_df.to_excel(xl, sheet_name="Top Hashtags", index=False)
    month_df.to_excel(xl, sheet_name="Saved by Month", index=False)
    coll_df.to_excel(xl, sheet_name="Collections", index=False)
    music_df.to_excel(xl, sheet_name="Saved Music", index=False)
    # widen columns a bit
    for ws in xl.book.worksheets:
        for col in ws.columns:
            width = min(60, max((len(str(c.value)) for c in col if c.value), default=10) + 2)
            ws.column_dimensions[col[0].column_letter].width = width

# ---- console summary ----
print(f"Unique reels/posts: {len(reels)}")
print(f"From {df['Saved date'].dropna().min()} to {df['Saved date'].dropna().max()}")
print("\nTOP TOPICS:")
for _, row in topic_df.head(12).iterrows():
    print(f"  {row['Reels']:>4}  {row['Topic']}")
print("\nTOP 12 CREATORS:")
for _, row in creator_df.head(12).iterrows():
    print(f"  {row['Reels']:>3}  @{row['Creator (@)']}")
print(f"\nCollections: {len(coll_df)} | Saved tracks: {len(music_df)}")
print(f"\nSaved Excel -> {OUT}")
