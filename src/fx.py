"""Efek motion comic yang dibuat sepenuhnya oleh kode (tanpa aset eksternal):
- overlay bingkai panel + halftone (statis)
- garis kecepatan (2 varian yang berkedip bergantian)
- efek suara: whoosh dan hantaman (hit), disintesis lalu dijadwalkan sesuai timeline
"""
import array
import math
import random
import wave
from pathlib import Path

W, H = 1080, 1920
SR = 44100


# ---------------------------------------------------------------- overlay gambar
def _frame_and_halftone(path):
    from PIL import Image, ImageDraw

    # Halftone: titik hitam makin besar ke arah tepi (efek cetak komik + vignette)
    half = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(half)
    step = 20
    for y in range(0, H, step):
        for x in range(0, W, step):
            dx = (x - W / 2) / (W / 2)
            dy = (y - H / 2) / (H / 2)
            dist = min(math.sqrt(dx * dx + dy * dy) / 1.25, 1.0)
            r = 0.6 + 6.2 * (dist ** 2.2)
            if r > 1.0:
                d.ellipse((x - r, y - r, x + r, y + r), fill=(0, 0, 0, 120))

    # Bingkai panel hitam dengan tepi dalam sedikit tidak rata (digambar tangan)
    mask = Image.new("L", (W, H), 255)
    md = ImageDraw.Draw(mask)
    b, rnd = 26, random.Random(7)
    pts = []
    for x in range(b, W - b + 1, 90):
        pts.append((x, b + rnd.randint(-4, 4)))
    for y in range(b, H - b + 1, 90):
        pts.append((W - b + rnd.randint(-4, 4), y))
    for x in range(W - b, b - 1, -90):
        pts.append((x, H - b + rnd.randint(-4, 4)))
    for y in range(H - b, b - 1, -90):
        pts.append((b + rnd.randint(-4, 4), y))
    md.polygon(pts, fill=0)
    frame = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    frame.putalpha(mask)

    Image.alpha_composite(half, frame).save(path)


def _speed_lines(path, seed):
    from PIL import Image, ImageDraw

    rnd = random.Random(seed)
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx, cy = W / 2, H / 2 - 80
    for _ in range(110):
        a = rnd.uniform(0, 2 * math.pi)
        wdt = rnd.uniform(0.004, 0.017)
        r_in = rnd.uniform(430, 780)
        r_out = 1700
        inner = (cx + r_in * math.cos(a), cy + r_in * math.sin(a))
        left = (cx + r_out * math.cos(a - wdt), cy + r_out * math.sin(a - wdt))
        right = (cx + r_out * math.cos(a + wdt), cy + r_out * math.sin(a + wdt))
        d.polygon([inner, left, right], fill=(255, 255, 255, 150))
    img.save(path)


def make_overlays(work: Path):
    work.mkdir(parents=True, exist_ok=True)
    paths = {
        "overlay": work / "overlay.png",
        "speed_a": work / "speed_a.png",
        "speed_b": work / "speed_b.png",
    }
    _frame_and_halftone(paths["overlay"])
    _speed_lines(paths["speed_a"], 11)
    _speed_lines(paths["speed_b"], 29)
    return {k: str(v.resolve()) for k, v in paths.items()}


# ---------------------------------------------------------------- efek suara
def _hit():
    rnd = random.Random(3)
    out = []
    for i in range(int(SR * 0.55)):
        t = i / SR
        f = 48 + 90 * math.exp(-t * 30)
        s = 0.95 * math.sin(2 * math.pi * f * t) * math.exp(-t * 7)
        s += 0.45 * (rnd.random() * 2 - 1) * math.exp(-t * 45)
        out.append(s)
    return out


def _whoosh(dur=0.5):
    rnd = random.Random(5)
    n = int(SR * dur)
    lp, out = 0.0, []
    for i in range(n):
        t = i / n
        env = math.sin(math.pi * t) ** 2
        a = 0.04 + 0.5 * t          # filter makin terang -> kesan melesat
        x = rnd.random() * 2 - 1
        lp += a * (x - lp)
        out.append(0.55 * env * (x * 0.25 * t + lp))
    return out


def build_sfx(events, total, path: Path):
    """events: list of (jenis, detik, volume). Tulis WAV stereo 44.1 kHz sepanjang video."""
    samples = {"hit": _hit(), "whoosh": _whoosh()}
    n = int((total + 1.0) * SR)
    buf = [0.0] * n
    for kind, t, vol in events:
        start = int(max(t, 0) * SR)
        for i, v in enumerate(samples.get(kind, samples["hit"])):
            if start + i >= n:
                break
            buf[start + i] += v * vol
    pcm = array.array("h")
    for x in buf:
        v = int(max(-1.0, min(1.0, x)) * 30000)
        pcm.append(v)
        pcm.append(v)  # stereo
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    return str(Path(path).resolve())
