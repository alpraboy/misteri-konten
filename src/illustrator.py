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

BASE = "https://image.pollinations.ai/prompt/"
W, H = 768, 1344  # rasio 9:16, nanti di-upscale oleh editor
GAP = 16          # jeda antar permintaan (detik)

STYLE = (
    "black and white ink comic illustration, graphic novel panel, bold brush ink linework, "
    "heavy cross-hatching, high contrast chiaroscuro, grainy paper texture, "
    "monochrome with a single {accent} color accent on one key element, "
    "vertical composition, no text, no letters, no watermark"
)

EXT = {"image/png": ".png", "image/webp": ".webp"}


def build_prompt(script, cfg, sc):
    parts = [STYLE.format(accent=cfg["style"]["accent_prompt"])]
    if sc.get("with_character") and script.get("character"):
        parts.append(f"main character: {script['character']}")
    parts.append(sc["image_prompt"])
    return ", ".join(parts)[:900]


def _fetch(prompt, seed, dest_stem: Path):
    params = {"width": W, "height": H, "seed": seed, "nologo": "true", "private": "true"}
    model = os.environ.get("POLLINATIONS_MODEL", "").strip()
    if model:
        params["model"] = model
    headers = {}
    key = os.environ.get("POLLINATIONS_API_KEY", "").strip()
    if key:
        headers["Authorization"] = f"Bearer {key}"

    for attempt in range(4):
        try:
            r = requests.get(
                BASE + quote(prompt, safe=""), params=params, headers=headers,
                timeout=(15, 150),
            )
            ctype = r.headers.get("content-type", "").split(";")[0].strip()
            if r.status_code == 200 and ctype.startswith("image/") and len(r.content) > 15000:
                dest = dest_stem.with_suffix(EXT.get(ctype, ".jpg"))
                dest.write_bytes(r.content)
                return dest
            print(f"  respons {r.status_code} ({ctype}, {len(r.content)} byte), coba lagi...")
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
