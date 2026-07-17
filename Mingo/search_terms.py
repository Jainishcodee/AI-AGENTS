"""Builds a list of plausible-looking search queries for the Bing searches.

Tries Google's daily trending-searches RSS feed (no API key needed); if that's
unreachable it falls back to randomly combining a topic with a modifier word so
the queries don't all look like "test test test".
"""
import random
import urllib.request
import xml.etree.ElementTree as ET

_TRENDS_URL = "https://trends.google.com/trends/trendingsearches/daily/rss?geo=US"

_MODIFIERS = [
    "weather", "news", "recipe", "review", "near me", "vs", "how to", "best",
    "2026", "price", "wikipedia", "tutorial", "schedule", "score", "cast",
    "meaning", "definition", "lyrics", "calculator", "map", "hotel", "flight",
    "symptoms", "salary", "net worth", "age", "highlights", "explained",
]
_TOPICS = [
    "nvidia", "tesla", "premier league", "olympics", "iphone 16", "world cup",
    "stock market", "bitcoin", "marvel", "real madrid", "nasa", "spacex",
    "amazon", "netflix", "windows 11", "electric car", "climate change",
    "cricket world cup", "champions league", "chatgpt", "playstation 5",
    "formula 1", "wimbledon", "the office", "interstellar", "python pandas",
    "mount everest", "great barrier reef", "northern lights", "solar eclipse",
]


def _from_trends(limit: int = 30):
    try:
        req = urllib.request.Request(_TRENDS_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            root = ET.fromstring(resp.read())
        titles = [el.text.strip() for el in root.iter("title") if el.text]
        return [t for t in titles if t and t.lower() != "daily search trends"][:limit]
    except Exception:  # noqa: BLE001 - offline or feed changed; just fall back
        return []


def get_search_terms(n: int):
    terms = _from_trends()
    random.shuffle(terms)
    out = list(dict.fromkeys(terms))[:n]  # de-dupe, keep order
    while len(out) < n:
        topic = random.choice(_TOPICS)
        q = topic if random.random() < 0.3 else f"{topic} {random.choice(_MODIFIERS)}"
        if q not in out:
            out.append(q)
    random.shuffle(out)
    return out[:n]
