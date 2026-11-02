"""Agen editing: HANYA 3 style, WAJIB memilih salah satu per video.

  MYSTERY_VHS         Analog horror VHS (ketakutan personal, rekaman bocor, POV orang pertama)
  MYSTERY_CONSPIRACY  Papan gabus + benang merah (investigasi, ditutupi, pola tersembunyi)
  MYSTERY_WAYANG      Wayang kulit horor (sakral, leluhur, ritual, makhluk penjaga)

Setiap style membawa: kapan dipakai, template prompt gambar + negative, palet warna,
tipografi, efek bergerak, dan profil audio. `apply()` menggabungkannya ke konfigurasi tema.
"""
import copy

STYLE_KEYS = ["MYSTERY_VHS", "MYSTERY_CONSPIRACY", "MYSTERY_WAYANG"]

STYLES = {
    "MYSTERY_VHS": {
        "label": "Analog Horror VHS",
        "look": "vhs",
        "use_when": (
            "Tujuan: MEMBUAT PENONTON TAKUT, MERINDING, merasa melihat kejadian nyata. Topik: pengalaman pribadi "
            "yang menyeramkan, kejadian aneh yang tak bisa dijelaskan logika, rekaman yang katanya bocor, atau cerita "
            "orang pertama di lokasi angker. Fokus: KETAKUTAN PERSONAL dan SUASANA MENCEKAM."
        ),
        "scene_rule": (
            "Setiap adegan = potongan rekaman CCTV/HP jadul dari sudut pandang orang pertama di sebuah lokasi gelap "
            "(lorong, rumah kosong, gedung, hutan malam). image_prompt = apa yang terlihat kamera: lokasi, bayangan, "
            "benda aneh, sosok samar di sudut. Tanpa wajah jelas, tanpa teks."
        ),
        "prefix": "Analog horror VHS found footage, Indonesian story, ",
        "suffix": (
            ", dark empty location, distorted low-res CCTV footage at night, heavy VHS tracking glitch, "
            "green night vision flicker, blurred shadow figure in the corner, grainy, terrifying, "
            "photorealistic horror, 9:16 vertical, no text, no letters"
        ),
        "negative": "cute, pastel, clay 3d, paper scrapbook, clean studio, colorful, happy, cartoon, text, watermark",
        "pitch": "-6Hz",
        "voice_fx": "aresample=44100,highpass=f=170,lowpass=f=4200,acrusher=bits=11:mix=0.2:mode=lin,tremolo=f=5.5:d=0.10,aecho=0.8:0.5:35:0.22",
        "tts": {"voice": "Enceladus",
                "style": "Say in Indonesian, in a hushed, trembling, breathy whisper like a terrified person secretly recording, slowly, with tense pauses"},
        "style": {
            "font": "DejaVu Sans Mono", "size": 60, "title_size": 52,
            "color": "&H0041FF00&",         # hijau night vision #00FF41 (kata aktif)
            "color2": "&H0000008B&",        # merah darah gelap #8B0000 (kata penting)
            "accent_rgb": [0, 255, 65], "accent_prompt": "night vision green",
            "uppercase": True, "flicker": True, "heartbeat": True,
            "grade": "eq=contrast=1.22:brightness=-0.07:saturation=0.45",
            "fx_default": ["scan", "tracking"], "shot_len": 2.3,
            "ambience": {"drone_hz": 41, "wind": 0.15},
        },
    },
    "MYSTERY_CONSPIRACY": {
        "label": "Red String Conspiracy Board",
        "look": "conspiracy",
        "use_when": (
            "Tujuan: MEMBUAT PENONTON CURIGA, MENGHUBUNGKAN TITIK-TITIK, mempertanyakan kebenaran yang diajarkan. "
            "Topik: sesuatu yang ditutupi, kejanggalan cerita resmi, pola tersembunyi, pertanyaan 'kenapa ini "
            "disembunyikan?'. Fokus: RASA PENASARAN, INVESTIGASI, MEMBONGKAR RAHASIA."
        ),
        "scene_rule": (
            "Setiap adegan = SATU 'barang bukti' yang ditempel di papan: foto lama hitam-putih, dokumen, peta, "
            "artefak, potongan koran. image_prompt = isi foto/barang bukti itu saja (objek/tempat/benda yang disebut "
            "narasi), seperti foto arsip yang buram dan berbutir. Tanpa teks di dalam gambar."
        ),
        "prefix": "Old grainy black and white archive evidence photograph, investigation file, ",
        "suffix": (
            ", vintage documentary photo, harsh flash, film grain, faded, cinematic investigative documentary, "
            "no text, no letters"
        ),
        "negative": "cute, pastel, clay chibi, neon glowing, clean corporate, happy, paper cute, colorful, text, watermark",
        "pitch": "-4Hz",
        "voice_fx": "aresample=44100,highpass=f=110,acompressor=threshold=-20dB:ratio=3:attack=15:release=250,equalizer=f=3200:t=q:w=1.2:g=2,aecho=0.8:0.5:55:0.15",
        "tts": {"voice": "Charon",
                "style": "Say in Indonesian, in a low, calm, suspicious investigative tone, slowly, like a detective revealing a hidden truth"},
        "style": {
            "font": "DejaVu Sans Mono", "size": 58, "title_size": 54,
            "color": "&H002222B2&",         # benang merah #B22222
            "color2": "&H002222B2&",
            "accent_rgb": [178, 34, 34], "accent_prompt": "red thread red",
            "uppercase": False, "flicker": False, "heartbeat": False,
            "grade": "eq=contrast=1.10:brightness=-0.05:saturation=0.9",
            "fx_default": ["lamp", "haze"], "shot_len": 3.2,
            "ambience": {"drone_hz": 49, "wind": 0.10},
        },
    },
    "MYSTERY_WAYANG": {
        "label": "Dark Wayang Folklore",
        "look": "wayang",
        "use_when": (
            "Tujuan: MEMBUAT PENONTON MERASA SAKRAL, MISTIS, terhubung dengan kepercayaan lama. Topik: cerita "
            "turun-temurun leluhur, kepercayaan tentang alam gaib, ritual, perjanjian, makhluk penjaga. "
            "Fokus: BUDAYA, KEARIFAN LOKAL, KESAKRALAN."
        ),
        "scene_rule": (
            "Setiap adegan = siluet WAYANG KULIT versi horor di balik kelir (layar wayang) dengan cahaya obor dari "
            "bawah. image_prompt = siapa/apa yang dipentaskan sebagai siluet wayang (penjaga, makhluk, ritual, "
            "tempat sakral) dan komposisinya. Tanpa wajah manusia fotorealistik, tanpa teks."
        ),
        "prefix": "Dark Javanese wayang kulit folklore horror, terrifying shadow puppet silhouette of ",
        "suffix": (
            ", behind white wayang screen (kelir), flickering torch underlight, thick incense smoke, ancient batik "
            "texture, gold and blood red accent, mystical ritual atmosphere, dust particles, sacred and scary, "
            "9:16 vertical, no text, no letters"
        ),
        "negative": "modern, cute, chibi, tech HUD, clay 3d, photorealistic face, colorful pastel, clean corporate, happy, text, watermark",
        "pitch": "-10Hz",
        "voice_fx": "aresample=44100,asetrate=41895,aresample=44100,atempo=1.0526,bass=g=4:f=140,aecho=0.8:0.65:170|310:0.32|0.2",
        "tts": {"voice": "Algenib",
                "style": "Say in Indonesian, in a deep, slow, solemn, gravelly ancient storyteller voice, sacred and eerie, like a dalang narrating a ritual"},
        "style": {
            "font": "DejaVu Serif", "size": 64, "title_size": 56,
            "color": "&H002F6B8C&",         # emas pudar #8C6B2F
            "color2": "&H001A1A7A&",        # merah membara #7A1A1A
            "accent_rgb": [140, 107, 47], "accent_prompt": "faded gold",
            "uppercase": False, "flicker": True, "heartbeat": False,
            "grade": "eq=contrast=1.12:brightness=-0.04:saturation=1.0",
            "fx_default": ["smoke", "dust", "batik"], "shot_len": 3.6,
            "ambience": {"drone_hz": 46, "wind": 0.2},
        },
    },
}

# Gaya bawaan bila model tidak memilih / pilihan tidak valid (berdasarkan tema konten)
DEFAULT_BY_THEME = {
    "sejarah": "MYSTERY_CONSPIRACY", "cerita": "MYSTERY_VHS", "berita": "MYSTERY_CONSPIRACY",
    "horor_nusantara": "MYSTERY_WAYANG", "legenda_urban": "MYSTERY_VHS",
    "kasus_tak_terpecahkan": "MYSTERY_CONSPIRACY", "ufo_uap": "MYSTERY_VHS",
    "kriptid": "MYSTERY_VHS", "tempat_angker": "MYSTERY_VHS",
    "peradaban_hilang": "MYSTERY_CONSPIRACY", "artefak_terkutuk": "MYSTERY_WAYANG",
    "fenomena_alam": "MYSTERY_CONSPIRACY",
}


def normalize(key, theme=None):
    """Kembalikan kode style yang valid. Wajib salah satu dari tiga."""
    k = str(key or "").strip().upper().replace(" ", "_")
    aliases = {"VHS": "MYSTERY_VHS", "CONSPIRACY": "MYSTERY_CONSPIRACY", "WAYANG": "MYSTERY_WAYANG"}
    k = aliases.get(k, k)
    if k in STYLES:
        return k
    return DEFAULT_BY_THEME.get(theme, "MYSTERY_VHS")


def choice_brief():
    """Ringkasan 3 style untuk prompt pemilihan oleh model."""
    return "\n".join(f"- {k}: {v['use_when']}" for k, v in STYLES.items())


def apply(cfg, key):
    """Gabungkan style visual ke konfigurasi tema (tema tetap menentukan suara, nada, sumber)."""
    st = STYLES[key]
    out = copy.deepcopy(cfg)
    base = out.get("style", {})
    base.update(copy.deepcopy(st["style"]))
    out["style"] = base
    out["visual_style"] = key
    out["look"] = st["look"]
    out["visual"] = {k: st[k] for k in ("label", "prefix", "suffix", "negative", "scene_rule")}
    out["pitch"] = st.get("pitch", "+0Hz")
    out["tts"] = dict(st.get("tts", {}))
    out["voice_fx"] = st.get("voice_fx", "")
    out["fallback_keywords"] = out.get("fallback_keywords", [])
    return out
