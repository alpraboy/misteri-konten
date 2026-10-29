"""Agen ilustrasi: komik tinta hitam-putih + satu warna aksen, via Pollinations (tanpa key).

Konsistensi: awalan gaya yang sama di semua adegan, deskripsi tokoh yang sama,
dan seed yang sama dalam satu video.
Batas anonim Pollinations sekitar 1 permintaan / 15 detik, jadi ada jeda.
"""
import os
import random
import time
from pathlib import Path
from urllib.parse import quote

import requests

GEN = "https://gen.pollinations.ai/image/"        # endpoint resmi (pakai key gratis)
LEGACY = "https://image.pollinations.ai/prompt/"  # cadangan tanpa key
W, H = 1024, 1792  # rasio 9:16
GAP = 16          # jeda antar permintaan (detik)

STYLE = (
    "cinematic documentary still blended with refined motion-graphics art direction, "
    "photorealistic atmospheric lighting with subtle graphic-novel texture, controlled contrast, "
    "deep shadows and one restrained {accent} accent on a relevant clue, "
    "clear foreground midground background, one clear focal subject, vertical 9:16 composition, "
    "editorial documentary framing, realistic material detail, no text, no letters, no watermark"
)

EXT = {"image/png": ".png", "image/webp": ".webp"}


def build_prompt(script, cfg, sc):
    parts = [STYLE.format(accent=cfg["style"]["accent_prompt"])]
    if sc.get("with_character") and script.get("character"):
        parts.append(f"main character: {script['character']}")
    parts.append(sc["image_prompt"])
    return ", ".join(parts)[:900]


def _fetch(prompt, seed, dest_stem: Path):
    key = os.environ.get("POLLINATIONS_API_KEY", "").strip()
    model = os.environ.get("POLLINATIONS_MODEL", "").strip() or ("flux" if key else "")
    use_key = bool(key)

    for attempt in range(4):
        params = {"width": W, "height": H, "seed": seed, "nologo": "true"}
        headers = {}
        if use_key:
            url = GEN + quote(prompt, safe="")
            headers["Authorization"] = f"Bearer {key}"
        else:
            url = LEGACY + quote(prompt, safe="")
            params["private"] = "true"
        if model:
            params["model"] = model
        try:
            r = requests.get(url, params=params, headers=headers, timeout=(15, 180))
            ctype = r.headers.get("content-type", "").split(";")[0].strip()
            if r.status_code == 200 and ctype.startswith("image/") and len(r.content) > 15000:
                dest = dest_stem.with_suffix(EXT.get(ctype, ".jpg"))
                dest.write_bytes(r.content)
                return dest
            print(f"  respons {r.status_code} ({ctype}, {len(r.content)} byte): {r.text[:120] if 'text' in ctype or 'json' in ctype else ''}")
            if use_key and r.status_code in (401, 402, 403):
                print("  key ditolak/habis -> pindah ke endpoint tanpa key")
                use_key = False
                model = os.environ.get("POLLINATIONS_MODEL", "").strip()
        except requests.RequestException as e:
            print(f"  gagal: {type(e).__name__}, coba lagi...")
        time.sleep(GAP * (attempt + 1))
    return None


def generate_all(script, cfg, work: Path):
    """Isi sc['image'] untuk adegan ilustrasi. Kembalikan daftar indeks yang gagal."""
    work.mkdir(parents=True, exist_ok=True)
    seed = random.randint(1, 999999)
    failed, first = [], True
    for i, sc in enumerate(script["scenes"]):
        if sc["visual"] != "illustration":
            continue
        if not first:
            time.sleep(GAP)
        first = False
        prompt = build_prompt(script, cfg, sc)
        print(f"Ilustrasi adegan {i}: {sc['image_prompt'][:80]}")
        path = _fetch(prompt, seed, work / f"img{i:02d}")
        if path:
            sc["image"] = str(path)
        else:
            print(f"  ! adegan {i} gagal dibuat")
            failed.append(i)
    return failed
