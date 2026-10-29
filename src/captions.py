"""Typography: subtitle kata-per-kata (highlight) + teks judul per adegan, format ASS."""

W, H = 1080, 1920
CHUNK = 3            # jumlah kata per tampilan
CAP_Y = 1350         # posisi vertikal subtitle
TITLE_Y = 420        # posisi vertikal teks judul


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
    font, size, hi = st["font"], st["size"], st["color"]
    upper = st.get("uppercase", False)
    box = st.get("title_box", False)

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Cap,{font},{size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,1,0,0,0,100,100,0,0,1,6,2,5,70,70,60,1
Style: Title,{font},{st['title_size']},&H00FFFFFF,&H00FFFFFF,{'&H000000C8' if box else '&H00000000'},{'&H000000C8' if box else '&H96000000'},1,0,0,0,100,100,2,0,{3 if box else 1},{14 if box else 6},0,5,90,90,60,1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
"""
    lines = []

    # 1) Teks judul per adegan (typography besar, fade in/out)
    for sc in script["scenes"]:
        text = sc.get("onscreen", "").strip()
        if not text:
            continue
        start = sc["start"] + 0.15
        end = sc["start"] + min(sc["duration"] - 0.2, 3.0)
        if end - start < 0.8:
            continue
        txt = _fmt(text, True if box else upper)
        lines.append(
            f"Dialogue: 1,{_t(start)},{_t(end)},Title,,0,0,0,,"
            f"{{\\an5\\pos({W // 2},{TITLE_Y})\\fad(250,250)"
            f"\\fscx85\\fscy85\\t(0,300,\\fscx100\\fscy100)}}{txt}"
        )

    # 2) Subtitle kata-per-kata: kata aktif berwarna + efek "pop"
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
                for k, cw in enumerate(chunk):
                    tok = _fmt(cw["text"], upper)
                    if k == j:
                        parts.append(f"{{\\c{hi}}}{tok}{{\\c&H00FFFFFF&}}")
                    else:
                        parts.append(tok)
                pop = "\\fscx92\\fscy92\\t(0,90,\\fscx100\\fscy100)"
                lines.append(
                    f"Dialogue: 0,{_t(start)},{_t(end)},Cap,,0,0,0,,"
                    f"{{\\an5\\pos({W // 2},{CAP_Y}){pop}}}{' '.join(parts)}"
                )

    with open(path, "w", encoding="utf-8") as f:
        f.write(header + "\n".join(lines) + "\n")
    print(f"Subtitle: {len(lines)} baris -> {path}")
