"""Typography bergaya komik: judul 'stiker' yang membanting masuk + subtitle kata-per-kata
dengan efek pop (overshoot) dan kata aktif berwarna aksen. Format ASS."""

W, H = 1080, 1920
CHUNK = 3            # jumlah kata per tampilan
CAP_Y = 1360         # posisi vertikal subtitle
TITLE_Y = 430        # posisi vertikal teks judul
WHITE = "&H00FFFFFF&"


def _t(sec):
    sec = max(sec, 0)
    h = int(sec // 3600)
    m = int(sec % 3600 // 60)
    s = sec % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _esc(text):
    return text.replace("\\", "").replace("{", "(").replace("}", ")")


def _fmt(word, upper):
    word = _esc(word)
    return word.upper() if upper else word


def build_ass(script, cfg, path):
    st = cfg["style"]
    font, size, accent = st["font"], st["size"], st["color"]
    upper = st.get("uppercase", False)

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Cap,{font},{size},{WHITE},{WHITE},&H00000000,&H00000000,1,0,0,0,100,100,1,0,1,9,4,5,70,70,60,1
Style: Title,{font},{st['title_size']},&H00000000,&H00000000,{accent},{accent},1,0,0,0,100,100,2,0,3,18,0,5,90,90,60,1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
"""
    lines = []

    # 1) Judul 'stiker komik': membanting masuk (besar -> normal), miring, lalu memudar
    for k, sc in enumerate(script["scenes"]):
        text = sc.get("onscreen", "").strip()
        if not text:
            continue
        start = sc["start"] + 0.12
        end = sc["start"] + min(sc["duration"] - 0.2, 3.2)
        if end - start < 0.8:
            continue
        tilt = -3 if k % 2 == 0 else 3
        slam = "\\fscx165\\fscy165\\t(0,170,\\fscx100\\fscy100)"
        lines.append(
            f"Dialogue: 2,{_t(start)},{_t(end)},Title,,0,0,0,,"
            f"{{\\an5\\pos({W // 2},{TITLE_Y})\\frz{tilt}{slam}\\fad(0,220)}}{_fmt(text, True)}"
        )

    # 2) Subtitle kata-per-kata: kata aktif beraksen + pop dengan overshoot
    for sc in script["scenes"]:
        words = sc["words"]
        for c in range(0, len(words), CHUNK):
            chunk = words[c:c + CHUNK]
            nxt = words[c + CHUNK]["start"] if c + CHUNK < len(words) else None
            for j, w in enumerate(chunk):
                start = w["start"]
                if j + 1 < len(chunk):
                    end = chunk[j + 1]["start"]
                else:
                    end = nxt if nxt is not None else w["end"] + 0.15
                if end - start < 0.05:
                    continue
                parts = []
                for kk, cw in enumerate(chunk):
                    tok = _fmt(cw["text"], upper)
                    if kk == j:
                        pop = "\\fscx70\\fscy70\\t(0,80,\\fscx124\\fscy124)\\t(80,170,\\fscx110\\fscy110)"
                        parts.append(f"{{\\c{accent}{pop}}}{tok}{{\\r}}")
                    else:
                        parts.append(tok)
                lines.append(
                    f"Dialogue: 1,{_t(start)},{_t(end)},Cap,,0,0,0,,"
                    f"{{\\an5\\pos({W // 2},{CAP_Y})}}{' '.join(parts)}"
                )

    with open(path, "w", encoding="utf-8") as f:
        f.write(header + "\n".join(lines) + "\n")
    print(f"Subtitle: {len(lines)} baris -> {path}")
