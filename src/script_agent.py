"""Agen skrip: memilih topik, mengambil sumber, lalu menulis skrip 60 detik (JSON)."""
import json
import os
import random
import re
import time
from datetime import date

import requests

import sources

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


# Nama model bisa dipensiunkan Google (gemini-2.5-* berhenti 16 Okt 2026).
# Alias "-latest" otomatis menunjuk model terbaru; sisanya cadangan.
MODELS = ["gemini-flash-latest", "gemini-3-flash-preview", "gemini-flash-lite-latest"]


def _gemini(prompt, temperature=0.9):
    key = os.environ["GEMINI_API_KEY"]
    env_model = os.environ.get("GEMINI_MODEL", "").strip()
    models = ([env_model] if env_model else []) + MODELS
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": temperature,
            "responseMimeType": "application/json",
        },
    }
    last = None
    for round_ in range(3):  # ulangi seluruh daftar model bila semuanya sedang sibuk
        for model in models:
            for attempt in range(2):
                try:
                    r = requests.post(
                        GEMINI_URL.format(model=model),
                        headers={"x-goog-api-key": key, "Content-Type": "application/json"},
                        json=body, timeout=(15, 150),
                    )
                except (requests.Timeout, requests.ConnectionError) as e:
                    last = f"{type(e).__name__}"
                    print(f"Model {model} timeout/koneksi putus, coba lagi...")
                    time.sleep(5)
                    continue
                if r.status_code == 404:
                    last = r.text[:300]
                    print(f"Model {model} tidak tersedia (404), coba model berikutnya...")
                    break
                if r.status_code in (429, 500, 502, 503, 504):
                    last = f"{r.status_code} {r.text[:200]}"
                    print(f"Model {model} sibuk ({r.status_code}), menunggu...")
                    time.sleep(6 * (attempt + 1))
                    continue
                if r.status_code >= 400:
                    print(r.text[:500])
                r.raise_for_status()
                try:
                    parts = r.json()["candidates"][0]["content"]["parts"]
                    text = "".join(p.get("text", "") for p in parts)
                    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
                    data = json.loads(text)
                except (KeyError, IndexError, ValueError) as e:
                    last = f"respons tidak valid: {e}"
                    print(f"Model {model} mengembalikan respons tak valid, coba lagi...")
                    continue
                print(f"Model dipakai: {model}")
                return data
        print(f"Putaran {round_ + 1} gagal semua; menunggu sebelum mengulang...")
        time.sleep(20)
    raise RuntimeError(f"Semua model Gemini gagal. Terakhir: {last}")


def _pick_topic(theme, cfg, topic):
    """Kembalikan kata kunci topik. Bila kosong, minta model mengusulkan."""
    if topic.strip():
        return topic.strip()
    if cfg["source"] == "news":
        return cfg["topic_hint"]  # query RSS, bukan topik tunggal
    region = random.choice(cfg["regions"])
    prompt = (
        f"Hari ini {date.today().isoformat()}. Usulkan 1 topik untuk video pendek bertema "
        f"{cfg['topic_hint']} dengan latar/wilayah: {region}. "
        'Balas JSON: {"topic": "kata kunci pencarian singkat 2-5 kata"}'
    )
    return _gemini(prompt, temperature=1.0)["topic"].strip()


MOTIONS = ["zoom_in", "zoom_out", "pan_left", "pan_right", "tilt_up", "tilt_down"]

SCHEMA = """{
  "title": "judul video, maks 70 karakter, memancing rasa penasaran",
  "character": "deskripsi visual tokoh utama dalam BAHASA INGGRIS, 25-40 kata, tetap (usia, pakaian, ciri khas); kosongkan bila tidak ada tokoh",
  "scenes": [
    {
      "narration": "narasi adegan, 10-20 kata, bahasa Indonesia lisan yang enak didengar",
      "visual": "illustration atau footage",
      "image_prompt": "BAHASA INGGRIS: subjek, aksi, latar, sudut kamera, suasana. Tanpa teks/huruf di gambar.",
      "with_character": true,
      "keywords": [],
      "motion": "salah satu dari: zoom_in, zoom_out, pan_left, pan_right, tilt_up, tilt_down",
      "impact_word": "SATU kata penting yang persis ada di narasi adegan ini untuk dimunculkan raksasa; kosongkan bila tidak perlu",
      "onscreen": "teks besar di layar, maks 5 kata, boleh kosong"
    }
  ],
  "caption": "deskripsi 1-2 kalimat untuk unggahan",
  "hashtags": ["#misteri", "..."],
  "claims_to_verify": ["klaim faktual penting yang perlu dicek manusia sebelum upload"]
}"""


def generate(theme, cfg, topic=""):
    topic = _pick_topic(theme, cfg, topic)
    material, source_note, source_urls = "", "", []

    if cfg["source"] == "wikipedia":
        res = sources.wikipedia_context(topic)
        if res:
            title, text, url = res
            material = f"SUMBER (Wikipedia: {title}):\n{text}"
            source_note = "Gunakan HANYA fakta yang ada di SUMBER. Jangan menambah tanggal, nama, atau angka dari luar sumber."
            source_urls.append(url)
        else:
            source_note = "Sumber tidak ditemukan. Gunakan hanya fakta yang sangat umum dan pasti; tandai sisanya sebagai teori."
    elif cfg["source"] == "news":
        items = sources.news_headlines(topic, cfg.get("news_window", "7d"))
        if not items:
            raise RuntimeError("Tidak ada berita ditemukan untuk query ini. Coba isi topik lain.")
        lines = [f"- {i['title']} ({i['date']})" for i in items]
        material = "JUDUL BERITA TERBARU:\n" + "\n".join(lines)
        source_note = (
            "Pilih SATU peristiwa paling menarik dari daftar judul. Gunakan HANYA informasi yang tersirat "
            "dari judul; jangan mengarang detail. Pakai frasa 'dilaporkan' / 'menurut pemberitaan'. "
            "Jangan menuduh individu."
        )
        source_urls += [i["link"] for i in items[:3]]
    else:  # cerita
        source_note = (
            f"Tema/wilayah: {topic}. Ini cerita legenda/fiksi. Jangan menyebut kejadian nyata terbaru "
            "atau nama orang sungguhan. Sebutkan di narasi bahwa ini kisah/legenda."
        )

    prompt = f"""Kamu penulis skrip + storyboard video pendek vertikal (YouTube Shorts/TikTok) bertema {cfg['label']}.
Gaya narasi: {cfg['tone']}
Gaya visual: cinematic mystery documentary, graphic-novel illustration yang matang, hitam-putih/warna redup dengan satu aksen warna. Kamera dan komposisi harus terasa seperti dokumenter, bukan slideshow template.

{source_note}

{material}

Aturan:
- Total narasi 85-100 kata, dibagi 7-8 adegan. Utamakan kalimat jelas, jeda alami, dan tempo tenang; satu ide utama per adegan. Sisakan ruang bernapas; jangan memadatkan terlalu banyak informasi per kalimat.
- Adegan 1 adalah HOOK 1-2 kalimat yang membuat orang berhenti scroll. Adegan terakhir: penutup/pertanyaan terbuka.
- "character": buat SATU tokoh utama bila ceritanya butuh tokoh (deskripsi visual tetap, bahasa Inggris). Set "with_character": true pada adegan yang menampilkan tokoh itu.
- Hampir semua adegan "visual": "illustration". Gunakan "footage" PALING BANYAK 2 adegan di tengah, hanya untuk suasana umum yang mudah dicari di stok video (mis. "foggy forest", "ocean waves", "night sky"); isi "keywords" 2 alternatif berbahasa Inggris. Adegan pertama dan terakhir harus illustration.
- "impact_word": isi string kosong pada semua adegan; jangan gunakan teks raksasa yang mengganggu narasi.
- Komposisi gambar harus SEDERHANA agar hasil AI tidak berantakan: satu subjek utama yang jelas, hindari kerumunan, hindari close-up tangan/wajah; lebih baik siluet, tokoh dari belakang, atau pemandangan/bangunan.
- "image_prompt" wajib menggambarkan tepat isi narasi adegan itu, bukan gambar misterius generik. Rancang urutan visual: establishing wide shot untuk lokasi, medium shot untuk aksi, close-up hanya untuk bukti/objek penting, lalu wide/quiet shot untuk penutup. Setiap adegan harus menambah informasi visual baru. Pertahankan palet, era, cuaca, dan desain tokoh yang konsisten. Jangan ada teks atau huruf di dalam gambar.
- Jangan menggambarkan orang sungguhan secara spesifik; gunakan tokoh gambar/siluet anonim. Hindari gore dan kekerasan grafis, SARA, dan konten untuk anak.
- "motion": gerak kamera harus sangat halus dan punya alasan. Gunakan zoom_in hanya saat mengungkap detail, zoom_out untuk memperlihatkan konteks, pan untuk lokasi lebar, tilt untuk bangunan/langit. Hindari gerak kamera pada tiap adegan secara berlebihan; variasikan dengan tenang.
- Isi "claims_to_verify" dengan klaim faktual penting (nama, tanggal, angka).
- "onscreen" opsional dan maksimal 3-4 kata; gunakan hanya untuk lokasi, tahun, atau konsep penting. Jangan mengulang narasi sebagai teks besar.
- Rasa akhir: dokumenter sinematik yang elegan, misterius, mudah diikuti, tidak ramai, tanpa jumpscare visual.

Balas HANYA JSON dengan bentuk:
{SCHEMA}"""

    data = _gemini(prompt)
    scenes = data.get("scenes", [])
    if not (5 <= len(scenes) <= 14):
        raise RuntimeError(f"Jumlah adegan tidak wajar: {len(scenes)}")

    footage_used = 0
    for i, s in enumerate(scenes):
        s["narration"] = s["narration"].strip()
        kw = s.get("keywords") or []
        s["keywords"] = [kw] if isinstance(kw, str) else list(kw)
        s["onscreen"] = (s.get("onscreen") or "").strip()
        s["image_prompt"] = (s.get("image_prompt") or "").strip()
        s["impact_word"] = (s.get("impact_word") or "").strip().split(" ")[0]

        vis = s.get("visual", "illustration")
        if vis == "footage" and (i in (0, len(scenes) - 1) or footage_used >= 2 or not s["keywords"]):
            vis = "illustration"
        if vis != "footage":
            vis = "illustration"
        else:
            footage_used += 1
        if vis == "illustration" and not s["image_prompt"]:
            s["image_prompt"] = ", ".join(s["keywords"]) or "mysterious atmospheric scene, dramatic shadows"
        s["visual"] = vis
        s["with_character"] = bool(s.get("with_character"))
        if s.get("motion") not in MOTIONS:
            s["motion"] = MOTIONS[i % len(MOTIONS)]

    kept = 0
    for s in scenes:  # batasi kata raksasa maksimal 6 per video
        if s["impact_word"]:
            kept += 1
            if kept > 6:
                s["impact_word"] = ""
    data["character"] = (data.get("character") or "").strip()
    data["topic"] = topic
    data["source_urls"] = source_urls
    words = sum(len(s["narration"].split()) for s in scenes)
    print(f"Skrip: {len(scenes)} adegan ({footage_used} footage), {words} kata")
    return data
