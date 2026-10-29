"""Agen editor: b-roll bergerak (zoom/pan), color grade, transisi, subtitle, mixing audio."""
import random
from pathlib import Path

from util import run

FADE = 0.15  # dip-to-black antar adegan (detik)


def scene_clip(src, dur, idx, grade, out):
    """Satu adegan: crop 9:16, gerak zoom-in/zoom-out bergantian, grade, fade."""
    zoom = 0.12
    if idx % 2 == 0:
        z = f"(1+{zoom}*t/{dur:.3f})"          # zoom in
    else:
        z = f"({1 + zoom}-{zoom}*t/{dur:.3f})"  # zoom out
    vf = (
        "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30,"
        f"scale=w='trunc(1080*{z}/2)*2':h='trunc(1920*{z}/2)*2':eval=frame,"
        f"crop=1080:1920,{grade},"
        f"fade=t=in:st=0:d={FADE},fade=t=out:st={dur - FADE:.3f}:d={FADE},"
        "format=yuv420p"
    )
    run([
        "ffmpeg", "-y", "-stream_loop", "-1", "-i", src, "-t", f"{dur:.3f}",
        "-an", "-vf", vf,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", out,
    ])


def pick_music(theme):
    base = Path("assets/music")
    for folder in (base / theme, base):
        files = sorted(p for p in folder.glob("*") if p.suffix.lower() in (".mp3", ".wav", ".m4a", ".ogg"))
        if files:
            return random.choice(files)
    return None


def render(script, cfg, theme, narration, ass_name, work: Path, out: Path):
    work = work.resolve()
    clips = []
    for i, sc in enumerate(script["scenes"]):
        clip = work / f"scene_v{i:02d}.mp4"
        scene_clip(sc["clip"], sc["duration"], i, cfg["style"]["grade"], clip)
        clips.append(clip)

    lst = work / "clips.txt"
    lst.write_text("".join(f"file '{c}'\n" for c in clips))

    music = pick_music(theme)
    total = script["total_duration"]
    cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-i", Path(narration).resolve()]
    if music:
        print(f"Musik latar: {music}")
        cmd += ["-stream_loop", "-1", "-i", music.resolve()]
        audio = (
            "[1:a]asplit=2[n1][n2];[2:a]volume=0.28[m];"
            "[m][n1]sidechaincompress=threshold=0.02:ratio=10:attack=20:release=500[d];"
            "[n2][d]amix=inputs=2:duration=first:normalize=0,"
            "loudnorm=I=-16:TP=-1.5:LRA=11[a]"
        )
    else:
        print("Tidak ada musik di assets/music/ -> video tanpa musik latar.")
        audio = "[1:a]loudnorm=I=-16:TP=-1.5:LRA=11[a]"

    fc = f"[0:v]ass={ass_name}[v];{audio}"
    cmd += [
        "-filter_complex", fc, "-map", "[v]", "-map", "[a]", "-t", f"{total:.3f}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out.resolve(),
    ]
    # cwd = work agar "ass=captions.ass" ditemukan lewat path relatif sederhana
    run(cmd, cwd=work)

    thumb = out.with_name("thumbnail.jpg")
    run(["ffmpeg", "-y", "-ss", "1.0", "-i", out.resolve(), "-frames:v", "1", "-q:v", "2", thumb.resolve()])
    return thumb
