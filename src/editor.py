"""Agen editor: ilustrasi bergerak (6 gerak kamera), grain/kedip film, transisi xfade,
subtitle ASS, dan mixing audio (musik menurun saat narasi)."""
import random
from pathlib import Path

from util import run

FPS = 30
T = 0.30  # lama transisi antar adegan (detik)
TRANSITIONS = [
    "slideleft", "fadegrays", "circleopen", "wipeup",
    "dissolve", "slideright", "fadeblack", "wipeleft",
]
# footage dibuat mendekati monokrom agar menyatu dengan gaya komik tinta
FOOTAGE_LOOK = "hue=s=0.12,eq=contrast=1.3:brightness=-0.07"


def _motion(motion, d):
    """Ekspresi zoompan (z, x, y) untuk tiap jenis gerak kamera."""
    cx = "iw/2-(iw/zoom/2)"
    cy = "ih/2-(ih/zoom/2)"
    if motion == "zoom_out":
        return f"1.20-0.20*on/{d}", cx, cy
    if motion == "pan_left":
        return "1.22", f"(iw-iw/zoom)*(1-on/{d})", cy
    if motion == "pan_right":
        return "1.22", f"(iw-iw/zoom)*on/{d}", cy
    if motion == "tilt_up":
        return "1.22", cx, f"(ih-ih/zoom)*(1-on/{d})"
    if motion == "tilt_down":
        return "1.22", cx, f"(ih-ih/zoom)*on/{d}"
    return f"1+0.20*on/{d}", cx, cy  # zoom_in


def _finish(cfg, with_flicker):
    """Filter akhir tiap klip: grade tema + grain film (+ kedip bila diminta)."""
    parts = [cfg["style"]["grade"], "noise=alls=12:allf=t+u"]
    if with_flicker:
        parts.append("eq=brightness='0.04*sin(37*t)*sin(11*t)':eval=frame")
    parts.append("format=yuv420p")
    return ",".join(parts)


def image_clip(img, dur, motion, cfg, out):
    d = max(int(round(dur * FPS)), 2)
    z, x, y = _motion(motion, d)
    vf = (
        "scale=2160:3840:force_original_aspect_ratio=increase:flags=lanczos,"
        "crop=2160:3840,setsar=1,"
        f"zoompan=z='{z}':x='{x}':y='{y}':d={d}:s=1080x1920:fps={FPS},"
        f"{_finish(cfg, cfg['style'].get('flicker', False))}"
    )
    run([
        "ffmpeg", "-y", "-i", img, "-vf", vf, "-frames:v", d,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", out,
    ])


def video_clip(src, dur, idx, cfg, out):
    zoom = 0.10
    if idx % 2 == 0:
        z = f"(1+{zoom}*t/{dur:.3f})"
    else:
        z = f"({1 + zoom}-{zoom}*t/{dur:.3f})"
    vf = (
        "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,"
        f"fps={FPS},"
        f"scale=w='trunc(1080*{z}/2)*2':h='trunc(1920*{z}/2)*2':eval=frame,"
        f"crop=1080:1920,{FOOTAGE_LOOK},{_finish(cfg, cfg['style'].get('flicker', False))}"
    )
    run([
        "ffmpeg", "-y", "-stream_loop", "-1", "-i", src, "-t", f"{dur:.3f}",
        "-an", "-vf", vf,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", out,
    ])


def pick_music(theme):
    base = Path("assets/music")
    for folder in (base / theme, base):
        files = sorted(
            p for p in folder.glob("*")
            if p.suffix.lower() in (".mp3", ".wav", ".m4a", ".ogg")
        )
        if files:
            return random.choice(files)
    return None


def render(script, cfg, theme, narration, ass_name, work: Path, out: Path):
    work = work.resolve()
    scenes = script["scenes"]
    n = len(scenes)

    # 1) Satu klip per adegan. Klip selain yang terakhir diperpanjang T detik
    #    supaya transisi xfade tidak memendekkan total durasi.
    clips = []
    for i, sc in enumerate(scenes):
        length = sc["duration"] + (T if i < n - 1 else 0)
        clip = work / f"scene_v{i:02d}.mp4"
        if sc.get("image"):
            image_clip(sc["image"], length, sc["motion"], cfg, clip)
        else:
            video_clip(sc["clip"], length, i, cfg, clip)
        clips.append(clip)

    # 2) Rangkai semua dalam satu perintah: xfade antar adegan + subtitle + audio
    cmd = ["ffmpeg", "-y"]
    for c in clips:
        cmd += ["-i", c]
    cmd += ["-i", Path(narration).resolve()]
    a_narr = n
    music = pick_music(theme)
    if music:
        print(f"Musik latar: {music}")
        cmd += ["-stream_loop", "-1", "-i", music.resolve()]
        audio = (
            f"[{a_narr}:a]asplit=2[n1][n2];[{a_narr + 1}:a]volume=0.28[m];"
            "[m][n1]sidechaincompress=threshold=0.02:ratio=10:attack=20:release=500[d];"
            "[n2][d]amix=inputs=2:duration=first:normalize=0,"
            "loudnorm=I=-16:TP=-1.5:LRA=11[a]"
        )
    else:
        print("Tidak ada musik di assets/music/ -> video tanpa musik latar.")
        audio = f"[{a_narr}:a]loudnorm=I=-16:TP=-1.5:LRA=11[a]"

    chains = [
        f"[{i}:v]fps={FPS},settb=AVTB,setpts=PTS-STARTPTS,format=yuv420p[v{i}]"
        for i in range(n)
    ]
    prev, acc = "v0", 0.0
    for k in range(n - 1):
        acc += scenes[k]["duration"]
        tr = TRANSITIONS[k % len(TRANSITIONS)]
        chains.append(
            f"[{prev}][v{k + 1}]xfade=transition={tr}:duration={T}:offset={acc:.3f}[x{k + 1}]"
        )
        prev = f"x{k + 1}"
    chains.append(f"[{prev}]ass={ass_name}[v]")
    chains.append(audio)

    total = script["total_duration"]
    cmd += [
        "-filter_complex", ";".join(chains), "-map", "[v]", "-map", "[a]",
        "-t", f"{total:.3f}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out.resolve(),
    ]
    run(cmd, cwd=work)  # cwd = work agar "ass=captions.ass" ditemukan

    thumb = out.with_name("thumbnail.jpg")
    run(["ffmpeg", "-y", "-ss", "1.2", "-i", out.resolve(), "-frames:v", "1", "-q:v", "2", thumb.resolve()])
    return thumb
