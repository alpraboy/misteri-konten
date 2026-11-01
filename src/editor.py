"""Editor v7 'cerita bergambar horor': tiap ilustrasi hitam-putih dihidupkan dengan
gerak kamera berlapis (goyang tangan + garis 'mendidih'), kabut/debu/hujan/bara bergerak,
kedip cahaya, vignette berdenyut, kilat & glitch di momen penting, inset b-roll footage kecil
di beberapa adegan, transisi bergaya, bingkai panel, grain film, dan suara horor."""
import random
import shutil
from pathlib import Path

from util import run

FPS = 30
T = 0.40          # lama transisi antar adegan (detik)
SHOT_LEN = 3.1    # target durasi satu bidikan (detik)
CYCLE = ["dissolve", "fadeblack", "wipeleft", "fade", "slideleft", "circleclose"]
CYCLE_BY_LOOK = {
    "vhs": ["pixelize", "fadeblack", "dissolve", "wipeleft"],
    "conspiracy": ["fade", "slideleft", "wipeleft", "dissolve"],
    "wayang": ["fadeblack", "dissolve", "fade", "circleclose"],
}

# Bidikan: zoom awal/akhir (z0,z1) dan titik fokus jendela potong (0..1) awal/akhir
SHOTS = {
    "wide_in":   {"z0": 1.04, "z1": 1.20, "f0": (.5, .5), "f1": (.5, .5)},
    "wide_out":  {"z0": 1.22, "z1": 1.04, "f0": (.5, .5), "f1": (.5, .5)},
    "pan_left":  {"z0": 1.24, "z1": 1.24, "f0": (.85, .5), "f1": (.15, .5)},
    "pan_right": {"z0": 1.24, "z1": 1.24, "f0": (.15, .5), "f1": (.85, .5)},
    "tilt_up":   {"z0": 1.24, "z1": 1.24, "f0": (.5, .9), "f1": (.5, .1)},
    "tilt_down": {"z0": 1.24, "z1": 1.24, "f0": (.5, .1), "f1": (.5, .9)},
    "close_top": {"z0": 1.50, "z1": 1.68, "f0": (.5, .28), "f1": (.5, .34)},
    "close_low": {"z0": 1.58, "z1": 1.42, "f0": (.5, .78), "f1": (.45, .72)},
    "detail_l":  {"z0": 1.72, "z1": 1.55, "f0": (.22, .55), "f1": (.30, .50)},
    "detail_r":  {"z0": 1.55, "z1": 1.72, "f0": (.78, .50), "f1": (.70, .55)},
    "creep":     {"z0": 1.00, "z1": 1.42, "f0": (.5, .45), "f1": (.5, .40)},
}
MOTION_TO_SHOT = {
    "zoom_in": "wide_in", "zoom_out": "wide_out", "pan_left": "pan_left",
    "pan_right": "pan_right", "tilt_up": "tilt_up", "tilt_down": "tilt_down",
}
SEQ = ["wide_in", "close_top", "pan_right", "detail_l", "tilt_up", "close_low",
       "pan_left", "detail_r", "wide_out", "tilt_down"]
FOOTAGE_LOOK = "hue=s=0,eq=contrast=1.35:brightness=-0.06"


# ------------------------------------------------------------------ perencanaan
def _center_f(p, zoom):
    """Fokus jendela potong (0..1) agar titik p (pecahan gambar) berada di tengah bingkai."""
    if zoom <= 1.0001:
        return 0.5
    return min(1.0, max(0.0, (p - 0.5 / zoom) / (1.0 - 1.0 / zoom)))


def plan_shots(script, shot_len=SHOT_LEN):
    """Bagi tiap adegan ilustrasi menjadi bidikan; simpan di sc['shots'] (waktu global)."""
    counter = 0
    for sc in script["scenes"]:
        if not sc.get("image"):
            sc["shots"] = []
            continue
        k = max(1, int(round(sc["duration"] / shot_len)))
        base = sc["duration"] / k
        first = MOTION_TO_SHOT.get(sc.get("motion"), "wide_in")
        shots, prev = [], None
        for j in range(k):
            name = first if j == 0 else SEQ[(counter + j) % len(SEQ)]
            if name == prev:
                name = SEQ[(counter + j + 3) % len(SEQ)]
            if sc.get("beat") == "reveal" and j == k - 1 and k > 1:
                name = "creep"
            shot = {"name": name, "start": sc["start"] + j * base, "dur": base,
                    "jolt": bool(sc.get("beat") == "reveal" and j == 0)}
            bf = sc.get("board_focus")
            if bf and j == 0:   # kamera mengikuti benang dari barang bukti sebelumnya ke yang baru
                z = 1.35
                (ax, ay), (bx, by) = bf["from"], bf["to"]
                shot["name"] = "board_pan"
                shot["spec"] = {"z0": z, "z1": z + 0.12,
                                "f0": (_center_f(ax, z), _center_f(ay, z)),
                                "f1": (_center_f(bx, z + 0.12), _center_f(by, z + 0.12))}
            elif bf:            # setelah tiba: dekati barang bukti, lalu mundur melihat benang
                bx, by = bf["to"]
                if j % 2 == 1:
                    shot["name"] = "board_close"
                    shot["spec"] = {"z0": 1.65, "z1": 1.95, "f0": (_center_f(bx, 1.65), _center_f(by, 1.65)),
                                    "f1": (_center_f(bx, 1.95), _center_f(by, 1.95))}
                else:
                    shot["name"] = "board_wide"
                    shot["spec"] = {"z0": 1.0, "z1": 1.18, "f0": (.5, .5), "f1": (.5, .5)}
            shots.append(shot)
            prev = name
        counter += k
        sc["shots"] = shots


def inset_window(sc, look=None):
    """(mulai, selesai) detik RELATIF terhadap adegan untuk inset b-roll, atau None."""
    if look == "wayang" or not sc.get("broll_clip") or sc["duration"] < 4.2:
        return None
    t0 = 1.4
    t1 = min(t0 + 3.2, sc["duration"] - 1.0)
    return (t0, t1) if t1 - t0 >= 1.6 else None


def sfx_events(script, impacts, cfg):
    """Jadwal suara: whoosh pergantian adegan, riser+hantaman di reveal, detak jantung saat tegang."""
    ev, scenes = [], script["scenes"]
    heart = cfg["style"].get("heartbeat", False)
    look = cfg.get("look", "ink")
    for k, sc in enumerate(scenes):
        if k > 0:
            if look == "vhs":
                ev.append(("glitch", sc["start"] - 0.1, 0.30))          # semburat statis saat pindah rekaman
            elif look == "conspiracy":
                ev.append(("rustle", sc["start"] - 0.2, 0.32))          # kertas digeser
                ev.append(("thump", sc["start"] + 0.1, 0.30))           # foto ditempel
            else:
                ev.append(("whoosh", sc["start"] - 0.15, 0.22))
        if sc.get("beat") == "reveal":
            ev.append(("riser", sc["start"] - 1.2, 0.40))
            ev.append(("gong" if look == "wayang" else "hit", sc["start"], 0.65))
        if heart and sc.get("beat") in ("complication", "reveal"):
            t = sc["start"] + 0.6
            while t < sc["start"] + sc["duration"] - 0.5:
                ev.append(("thump", t, 0.50))
                ev.append(("thump", t + 0.24, 0.32))
                t += 0.95
        w = inset_window(sc, look)
        if w:
            ev.append(("whoosh", sc["start"] + w[0] - 0.05, 0.22))
    for t, _ in impacts:
        ev.append(("hit", t, 0.45))
    return ev


# ------------------------------------------------------------------ klip bidikan
def _grade(cfg):
    return f"{cfg['style']['grade']},format=yuv420p"


def shot_clip(img, shot, length, cfg, out):
    look = cfg.get("look", "ink")
    spec = shot.get("spec") or SHOTS[shot["name"]]
    d = max(int(round(length * FPS)), 3)
    # wayang: gerakan patah-patah (dalang) -> waktu gerak dikuantisasi per 5 bingkai
    on = "floor(on/5)*5" if look == "wayang" else "on"
    z = f"{spec['z0']}+({spec['z1']}-{spec['z0']})*{on}/{d}"
    (fx0, fy0), (fx1, fy1) = spec["f0"], spec["f1"]
    if look == "vhs":      # shaky cam POV orang pertama: goyang cepat + sentakan acak
        sway_x = "+26*sin(on*0.9)*sin(on*0.23)+12*sin(on*2.1+1.0)"
        sway_y = "+22*sin(on*0.7+0.5)*sin(on*0.19)+10*sin(on*1.7)"
        boil_x = "+9*sin(floor(on/2)*12.9898)"
        boil_y = "+9*sin(floor(on/2)*78.233)"
    elif look == "wayang":
        sway_x, sway_y = "+3*sin(on*0.05)", "+3*sin(on*0.04+0.8)"
        boil_x = boil_y = ""
    elif look == "conspiracy":
        sway_x, sway_y = "+7*sin(on*0.07)+4*sin(on*0.21+1.3)", "+6*sin(on*0.06+0.6)"
        boil_x = boil_y = ""
    else:                  # gaya komik lama
        sway_x, sway_y = "+9*sin(on*0.11)+5*sin(on*0.27+1.3)", "+7*sin(on*0.09+0.6)"
        boil_x, boil_y = "+5*sin(floor(on/3)*12.9898)", "+5*sin(floor(on/3)*78.233)"
    jolt_x = "+28*sin(on*2.7)*exp(-on/5)" if shot.get("jolt") else ""
    jolt_y = "+22*sin(on*3.3+1)*exp(-on/5)" if shot.get("jolt") else ""
    x = f"(iw-iw/zoom)*({fx0}+({fx1}-{fx0})*{on}/{d}){sway_x}{boil_x}{jolt_x}"
    y = f"(ih-ih/zoom)*({fy0}+({fy1}-{fy0})*{on}/{d}){sway_y}{boil_y}{jolt_y}"
    sharpen = "" if look == "vhs" else "unsharp=5:5:0.7,"
    vf = (
        "scale=2160:3840:force_original_aspect_ratio=increase:flags=lanczos,"
        "crop=2160:3840,setsar=1,"
        f"zoompan=z='{z}':x='{x}':y='{y}':d={d}:s=1080x1920:fps={FPS},"
        f"{sharpen}{_grade(cfg)}"
    )
    run(["ffmpeg", "-y", "-i", img, "-vf", vf, "-frames:v", d,
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", out])


def video_clip(src, dur, idx, cfg, out):
    """Footage pengganti (bila ilustrasi gagal): hitam-putih + zoom pelan; cadangan versi polos."""
    n = max(int(round(dur * FPS)), 3)
    z = f"1+0.06*on/{n}" if idx % 2 == 0 else f"1.06-0.06*on/{n}"
    enc = ["-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", out]
    look = f"{FOOTAGE_LOOK},{_grade(cfg)}"
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


# ------------------------------------------------------------------ efek per adegan
def scene_fx(src, sc, cfg, fxp, out, length):
    """Satu lintasan per adegan: efek khas style (VHS/papan/wayang) + overlay bergerak + inset b-roll."""
    st = cfg["style"]
    look = cfg.get("look", "ink")
    fx = list(sc.get("fx", []))
    base = ["null"]
    if look == "vhs":      # rekaman jadul: chroma bleed, noise berat, kedip kasar
        base.append("rgbashift=rh=4:bh=-4")
        base.append("noise=alls=22:allf=t+u")
        base.append("eq=brightness='0.05*sin(53*t)*sin(17*t)+0.02*sin(131*t)':eval=frame")
    elif look == "wayang":  # obor berkedip dari bawah
        base.append("eq=brightness='0.055*sin(19*t)*sin(5.3*t)+0.02*sin(47*t)':eval=frame")
    if st.get("heartbeat") and sc.get("beat") in ("complication", "reveal"):
        base.append("eq=brightness='0.045*pow(0.5+0.5*sin(6.6*t-2.389),12)':eval=frame")  # denyut ~detak suara
    if st.get("flicker") and look in ("ink",):
        base.append("eq=brightness='0.030*sin(23*t)*sin(7.3*t)+0.012*sin(61*t)':eval=frame")
    if "lightning" in fx:
        ta = 0.30 * length
        base.append(f"eq=brightness='0.55*lt(abs(t-{ta:.2f}),0.04)+0.40*lt(abs(t-{ta + 0.16:.2f}),0.05)':eval=frame")
    if "glitch" in fx or sc.get("beat") == "reveal":
        base.append("rgbashift=rh=-9:bh=9:enable='between(t,0.10,0.32)'")

    cmd = ["ffmpeg", "-y", "-i", src]
    parts = [f"[0:v]{','.join(base)}[b0]"]
    cur, idx = "b0", 1

    def add(png, x, y, enable=""):
        nonlocal cur, idx
        cmd.extend(["-framerate", FPS, "-i", png])
        nxt = f"o{idx}"
        en = f":enable='{enable}'" if enable else ""
        parts.append(f"[{idx}:v]format=yuva420p,loop=loop=-1:size=1[l{idx}]")
        parts.append(f"[{cur}][l{idx}]overlay=x='{x}':y='{y}':shortest=1{en}[{nxt}]")
        cur, idx = nxt, idx + 1

    if "fog" in fx and "fog_a" in fxp:
        add(fxp["fog_a"], "-mod(t*26,1080)", "0")
        add(fxp["fog_b"], "-1080+mod(t*41,1080)", "0")
    if "haze" in fx and "haze" in fxp:
        add(fxp["haze"], "-mod(t*18,1080)", "0")
    if "smoke" in fx and "smoke" in fxp:
        add(fxp["smoke"], "0", "-mod(t*34,1920)")
    if "batik" in fx and "batik" in fxp:
        add(fxp["batik"], "0", "0")
    if "dust" in fx and "dust" in fxp:
        add(fxp["dust"], "0", "-mod(t*38,1920)")
    if "embers" in fx and "embers" in fxp:
        add(fxp["embers"], "18*sin(t*1.7)", "-mod(t*74,1920)")
    if "rain" in fx and "rain" in fxp:
        add(fxp["rain"], "0", "-1920+mod(t*2300,1920)")
    if "scan" in fx and "scan" in fxp:
        add(fxp["scan"], "0", "0")
    if "tracking" in fx and "tracking" in fxp:   # pita tracking rusak muncul sesekali
        add(fxp["tracking"], "0", "-mod(t*210,1920)", enable="lt(mod(t,5.3),0.9)")
    if "glow" in fxp:
        add(fxp["glow"], "0", "0")
    if "lamp" in fx and "lamp" in fxp:           # lampu gantung yang bergoyang (bayangan bergerak)
        add(fxp["lamp"], "-540+260*sin(t*1.25)", "14*sin(t*2.5)")

    win = inset_window(sc, look)
    if win:
        t0, t1 = win
        cmd.extend(["-stream_loop", "-1", "-t", f"{t1 - t0 + 0.4:.2f}", "-i", sc["broll_clip"]])
        parts.append(
            f"[{idx}:v]fps={FPS},scale=440:580:force_original_aspect_ratio=increase,crop=440:580,"
            f"{FOOTAGE_LOOK},pad=iw+14:ih+14:7:7:color=white,pad=iw+8:ih+8:4:4:color=black,"
            f"setpts=PTS-STARTPTS+{t0}/TB[bro]"
        )
        slide_in = f"if(lt(t-{t0},0.45),(1-(t-{t0})/0.45)*(w+130),0)"
        slide_out = f"if(gt(t-{t1},-0.40),(t-{t1}+0.40)/0.40*(w+130),0)"
        parts.append(
            f"[{cur}][bro]overlay=x='W-w-56+{slide_in}+{slide_out}':y=430"
            f":enable='between(t,{t0},{t1})'[bx]"
        )
        cur = "bx"
    parts.append(f"[{cur}]format=yuv420p[v]")
    cmd += ["-filter_complex", ";".join(parts), "-map", "[v]", "-t", f"{length:.3f}",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", out]
    run(cmd)


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


def _transition(k, scenes, look=None):
    nxt = scenes[k + 1].get("beat")
    if nxt == "reveal":
        return "fadewhite"
    if nxt == "payoff":
        return "fadeblack"
    cyc = CYCLE_BY_LOOK.get(look, CYCLE)
    return cyc[k % len(cyc)]


# ------------------------------------------------------------------ render akhir
def render(script, cfg, theme, narration, ass_name, work: Path, out: Path, fxp, syn_path):
    work = work.resolve()
    scenes = script["scenes"]
    n = len(scenes)

    # 1) Klip per adegan (non-terakhir diperpanjang T agar xfade tidak memendekkan total)
    clips = []
    for i, sc in enumerate(scenes):
        length = sc["duration"] + (T if i < n - 1 else 0)
        raw = work / f"scene_raw{i:02d}.mp4"
        if sc.get("image"):
            parts, shots = [], sc["shots"]
            for j, sh in enumerate(shots):
                dur = sh["dur"] + (T if (j == len(shots) - 1 and i < n - 1) else 0)
                f = work / f"shot{i:02d}_{j}.mp4"
                try:
                    shot_clip(sc["image"], sh, dur, cfg, f)
                except RuntimeError:
                    print(f"Bidikan {i}-{j} gagal -> diganti bidikan sederhana")
                    shot_clip(sc["image"], dict(sh, name="wide_in", jolt=False), dur, cfg, f)
                parts.append(f)
            _concat(parts, raw)
        else:
            video_clip(sc["clip"], length, i, cfg, raw)

        final = work / f"scene_v{i:02d}.mp4"
        try:
            scene_fx(raw, sc, cfg, fxp, final, length)
        except RuntimeError:
            print(f"Efek adegan {i} gagal -> memakai klip tanpa efek tambahan")
            shutil.copy(raw, final)
        clips.append(final)

    # 2) Satu perintah akhir: xfade + bingkai + grain + subtitle + audio
    cmd = ["ffmpeg", "-y"]
    for c in clips:
        cmd += ["-i", c]
    nxt, i_frame = n, None
    if "frame" in fxp:
        i_frame, nxt = nxt, nxt + 1
        cmd += ["-framerate", FPS, "-i", fxp["frame"]]
    i_narr, i_syn = nxt, nxt + 1
    cmd += ["-i", Path(narration).resolve(), "-i", syn_path]

    music = pick_music(theme)
    mix = [f"[{i_narr}:a]asplit={3 if music else 2}[na][nb]" + ("[nc]" if music else "")]
    mix.append(f"[{i_syn}:a]aresample=44100,aformat=channel_layouts=stereo,volume=0.85[sx]")
    mix.append("[sx][na]sidechaincompress=threshold=0.03:ratio=3:attack=50:release=700[sd]")
    mix_inputs = "[nb][sd]"
    if music:
        print(f"Musik latar: {music}")
        cmd += ["-stream_loop", "-1", "-i", music.resolve()]
        mix.append(f"[{i_syn + 1}:a]aresample=44100,aformat=channel_layouts=stereo,volume=0.055[mu]")
        mix.append("[mu][nc]sidechaincompress=threshold=0.018:ratio=5:attack=80:release=1000[du]")
        mix_inputs += "[du]"
    else:
        print("Tidak ada musik di assets/music/ -> hanya narasi + suara latar horor.")
    mix.append(
        f"{mix_inputs}amix=inputs={3 if music else 2}:duration=first:normalize=0,"
        "loudnorm=I=-16:TP=-1.5:LRA=9[a]"
    )

    chains = [
        f"[{i}:v]fps={FPS},settb=AVTB,setpts=PTS-STARTPTS,format=yuv420p[v{i}]"
        for i in range(n)
    ]
    prev, acc = "v0", 0.0
    for k in range(n - 1):
        acc += scenes[k]["duration"]
        chains.append(
            f"[{prev}][v{k + 1}]xfade=transition={_transition(k, scenes, cfg.get("look"))}:duration={T}:offset={acc:.3f}[x{k + 1}]"
        )
        prev = f"x{k + 1}"
    if i_frame is not None:
        chains.append(f"[{i_frame}:v]format=yuva420p,loop=loop=-1:size=1[frm]")
        chains.append(f"[{prev}][frm]overlay=0:0:shortest=1[vo]")
    else:
        chains.append(f"[{prev}]null[vo]")
    grain = 14 if cfg.get("look") == "vhs" else 6
    chains.append(f"[vo]noise=alls={grain}:allf=t[vn]")
    chains.append(f"[vn]ass={ass_name}[v]")
    chains += mix

    cmd += [
        "-filter_complex", ";".join(chains), "-map", "[v]", "-map", "[a]",
        "-t", f"{script['total_duration']:.3f}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "24", "-maxrate", "9M", "-bufsize", "18M",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out.resolve(),
    ]
    run(cmd, cwd=work)  # cwd = work agar "ass=captions.ass" ditemukan

    thumb = out.with_name("thumbnail.jpg")
    run(["ffmpeg", "-y", "-ss", "1.2", "-i", out.resolve(), "-frames:v", "1", "-q:v", "2", thumb.resolve()])
    return thumb
