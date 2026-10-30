"""Cinematic documentary editor: slow motivated camera moves, gentle dissolves and clean narration-first mix."""
import random
from pathlib import Path

from util import run

FPS = 30
T = 0.25  # lama transisi antar adegan (detik)
SHOT_LEN = 6.5  # shot lebih panjang; mengurangi rasa gelisah
TRANSITIONS = ["fade", "fade", "fade"]  # dissolve sederhana dan konsisten
FOOTAGE_LOOK = "eq=contrast=1.08:brightness=-0.025:saturation=0.88,vignette=PI/5"

# Bidikan: zoom awal/akhir (z0,z1) dan titik fokus jendela potong (0..1) awal/akhir
SHOTS = {
    "wide_in":   {"z0": 1.015, "z1": 1.055, "f0": (.5, .5), "f1": (.5, .5)},
    "wide_out":  {"z0": 1.055, "z1": 1.015, "f0": (.5, .5), "f1": (.5, .5)},
    "pan_left":  {"z0": 1.045, "z1": 1.045, "f0": (.54, .5), "f1": (.46, .5)},
    "pan_right": {"z0": 1.045, "z1": 1.045, "f0": (.46, .5), "f1": (.54, .5)},
    "tilt_up":   {"z0": 1.04, "z1": 1.04, "f0": (.5, .54), "f1": (.5, .46)},
    "tilt_down": {"z0": 1.04, "z1": 1.04, "f0": (.5, .46), "f1": (.5, .54)},
    "close_top": {"z0": 1.06, "z1": 1.085, "f0": (.5, .42), "f1": (.5, .44)},
    "close_low": {"z0": 1.08, "z1": 1.055, "f0": (.5, .56), "f1": (.5, .54)},
    "punch":     {"z0": 1.02, "z1": 1.07, "f0": (.5, .48), "f1": (.5, .46)},
}
MOTION_TO_SHOT = {
    "zoom_in": "wide_in", "zoom_out": "wide_out", "pan_left": "pan_left",
    "pan_right": "pan_right", "tilt_up": "tilt_up", "tilt_down": "tilt_down",
}
FILLERS = ["wide_in", "pan_right", "wide_out", "pan_left", "tilt_up", "close_top", "tilt_down", "close_low"]


# ------------------------------------------------------------------ perencanaan
def plan_shots(script):
    """Bagi tiap adegan ilustrasi menjadi bidikan; simpan di sc['shots'] (waktu global)."""
    counter = 0
    for sc in script["scenes"]:
        if not sc.get("image"):
            sc["shots"] = []
            continue
        k = max(1, int(round(sc["duration"] / SHOT_LEN)))
        base = sc["duration"] / k
        first = MOTION_TO_SHOT.get(sc.get("motion"), "wide_in")
        shots = []
        for j in range(k):
            name = first if j == 0 else FILLERS[(counter + j) % len(FILLERS)]
            shots.append({"name": name, "start": sc["start"] + j * base, "dur": base})
        counter += k
        sc["shots"] = shots


def sfx_events(script, impacts):
    """Jadwal efek suara: whoosh di pergantian adegan, hit di bidikan punch & kata raksasa."""
    ev = []
    scenes = script["scenes"]
    for k in range(1, len(scenes)):
        ev.append(("whoosh", scenes[k]["start"] - 0.15, 0.55))
    for sc in scenes:
        for j, sh in enumerate(sc.get("shots", [])):
            if j == 0:
                continue
            if SHOTS[sh["name"]].get("impact"):
                ev.append(("hit", sh["start"], 0.6))
            else:
                ev.append(("whoosh", sh["start"] - 0.1, 0.22))
    for t, _ in impacts:
        ev.append(("hit", t, 0.9))
    return ev


# ------------------------------------------------------------------ klip
def _finish(cfg):
    parts = [cfg["style"]["grade"]]
    if cfg["style"].get("flicker"):
        parts.append("eq=brightness='0.04*sin(37*t)*sin(11*t)':eval=frame")
    parts.append("format=yuv420p")
    return ",".join(parts)


def shot_clip(img, shot, first_in_scene, length, cfg, fxp, out):
    spec = SHOTS[shot["name"]]
    d = max(int(round(length * FPS)), 3)
    z = f"{spec['z0']}+({spec['z1']}-{spec['z0']})*on/{d}"
    (fx0, fy0), (fx1, fy1) = spec["f0"], spec["f1"]
    amp = 0  # tanpa getaran kamera; motion tetap halus
    shx = ""
    shy = ""
    x = f"(iw-iw/zoom)*({fx0}+({fx1}-{fx0})*on/{d}){shx}"
    y = f"(ih-ih/zoom)*({fy0}+({fy1}-{fy0})*on/{d}){shy}"

    base = (
        "scale=2160:3840:force_original_aspect_ratio=increase:flags=lanczos,"
        "crop=2160:3840,setsar=1,"
        f"zoompan=z='{z}':x='{x}':y='{y}':d={d}:s=1080x1920:fps={FPS}"
    )

    enc = ["-frames:v", d, "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", out]

    run(["ffmpeg", "-y", "-i", img, "-vf", f"{base},{_finish(cfg)}", *enc])


def video_clip(src, dur, idx, cfg, out):
    """Footage: zoom pelan via zoompan; bila gagal, coba versi polos tanpa zoom."""
    n = max(int(round(dur * FPS)), 3)
    z = f"1+0.035*on/{n}" if idx % 2 == 0 else f"1.035-0.035*on/{n}"
    enc = ["-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", out]
    look = f"{FOOTAGE_LOOK},{_finish(cfg)}"
    vf = (
        "scale=1620:2880:force_original_aspect_ratio=increase,crop=1620:2880,setsar=1,"
        f"fps={FPS},zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=1080x1920:fps={FPS},"
        f"{look}"
    )
    try:
        run(["ffmpeg", "-y", "-stream_loop", "-1", "-i", src, "-t", f"{dur:.3f}", "-vf", vf, *enc])
    except RuntimeError:
        print("Footage zoom gagal -> memakai versi polos tanpa zoom")
        plain = (
            "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,"
            f"fps={FPS},{look}"
        )
        run(["ffmpeg", "-y", "-stream_loop", "-1", "-i", src, "-t", f"{dur:.3f}", "-vf", plain, *enc])


def _concat(files, out):
    lst = out.with_suffix(".txt")
    lst.write_text("".join(f"file '{Path(f).resolve()}'\n" for f in files))
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", out])


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


# ------------------------------------------------------------------ render akhir
def render(script, cfg, theme, narration, ass_name, work: Path, out: Path, fxp, sfx_path):
    work = work.resolve()
    scenes = script["scenes"]
    n = len(scenes)

    # 1) Klip per adegan (adegan non-terakhir diperpanjang T agar xfade tidak memendekkan total)
    clips = []
    for i, sc in enumerate(scenes):
        extra = T if i < n - 1 else 0
        clip = work / f"scene_v{i:02d}.mp4"
        if sc.get("image"):
            parts, shots = [], sc["shots"]
            for j, sh in enumerate(shots):
                length = sh["dur"] + (extra if j == len(shots) - 1 else 0)
                f = work / f"shot{i:02d}_{j}.mp4"
                try:
                    shot_clip(sc["image"], sh, j == 0, length, cfg, fxp, f)
                except RuntimeError:
                    print(f"Bidikan {i}-{j} gagal -> diganti bidikan sederhana")
                    shot_clip(sc["image"], dict(sh, name="wide_in"), False, length, cfg, fxp, f)
                parts.append(f)
            _concat(parts, clip)
        else:
            video_clip(sc["clip"], sc["duration"] + extra, i, cfg, clip)
        clips.append(clip)

    # 2) Satu perintah akhir: xfade antar adegan + bingkai/halftone + subtitle + audio
    cmd = ["ffmpeg", "-y"]
    for c in clips:
        cmd += ["-i", c]
    i_narr = n
    cmd += ["-i", Path(narration).resolve()]

    music = pick_music(theme)
    if music:
        print(f"Musik latar: {music}")
        cmd += ["-stream_loop", "-1", "-i", music.resolve()]
        i_mus = n + 1
        audio = (
            f"[{i_narr}:a]asplit=2[na][nb];"
            f"[{i_mus}:a]aresample=44100,aformat=channel_layouts=stereo,volume=0.055[mu];"
            "[mu][na]sidechaincompress=threshold=0.018:ratio=5:attack=80:release=1000[du];"
            "[nb][du]amix=inputs=2:duration=first:normalize=0,"
            "loudnorm=I=-16:TP=-1.5:LRA=9[a]"
        )
    else:
        print("Tidak ada musik di assets/music/ -> tanpa musik latar.")
        audio = (
            f"[{i_narr}:a]loudnorm=I=-16:TP=-1.5:LRA=9[a]"
        )

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

    cmd += [
        "-filter_complex", ";".join(chains), "-map", "[v]", "-map", "[a]",
        "-t", f"{script['total_duration']:.3f}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-maxrate", "14M", "-bufsize", "28M",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out.resolve(),
    ]
    run(cmd, cwd=work)  # cwd = work agar "ass=captions.ass" ditemukan

    thumb = out.with_name("thumbnail.jpg")
    run(["ffmpeg", "-y", "-ss", "1.2", "-i", out.resolve(), "-frames:v", "1", "-q:v", "2", thumb.resolve()])
    return thumb
