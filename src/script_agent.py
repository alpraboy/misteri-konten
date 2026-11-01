"""Agen skrip: memilih topik, mengambil sumber, lalu menulis skrip 60 detik (JSON)."""
import json
import os
import random
import re
import time
from datetime import date

import requests

import sources
import styles

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
  "style": "MYSTERY_VHS atau MYSTERY_CONSPIRACY atau MYSTERY_WAYANG (WAJIB pilih tepat satu)",
  "style_reason": "alasan singkat 1 kalimat mengapa style itu paling cocok",
  "title": "judul video, maks 70 karakter, memancing rasa penasaran",
  "character": "deskripsi visual tokoh utama dalam BAHASA INGGRIS, 25-40 kata, tetap (usia, pakaian, ciri khas); kosongkan bila tidak ada tokoh",
  "scenes": [
    {
      "narration": "narasi adegan, 10-20 kata, bahasa Indonesia lisan yang enak didengar",
      "visual": "illustration",
      "image_prompt": "BAHASA INGGRIS: subjek, aksi, latar, sudut kamera, suasana horor/mistis. Tanpa teks/huruf di gambar.",
      "with_character": true,
      "keywords": [],
      "broll_keywords": [],
      "motion": "salah satu dari: zoom_in, zoom_out, pan_left, pan_right, tilt_up, tilt_down",
      "emphasis": ["kata penting yang persis ada di narasi"],
      "impact_word": "SATU kata yang persis ada di narasi untuk dimunculkan raksasa; kosongkan bila tidak perlu",
      "onscreen": "label singkat maks 4 kata (lokasi/tahun/konsep), boleh kosong",
      "beat": "hook, context, clue, complication, reveal, atau payoff",
      "visual_role": "establishing, action, evidence, comparison, atau closing"
    }
  ],
  "caption": "deskripsi 1-2 kalimat untuk unggahan",
  "hashtags": ["#misteri", "..."],
  "claims_to_verify": ["klaim faktual penting yang perlu dicek manusia sebelum upload"]
}"""


def generate(theme, cfg, topic="", style=None):
    topic = _pick_topic(theme, cfg, topic)
    material, source_note, source_urls = "", "", []

    if cfg["source"] == "wikipedia":
        res = sources.wikipedia_context(topic)
        if res:
            title, text, url = res
            material = f"SUMBER (Wikipedia: {title}):\n{text}"
            source_note = "Gunakan HANYA fakta yang ada di SUMBER. Jangan menambah tanggal, nama, atau angka dari luar sumber."
            source_urls.append(url)
        else:  # coba Wikipedia Inggris dengan kata kunci yang diterjemahkan
            try:
                en = _gemini(
                    f'Terjemahkan topik ini menjadi kata kunci pencarian Wikipedia bahasa Inggris (2-5 kata): "{topic}". '
                    'Balas JSON: {"q": "..."}', temperature=0.2)["q"]
                res = sources.wikipedia_context(str(en), lang="en")
            except Exception:
                res = None
            if not res:
                raise RuntimeError(
                    f"Sumber Wikipedia tidak ditemukan untuk topik '{topic}'. "
                    "Produksi faktual dihentikan agar agen tidak mengarang fakta. Coba topik yang lebih spesifik."
                )
            title, text, url = res
            material = f"SUMBER (Wikipedia Inggris: {title}; tulis narasi dalam bahasa Indonesia):\n{text}"
            source_note = "Gunakan HANYA fakta yang ada di SUMBER. Jangan menambah tanggal, nama, atau angka dari luar sumber."
            source_urls.append(url)
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

    forced = None
    if style and str(style).strip().lower() not in ("", "auto"):
        forced = styles.normalize(style, theme)
    if forced:
        st = styles.STYLES[forced]
        style_block = (
            f"Gaya visual SUDAH DITENTUKAN: {forced} ({st['label']}). Isi \"style\" dengan {forced}.\n"
            f"Aturan adegan style ini: {st['scene_rule']}"
        )
    else:
        rules = "\n".join(f"  * {k}: {v['scene_rule']}" for k, v in styles.STYLES.items())
        style_block = (
            "Agen editing HANYA punya 3 style visual dan WAJIB memilih TEPAT SATU yang paling cocok dengan tujuan "
            f"video ini:\n{styles.choice_brief()}\nAturan adegan per style:\n{rules}\n"
            "Isi \"style\" dengan kode style terpilih dan \"style_reason\" dengan alasan singkat."
        )

    prompt = f"""Kamu penulis skrip + storyboard video pendek vertikal (YouTube Shorts/TikTok) bertema {cfg['label']}.
Gaya narasi: {cfg['tone']}
{style_block}

{source_note}

{material}

Aturan RETENTION ENGINE v6:
- Total narasi 145-175 kata, dibagi 9-12 adegan, target hasil audio 60-90 detik pada tempo tenang. Satu gagasan utama per adegan, kalimat lisan natural, tidak terburu-buru.
- Urutan cerita wajib: hook (0-3 detik), context, clue, complication/kontradiksi, reveal yang didukung fakta, lalu payoff/penutup. Jangan membuat clickbait yang tidak terjawab.
- Setiap 1-3 adegan harus menambahkan informasi baru atau pertanyaan spesifik; jangan mengulang kalimat dengan sinonim. Bangun rasa ingin tahu tanpa menahan fakta penting secara menyesatkan.
- Adegan 1 adalah hook konkret: detail paling ganjil/konflik yang benar-benar ada dalam sumber atau premis fiksi. Jangan mulai dengan salam, logo, atau pengantar umum. Adegan terakhir memberi jawaban/kesimpulan yang memuaskan, lalu pertanyaan relevan jika cocok.
- Untuk tema faktual, jangan menyebut klaim yang tidak didukung bahan sumber. Bedakan fakta, dugaan, dan teori dengan bahasa eksplisit. Jika sumber tidak cukup, katakan bukti terbatas dan jangan mengarang pengungkapan. Untuk berita, sumber input hanya headline; jangan menyimpulkan detail yang tidak ada di headline.
- Setiap scene harus punya beat dan visual_role sesuai schema; variasikan establishing, action, evidence, comparison, closing. Jangan menambahkan label beat, progress bar, atau dekorasi layar yang tidak diperlukan. Subtitle harus mudah dibaca dan tidak menutupi objek utama.
- Jangan memaksa cliffhanger palsu; penonton harus mendapat nilai/penjelasan yang dijanjikan di hook.
- "character": buat SATU tokoh utama bila ceritanya butuh tokoh (deskripsi visual tetap, bahasa Inggris). Set "with_character": true pada adegan yang menampilkan tokoh itu.
- SEMUA adegan "visual": "illustration" (gambar sesuai style terpilih, spesifik terhadap isi narasi). Footage hanya sebagai INSET KECIL: isi "broll_keywords" (2-3 frasa Inggris yang konkret & bisa dicari, mis. "old stone temple", "foggy forest", BUKAN "mystery"/"cinematic") pada PALING BANYAK 3 adegan tengah yang memang punya objek/tempat nyata; selain itu biarkan []. Adegan pertama dan terakhir tanpa b-roll.
- "impact_word": isi di 3-4 adegan saja (momen paling menegangkan/mengejutkan), satu kata persis seperti di narasi, tanpa tanda baca; selain itu string kosong. "emphasis": 1-3 kata kunci per adegan (persis seperti di narasi) yang akan ditampilkan beraksen di subtitle.
- Komposisi gambar harus SEDERHANA agar hasil AI tidak berantakan: satu subjek utama yang jelas, hindari kerumunan, hindari close-up tangan/wajah; lebih baik siluet, tokoh dari belakang, atau pemandangan/bangunan.
- "image_prompt" wajib menggambarkan tepat isi narasi adegan itu, bukan gambar misterius generik. Rancang urutan visual: establishing wide shot untuk lokasi, medium shot untuk aksi, close-up hanya untuk bukti/objek penting, lalu wide/quiet shot untuk penutup. Setiap adegan harus menambah informasi visual baru. Pertahankan palet, era, cuaca, dan desain tokoh yang konsisten. Jangan ada teks atau huruf di dalam gambar.
- Jangan menggambarkan orang sungguhan secara spesifik; gunakan tokoh gambar/siluet anonim. Hindari gore dan kekerasan grafis, SARA, dan konten untuk anak.
- "motion": gerak kamera pembuka tiap adegan: zoom_in untuk ketegangan/detail, zoom_out untuk konteks, pan untuk lokasi lebar, tilt untuk bangunan/langit; variasikan antar adegan.
- Isi "claims_to_verify" dengan klaim faktual penting (nama, tanggal, angka).
- "onscreen" opsional dan maksimal 3-4 kata; gunakan hanya untuk lokasi, tahun, atau konsep penting. Jangan mengulang narasi sebagai teks besar.
- Rasa akhir: horor-mistis yang mencekam dan atmosferik (suasana, bayangan, kabut, keheningan yang janggal), mudah diikuti, tanpa gore. image_prompt ditulis dalam bahasa Inggris dan hanya mendeskripsikan ISI adegan (subjek, aksi, tempat, suasana); gaya visual ditambahkan otomatis oleh sistem sesuai style, jadi JANGAN menulis nama style atau istilah teknis kamera di dalamnya.

Balas HANYA JSON dengan bentuk:
{SCHEMA}"""

    data = _gemini(prompt)
    scenes = data.get("scenes", [])
    initial_words = sum(len(str(sc.get("narration", "")).split()) for sc in scenes)
    if not (9 <= len(scenes) <= 12) or not (145 <= initial_words <= 175):
        repair_prompt = f"""Perbaiki JSON skrip video Agen Misteri v6 di bawah.
WAJIB: 9-12 adegan dan total narasi 145-175 kata bahasa Indonesia.
Alur wajib hook konkret -> konteks -> petunjuk -> komplikasi -> pengungkapan berbasis sumber -> payoff.
Jangan menambah fakta di luar bahan sumber. Pertahankan judul/topik dan isi yang didukung sumber; tiap adegan tetap punya narration, visual, image_prompt, with_character, keywords, broll_keywords, motion, emphasis, impact_word, onscreen, beat, visual_role.
Bahan sumber yang diizinkan:
{material}
Catatan sumber: {source_note}
JSON yang perlu diperbaiki:
{json.dumps(data, ensure_ascii=False)}
Kembalikan HANYA JSON valid dengan skema ini:
{SCHEMA}
"""
        print(f"Skrip di luar target ({len(scenes)} adegan/{initial_words} kata); mencoba satu kali perbaikan terstruktur...")
        data = _gemini(repair_prompt, temperature=0.35)
        scenes = data.get("scenes", [])
    if not (9 <= len(scenes) <= 12):
        raise RuntimeError(f"Skrip gagal memenuhi target 9-12 adegan setelah satu kali perbaikan: {len(scenes)}")

    footage_used = 0
    for i, s in enumerate(scenes):
        s["narration"] = s["narration"].strip()
        kw = s.get("keywords") or []
        s["keywords"] = [kw] if isinstance(kw, str) else list(kw)
        s["onscreen"] = (s.get("onscreen") or "").strip()
        s["image_prompt"] = (s.get("image_prompt") or "").strip()
        s["impact_word"] = (s.get("impact_word") or "").strip().split(" ")[0]

        vis = s.get("visual", "illustration")
        vis = "illustration"  # v7: footage hanya sebagai inset (broll) atau cadangan bila gambar gagal
        if vis == "illustration" and not s["image_prompt"]:
            s["image_prompt"] = ", ".join(s["keywords"]) or "mysterious atmospheric scene, dramatic shadows"
        s["visual"] = vis
        s["with_character"] = bool(s.get("with_character"))
        if s.get("motion") not in MOTIONS:
            s["motion"] = MOTIONS[i % len(MOTIONS)]

    # --- v8: style wajib salah satu dari 3 ---
    style_key = forced or styles.normalize(data.get("style"), theme)
    if not forced and str(data.get("style", "")).strip().upper().replace(" ", "_") != style_key:
        print(f"Style dari model tidak valid ({data.get('style')!r}) -> memakai {style_key} (bawaan tema)")
    data["visual_style"] = style_key
    data["style_reason"] = str(data.get("style_reason") or "").strip()[:240]
    fx_default = list(styles.STYLES[style_key]["style"]["fx_default"])
    # --- normalisasi emphasis, impact_word, broll_keywords ---
    norm = lambda w: re.sub(r"[^\w]", "", str(w).lower())
    broll_used, impact_used = 0, 0
    for i, s in enumerate(scenes):
        narr = {norm(w) for w in s["narration"].split()}
        s["fx"] = list(fx_default)  # efek ditentukan oleh style, bukan oleh model
        em = s.get("emphasis") or []
        em = [em] if isinstance(em, str) else list(em)
        s["emphasis"] = [str(w).strip() for w in em if norm(w) and norm(w) in narr][:3]
        if s["impact_word"] and (norm(s["impact_word"]) not in narr or impact_used >= 4):
            s["impact_word"] = ""
        if s["impact_word"]:
            impact_used += 1
        bk = s.get("broll_keywords") or []
        bk = [bk] if isinstance(bk, str) else list(bk)
        bk = [str(q).strip() for q in bk if str(q).strip()][:3]
        if i in (0, len(scenes) - 1) or broll_used >= 3:
            bk = []
        elif bk:
            broll_used += 1
        s["broll_keywords"] = bk
    data["character"] = (data.get("character") or "").strip()
    # Normalize narrative beats so the editor can apply consistent motion graphics.
    default_beats = ["hook", "context", "clue", "clue", "complication", "clue", "reveal", "payoff"]
    default_roles = ["establishing", "establishing", "evidence", "action", "comparison", "evidence", "evidence", "closing"]
    for i, scene in enumerate(scenes):
        scene["beat"] = (scene.get("beat") or default_beats[min(i, len(default_beats)-1)]).strip().lower()
        if scene["beat"] not in {"hook", "context", "clue", "complication", "reveal", "payoff"}:
            scene["beat"] = default_beats[min(i, len(default_beats)-1)]
        scene["visual_role"] = (scene.get("visual_role") or default_roles[min(i, len(default_roles)-1)]).strip().lower()
        if scene["visual_role"] not in {"establishing", "action", "evidence", "comparison", "closing"}:
            scene["visual_role"] = default_roles[min(i, len(default_roles)-1)]
        scene["onscreen"] = scene["onscreen"][:42]
    data["source_evidence"] = material
    data["source_note"] = source_note
    data["character"] = (data.get("character") or "").strip()
    data["topic"] = topic
    data["source_urls"] = source_urls
    words = sum(len(s["narration"].split()) for s in scenes)
    print(f"Skrip: {len(scenes)} adegan ({broll_used} b-roll inset), {words} kata; style {style_key}; target 145-175 kata / 60-90 detik")
    return data
