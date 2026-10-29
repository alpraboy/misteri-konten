"""Cinematic documentary typography: restrained title cards and stable readable captions."""
import re

W, H = 1080, 1920
CHUNK = 5
CAP_Y = 1510
TITLE_Y = 310
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


def build_ass(script, cfg, path):
    """Create subtle titles, clean 1-line/2-line caption groups and a quiet end card."""
    st = cfg["style"]
    font, size, accent = st["font"], st["size"], st["color"]
    upper = st.get("uppercase", False)
    title_size = st.get("title_size", 60)

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Cap,{font},{size},{WHITE},{WHITE},&H00101010,&H78000000,0,0,0,0,100,100,0,0,1,4,1,2,90,90,100,1
Style: Title,{font},{title_size},&H00FFFFFF,&H00FFFFFF,{accent},&H90000000,1,0,0,0,100,100,1,0,1,2,2,8,100,100,70,1
Style: Brand,Montserrat,28,&H00FFFFFF,&H00FFFFFF,{accent},&H90000000,1,0,0,0,100,100,2,0,1,1,1,7,68,68,62,1
Style: EndCard,{font},54,&H00FFFFFF,&H00FFFFFF,{accent},&H90000000,1,0,0,0,100,100,1,0,1,3,2,5,90,90,80,1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
"""
    lines = []
    total = float(script.get("total_duration", 0))
    title = _esc(script.get("title", "Misteri yang Belum Terjawab"))

    # Small brand marker persists throughout; no bouncing or flashing.
    if total > 1:
        lines.append(
            f"Dialogue: 0,{_t(0)},{_t(max(total - 0.4, 0.5))},Brand,,0,0,0,,"
            f"{{\\an7\\fad(500,400)\\alpha&H18&}}AGEN MISTERI"
        )

    # One quiet opening title, held briefly and faded away.
    first_scene = script["scenes"][0] if script.get("scenes") else {}
    open_end = min(max(float(first_scene.get("duration", 2.6)) - 0.25, 1.8), 3.0)
    lines.append(
        f"Dialogue: 2,{_t(0.25)},{_t(open_end)},Title,,0,0,0,,"
        f"{{\\an8\\pos({W // 2},{TITLE_Y})\\fad(450,650)}}{title}"
    )

    # Per-scene labels are optional, restrained and fade rather than slam in.
    for scene_index, sc in enumerate(script.get("scenes", [])):
        if scene_index == 0:
            continue  # opening title already introduces the story; avoid stacking labels
        text = _esc(sc.get("onscreen", "")).strip()
        if not text:
            continue
        start = float(sc["start"]) + 0.35
        end = min(float(sc["start"]) + float(sc["duration"]) - 0.25, start + 2.8)
        if end - start >= 0.7:
            lines.append(
                f"Dialogue: 2,{_t(start)},{_t(end)},Title,,0,0,0,,"
                f"{{\\an8\\pos({W // 2},{TITLE_Y})\\fad(300,450)}}{_fmt(text, upper)}"
            )

    # Stable grouped subtitles: highlight is static for each word, no scale pop/jitter.
    for sc in script.get("scenes", []):
        words = sc.get("words", [])
        for c in range(0, len(words), CHUNK):
            chunk = words[c:c + CHUNK]
            for j, w in enumerate(chunk):
                start = float(w["start"])
                if j + 1 < len(chunk):
                    end = float(chunk[j + 1]["start"])
                elif c + CHUNK < len(words):
                    end = float(words[c + CHUNK]["start"])
                else:
                    end = float(w.get("end", start + 0.3)) + 0.12
                if end - start < 0.04:
                    continue
                parts = []
                for kk, cw in enumerate(chunk):
                    tok = _fmt(cw["text"], upper)
                    if kk == j:
                        parts.append(f"{{\\c{accent}}}{tok}{{\\c{WHITE}}}")
                    else:
                        parts.append(tok)
                caption = " ".join(parts)
                lines.append(
                    f"Dialogue: 1,{_t(start)},{_t(end)},Cap,,0,0,0,,"
                    f"{{\\an2\\pos({W // 2},{CAP_Y})\\fad(70,70)}}{caption}"
                )

    # Minimal closing card; only appears if the final scene is long enough.
    if total > 3.5:
        end_start = max(total - 1.65, 0)
        lines.append(
            f"Dialogue: 3,{_t(end_start)},{_t(total)},EndCard,,0,0,0,,"
            f"{{\\an5\\pos({W // 2},{H // 2})\\fad(350,350)}}TERUS TELUSURI MISTERINYA"
        )

    with open(path, "w", encoding="utf-8") as f:
        f.write(header + "\n".join(lines) + "\n")
    print(f"Subtitle cinematic: {len(lines)} baris -> {path}")
