"""Papan gabus investigasi (MYSTERY_CONSPIRACY).

Tiap adegan = satu barang bukti (foto arsip) yang ditempel di papan gabus besar dengan pin
dan benang merah dari barang bukti sebelumnya. Hasil per adegan adalah potongan papan yang
memuat barang bukti sebelumnya dan yang baru, sehingga kamera 'mengikuti benang'.
"""
import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

BOARD_RED = (178, 34, 34)
KRAFT = (193, 154, 107)
FONT_MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"
OUT_W, OUT_H = 1024, 1792


def _font(size):
    try:
        return ImageFont.truetype(FONT_MONO, size)
    except Exception:
        return ImageFont.load_default()


def _cork(w, h, seed=5):
    """Papan gabus: warna kraft berbintik + bercak gelap + bingkai kayu tua."""
    rnd = random.Random(seed)
    base = Image.new("RGB", (w, h), KRAFT)
    px = Image.effect_noise((w // 4, h // 4), 70).resize((w, h), Image.BICUBIC).convert("L")
    base = Image.blend(base, Image.merge("RGB", (px, px, px)).point(lambda v: int(v * 0.62)), 0.30)
    d = ImageDraw.Draw(base)
    for _ in range(int(w * h / 3500)):
        x, y, r = rnd.randint(0, w), rnd.randint(0, h), rnd.randint(1, 4)
        c = rnd.choice(((120, 84, 50), (214, 176, 128), (92, 62, 36)))
        d.ellipse((x - r, y - r, x + r, y + r), fill=c)
    d.rectangle((0, 0, w - 1, h - 1), outline=(58, 36, 20), width=70)       # bingkai kayu
    return base.filter(ImageFilter.GaussianBlur(0.6))


def _polaroid(photo, caption, rnd):
    pw, ph = 540, 680
    photo = photo.convert("RGB").resize((pw, ph), Image.LANCZOS)
    card = Image.new("RGB", (pw + 56, ph + 56 + 96), (236, 230, 214))
    card.paste(photo, (28, 28))
    d = ImageDraw.Draw(card)
    d.text((34, ph + 52), caption[:22], font=_font(34), fill=(40, 34, 28))
    card = card.convert("RGBA")
    card = card.rotate(rnd.uniform(-5.5, 5.5), expand=True, resample=Image.BICUBIC)
    return card


def _shadowed_paste(board, item, cx, cy):
    """Tempel RGBA di tengah (cx,cy) dengan bayangan jatuh."""
    w, h = item.size
    x, y = int(cx - w / 2), int(cy - h / 2)
    shadow = Image.new("RGBA", (w + 60, h + 60), (0, 0, 0, 0))
    alpha = item.split()[3].point(lambda v: int(v * 0.55))
    shadow.paste((0, 0, 0, 255), (30, 30), alpha)
    shadow = shadow.filter(ImageFilter.GaussianBlur(14))
    board.alpha_composite(shadow, (max(0, x - 30 + 14), max(0, y - 30 + 22)))
    board.alpha_composite(item, (max(0, x), max(0, y)))
    return (x, y, w, h)


def _pin(board, x, y):
    d = ImageDraw.Draw(board)
    d.ellipse((x - 17, y - 11, x + 21, y + 27), fill=(0, 0, 0, 90))
    d.ellipse((x - 16, y - 16, x + 16, y + 16), fill=(150, 20, 20, 255))
    d.ellipse((x - 9, y - 11, x + 1, y - 2), fill=(255, 150, 140, 255))


def _thread(board, a, b):
    """Benang merah melengkung ringan dari pin a ke pin b (dengan bayangan)."""
    (x0, y0), (x1, y1) = a, b
    mx, my = (x0 + x1) / 2, (y0 + y1) / 2 + 70
    pts = []
    for k in range(41):
        t = k / 40
        pts.append(((1 - t) ** 2 * x0 + 2 * (1 - t) * t * mx + t * t * x1,
                    (1 - t) ** 2 * y0 + 2 * (1 - t) * t * my + t * t * y1))
    d = ImageDraw.Draw(board)
    d.line([(x + 7, y + 11) for x, y in pts], fill=(0, 0, 0, 80), width=8)
    d.line(pts, fill=BOARD_RED + (255,), width=7)
    d.line([(x - 1, y - 2) for x, y in pts], fill=(225, 90, 80, 150), width=2)


def _note(board, text, cx, cy, rnd):
    """Kertas catatan kuning dengan kata kunci ketikan mesin tik."""
    w, h = 330, 190
    note = Image.new("RGBA", (w, h), (232, 214, 150, 255))
    d = ImageDraw.Draw(note)
    d.text((22, 62), text.upper()[:14], font=_font(42), fill=(58, 30, 24))
    d.line((22, 128, w - 22, 128), fill=(150, 130, 90, 255), width=2)
    note = note.rotate(rnd.uniform(-9, 9), expand=True, resample=Image.BICUBIC)
    _shadowed_paste(board, note, cx, cy)


def compose(script, cfg, work: Path):
    """Ganti sc['image'] dengan potongan papan per adegan; isi sc['board_focus']."""
    work.mkdir(parents=True, exist_ok=True)
    scenes = [sc for sc in script["scenes"] if sc.get("image")]
    n = len(scenes)
    if n == 0:
        return
    rnd = random.Random(21)
    STEP = 780
    CW, CH = 2500, STEP * n + 1300
    board = _cork(CW, CH).convert("RGBA")
    pos = []
    for i in range(n):   # zig-zag ke bawah: kiri-kanan bergantian -> potongan 9:16 pas memuat dua barang bukti
        x = CW * (0.38 if i % 2 == 0 else 0.62) + rnd.uniform(-40, 40)
        pos.append((x, 700 + i * STEP + rnd.uniform(-30, 30)))

    for i, sc in enumerate(scenes):
        cx, cy = pos[i]
        photo = Image.open(sc["image"])
        cap = (sc.get("onscreen") or f"FIG. {i + 1:02d}").upper()
        pol = _polaroid(photo, cap, rnd)
        if i > 0:
            _thread(board, (pos[i - 1][0], pos[i - 1][1] - pol.size[1] / 2 + 34),
                    (cx, cy - pol.size[1] / 2 + 34))
        x, y, w, h = _shadowed_paste(board, pol, cx, cy)
        _pin(board, int(cx), int(cy - h / 2 + 34))
        emph = (sc.get("emphasis") or [])
        if emph:
            _note(board, emph[0], cx + (1 if i % 2 == 0 else -1) * (w * 0.20), cy + h / 2 + 62, rnd)

        # potongan papan: memuat barang bukti sebelumnya & sekarang, rasio 9:16
        px, py = pos[i - 1] if i > 0 else (cx, cy - 330)
        need_w = abs(cx - px) + 760
        need_h = abs(cy - py) + 1000
        cw = int(min(max(need_w, need_h * OUT_W / OUT_H) + 40, CW))
        ch = int(cw * OUT_H / OUT_W)
        if ch > CH:
            ch, cw = CH, int(CH * OUT_W / OUT_H)
        mx, my = (cx + px) / 2, (cy + py) / 2
        x0 = int(min(max(mx - cw / 2, 0), CW - cw))
        y0 = int(min(max(my - ch / 2, 0), CH - ch))
        crop = board.crop((x0, y0, x0 + cw, y0 + ch)).convert("RGB").resize((OUT_W, OUT_H), Image.LANCZOS)
        out = work / f"board{i:02d}.jpg"
        crop.save(out, "JPEG", quality=93)
        sc["image"] = str(out)
        sc["board_focus"] = {"from": ((px - x0) / cw, (py - y0) / ch), "to": ((cx - x0) / cw, (cy - y0) / ch)}
    print(f"Papan konspirasi: {n} barang bukti, kanvas {CW}x{CH}")
