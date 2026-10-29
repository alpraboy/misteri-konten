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
    for model in models:
        for attempt in range(3):
            r = requests.post(
                GEMINI_URL.format(model=model),
                headers={"x-goog-api-key": key, "Content-Type": "application/json"},
                json=body, timeout=120,
            )
            if r.status_code == 404:
                last = r.text[:300]
                print(f"Model {model} tidak tersedia (404), coba model berikutnya...")
                break
            if r.status_code in (429, 500, 502, 503):
                last = r.text[:300]
                print(f"Model {model} sibuk ({r.status_code}), menunggu...")
                time.sleep(8 * (attempt + 1))
                continue
            if r.status_code >= 400:
                print(r.text[:500])
            r.raise_for_status()
            parts = r.json()["candidates"][0]["content"]["parts"]
            text = "".join(p.get("text", "") for p in parts)
            text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
            print(f"Model dipakai: {model}")
            return json.loads(text)
    raise RuntimeError(f"Semua model Gemini gagal. Respons terakhir: {last}")


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


SCHEMA = """{
  "title": "judul video, maks 70 karakter, memancing rasa penasaran",
  "scenes": [
    {
      "narration": "narasi adegan, 10-20 kata, bahasa Indonesia lisan yang enak didengar",
      "keywords": ["2-3 kata kunci footage BAHASA INGGRIS, visual konkret", "alternatif"],
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

    prompt = f"""Kamu penulis skrip video pendek vertikal (YouTube Shorts/TikTok) bertema {cfg['label']}.
Gaya: {cfg['tone']}

{source_note}

{material}

Aturan:
- Total narasi 130-155 kata (muat sekitar 60 detik), dibagi 8-11 adegan.
- Adegan 1 adalah HOOK 1-2 kalimat yang membuat orang berhenti scroll. Adegan terakhir: penutup/pertanyaan terbuka.
- Hindari kekerasan grafis, SARA, dan konten untuk menakut-nakuti anak.
- Kata kunci footage harus konkret & bisa ditemukan di stok video (mis. "foggy forest night", "old stone ruins"), bukan konsep abstrak.
- Isi "claims_to_verify" dengan klaim faktual penting (nama, tanggal, angka).

Balas HANYA JSON dengan bentuk:
{SCHEMA}"""

    data = _gemini(prompt)
    scenes = data.get("scenes", [])
    if not (5 <= len(scenes) <= 14):
        raise RuntimeError(f"Jumlah adegan tidak wajar: {len(scenes)}")
    for s in scenes:
        s["narration"] = s["narration"].strip()
        kw = s.get("keywords") or []
        s["keywords"] = [kw] if isinstance(kw, str) else list(kw)
        s["onscreen"] = (s.get("onscreen") or "").strip()
    data["topic"] = topic
    data["source_urls"] = source_urls
    words = sum(len(s["narration"].split()) for s in scenes)
    print(f"Skrip: {len(scenes)} adegan, {words} kata")
    return data
