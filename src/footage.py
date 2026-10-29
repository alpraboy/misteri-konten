"""Agen footage: cari & unduh klip gratis dari Pixabay atau Pexels, hindari klip berulang.

Pilih penyedia lewat secret yang tersedia:
- PIXABAY_API_KEY  -> Pixabay (dipakai bila ada)
- PEXELS_API_KEY   -> Pexels  (cadangan; pendaftaran key baru sedang dijeda)
"""
import os
import time
from pathlib import Path

import requests


# ---------- Penyedia: Pixabay ----------
def _pixabay(query, portrait=True):
    r = requests.get(
        "https://pixabay.com/api/videos/",
        params={
            "key": os.environ["PIXABAY_API_KEY"], "q": query[:100],
            "per_page": 20, "safesearch": "true",
        },
        timeout=30,
    )
    r.raise_for_status()
    out = []
    for h in r.json().get("hits", []):
        files = [
            v for v in h.get("videos", {}).values()
            if v.get("url") and v.get("height") and v["height"] <= 2560
        ]
        if not files:
            continue
        f = min(files, key=lambda v: abs(v["height"] - 1920))
        out.append({
            "id": f"pixabay-{h['id']}", "link": f["url"],
            "w": f["width"], "h": f["height"],
            "credit": f"{h.get('user', 'Pixabay')} ({h.get('pageURL', '')})",
        })
    return out


# ---------- Penyedia: Pexels ----------
def _pexels(query, portrait=True):
    params = {"query": query, "per_page": 12, "size": "medium"}
    if portrait:
        params["orientation"] = "portrait"
    r = requests.get(
        "https://api.pexels.com/videos/search", params=params,
        headers={"Authorization": os.environ["PEXELS_API_KEY"]}, timeout=30,
    )
    r.raise_for_status()
    out = []
    for v in r.json().get("videos", []):
        files = [
            f for f in v.get("video_files", [])
            if f.get("file_type") == "video/mp4" and f.get("height") and f["height"] <= 2560
        ]
        if not files:
            continue
        f = min(files, key=lambda x: abs(x["height"] - 1920))
        out.append({
            "id": f"pexels-{v['id']}", "link": f["link"],
            "w": f["width"], "h": f["height"],
            "credit": f"{v.get('user', {}).get('name', 'Pexels')} ({v.get('url', '')})",
        })
    return out


def _provider():
    if os.environ.get("PIXABAY_API_KEY"):
        return _pixabay, False  # Pixabay tidak punya filter orientasi video
    if os.environ.get("PEXELS_API_KEY"):
        return _pexels, True
    raise RuntimeError("Isi secret PIXABAY_API_KEY (atau PEXELS_API_KEY).")


def _download(url, dest: Path):
    for attempt in range(3):
        try:
            with requests.get(url, stream=True, timeout=90) as r:
                r.raise_for_status()
                with open(dest, "wb") as f:
                    for chunk in r.iter_content(1 << 20):
                        f.write(chunk)
            return
        except Exception as e:
            print(f"Unduh gagal ({attempt + 1}): {e}")
            time.sleep(3)
    raise RuntimeError(f"Gagal mengunduh {url}")


def fetch_all(script, cfg, work: Path):
    """Isi tiap scene dengan 'clip' (path file). Kembalikan daftar kredit."""
    work.mkdir(parents=True, exist_ok=True)
    search, has_portrait = _provider()
    used, credits = set(), []
    fallback = list(cfg["fallback_keywords"])

    for i, sc in enumerate(script["scenes"]):
        chosen = None
        for q in list(sc["keywords"]) + fallback:
            for portrait in ((True, False) if has_portrait else (False,)):
                try:
                    vids = search(q, portrait)
                except Exception as e:
                    print(f"Pencarian '{q}' gagal: {e}")
                    continue
                for v in vids:
                    if v["id"] not in used:
                        chosen = (v, q)
                        break
                if chosen:
                    break
            if chosen:
                break
            time.sleep(0.7)  # hormati batas ~100 permintaan/menit
        if not chosen:
            raise RuntimeError(f"Tidak menemukan footage untuk adegan {i}")

        v, q = chosen
        used.add(v["id"])
        dest = work / f"clip{i:02d}.mp4"
        _download(v["link"], dest)
        sc["clip"] = str(dest)
        credits.append(v["credit"])
        print(f"Adegan {i}: '{q}' -> {v['id']} ({v['w']}x{v['h']})")
    return credits
