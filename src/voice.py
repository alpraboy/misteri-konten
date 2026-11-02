"""Agen suara: Edge-TTS (gratis) per adegan, lengkap dengan timestamp per kata."""
import asyncio
import os
import re
from pathlib import Path

from util import run, duration

PAD = 0.48  # jeda alami antarscene agar narasi punya ruang bernapas


async def _tts(text, voice, rate, mp3_path, pitch="+0Hz"):
    import edge_tts  # impor di sini agar uji lokal tanpa edge-tts tetap jalan
    try:
        comm = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch, boundary="WordBoundary")
    except TypeError:  # edge-tts versi lama
        comm = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    words = []
    with open(mp3_path, "wb") as f:
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                start = chunk["offset"] / 1e7
                words.append({
                    "text": chunk["text"],
                    "start": start,
                    "end": start + chunk["duration"] / 1e7,
                })
    return words


# Prosodi per tahap cerita (selisih rate %, selisih pitch Hz): makin tegang makin pelan & rendah
BEAT_PROSODY = {"hook": (-2, -2), "context": (0, 0), "clue": (-2, -2),
                "complication": (-6, -6), "reveal": (-10, -10), "payoff": (-8, -8)}


def _num(text):
    m = re.match(r"\s*([+-]?\d+)", str(text))
    return int(m.group(1)) if m else 0


def _prosody(rate, pitch, beat):
    """Rate/pitch Edge-TTS untuk satu adegan, disesuaikan dengan tahap ceritanya."""
    dr, dp = BEAT_PROSODY.get(str(beat or "").lower(), (0, 0))
    r = max(-45, min(25, _num(rate) + dr))
    p = max(-40, min(20, _num(pitch) + dp))
    return f"{r:+d}%", f"{p:+d}Hz"


def _even_words(text, dur):
    """Cadangan bila timestamp kata tidak tersedia: bagi rata sepanjang audio."""
    toks = text.split()
    step = dur / max(len(toks), 1)
    return [{"text": t, "start": i * step, "end": (i + 1) * step} for i, t in enumerate(toks)]


def _raw_gemini(script, cfg, work: Path):
    """Semua adegan lewat Gemini TTS. Gagal satu = gagal semua (supaya suara tidak campur)."""
    import tts_gemini
    t = cfg.get("tts") or {}
    engine = tts_gemini.GeminiTTS(t.get("voice", "Charon"), t.get("style", ""))
    print(f"Suara: Gemini TTS, suara '{engine.voice}'")
    out = []
    for i, sc in enumerate(script["scenes"]):
        raw = work / f"raw{i:02d}.wav"
        words = engine.synthesize(sc["narration"], raw)
        print(f"  adegan {i}: ok (model {engine.working[0]})" if engine.working else f"  adegan {i}: ok")
        out.append((raw, words))
    return out


def _raw_edge(script, cfg, work: Path, rate):
    print(f"Suara: Edge-TTS ({cfg['voice']})")
    out = []
    for i, sc in enumerate(script["scenes"]):
        mp3 = work / f"scene{i:02d}.mp3"
        words = []
        for attempt in range(3):
            try:
                r_i, p_i = _prosody(rate or cfg["rate"], cfg.get("pitch", "+0Hz"), sc.get("beat"))
                words = asyncio.run(_tts(sc["narration"], cfg["voice"], r_i, mp3, p_i))
                if mp3.stat().st_size > 0:
                    break
            except Exception as e:  # jaringan/Edge kadang gagal sesaat
                print(f"TTS adegan {i} percobaan {attempt + 1} gagal: {e}")
                if attempt == 2:
                    raise
        out.append((mp3, words))
    return out


def synthesize(script, cfg, work: Path, rate=None):
    """Isi tiap scene dengan: wav, duration, start (global), words (global).

    Mesin suara: env TTS_ENGINE = auto (Gemini lalu cadangan Edge) | gemini | edge.
    """
    work.mkdir(parents=True, exist_ok=True)
    engine = os.environ.get("TTS_ENGINE", "auto").strip().lower()
    raws, used = None, "edge"
    if engine in ("auto", "gemini") and os.environ.get("GEMINI_API_KEY"):
        try:
            raws, used = _raw_gemini(script, cfg, work), "gemini"
        except Exception as e:
            print(f"Gemini TTS tidak dipakai: {e}")
            if engine == "gemini":
                raise
            print("-> memakai Edge-TTS untuk seluruh video.")
    if raws is None:
        raws = _raw_edge(script, cfg, work, rate)

    # Efek suara bernuansa horor hanya untuk Edge-TTS (Gemini sudah ekspresif). VOICE_FX=0 mematikan.
    fx = cfg.get("voice_fx", "") if used == "edge" and os.environ.get("VOICE_FX", "1") != "0" else ""
    if fx:
        print("Efek suara style aktif untuk Edge-TTS.")
    af = f"{fx},apad=pad_dur={PAD}" if fx else f"apad=pad_dur={PAD}"

    t0 = 0.0
    wavs = []
    for i, (sc, (src, words)) in enumerate(zip(script["scenes"], raws)):
        wav = work / f"scene{i:02d}.wav"
        run([
            "ffmpeg", "-y", "-i", src, "-af", af,
            "-ar", "44100", "-ac", "2", wav,
        ])
        dur = duration(wav)
        if not words:
            words = _even_words(sc["narration"], dur - PAD)

        sc["wav"] = str(wav)
        sc["duration"] = dur
        sc["start"] = t0
        sc["words"] = [
            {"text": w["text"], "start": t0 + w["start"], "end": t0 + w["end"]} for w in words
        ]
        wavs.append(wav)
        t0 += dur

    lst = work / "narration.txt"
    lst.write_text("".join(f"file '{w.resolve()}'\n" for w in wavs))
    out = work / "narration.wav"
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", out])
    script["total_duration"] = t0
    print(f"Durasi total narasi: {t0:.1f} detik")
    if not 60 <= t0 <= 90:
        print(f"PERINGATAN: durasi {t0:.1f} detik di luar target v6 60-90 detik; jangan percepat suara secara paksa.")
    else:
        print("Durasi sesuai target v6: 60-90 detik.")
    return out
