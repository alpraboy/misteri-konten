"""Pengolahan gambar per style (setelah gambar AI diunduh), agar seragam dan sesuai palet:

  vhs         low-res ~240p, blur, chroma bleed, scanline, noise, tint night-vision
  wayang      peta warna 3 tinta: hitam arang #0A0A0A -> merah membara #7A1A1A -> emas pudar #8C6B2F
  conspiracy  foto arsip: hitam-putih berbutir, sepia tipis, flash keras (ditempel di papan oleh board.py)
"""
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter, ImageOps

CHARCOAL = (10, 10, 10)
EMBER = (122, 26, 26)
GOLD = (140, 107, 47)


def _arr(im):
    return np.asarray(im.convert("RGB"), dtype=np.float32)


def _img(a):
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "RGB")


def vhs(im: Image.Image, idx: int = 0, seed: int = 1) -> Image.Image:
    """Rekaman CCTV/HP jadul: 240p -> diperbesar kembali, tinted, bergaris, berbutir."""
    rng = np.random.default_rng(seed + idx)
    w, h = im.size
    small = im.convert("RGB").resize((max(2, w // 4), max(2, h // 4)), Image.BILINEAR)
    small = small.filter(ImageFilter.GaussianBlur(0.8))
    a = _arr(small.resize((w, h), Image.BILINEAR))

    lum = (0.299 * a[..., 0] + 0.587 * a[..., 1] + 0.114 * a[..., 2])
    lum = np.clip((lum - 18) * 1.35, 0, 255)                       # kontras keras, hitam pekat
    if idx % 3 == 1:                                               # adegan night-vision hijau
        out = np.stack([lum * 0.10, lum * 1.0, lum * 0.28], axis=-1)
        out[..., 1] = np.clip(out[..., 1] * 1.05 + 6, 0, 255)
    else:                                                          # putih pucat dingin
        out = np.stack([lum * 0.93, lum * 0.97, lum * 1.0], axis=-1)
        if idx % 3 == 2:                                           # sisipan merah darah di bayangan terang
            out[..., 0] = np.clip(out[..., 0] + (lum / 255.0) ** 3 * 60, 0, 255)
    # chroma bleed: geser kanal merah/biru horizontal
    out[..., 0] = np.roll(out[..., 0], 5, axis=1)
    out[..., 2] = np.roll(out[..., 2], -5, axis=1)
    # scanline + noise + vinyet
    out[::3, :, :] *= 0.80
    out += rng.normal(0, 16, size=(h, w, 1))
    yy, xx = np.mgrid[0:h, 0:w]
    d = np.sqrt(((xx - w / 2) / (w / 2)) ** 2 + ((yy - h / 2) / (h / 2)) ** 2)
    out *= np.clip(1.15 - 0.55 * d ** 1.6, 0.25, 1.0)[..., None]
    return _img(out)


def wayang(im: Image.Image) -> Image.Image:
    """Peta gradien 3 tinta: hitam arang -> merah membara -> emas pudar (tanpa warna lain)."""
    g = ImageOps.autocontrast(ImageOps.grayscale(im), cutoff=1)
    t = np.asarray(g, dtype=np.float32) / 255.0
    t = np.clip((t - 0.05) / 0.9, 0, 1) ** 1.25                    # bayangan lebih pekat
    c0, c1, c2 = (np.array(c, dtype=np.float32) for c in (CHARCOAL, EMBER, GOLD))
    lo = np.clip(t / 0.55, 0, 1)[..., None]
    hi = np.clip((t - 0.55) / 0.45, 0, 1)[..., None]
    out = np.where(t[..., None] < 0.55, c0 + (c1 - c0) * lo, c1 + (c2 - c1) * hi)
    h, w = t.shape
    yy, xx = np.mgrid[0:h, 0:w]
    d = np.sqrt(((xx - w / 2) / (w / 2)) ** 2 + ((yy - h / 2) / (h / 2)) ** 2)
    out *= np.clip(1.10 - 0.45 * d ** 1.8, 0.35, 1.0)[..., None]
    return _img(out)


def evidence(im: Image.Image, seed: int = 3) -> Image.Image:
    """Foto arsip: hitam-putih, sepia tipis, kontras keras, berbutir."""
    rng = np.random.default_rng(seed)
    g = np.asarray(ImageOps.autocontrast(ImageOps.grayscale(im), cutoff=1.5), dtype=np.float32)
    g = np.clip((g - 128) * 1.18 + 128 - 8, 0, 255)
    g = g + rng.normal(0, 11, size=g.shape)
    out = np.stack([g * 1.02, g * 0.93, g * 0.78], axis=-1)        # sepia tipis
    h, w = g.shape
    yy, xx = np.mgrid[0:h, 0:w]
    d = np.sqrt(((xx - w / 2) / (w / 2)) ** 2 + ((yy - h / 2) / (h / 2)) ** 2)
    out *= np.clip(1.08 - 0.40 * d ** 1.7, 0.4, 1.0)[..., None]
    return _img(out)


def process(path: Path, look: str, idx: int = 0, seed: int = 1) -> Path:
    """Baca gambar, terapkan look, simpan sebagai .jpg; kembalikan path baru."""
    im = Image.open(path).convert("RGB")
    if look == "vhs":
        out = vhs(im, idx, seed)
    elif look == "wayang":
        out = wayang(im)
    else:
        out = evidence(im, seed + idx)
    dest = Path(path).with_suffix(".jpg")
    out.save(dest, "JPEG", quality=93)
    return dest
