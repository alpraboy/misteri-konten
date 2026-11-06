"""Agen ilustrasi v7: komik tinta hitam-putih bergaya horor gotik, via Pollinations (cadangan: Cloudflare, Gemini, Hugging Face).

Setiap gambar diproses ulang (grayscale + kontras + duotone 'tinta di kertas tua') supaya
seluruh adegan tampil seragam, dengan sedikit warna aksen dipertahankan bila ada.

Konsistensi: awalan gaya yang sama di semua adegan, deskripsi tokoh yang sama,
dan seed yang sama dalam satu video.
Batas anonim Pollinations sekitar 1 permintaan / 15 detik, jadi ada jeda.
"""
import base64
import colorsys
import io
import math
import os
import random
import time
from pathlib import Path
from urllib.parse import quote

import requests
from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageOps

GEN = "https://gen.pollinations.ai/image/"        # endpoint resmi (pakai key gratis)
LEGACY = "https://image.pollinations.ai/prompt/"  # cadangan tanpa key
W, H = 1024, 1792  # rasio 9:16
GAP = 2           # jeda pendek; layanan yang gagal diputus dengan circuit breaker
REMOTE_BROKEN = False
QUOTA_EXHAUSTED = False   # layanan gambar menolak karena saldo/kuota habis (402/429)

# Cadangan gambar #1: Gemini (memakai GEMINI_API_KEY yang sama dengan naskah & suara).
# Nama model sering berubah; dicoba berurutan, bisa dipaksa lewat env GEMINI_IMAGE_MODEL.
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
GEMINI_MODELS = ["gemini-2.5-flash-image", "gemini-3.1-flash-image-preview"]
GEMINI_BROKEN = False     # Gemini gambar tidak bisa dipakai (kuota/tier/kunci) -> lewati sisa adegan

# Cadangan gambar #2: Cloudflare Workers AI (FLUX schnell; jatah gratis harian). Butuh 2 secret:
# CLOUDFLARE_ACCOUNT_ID dan CLOUDFLARE_API_TOKEN. Bisa ganti model lewat env CLOUDFLARE_IMAGE_MODEL.
CF_URL = "https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/{model}"
CF_MODEL = "@cf/black-forest-labs/flux-1-schnell"
CF_BROKEN = False

# Cadangan gambar #3: Hugging Face (butuh secret HF_TOKEN; kredit gratisnya kecil, jadi dipakai paling akhir).
# Bisa ganti model lewat env HF_IMAGE_MODEL.
HF_MODEL = "black-forest-labs/FLUX.1-schnell"
HF_BROKEN = False

STYLE = (
    "black and white horror ink illustration, gothic graphic novel panel, "
    "heavy black ink, dense crosshatching, woodcut linocut texture, dramatic chiaroscuro, "
    "eerie fog, deep black shadows, high contrast, grayscale, "
    "a faint {accent} glow on one key element only, "
    "one clear focal subject, simple readable composition, vertical 9:16, "
    "no text, no letters, no watermark, not a photograph"
)

EXT = {"image/png": ".png", "image/webp": ".webp"}


def build_prompt(script, cfg, sc):
    """Susun prompt: template style (prefix + isi adegan + suffix). Tanpa 'visual' -> gaya komik lama."""
    v = cfg.get("visual")
    if v:
        core = sc["image_prompt"]
        if sc.get("with_character") and script.get("character"):
            core = f"{core}, featuring {script['character']}"
        return f"{v['prefix']}{core}{v['suffix']}"[:900]
    parts = [STYLE.format(accent=cfg["style"]["accent_prompt"])]
    if sc.get("with_character") and script.get("character"):
        parts.append(f"main character: {script['character']}")
    parts.append(sc["image_prompt"])
    return ", ".join(parts)[:900]


def _fetch(prompt, seed, dest_stem: Path, negative=""):
    """Fetch remote image briefly; stop retry storms when provider returns server errors."""
    global REMOTE_BROKEN, QUOTA_EXHAUSTED
    if REMOTE_BROKEN or QUOTA_EXHAUSTED:
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
        if negative and use_key:  # negative_prompt didukung model flux/zimage di endpoint resmi
            params["negative_prompt"] = negative
        try:
            r = requests.get(url, params=params, headers=headers, timeout=(8, 45))
            ctype = r.headers.get("content-type", "").split(";")[0].strip()
            if r.status_code == 200 and ctype.startswith("image/") and len(r.content) > 15000:
                dest = dest_stem.with_suffix(EXT.get(ctype, ".jpg"))
                dest.write_bytes(r.content)
                return dest
            body = r.text[:140].replace("\n", " ") if ("json" in ctype or "text" in ctype) else ""
            print(f"  respons {r.status_code} ({ctype}, {len(r.content)} byte) {body}")
            if r.status_code in (402, 429) and not use_key:   # tanpa key pun ditolak -> saldo/kuota habis
                QUOTA_EXHAUSTED = True
                print("  saldo/kuota layanan gambar habis; sisa adegan memakai gambar yang sudah jadi (sudut kamera berbeda).")
                return None
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


def _fetch_gemini(prompt, seed, dest_stem: Path, negative=""):
    """Cadangan: buat gambar lewat Gemini. Mengembalikan path file atau None (tanpa melempar error)."""
    global GEMINI_BROKEN
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if GEMINI_BROKEN or not key:
        return None
    text = prompt if not negative else f"{prompt}. Avoid: {negative}"
    body = {
        "contents": [{"parts": [{"text": text[:1800]}]}],
        "generationConfig": {
            "responseModalities": ["IMAGE"],
            "imageConfig": {"aspectRatio": "9:16"},
        },
    }
    forced = os.environ.get("GEMINI_IMAGE_MODEL", "").strip()
    for model in ([forced] if forced else GEMINI_MODELS):
        for attempt in range(2):
            try:
                r = requests.post(GEMINI_URL.format(model=model), json=body,
                                  headers={"x-goog-api-key": key}, timeout=(8, 90))
            except requests.RequestException as e:
                print(f"  Gemini gambar gagal: {type(e).__name__}")
                GEMINI_BROKEN = True
                return None
            if r.status_code == 200:
                try:
                    parts = r.json()["candidates"][0]["content"]["parts"]
                    data = next(p.get("inlineData") or p.get("inline_data") for p in parts
                                if p.get("inlineData") or p.get("inline_data"))
                    raw = base64.b64decode(data["data"])
                    im = Image.open(io.BytesIO(raw)).convert("RGB")
                except (KeyError, IndexError, StopIteration, ValueError, OSError, TypeError):
                    print(f"  Gemini ({model}) tidak mengembalikan gambar (mungkin diblokir filter); adegan ini dilewati")
                    return None   # kemungkinan prompt ditolak filter: model sama tidak perlu dicoba ulang
                print(f"  gambar dibuat oleh Gemini ({model})")
                return _save_fitted(im, dest_stem)
            print(f"  Gemini ({model}) respons {r.status_code} {r.text[:120]!r}")
            if r.status_code == 429 and attempt == 0:
                time.sleep(20)          # batas per-menit: tunggu sebentar lalu coba sekali lagi
                continue
            if r.status_code == 404:    # nama model tidak ada -> coba nama berikutnya
                break
            GEMINI_BROKEN = True        # 429 lagi / 400 / 401 / 403: kuota habis atau tier gratis tak mendukung
            return None
    GEMINI_BROKEN = True
    return None


def _save_fitted(im, dest_stem: Path) -> Path:
    """Paksa gambar ke rasio 9:16 (potong tengah) lalu simpan sebagai PNG."""
    im = ImageOps.fit(im.convert("RGB"), (W, H), method=Image.LANCZOS)
    dest = dest_stem.with_suffix(".png")
    im.save(dest, "PNG")
    return dest


def _fetch_cloudflare(prompt, seed, dest_stem: Path, negative=""):
    """Cadangan: FLUX schnell di Cloudflare Workers AI. Path file atau None (tanpa melempar error)."""
    global CF_BROKEN
    account = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip()
    token = os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()
    if CF_BROKEN or not account or not token:
        return None
    model = os.environ.get("CLOUDFLARE_IMAGE_MODEL", "").strip() or CF_MODEL
    body = {"prompt": prompt[:2000], "steps": 4, "seed": int(seed) % 1000000}
    for attempt in range(2):
        try:
            r = requests.post(CF_URL.format(account=account, model=model), json=body,
                              headers={"Authorization": f"Bearer {token}"}, timeout=(8, 90))
        except requests.RequestException as e:
            print(f"  Cloudflare gambar gagal: {type(e).__name__}")
            CF_BROKEN = True
            return None
        if r.status_code == 200:
            try:
                raw = base64.b64decode(r.json()["result"]["image"])
                im = Image.open(io.BytesIO(raw))
                im.load()
            except (KeyError, TypeError, ValueError, OSError):
                print("  Cloudflare tidak mengembalikan gambar yang valid; adegan ini dilewati")
                return None
            print(f"  gambar dibuat oleh Cloudflare ({model})")
            return _save_fitted(im, dest_stem)
        print(f"  Cloudflare respons {r.status_code} {r.text[:120]!r}")
        if r.status_code >= 500 and attempt == 0:
            time.sleep(3)
            continue
        CF_BROKEN = True     # 401/403 (token), 429 (jatah harian habis), 4xx lain: lewati sisa adegan
        return None
    CF_BROKEN = True
    return None


def _fetch_hf(prompt, seed, dest_stem: Path, negative=""):
    """Cadangan terakhir: Hugging Face Inference Providers. Path file atau None."""
    global HF_BROKEN
    token = os.environ.get("HF_TOKEN", "").strip()
    if HF_BROKEN or not token:
        return None
    model = os.environ.get("HF_IMAGE_MODEL", "").strip() or HF_MODEL
    try:
        from huggingface_hub import InferenceClient   # diimpor di sini agar tidak wajib bila HF_TOKEN kosong
        client = InferenceClient(provider="auto", api_key=token, timeout=90)
        im = client.text_to_image(prompt[:1500], model=model)
        print(f"  gambar dibuat oleh Hugging Face ({model})")
        return _save_fitted(im, dest_stem)
    except Exception as e:   # kuota/kredit habis, model tak tersedia, paket belum terpasang, dsb.
        print(f"  Hugging Face gagal ({type(e).__name__}: {str(e)[:100]}); dilewati")
        HF_BROKEN = True
        return None


def _fetch_any(prompt, seed, dest_stem: Path, negative=""):
    """Rantai penyedia gambar. Urutan: Pollinations > Cloudflare > Gemini > Hugging Face.
    Penyedia yang tidak punya secret otomatis dilewati. Mengembalikan path atau None."""
    for fetch in (_fetch, _fetch_cloudflare, _fetch_gemini, _fetch_hf):
        path = fetch(prompt, seed, dest_stem, negative)
        if path:
            return path
    return None


def _curve(x):
    """Kurva-S yang menggelapkan bayangan: hitam lebih pekat, putih tetap bersih."""
    x = x ** 1.05
    return 0.5 + 0.5 * math.tanh((x - 0.5) * 2.6) / math.tanh(1.3)


def _selective_accent(orig, base, rgb):
    """Pertahankan warna HANYA di area yang berwarna aksen (gaya 'selective color')."""
    hue = colorsys.rgb_to_hsv(*(c / 255 for c in rgb))[0] * 255
    h, s, v = orig.convert("HSV").split()

    def near(val):
        d = abs(val - hue)
        return 255 if min(d, 256 - d) <= 34 else 0

    mh = h.point([near(i) for i in range(256)])
    ms = s.point([255 if i > 120 else 0 for i in range(256)])
    mv = v.point([255 if i > 70 else 0 for i in range(256)])
    mask = ImageChops.multiply(ImageChops.multiply(mh, ms), mv)
    cover = mask.histogram()[255] / float(mask.size[0] * mask.size[1])
    if cover < 0.003 or cover > 0.28:   # tak ada aksen / seluruh gambar berwarna -> hitam-putih murni
        return base
    mask = mask.filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.GaussianBlur(3))
    return Image.composite(ImageEnhance.Color(orig).enhance(1.15), base, mask)


def postprocess(path: Path, cfg, idx: int = 0, seed: int = 1) -> Path:
    """Pasca-proses gambar. Bila cfg punya 'look' (vhs/conspiracy/wayang) pakai looks.py."""
    if cfg.get("look"):
        try:
            import looks
            return looks.process(path, cfg["look"], idx, seed)
        except Exception as e:
            print(f"  look '{cfg['look']}' gagal ({type(e).__name__}: {e}); memakai gambar asli")
            return path
    return _postprocess_ink(path, cfg)


def _postprocess_ink(path: Path, cfg) -> Path:
    """Seragamkan tampilan: grayscale -> kontras -> duotone tinta/kertas (+ aksen selektif)."""
    st = cfg["style"]
    duo = st.get("duotone", {})
    black = tuple(duo.get("black", (6, 5, 8)))
    white = tuple(duo.get("white", (228, 218, 200)))
    try:
        im = Image.open(path).convert("RGB")
        gray = ImageOps.autocontrast(ImageOps.grayscale(im), cutoff=1)
        gray = gray.point([int(255 * _curve(i / 255.0)) for i in range(256)])
        out = ImageOps.colorize(gray, black=black, white=white)
        if st.get("accent_rgb"):
            out = _selective_accent(im, out, st["accent_rgb"])
        dest = path.with_suffix(".jpg")
        out.save(dest, "JPEG", quality=95)
        return dest
    except Exception as e:  # jangan hentikan render hanya karena pasca-proses gagal
        print(f"  pasca-proses gagal ({type(e).__name__}); memakai gambar asli")
        return path


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
    global REMOTE_BROKEN, QUOTA_EXHAUSTED, GEMINI_BROKEN, CF_BROKEN, HF_BROKEN
    work.mkdir(parents=True, exist_ok=True)
    seed = random.randint(1, 999999)
    failed = []
    REMOTE_BROKEN = False
    QUOTA_EXHAUSTED = False
    GEMINI_BROKEN = False
    CF_BROKEN = False
    HF_BROKEN = False
    for i, sc in enumerate(script["scenes"]):
        if sc["visual"] != "illustration":
            continue
        prompt = build_prompt(script, cfg, sc)
        print(f"Ilustrasi AI adegan {i}: {sc['image_prompt'][:80]}")
        path = _fetch_any(prompt, seed + i, work / f"img{i:02d}", cfg.get("visual", {}).get("negative", ""))
        if path:
            path = postprocess(path, cfg, i, seed)
            sc["image"] = str(path)
            sc["image_fallback"] = False
        else:
            sc.pop("image", None)
            sc["image_fallback"] = False
            failed.append(i)
            print(f"  ! Ilustrasi AI adegan {i} gagal; tidak membuat visual lokal.")
    return failed


def reuse_nearest(script, indices):
    """Adegan yang gambarnya gagal memakai ulang gambar adegan terdekat, dengan bidikan pembuka yang lebih dekat
    (peran 'evidence' -> close_top) agar tidak terlihat sama persis. Berhenti bila TIDAK ada satu pun gambar."""
    scenes = script["scenes"]
    have = [i for i, sc in enumerate(scenes) if sc.get("image")]
    if not have:
        raise RuntimeError(
            "Semua ilustrasi AI gagal dibuat (semua penyedia gambar gagal; kemungkinan kuota habis). "
            "Periksa pollen di enter.pollinations.ai serta kuota Cloudflare/Gemini, atau jalankan ulang nanti."
        )
    for i in indices:
        donor = min(have, key=lambda k: (abs(k - i), k > i))
        sc = scenes[i]
        sc["image"] = scenes[donor]["image"]
        sc["visual"] = "illustration"
        sc["image_reused_from"] = donor
        sc["visual_role"] = "evidence"
        print(f"Adegan {i}: gambar adegan {donor} dipakai ulang (gambar baru gagal dibuat).")
