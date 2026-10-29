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
from PIL import Image, ImageDraw, ImageFilter

GEN = "https://gen.pollinations.ai/image/"        # endpoint resmi (pakai key gratis)
LEGACY = "https://image.pollinations.ai/prompt/"  # cadangan tanpa key
W, H = 1024, 1792  # rasio 9:16
GAP = 2           # jeda pendek; layanan yang gagal diputus dengan circuit breaker
REMOTE_BROKEN = False

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
    """Fetch remote image briefly; stop retry storms when provider returns server errors."""
    global REMOTE_BROKEN
    if REMOTE_BROKEN:
        return None
    key = os.environ.get("POLLINATIONS_API_KEY", "").strip()
    model = os.environ.get("POLLINATIONS_MODEL", "").strip() or ("flux" if key else "")
    use_key = bool(key)
    # Keep retries bounded: a provider-side 5xx should not burn minutes per scene.
    for attempt in range(2):
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
            r = requests.get(url, params=params, headers=headers, timeout=(8, 45))
            ctype = r.headers.get("content-type", "").split(";")[0].strip()
            if r.status_code == 200 and ctype.startswith("image/") and len(r.content) > 15000:
                dest = dest_stem.with_suffix(EXT.get(ctype, ".jpg"))
                dest.write_bytes(r.content)
                return dest
            print(f"  respons {r.status_code} ({ctype}, {len(r.content)} byte)")
            if r.status_code >= 500:
                print("  layanan ilustrasi mengembalikan 5xx; aktifkan fallback lokal untuk sisa adegan")
                REMOTE_BROKEN = True
                return None
            if use_key and r.status_code in (401, 402, 403):
                print("  key ditolak/habis -> mencoba endpoint tanpa key")
                use_key = False
                model = ""
            elif r.status_code in (400, 404, 422):
                return None
        except requests.RequestException as e:
            print(f"  gagal: {type(e).__name__}")
            if attempt == 1:
                REMOTE_BROKEN = True
                return None
        time.sleep(2 * (attempt + 1))
    return None


def _local_cinematic_fallback(prompt: str, dest: Path, seed: int) -> Path:
    """Create a polished abstract 9:16 scene card when the remote image API is down.

    It is intentionally labeled in metadata/reporting as a fallback; it does not pretend
    to be a photorealistic depiction of the prompt.
    """
    import hashlib
    import math
    import random as _random

    rng = _random.Random(seed + int(hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:8], 16))
    w, h = 720, 1280
    top = (5, 12, 25)
    bottom = (11, 39, 58)
    im = Image.new("RGB", (w, h))
    pix = im.load()
    for y in range(h):
        t = y / max(1, h - 1)
        wave = 0.5 + 0.5 * math.sin(y / 83.0 + seed % 7)
        col = tuple(int(top[i] * (1-t) + bottom[i] * t + (3 * wave if i == 2 else 0)) for i in range(3))
        for x in range(w):
            glow = max(0, 1 - math.sqrt(((x-w*.52)/(w*.72))**2 + ((y-h*.43)/(h*.55))**2))
            pix[x, y] = tuple(min(255, int(col[i] + glow * (8 if i == 1 else 20 if i == 2 else 1))) for i in range(3))
    haze = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    hd = ImageDraw.Draw(haze)
    accent = (0, 220, 235, 55)
    for _ in range(12):
        x = rng.randint(-100, w)
        y = rng.randint(int(h*.18), int(h*.86))
        rw = rng.randint(80, 260)
        rh = rng.randint(25, 95)
        hd.ellipse((x-rw, y-rh, x+rw, y+rh), fill=(55, 115, 145, rng.randint(5, 18)))
    # abstract focal silhouette and a subtle evidence-frame motif
    cx = rng.randint(int(w*.38), int(w*.62))
    base_y = int(h*.76)
    hd.ellipse((cx-68, base_y-300, cx+68, base_y-164), fill=(2, 5, 12, 245))
    hd.polygon([(cx-120, base_y+100), (cx-80, base_y-190), (cx+80, base_y-190), (cx+120, base_y+100)], fill=(2, 5, 12, 245))
    hd.line((52, 95, 190, 95), fill=accent, width=3)
    hd.line((52, 95, 52, 230), fill=accent, width=3)
    hd.line((w-52, h-95, w-190, h-95), fill=accent, width=3)
    hd.line((w-52, h-95, w-52, h-230), fill=accent, width=3)
    haze = haze.filter(ImageFilter.GaussianBlur(22))
    im = Image.alpha_composite(im.convert("RGBA"), haze)
    draw = ImageDraw.Draw(im)
    draw.line((80, int(h*.86), w-80, int(h*.86)), fill=(0, 220, 235, 95), width=2)
    dest = dest.with_suffix(".png")
    im.convert("RGB").save(dest, "PNG", optimize=True)
    return dest


def generate_all(script, cfg, work: Path):
    """Generate AI images only. Failed scenes are returned to main for footage fallback.

    No local placeholder images are created: the pipeline either uses a real AI image,
    routes the scene to stock footage, or stops with a clear error.
    """
    global REMOTE_BROKEN
    work.mkdir(parents=True, exist_ok=True)
    seed = random.randint(1, 999999)
    failed = []
    REMOTE_BROKEN = False
    for i, sc in enumerate(script["scenes"]):
        if sc["visual"] != "illustration":
            continue
        prompt = build_prompt(script, cfg, sc)
        print(f"Ilustrasi AI adegan {i}: {sc['image_prompt'][:80]}")
        path = _fetch(prompt, seed + i, work / f"img{i:02d}")
        if path:
            sc["image"] = str(path)
            sc["image_fallback"] = False
        else:
            sc.pop("image", None)
            sc["image_fallback"] = False
            failed.append(i)
            print(f"  ! Ilustrasi AI adegan {i} gagal; tidak membuat visual lokal.")
    return failed
