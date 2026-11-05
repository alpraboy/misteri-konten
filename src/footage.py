"""Agen footage: cari & unduh klip gratis dari Pixabay atau Pexels, hindari klip berulang.

Pilih penyedia lewat secret yang tersedia:
- PIXABAY_API_KEY  -> Pixabay (dipakai bila ada)
- PEXELS_API_KEY   -> Pexels  (cadangan; pendaftaran key baru sedang dijeda)
"""
import os
import time
import re
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
            "meta": f"{h.get('tags', '')} {h.get('pageURL', '')}",
            "provider_ranked": False,
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
            "meta": f"{v.get('url', '')} {v.get('alt', '')}",
            "provider_ranked": True,
        })
    return out



def _tokens(text):
    stop = {"the", "and", "with", "from", "into", "over", "under", "for", "dark", "cinematic", "video", "footage", "night", "mystery"}
    return {t for t in re.findall(r"[a-z0-9]+", str(text).lower()) if len(t) >= 3 and t not in stop}


def _relevance(query, item):
    q = _tokens(query)
    meta = _tokens(item.get("meta", ""))
    # Pexels often returns no descriptive metadata in its video-search payload;
    # in that case retain the provider's query-ranked order rather than rejecting all clips.
    if not q or not meta:
        return 1.0 if item.get("provider_ranked", False) else 0.0
    return len(q & meta) / len(q)


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


def _choose(search, has_portrait, queries, used):
    """Pilih klip paling relevan (>= 0.20) yang belum dipakai; None bila tidak ada."""
    for q in queries:
        for portrait in ((True, False) if has_portrait else (False,)):
            try:
                vids = search(q, portrait)
            except Exception as e:
                print(f"Pencarian '{q}' gagal: {e}")
                continue
            vids = sorted(vids, key=lambda v: _relevance(q, v), reverse=True)
            for v in vids:
                if v["id"] not in used and _relevance(q, v) >= 0.20:
                    return v, q
        time.sleep(0.7)  # hormati batas ~100 permintaan/menit
    return None


def fetch_all(script, cfg, work: Path, strict=True):
    """Unduh footage. Dua jenis:
    - visual == 'footage'  : pengganti ilustrasi yang gagal (WAJIB; gagal -> berhenti)
    - broll_keywords       : inset kecil di beberapa adegan (OPSIONAL; gagal -> dilewati)
    Kembalikan daftar kredit."""
    work.mkdir(parents=True, exist_ok=True)
    scenes = script["scenes"]
    wanted = [i for i, sc in enumerate(scenes) if sc.get("visual") == "footage" or sc.get("broll_keywords")]
    if not wanted:
        return []
    try:
        search, has_portrait = _provider()
    except RuntimeError:
        if any(sc.get("visual") == "footage" for sc in scenes):
            raise
        print("Tidak ada API footage -> b-roll inset dilewati.")
        return []

    used, credits = set(), []
    for i in wanted:
        sc = scenes[i]
        required = sc.get("visual") == "footage"
        queries = [str(q).strip() for q in (sc.get("keywords") if required else sc.get("broll_keywords")) or [] if str(q).strip()]
        chosen = _choose(search, has_portrait, queries, used)
        if not chosen:
            if required and not strict:   # jangan hentikan render: pemanggil akan memakai ulang gambar
                print(f"Footage adegan {i} tidak ditemukan yang relevan -> adegan memakai gambar yang ada.")
                sc["visual"] = "illustration"
                sc["footage_missing"] = True
                continue
            if required:
                raise RuntimeError(
                    f"Tidak menemukan footage yang cukup relevan untuk adegan {i}. "
                    "Render dihentikan agar tidak memakai klip yang melenceng dari tema. "
                    "Perbaiki keywords adegan atau gunakan ilustrasi AI untuk adegan ini."
                )
            print(f"B-roll adegan {i} dilewati (tidak ada klip yang cukup relevan).")
            sc["broll_keywords"] = []
            continue

        v, q = chosen
        used.add(v["id"])
        dest = work / f"{'clip' if required else 'broll'}{i:02d}.mp4"
        try:
            _download(v["link"], dest)
        except RuntimeError:
            if required and strict:
                raise
            if required:
                sc["visual"] = "illustration"
                sc["footage_missing"] = True
            print(f"{'Footage' if required else 'B-roll'} adegan {i} dilewati (unduhan gagal).")
            continue
        sc["clip" if required else "broll_clip"] = str(dest)
        credits.append(v["credit"])
        print(f"Adegan {i} ({'footage' if required else 'b-roll'}): '{q}' -> {v['id']} "
              f"({v['w']}x{v['h']}), relevansi={_relevance(q, v):.2f}")
    return credits
