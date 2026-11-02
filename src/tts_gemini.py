"""Suara VO ekspresif lewat Gemini TTS (memakai GEMINI_API_KEY yang sama).

Gemini TTS tidak memberi penanda waktu per kata, jadi waktu kata diperkirakan dari panjang kata
di dalam rentang suara yang terdeteksi. Bila Gemini TTS tidak tersedia (kuota/tier gratis/model),
`TTSUnavailable` dilempar dan pemanggil memakai Edge-TTS untuk SELURUH video agar suara tidak campur.
"""
import base64
import os
import re
import time
import wave
from pathlib import Path

import requests

URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
# Nama model berubah-ubah; dicoba berurutan. Bisa dipaksa lewat env GEMINI_TTS_MODEL.
MODELS = ["gemini-2.5-flash-preview-tts", "gemini-3.1-flash-tts-preview", "gemini-3.8-flash-tts"]


class TTSUnavailable(RuntimeError):
    """Gemini TTS tidak dapat dipakai (kuota, tier, kunci, model)."""


def _payload(shape, text, style, voice):
    if shape == "prebuilt":   # bentuk lama: gaya ditulis di awal teks ("Say ...: teks")
        t = f"{style}: {text}" if style else text
        return {
            "contents": [{"parts": [{"text": t}]}],
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}},
            },
        }
    part = {"text": text}      # bentuk baru: gaya di speech_metadata
    if style:
        part["speech_metadata"] = {"style": style}
    return {
        "contents": [{"role": "user", "parts": [part]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {"voiceConfig": {"voice": voice}},
        },
    }


def _extract(resp_json):
    """Ambil (pcm_bytes, sample_rate) dari respons; ValueError bila tidak ada audio."""
    for cand in resp_json.get("candidates", []):
        for part in (cand.get("content") or {}).get("parts", []):
            inline = part.get("inlineData") or part.get("inline_data")
            if inline and inline.get("data"):
                mime = inline.get("mimeType") or inline.get("mime_type") or ""
                m = re.search(r"rate=(\d+)", mime)
                return base64.b64decode(inline["data"]), int(m.group(1)) if m else 24000
    raise ValueError("respons tanpa audio")


def speech_span(pcm: bytes, rate: int):
    """Perkirakan awal & akhir suara (detik) dengan ambang amplitudo sederhana."""
    import numpy as np

    a = np.frombuffer(pcm[: len(pcm) // 2 * 2], dtype="<i2").astype("float32")
    if a.size == 0:
        return 0.0, 0.0
    thr = max(250.0, 0.04 * float(np.abs(a).max()))
    idx = np.nonzero(np.abs(a) > thr)[0]
    if idx.size == 0:
        return 0.0, a.size / rate
    return max(idx[0] / rate - 0.05, 0.0), min(idx[-1] / rate + 0.12, a.size / rate)


def estimate_words(text, start, end):
    """Bagi rentang suara ke kata menurut panjangnya; koma/titik diberi bobot jeda."""
    toks = text.split()
    if not toks:
        return []
    weights = []
    for t in toks:
        w = len(re.sub(r"\W", "", t)) + 1.5
        if t.endswith((",", ";", ":")):
            w += 2.5
        elif t.endswith((".", "!", "?", "...")):
            w += 4.5
        weights.append(w)
    total, span, t0, out = sum(weights), max(end - start, 0.2), start, []
    for tok, w in zip(toks, weights):
        d = span * w / total
        out.append({"text": tok, "start": t0, "end": t0 + d * 0.92})
        t0 += d
    return out


def write_wav(pcm: bytes, rate: int, path: Path):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)


class GeminiTTS:
    def __init__(self, voice, style, key=None, gap=None):
        self.key = key or os.environ.get("GEMINI_API_KEY", "")
        if not self.key:
            raise TTSUnavailable("GEMINI_API_KEY kosong")
        self.voice = os.environ.get("GEMINI_TTS_VOICE", "").strip() or voice
        self.style = os.environ.get("GEMINI_TTS_STYLE", "").strip() or style
        forced = os.environ.get("GEMINI_TTS_MODEL", "").strip()
        self.models = ([forced] if forced else []) + [m for m in MODELS if m != forced]
        self.gap = float(os.environ.get("GEMINI_TTS_GAP", "7")) if gap is None else gap
        self.working = None      # (model, shape) yang sudah terbukti jalan
        self._last = 0.0

    def _post(self, model, shape, text, style):
        wait = self._last + self.gap - time.time()
        if wait > 0:
            time.sleep(wait)
        r = requests.post(
            URL.format(model=model),
            headers={"x-goog-api-key": self.key, "Content-Type": "application/json"},
            json=_payload(shape, text, style, self.voice), timeout=(15, 120),
        )
        self._last = time.time()
        return r

    def _call(self, text, style):
        """Satu panggilan sukses -> (pcm, rate). Menemukan model/bentuk yang bekerja bila belum ada."""
        combos = [self.working] if self.working else [(m, s) for m in self.models for s in ("prebuilt", "speech")]
        last = ""
        for model, shape in combos:
            for attempt in range(3):
                try:
                    r = self._post(model, shape, text, style)
                except requests.RequestException as e:
                    last = type(e).__name__
                    time.sleep(4)
                    continue
                body = r.text[:600]
                if r.status_code == 200:
                    try:
                        pcm, rate = _extract(r.json())
                        self.working = (model, shape)
                        return pcm, rate
                    except ValueError as e:
                        last = f"{model}/{shape}: {e}"
                        break
                if r.status_code in (401, 403):
                    raise TTSUnavailable(f"kunci ditolak/akses TTS belum aktif ({r.status_code}): {body[:160]}")
                if r.status_code == 429:
                    if re.search(r"PerDay|per day|limit: 0", body, re.I):
                        raise TTSUnavailable(f"kuota Gemini TTS habis/tidak tersedia di tier gratis: {body[:200]}")
                    m = re.search(r'"retryDelay":\s*"(\d+)', body)
                    time.sleep(min(int(m.group(1)) + 2 if m else 25, 70))
                    last = "429"
                    continue
                if r.status_code in (500, 502, 503, 504):
                    time.sleep(6 * (attempt + 1))
                    last = str(r.status_code)
                    continue
                last = f"{model}/{shape}: HTTP {r.status_code} {body[:140]}"
                break   # 400/404 -> coba kombinasi berikutnya
        raise TTSUnavailable(f"tidak ada model Gemini TTS yang berhasil ({last})")

    def synthesize(self, text, wav_path: Path):
        """Tulis WAV mentah; kembalikan list kata dengan waktu (detik, relatif awal berkas)."""
        pcm, rate = self._call(text, self.style)
        dur = len(pcm) / 2 / rate
        expected = len(text) / 13.0
        if self.style and dur > expected * 1.9 + 1.5:   # curiga instruksi gaya ikut terbaca
            print(f"  durasi {dur:.1f}s jauh melebihi perkiraan {expected:.1f}s -> ulang tanpa instruksi gaya")
            pcm, rate = self._call(text, "")
        write_wav(pcm, rate, wav_path)
        start, end = speech_span(pcm, rate)
        return estimate_words(text, start, end)
