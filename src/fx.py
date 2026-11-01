"""Efek horor-mistis yang dibuat sepenuhnya oleh kode (tanpa aset eksternal):
- overlay bergerak: kabut (2 lapis), debu, bara, hujan, cahaya aksen, bingkai panel
- suara: dengung (drone) + angin sebagai latar, whoosh, hantaman, riser, detak jantung
"""
import array
import math
import random
import wave
from pathlib import Path

W, H = 1080, 1920
SR = 24000  # cukup untuk dengung/angin/hantaman; ffmpeg yang mengubahnya ke 44.1 kHz


# ================================================================ overlay gambar
def _periodic_noise(cw, ch, seed, blur=8):
    """Noise lembut selebar W yang menyambung mulus bila diulang horizontal."""
    from PIL import Image, ImageFilter

    rnd = random.Random(seed)
    small = Image.new("L", (cw, ch))
    small.putdata([rnd.randint(0, 255) for _ in range(cw * ch)])
    tile = Image.new("L", (cw * 3, ch))
    for k in range(3):
        tile.paste(small, (k * cw, 0))
    wide = tile.resize((W * 3, H), Image.BICUBIC).filter(ImageFilter.GaussianBlur(blur))
    return wide.crop((W, 0, 2 * W, H))


def _fog(path, seed, alpha_max, color):
    from PIL import Image, ImageChops, ImageOps

    acc = None
    for n, (cw, ch, wgt) in enumerate([(5, 9, 0.55), (10, 18, 0.30), (20, 36, 0.15)]):
        layer = _periodic_noise(cw, ch, seed + n).point(lambda v, w=wgt: int(v * w))
        acc = layer if acc is None else ImageChops.add(acc, layer)
    acc = ImageOps.autocontrast(acc, cutoff=3)
    alpha = acc.point(lambda v: int(max(0, v - 100) * alpha_max * 255 / 155))
    tile = Image.new("RGBA", (W, H), tuple(color) + (0,))
    tile.putalpha(alpha)
    wide = Image.new("RGBA", (W * 2, H), (0, 0, 0, 0))  # 2 salinan -> bisa digeser mulus
    wide.paste(tile, (0, 0))
    wide.paste(tile, (W, 0))
    wide.save(path)


def _particles(path, seed, count, rmin, rmax, color, alpha_rng, blur):
    from PIL import Image, ImageDraw, ImageFilter

    rnd = random.Random(seed)
    img = Image.new("RGBA", (W, H * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for _ in range(count):
        x, y = rnd.uniform(0, W), rnd.uniform(0, H)
        r, a = rnd.uniform(rmin, rmax), rnd.randint(*alpha_rng)
        for yy in (y, y + H):  # 2 salinan vertikal -> bisa digeser mulus
            d.ellipse((x - r, yy - r, x + r, yy + r), fill=tuple(color) + (a,))
    img.filter(ImageFilter.GaussianBlur(blur)).save(path)


def _rain(path, seed):
    from PIL import Image, ImageDraw

    rnd = random.Random(seed)
    img = Image.new("RGBA", (W, H * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for _ in range(190):
        x, y = rnd.uniform(-60, W), rnd.uniform(0, H)
        length, a = rnd.uniform(50, 120), rnd.randint(40, 115)
        for yy in (y, y + H):
            d.line((x, yy, x + length * 0.18, yy + length), fill=(215, 222, 235, a), width=rnd.choice((1, 2)))
    img.save(path)


def _glow(path, rgb):
    """Cahaya aksen lembut di tepi bawah/atas layar (aksen warna pada gambar hitam-putih)."""
    from PIL import Image

    sw, sh = 135, 240
    img = Image.new("RGBA", (sw, sh))
    vig = Image.new("RGBA", (sw, sh))
    px = img.load()
    vx = vig.load()
    for y in range(sh):
        for x in range(sw):
            dx, dy = (x / (sw - 1) - 0.5) * 2, (y / (sh - 1) - 0.5) * 2
            vx[x, y] = (0, 0, 0, int(min(215, 190 * (min((dx * dx + dy * dy) / 2.0, 1.0) ** 1.3))))
            t = y / (sh - 1)
            bottom = 62 * (t ** 3.4)
            top = 18 * ((1 - t) ** 4)
            side = 14 * (abs(x / (sw - 1) - 0.5) * 2) ** 3
            px[x, y] = (rgb[0], rgb[1], rgb[2], int(min(90, bottom + top + side)))
    Image.alpha_composite(vig, img).resize((W, H), Image.LANCZOS).save(path)


def _frame(path):
    """Bingkai panel buku cerita: tepi hitam tipis tidak rata + halftone ringan di sudut."""
    from PIL import Image, ImageDraw

    half = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(half)
    step = 22
    for y in range(0, H, step):
        for x in range(0, W, step):
            dx, dy = (x - W / 2) / (W / 2), (y - H / 2) / (H / 2)
            dist = min(math.sqrt(dx * dx + dy * dy) / 1.25, 1.0)
            r = 0.4 + 5.0 * (dist ** 2.6)
            if r > 1.2:
                d.ellipse((x - r, y - r, x + r, y + r), fill=(0, 0, 0, 90))

    mask = Image.new("L", (W, H), 255)
    md = ImageDraw.Draw(mask)
    b, rnd = 20, random.Random(7)
    pts = []
    for x in range(b, W - b + 1, 90):
        pts.append((x, b + rnd.randint(-3, 3)))
    for y in range(b, H - b + 1, 90):
        pts.append((W - b + rnd.randint(-3, 3), y))
    for x in range(W - b, b - 1, -90):
        pts.append((x, H - b + rnd.randint(-3, 3)))
    for y in range(H - b, b - 1, -90):
        pts.append((b + rnd.randint(-3, 3), y))
    md.polygon(pts, fill=0)
    frame = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    frame.putalpha(mask)
    Image.alpha_composite(half, frame).save(path)


def _scanlines(path):
    import numpy as np
    from PIL import Image

    a = np.zeros((H, W, 4), dtype=np.uint8)
    a[::4, :, 3] = 62
    a[1::4, :, 3] = 34
    Image.fromarray(a, "RGBA").save(path)


def _tracking(path, seed):
    """Pita 'tracking rusak' VHS: pita noise horizontal + garis putus-putus, bisa digulir vertikal."""
    import numpy as np
    from PIL import Image

    rng = np.random.default_rng(seed)
    a = np.zeros((H * 2, W, 4), dtype=np.uint8)
    for _ in range(9):
        y = int(rng.integers(0, H - 60))
        hh = int(rng.integers(4, 26))
        noise = (rng.random((hh, W)) > 0.42) * rng.integers(70, 210, size=(hh, W))
        shift = int(rng.integers(-30, 30))
        noise = np.roll(noise, shift, axis=1)
        for yy in (y, y + H):
            a[yy:yy + hh, :, 0:3] = 235
            a[yy:yy + hh, :, 3] = noise.astype(np.uint8)
    for _ in range(26):  # dropout: garis putus pendek
        y, x, ln = int(rng.integers(0, H)), int(rng.integers(0, W - 200)), int(rng.integers(40, 260))
        for yy in (y, y + H):
            a[yy:yy + 2, x:x + ln, 0:3] = 255
            a[yy:yy + 2, x:x + ln, 3] = 150
    Image.fromarray(a, "RGBA").save(path)


def _lamp(path):
    """Topeng cahaya lampu gantung: gelap di luar, hangat kuning di tengah (digoyang oleh overlay)."""
    import numpy as np
    from PIL import Image

    sw, sh = 270, 240                                  # skala 1/8 dari 2160x1920
    yy, xx = np.mgrid[0:sh, 0:sw]
    d = np.sqrt(((xx - sw / 2) / (sw * 0.30)) ** 2 + ((yy - sh * 0.46) / (sh * 0.50)) ** 2)
    t = np.clip(d, 0, 1.6) / 1.6
    alpha = (28 + 190 * np.clip(t ** 1.15, 0, 1)).astype(np.uint8)
    warm = np.array([255, 205, 95], dtype=np.float32)
    col = (warm[None, None, :] * (1 - t[..., None])).astype(np.uint8)
    img = Image.fromarray(np.dstack([col, alpha]), "RGBA").resize((W * 2, H), Image.BILINEAR)
    img.save(path)


def _smoke(path, seed, alpha_max, color):
    """Asap kemenyan: noise lembut yang menyambung vertikal (digulir ke atas)."""
    from PIL import Image, ImageChops, ImageFilter, ImageOps

    acc = None
    for n, (cw, ch, wgt) in enumerate([(5, 8, 0.6), (9, 15, 0.4)]):
        rnd = random.Random(seed + n)
        small = Image.new("L", (cw, ch))
        small.putdata([rnd.randint(0, 255) for _ in range(cw * ch)])
        tile = Image.new("L", (cw, ch * 3))
        for k in range(3):
            tile.paste(small, (0, k * ch))
        big = tile.resize((W, H * 3), Image.BICUBIC).filter(ImageFilter.GaussianBlur(14)).crop((0, H, W, 2 * H))
        big = big.point(lambda v, w=wgt: int(v * w))
        acc = big if acc is None else ImageChops.add(acc, big)
    acc = ImageOps.autocontrast(acc, cutoff=3)
    alpha = acc.point(lambda v: int(max(0, v - 95) * alpha_max * 255 / 160))
    tile = Image.new("RGBA", (W, H), tuple(color) + (0,))
    tile.putalpha(alpha)
    tall = Image.new("RGBA", (W, H * 2), (0, 0, 0, 0))
    tall.paste(tile, (0, 0))
    tall.paste(tile, (0, H))
    tall.save(path)


def _batik(path):
    """Pola kawung samar (lingkaran saling bertumpuk) sebagai tekstur batik."""
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    step, r = 120, 60
    for gy in range(0, H + step, step):
        for gx in range(0, W + step, step):
            for dx, dy in ((0, -r // 2), (0, r // 2), (-r // 2, 0), (r // 2, 0)):
                d.ellipse((gx + dx - r // 2, gy + dy - r // 2, gx + dx + r // 2, gy + dy + r // 2),
                          outline=(0, 0, 0, 62), width=3)
    img.save(path)



def make_overlays(work: Path, cfg):
    """Buat hanya overlay yang dipakai style terpilih (hemat waktu)."""
    work.mkdir(parents=True, exist_ok=True)
    look = cfg.get("look", "ink")
    rgb = tuple(cfg["style"].get("accent_rgb", (220, 40, 60)))
    names = {
        "vhs": ("scan", "tracking"),
        "conspiracy": ("lamp", "haze", "dust"),
        "wayang": ("smoke", "dust", "batik"),
    }.get(look, ("fog_a", "fog_b", "dust", "embers", "rain", "glow", "frame"))
    p = {k: work / f"{k}.png" for k in names}
    if "scan" in p:
        _scanlines(p["scan"])
    if "tracking" in p:
        _tracking(p["tracking"], 77)
    if "lamp" in p:
        _lamp(p["lamp"])
    if "haze" in p:
        _fog(p["haze"], 606, 0.20, (200, 182, 150))
    if "smoke" in p:
        _smoke(p["smoke"], 707, 0.22, (205, 170, 112))
    if "batik" in p:
        _batik(p["batik"])
    if "dust" in p:
        gold = look == "wayang"
        _particles(p["dust"], 303, 150 if gold else 170, 0.8, 3.0 if gold else 3.2,
                   (170, 132, 66) if gold else (232, 232, 236), (60, 170), 0.8)
    if "fog_a" in p:   # gaya komik lama
        _fog(p["fog_a"], 101, 0.30, (178, 184, 196))
        _fog(p["fog_b"], 202, 0.18, (150, 156, 170))
        _particles(p["embers"], 404, 70, 1.6, 4.6, rgb, (110, 230), 1.6)
        _rain(p["rain"], 505)
        _glow(p["glow"], rgb)
        _frame(p["frame"])
    return {k: str(v.resolve()) for k, v in p.items()}


# ================================================================ suara
def _hit():
    rnd, out = random.Random(3), []
    for i in range(int(SR * 0.6)):
        t = i / SR
        f = 44 + 80 * math.exp(-t * 28)
        s = 0.95 * math.sin(2 * math.pi * f * t) * math.exp(-t * 6.5)
        s += 0.35 * (rnd.random() * 2 - 1) * math.exp(-t * 40)
        out.append(s)
    return out


def _thump():
    out = []
    for i in range(int(SR * 0.35)):
        t = i / SR
        out.append(math.sin(2 * math.pi * (46 + 30 * math.exp(-t * 30)) * t) * math.exp(-t * 14))
    return out


def _whoosh(dur=0.55):
    rnd, n, lp, out = random.Random(5), int(SR * dur), 0.0, []
    for i in range(n):
        t = i / n
        env = math.sin(math.pi * t) ** 2
        lp += (0.03 + 0.45 * t) * ((rnd.random() * 2 - 1) - lp)
        out.append(0.6 * env * lp)
    return out


def _riser(dur=1.3):
    rnd, n, lp, out = random.Random(9), int(SR * dur), 0.0, []
    for i in range(n):
        t = i / n
        lp += (0.02 + 0.5 * t) * ((rnd.random() * 2 - 1) - lp)
        out.append(0.9 * (t ** 2.2) * lp + 0.25 * (t ** 2.5) * math.sin(2 * math.pi * (60 + 140 * t) * (i / SR)))
    return out


def _bed(total, drone_hz, wind, hiss=0.0):
    """Dengung rendah yang bergelombang pelan + angin (noise tersaring) + desis (VHS)."""
    n, rnd, lp, hs = int((total + 1.0) * SR), random.Random(1), 0.0, 0.0
    f1, f2, f3 = drone_hz, drone_hz * 1.5, drone_hz * 2.01
    tp = 2 * math.pi
    out = array.array("f")
    for i in range(n):
        t = i / SR
        swell = 0.55 + 0.45 * (0.5 + 0.5 * math.sin(tp * 0.06 * t))
        s = (0.50 * math.sin(tp * f1 * t)
             + 0.28 * math.sin(tp * f2 * t + 0.8 * math.sin(tp * 0.11 * t))
             + 0.18 * math.sin(tp * f3 * t)) * swell
        lp += 0.015 * ((rnd.random() * 2 - 1) - lp)
        gust = 0.4 + 0.6 * (0.5 + 0.5 * math.sin(tp * 0.13 * t + 1.7))
        v = 0.13 * s + wind * 0.45 * lp * gust
        if hiss:
            hs += 0.55 * ((rnd.random() * 2 - 1) - hs)
            v += hiss * hs
        out.append(v)
    return out


# ---- sampel tambahan untuk 3 style
def _step():
    rnd, out = random.Random(11), []
    for i in range(int(SR * 0.28)):
        t = i / SR
        out.append(0.9 * math.sin(2 * math.pi * 72 * t) * math.exp(-t * 22) + 0.25 * (rnd.random() * 2 - 1) * math.exp(-t * 60))
    return out


def _breath():
    rnd, n, lp, out = random.Random(13), int(SR * 1.7), 0.0, []
    for i in range(n):
        t = i / n
        env = math.sin(math.pi * t) ** 1.6
        lp += 0.12 * ((rnd.random() * 2 - 1) - lp)
        out.append(0.55 * env * lp)
    return out


def _wail():
    out, n = [], int(SR * 1.9)
    for i in range(n):
        t = i / n
        f = 380 + 95 * t + 9 * math.sin(2 * math.pi * 6 * (i / SR))
        env = math.sin(math.pi * t) ** 2
        out.append(0.5 * env * (math.sin(2 * math.pi * f * (i / SR)) + 0.3 * math.sin(4 * math.pi * f * (i / SR))))
    return out


def _glitch():
    rnd, out, hold, v = random.Random(17), [], 0, 0.0
    for i in range(int(SR * 0.22)):
        if hold <= 0:
            v, hold = rnd.random() * 2 - 1, rnd.randint(1, 6)
        hold -= 1
        out.append(0.55 * v * (1.0 if (i // 800) % 2 == 0 else 0.5))
    return out


def _tick():
    rnd, out = random.Random(19), []
    for i in range(int(SR * 0.07)):
        t = i / SR
        out.append(0.8 * math.sin(2 * math.pi * 1700 * t) * math.exp(-t * 90) + 0.3 * (rnd.random() * 2 - 1) * math.exp(-t * 140))
    return out


def _rustle():
    rnd, n, prev, out = random.Random(23), int(SR * 0.5), 0.0, []
    for i in range(n):
        t = i / n
        x = rnd.random() * 2 - 1
        out.append(0.6 * (x - prev) * (math.sin(math.pi * t) ** 1.5) * (0.6 + 0.4 * math.sin(i * 0.02)))
        prev = x
    return out


def _bell(freq, dur=1.8):
    out, tp = [], 2 * math.pi
    for i in range(int(SR * dur)):
        t = i / SR
        out.append(0.5 * math.exp(-t * 2.4) * (math.sin(tp * freq * t) + 0.45 * math.sin(tp * freq * 2.76 * t)
                                                 + 0.25 * math.sin(tp * freq * 5.4 * t)))
    return out


def _gong(dur=5.0):
    out, tp = [], 2 * math.pi
    for i in range(int(SR * dur)):
        t = i / SR
        env = math.exp(-t * 0.85) * min(1.0, t * 60)
        out.append(0.75 * env * (math.sin(tp * 55 * t + 1.4 * math.sin(tp * 0.8 * t)) + 0.5 * math.sin(tp * 82.5 * t)
                                  + 0.3 * math.sin(tp * 134 * t) + 0.18 * math.sin(tp * 231 * t)))
    return out


def _crackle():
    rnd, out = random.Random(29), []
    for i in range(int(SR * 0.012)):
        out.append(0.7 * (rnd.random() * 2 - 1) * math.exp(-i / (SR * 0.003)))
    return out


def ambient_events(look, total):
    """Jadwal suara latar khas tiap style (deterministik)."""
    rnd, ev = random.Random(5), []
    if look == "vhs":
        t = 1.2
        while t < total:
            ev.append(("step", t, 0.33))               # langkah kaki jauh yang lambat
            t += rnd.uniform(1.25, 1.7)
        t = 2.0
        while t < total:
            ev.append(("breath", t, 0.30))             # napas berat POV
            t += rnd.uniform(3.2, 4.0)
        t = rnd.uniform(7, 11)
        while t < total - 3:
            ev.append(("wail", t, 0.16))               # tangisan samar
            t += rnd.uniform(12, 18)
    elif look == "conspiracy":
        t = 0.5
        while t < total:
            ev.append(("tick", t, 0.30))               # detak jam
            t += 1.0
    elif look == "wayang":
        notes = ["bell0", "bell1", "bell2", "bell3", "bell4"]
        t = 1.0
        while t < total:
            ev.append((rnd.choice(notes), t, 0.20))    # gamelan sumbang
            t += rnd.uniform(1.4, 2.8)
        t = 3.0
        while t < total:
            ev.append(("gong", t, 0.30))               # gong jauh
            t += rnd.uniform(8, 11)
        for _ in range(int(total * 3.2)):
            ev.append(("crackle", rnd.uniform(0, total), rnd.uniform(0.08, 0.2)))   # kemenyan berderak
    return ev


def build_audio(events, total, path: Path, cfg):
    """events: list (jenis, detik, volume). Tulis WAV stereo: latar + suara ambient style + efek terjadwal."""
    amb = cfg["style"].get("ambience", {})
    look = cfg.get("look", "ink")
    buf = _bed(total, amb.get("drone_hz", 50), amb.get("wind", 0.5), hiss=0.05 if look == "vhs" else 0.0)
    n = len(buf)
    rnd = random.Random(31)
    lib = {"hit": _hit(), "thump": _thump(), "whoosh": _whoosh(), "riser": _riser(), "step": _step(),
           "breath": _breath(), "wail": _wail(), "glitch": _glitch(), "tick": _tick(), "rustle": _rustle(),
           "gong": _gong(), "crackle": _crackle()}
    for k in range(5):  # gamelan out of tune: nada slendro-ish digeser acak
        lib[f"bell{k}"] = _bell(220 * [1.0, 1.12, 1.31, 1.50, 1.74][k] * (1 + rnd.uniform(-0.035, 0.035)))
    for kind, t, vol in list(events) + ambient_events(look, total):
        start = int(max(t, 0) * SR)
        for i, v in enumerate(lib.get(kind, lib["hit"])):
            if start + i >= n:
                break
            buf[start + i] += v * vol
    pcm = array.array("h")
    for x in buf:
        v = int(max(-1.0, min(1.0, x)) * 30000)
        pcm.append(v)
        pcm.append(v)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    return str(Path(path).resolve())
