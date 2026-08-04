"""Stage 1: IG export -> data/items.json

Pulls the reels out of the collections we care about. The collection an item
lives in is only a *hint* about what it is -- distill.py can override it, since
a "do this" reel sometimes lands in the facts collection and vice versa.
"""
import sys

from common import IG_EXPORT, DATA, THIN_CAPTION, extract_media, fix, load_json, shortcode, write_json

# collection name -> kind hint. "auto" lets the model decide per item.
# Names must match the export exactly, emoji included.
COLLECTIONS = {
    "Karle bhai": "task",
    "True 💯": "fact",
    # Mixed bag of study tasks and study tips, so let the model call each one.
    "Study it, Tips and tricks": "auto",
}


def main(only=None):
    raw = load_json(IG_EXPORT / "saved_collections.json")
    items, seen = [], set()

    for coll in raw:
        name = ""
        media = []
        for e in coll.get("label_values", []):
            if e.get("label") == "Name":
                name = fix(e.get("value", ""))
            elif e.get("title") == "Media" and e.get("dict"):
                media = e["dict"]
        if name not in COLLECTIONS:
            continue
        if only and name != only:
            continue

        hint = COLLECTIONS[name]
        for m in media:
            rec = extract_media(m.get("dict", []))
            sc = shortcode(rec["url"])
            if not sc or sc in seen:
                continue
            seen.add(sc)
            caption = rec["caption"].strip()
            items.append({
                "id": sc,
                "url": rec["url"],
                "collection": name,
                "kind_hint": hint,
                "caption": caption,
                "title": rec["title"],
                "hashtags": rec["hashtags"],
                "owner_user": rec["owner_user"],
                "owner_name": rec["owner_name"],
                "caption_len": len(caption),
                "needs_transcript": len(caption) < THIN_CAPTION,
                "transcript": "",
                "lang": "",
            })

    write_json(DATA / "items.json", items)

    thin = sum(1 for i in items if i["needs_transcript"])
    by_coll = {}
    for i in items:
        by_coll[i["collection"]] = by_coll.get(i["collection"], 0) + 1
    print(f"Ingested {len(items)} unique items")
    for k, v in sorted(by_coll.items(), key=lambda x: -x[1]):
        print(f"  {v:>4}  {k}")
    print(f"\nThin captions (<{THIN_CAPTION} chars, need transcript): {thin} "
          f"({thin * 100 // max(len(items), 1)}%)")
    print(f"-> {DATA / 'items.json'}")


if __name__ == "__main__":
    main(only=sys.argv[1] if len(sys.argv) > 1 else None)
