"""Tipografi kinetik horor-mistis (ASS): subtitle kata-per-kata dengan pop & kata penting
beraksen, label 'stiker' yang terbuka dengan sapuan, kata raksasa di momen penting."""
import re

W, H = 1080, 1920
CHUNK = 4
MAX_CAPTION_CHARS = 26
CAP_Y = 1490
TITLE_Y = 310
IMPACT_Y = 900
WHITE = "&H00FFFFFF&"


def _t(sec):
    sec = max(sec, 0)
    h = int(sec // 3600)
    m = int(sec % 3600 // 60)
    s = sec % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _esc(text):
    return str(text).replace("\\", "").replace("{", "(").replace("}", ")").replace("\n", " ")


def _fmt(word, upper):
    word = _esc(word)
    return word.upper() if upper else word


def _norm(w):
    return re.sub(r"[^\w]", "", str(w).lower())


def _lighten(ass_color, amount=0.32):
    """Campur warna ASS (&H00BBGGRR&) dengan putih supaya teks beraksen terbaca di latar gelap."""
    try:
        v = ass_color.strip("&H").rstrip("&")
        b, g, r = int(v[-6:-4], 16), int(v[-4:-2], 16), int(v[-2:], 16)
        mix = lambda c: int(c + (255 - c) * amount)
        return f"&H00{mix(b):02X}{mix(g):02X}{mix(r):02X}&"
    except Exception:
        return ass_color


def impact_events(script):
    """Cari waktu ucap kata raksasa tiap adegan. Kembalikan list (detik, TEKS)."""
    out = []
    for sc in script.get("scenes", []):
        target = _norm(sc.get("impact_word", "") or "")
        if not target:
            continue
        for w in sc.get("words", []):
            if _norm(w.get("text", "")) == target:
                out.append((float(w["start"]), target.upper()))
                break
    return out


def _impact_lines(t, text, size, accent, k):
    """Kata raksasa: muncul besar lalu 'jatuh' ke ukuran normal dengan getar singkat, bertahan, memudar."""
    jitter = [(-14, 9, 175), (12, -10, 150), (-7, 6, 128), (4, -3, 110)]
    tilt = -3 if k % 2 == 0 else 3
    lines = []
    for n, (dx, dy, sc) in enumerate(jitter):
        a = t + 0.045 * n
        lines.append(
            f"Dialogue: 3,{_t(a)},{_t(a + 0.045)},Impact,,0,0,0,,"
            f"{{\\an5\\pos({W // 2 + dx},{IMPACT_Y + dy})\\frz{tilt}\\fs{size}"
            f"\\fscx{sc}\\fscy{sc}\\blur1.5\\c{accent}}}{text}"
        )
    a = t + 0.18
    lines.append(
        f"Dialogue: 3,{_t(a)},{_t(a + 1.1)},Impact,,0,0,0,,"
        f"{{\\an5\\pos({W // 2},{IMPACT_Y})\\frz{tilt}\\fs{size}\\blur1.5\\c{accent}"
        f"\\t(0,1100,\\fscx104\\fscy104)\\fad(0,260)}}{text}"
    )
    return lines


def _token(tok, active, emph, pop, active_c, emph_c, base_c):
    """Satu kata dengan warna/ukuran sesuai peran: aktif (diucapkan), penting (emphasis), biasa."""
    scale, color = 100, base_c
    if emph:
        scale, color = 122, emph_c
    if active:
        scale, color = scale + 8, active_c
    if pop:
        s0 = int(scale * 0.84)
        return f"{{\\c{color}\\fscx{s0}\\fscy{s0}\\t(0,110,\\fscx{scale}\\fscy{scale})}}{tok}"
    return f"{{\\c{color}\\fscx{scale}\\fscy{scale}}}{tok}"


def _timer(sec):
    """Penghitung waktu CCTV: mulai 03:33:12 AM."""
    base = 3 * 3600 + 33 * 60 + 12 + int(sec)
    return f"{(base // 3600) % 12 or 12:02d}:{base // 60 % 60:02d}:{base % 60:02d} AM"


def build_ass(script, cfg, path):
    """Judul pembuka, label stiker, subtitle kinetik, kata raksasa, dan kartu penutup."""
    st = cfg["style"]
    font, size, accent = st.get("font", "Montserrat"), st.get("size", 76), st["color"]
    look = cfg.get("look", "ink")
    color2 = st.get("color2", accent)
    if look == "vhs":
        active_c, emph_c, base_c = accent, _lighten(color2, 0.55), "&H00E6E6E6&"
        cap_primary, cap_outline, cap_bs, cap_ol = "&H00E6E6E6&", "&H8C000000", 3, 8
    elif look == "conspiracy":
        active_c, emph_c, base_c = accent, color2, "&H00101018&"
        cap_primary, cap_outline, cap_bs, cap_ol = "&H00101018&", "&H00A0C7D9", 3, 12     # label mesin tik di kertas kraft
    elif look == "wayang":
        active_c, emph_c, base_c = _lighten(accent, 0.30), _lighten(color2, 0.50), "&H00C8DCE8&"
        cap_primary, cap_outline, cap_bs, cap_ol = "&H00C8DCE8&", "&H00050505", 1, 6
    else:
        text_accent = _lighten(accent)
        active_c = emph_c = text_accent
        base_c, cap_primary, cap_outline, cap_bs, cap_ol = WHITE, WHITE, "&H00101010", 1, 6
    text_accent = active_c
    upper = st.get("uppercase", False)
    title_size = st.get("title_size", 60)
    max_chars = max(14, min(MAX_CAPTION_CHARS, int(940 / (0.58 * size * (1.06 if upper else 1.0)))))

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Cap,{font},{size},{cap_primary},{cap_primary},{cap_outline},&H78000000,1,0,0,0,100,100,1,0,{cap_bs},{cap_ol},2,2,90,90,100,1
Style: Title,{font},{title_size + 8},&H00FFFFFF,&H00FFFFFF,{accent},&H90000000,1,0,0,0,100,100,2,0,1,4,3,8,100,100,70,1
Style: Tag,{font},{title_size},&H00000000,&H00000000,{accent},{accent},1,0,0,0,100,100,2,0,3,16,0,8,90,90,70,1
Style: Impact,{font},120,{accent},{accent},&H00000000,&H00000000,1,0,0,0,100,100,2,0,1,12,7,5,40,40,40,1
Style: Hud,DejaVu Sans Mono,40,&H00F0F0F0,&H00F0F0F0,&H00000000,&H90000000,1,0,0,0,100,100,2,0,1,3,2,7,60,60,60,1
Style: Rec,DejaVu Sans Mono,44,&H00F0F0F0,&H00F0F0F0,&H00000000,&H90000000,1,0,0,0,100,100,2,0,1,3,2,7,60,60,60,1
Style: Stamp,DejaVu Sans Mono,100,&H002222B2,&H002222B2,&H001010A0,&H90000000,1,0,0,0,100,100,6,0,1,7,3,5,40,40,40,1
Style: Brand,Montserrat,28,&H00FFFFFF,&H00FFFFFF,{accent},&H90000000,1,0,0,0,100,100,2,0,1,1,1,7,68,68,62,1
Style: EndCard,{font},54,&H00FFFFFF,&H00FFFFFF,{accent},&H90000000,1,0,0,0,100,100,1,0,1,3,2,5,90,90,80,1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
"""
    lines = []
    total = float(script.get("total_duration", 0))
    title = _esc(script.get("title", "Misteri yang Belum Terjawab"))

    # Penanda brand kecil sepanjang video.
    if total > 1 and look != "vhs":
        lines.append(
            f"Dialogue: 0,{_t(0)},{_t(max(total - 0.4, 0.5))},Brand,,0,0,0,,"
            f"{{\\an7\\fad(500,400)\\alpha&H18&}}AGEN MISTERI"
        )
    if look == "vhs" and total > 1:
        # HUD rekaman: REC berkedip + penghitung waktu 03:33:12 AM + label kamera
        lines.append(f"Dialogue: 5,{_t(0)},{_t(total)},Rec,,0,0,0,,{{\\an7\\pos(66,62)}}\\h\\h\\h\\hREC")
        for k in range(int(total) + 1):
            on_end = min(k + 0.62, total)
            lines.append(f"Dialogue: 5,{_t(k)},{_t(on_end)},Rec,,0,0,0,,{{\\an7\\pos(66,62)\\c&H000000E8&}}●")
            lines.append(f"Dialogue: 5,{_t(k)},{_t(min(k + 1, total))},Hud,,0,0,0,,{{\\an9\\pos(1014,62)}}{_timer(k)}")
        lines.append(f"Dialogue: 5,{_t(0)},{_t(total)},Hud,,0,0,0,,{{\\an1\\pos(66,1860)\\fs30\\alpha&H30&}}CAM 02  SP")

    # Judul pembuka: terbuka dengan sapuan dari kiri ke kanan, lalu memudar.
    first_scene = script["scenes"][0] if script.get("scenes") else {}
    open_end = min(max(float(first_scene.get("duration", 2.6)) - 0.25, 1.8), 3.2)
    tsize = max(40, min(title_size + 8, int(940 / (0.56 * max(len(title), 1)) * 1.6)))
    lines.append(
        f"Dialogue: 2,{_t(0.25)},{_t(open_end)},Title,,0,0,0,,"
        f"{{\\q0\\fs{tsize}\\an8\\pos({W // 2},{TITLE_Y})\\clip(0,200,0,640)\\t(0,420,\\clip(0,200,{W},640))\\fad(0,650)}}{title}"
    )

    # Label per adegan (lokasi/tahun/konsep): kotak aksen yang terbuka dengan sapuan.
    for scene_index, sc in enumerate(script.get("scenes", [])):
        if scene_index == 0:
            continue
        text = _esc(sc.get("onscreen", "")).strip()
        if not text:
            continue
        start = float(sc["start"]) + 0.35
        end = min(float(sc["start"]) + float(sc["duration"]) - 0.25, start + 2.8)
        if end - start >= 0.7:
            lines.append(
                f"Dialogue: 2,{_t(start)},{_t(end)},Tag,,0,0,0,,"
                f"{{\\q0\\an8\\pos({W // 2},{TITLE_Y})\\clip(0,200,0,520)\\t(0,320,\\clip(0,200,{W},520))\\fad(0,400)}}"
                f"{_fmt(text, True)}"
            )

    # Subtitle: kelompok kata dibatasi lebar (WrapStyle=2 tidak membungkus otomatis).
    for sc in script.get("scenes", []):
        words = sc.get("words", [])
        emph = {_norm(w) for w in sc.get("emphasis", [])}
        groups, current, chars = [], [], 0
        for w in words:
            token = _fmt(w.get("text", ""), upper)
            weight = 1.25 if _norm(w.get("text", "")) in emph else 1.0  # kata penting tampil lebih besar
            extra = int(len(token) * weight) + (1 if current else 0)
            if current and (len(current) >= CHUNK or chars + extra > max_chars):
                groups.append(current)
                current, chars = [], 0
                extra = int(len(token) * weight)
            current.append(w)
            chars += extra
        if current:
            groups.append(current)

        for group in groups:
            for j, w in enumerate(group):
                start = float(w["start"])
                if j + 1 < len(group):
                    end = float(group[j + 1]["start"])
                else:
                    idx = words.index(w)
                    if idx + 1 < len(words):
                        end = float(words[idx + 1]["start"])
                    else:
                        end = float(w.get("end", start + 0.3)) + 0.12
                if end - start < 0.04:
                    continue
                parts = []
                for kk, cw in enumerate(group):
                    tok = _fmt(cw.get("text", ""), upper)
                    parts.append(_token(
                        tok, active=(kk == j), emph=(_norm(cw.get("text", "")) in emph),
                        pop=(j == 0 or kk == j), active_c=active_c, emph_c=emph_c, base_c=base_c,
                    ))
                lines.append(
                    f"Dialogue: 1,{_t(start)},{_t(end)},Cap,,0,0,0,,"
                    f"{{\\an2\\pos({W // 2},{CAP_Y})\\fad(70,70)}}{' '.join(parts)}"
                )

    # Kata raksasa di tengah layar pada momen penting.
    for k, (t, text) in enumerate(impact_events(script)):
        size_i = max(80, min(190, int(880 / (0.80 * max(len(text), 1)))))
        lines += _impact_lines(t, text, size_i, text_accent, k)

    # Stempel CONFIDENTIAL (papan konspirasi) di momen pengungkapan / petunjuk penting.
    if look == "conspiracy":
        stamp_at = [sc for sc in script.get("scenes", []) if sc.get("beat") == "reveal"][:1]
        if not stamp_at and len(script.get("scenes", [])) > 2:
            stamp_at = [script["scenes"][2]]
        for sc in stamp_at:
            t = float(sc["start"]) + 0.7
            lines.append(
                f"Dialogue: 4,{_t(t)},{_t(t + 1.6)},Stamp,,0,0,0,,"
                f"{{\\an5\\pos({W // 2},560)\\frz-13\\fscx230\\fscy230\\t(0,130,\\fscx100\\fscy100)\\fad(0,320)}}CONFIDENTIAL"
            )

    # Kartu penutup ringkas.
    if total > 3.5:
        end_start = max(total - 1.65, 0)
        lines.append(
            f"Dialogue: 3,{_t(end_start)},{_t(total)},EndCard,,0,0,0,,"
            f"{{\\q0\\an5\\pos({W // 2},{H // 2})\\fad(350,350)}}TERUS TELUSURI MISTERINYA"
        )

    with open(path, "w", encoding="utf-8") as f:
        f.write(header + "\n".join(lines) + "\n")
    print(f"Tipografi kinetik: {len(lines)} baris -> {path}")
