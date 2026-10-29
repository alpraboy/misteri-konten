"""Agen footage: cari & unduh klip dari Pexels (gratis), hindari klip berulang."""
import os
import time
from pathlib import Path

import requests

PEXELS = "https://api.pexels.com/videos/search"


def _search(query, portrait=True):
    params = {"query": query, "per_page": 12, "size": "medium"}
    if portrait:
        params["orientation"] = "portrait"
    r = requests.get(
        PEXELS, params=params,
        headers={"Authorization": os.environ["PEXELS_API_KEY"]}, timeout=30,
    )
    r.raise_for_status()
    return r.json().get("videos", [])


def _best_file(video):
    """Pilih file mp4 dengan tinggi paling dekat 1920 (maks 2560) agar tidak berat."""
    files = [
        f for f in video.get("video_files", [])
        if f.get("file_type") == "video/mp4" and f.get("height") and f["height"] <= 2560
    ]
    if not files:
        return None
    return min(files, key=lambda f: abs(f["height"] - 1920))


def _download(url, dest: Path):
    for attempt in range(3):
        try:
            with requests.get(url, stream=True, timeout=60) as r:
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
    used, credits = set(), []
    fallback = list(cfg["fallback_keywords"])

    for i, sc in enumerate(script["scenes"]):
        queries = list(sc["keywords"]) + fallback
        chosen = None
        for q in queries:
            for portrait in (True, False):
                try:
                    vids = _search(q, portrait)
                except Exception as e:
                    print(f"Pencarian '{q}' gagal: {e}")
                    continue
                for v in vids:
                    if v["id"] in used:
                        continue
                    f = _best_file(v)
                    if f:
                        chosen = (v, f, q)
                        break
                if chosen:
                    break
            if chosen:
                break
        if not chosen:
            raise RuntimeError(f"Tidak menemukan footage untuk adegan {i}")

        v, f, q = chosen
        used.add(v["id"])
        dest = work / f"clip{i:02d}.mp4"
        _download(f["link"], dest)
        sc["clip"] = str(dest)
        credits.append(f"{v.get('user', {}).get('name', 'Pexels')} ({v.get('url', '')})")
        print(f"Adegan {i}: '{q}' -> video {v['id']} ({f['width']}x{f['height']})")
    return credits
