"""Sumber fakta gratis agar skrip tidak murni karangan model."""
import xml.etree.ElementTree as ET
from urllib.parse import quote

import requests

UA = {"User-Agent": "agen-misteri/1.0 (github actions; konten edukasi)"}
WIKI_API = "https://id.wikipedia.org/w/api.php"


def wikipedia_context(query, max_chars=6000):
    """Cari artikel Wikipedia Indonesia, kembalikan (judul, teks, url) atau None."""
    r = requests.get(WIKI_API, params={
        "action": "query", "list": "search", "srsearch": query,
        "format": "json", "srlimit": 1,
    }, headers=UA, timeout=25)
    r.raise_for_status()
    hits = r.json().get("query", {}).get("search", [])
    if not hits:
        return None
    title = hits[0]["title"]

    r = requests.get(WIKI_API, params={
        "action": "query", "prop": "extracts", "explaintext": 1,
        "exsectionformat": "plain", "titles": title, "redirects": 1,
        "format": "json",
    }, headers=UA, timeout=25)
    r.raise_for_status()
    pages = r.json().get("query", {}).get("pages", {})
    text = next(iter(pages.values())).get("extract", "")
    if not text.strip():
        return None
    url = "https://id.wikipedia.org/wiki/" + quote(title.replace(" ", "_"))
    return title, text[:max_chars], url


def news_headlines(query, window="7d", limit=8):
    """Ambil judul berita dari Google News RSS. Kembalikan list dict."""
    q = f"{query} when:{window}" if window else query
    url = f"https://news.google.com/rss/search?q={quote(q)}&hl=id&gl=ID&ceid=ID:id"
    r = requests.get(url, headers=UA, timeout=25)
    r.raise_for_status()
    root = ET.fromstring(r.content)
    items = []
    for it in root.iter("item"):
        items.append({
            "title": (it.findtext("title") or "").strip(),
            "source": (it.findtext("source") or "").strip(),
            "date": (it.findtext("pubDate") or "").strip(),
            "link": (it.findtext("link") or "").strip(),
        })
        if len(items) >= limit:
            break
    return items
