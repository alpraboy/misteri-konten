"""Agen suara: Edge-TTS (gratis) per adegan, lengkap dengan timestamp per kata."""
import asyncio
from pathlib import Path

import edge_tts

from util import run, duration

PAD = 0.48  # jeda alami antarscene agar narasi punya ruang bernapas


async def _tts(text, voice, rate, mp3_path):
    try:
        comm = edge_tts.Communicate(text, voice, rate=rate, boundary="WordBoundary")
    except TypeError:  # edge-tts versi lama
        comm = edge_tts.Communicate(text, voice, rate=rate)
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


def _even_words(text, dur):
    """Cadangan bila timestamp kata tidak tersedia: bagi rata sepanjang audio."""
    toks = text.split()
    step = dur / max(len(toks), 1)
    return [{"text": t, "start": i * step, "end": (i + 1) * step} for i, t in enumerate(toks)]


def synthesize(script, cfg, work: Path, rate=None):
    """Isi tiap scene dengan: wav, duration, start (global), words (global)."""
    work.mkdir(parents=True, exist_ok=True)
    t0 = 0.0
    wavs = []
    for i, sc in enumerate(script["scenes"]):
        mp3 = work / f"scene{i:02d}.mp3"
        wav = work / f"scene{i:02d}.wav"

        words = []
        for attempt in range(3):
            try:
                words = asyncio.run(_tts(sc["narration"], cfg["voice"], rate or cfg["rate"], mp3))
                if mp3.stat().st_size > 0:
                    break
            except Exception as e:  # jaringan/Edge kadang gagal sesaat
                print(f"TTS adegan {i} percobaan {attempt + 1} gagal: {e}")
                if attempt == 2:
                    raise
        run([
            "ffmpeg", "-y", "-i", mp3, "-af", f"apad=pad_dur={PAD}",
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
    if t0 > 62:
        print("PERINGATAN: lebih dari ~60 detik. Pertimbangkan memperpendek skrip.")
    return out
