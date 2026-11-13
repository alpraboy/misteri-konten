"""Riwayat topik/judul video yang sudah pernah dibuat, supaya agen tidak mengulang tema yang sama.

File riwayat: data/history.json (bisa diganti lewat env HISTORY_FILE). Di GitHub Actions file ini
disimpan balik ke repo oleh langkah 'Simpan riwayat topik' pada workflow.
"""
import json
import os
import random
import re
import unicodedata
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path

MAX_ENTRIES = 600

# Kata umum yang tidak membedakan satu topik dari topik lain.
_STOP = {
    "di", "ke", "dari", "yang", "dan", "atau", "dengan", "untuk", "pada", "dalam", "itu", "ini", "si", "sang",
    "tentang", "kisah", "cerita", "legenda", "misteri", "mistis", "rahasia", "kasus", "peristiwa", "fenomena",
    "the", "of", "and", "in", "at", "on", "to", "for", "with", "a", "an", "story", "legend", "mystery", "case",
}


def history_path() -> Path:
    return Path(os.environ.get("HISTORY_FILE", "").strip() or "data/history.json")


def load() -> list:
    """Baca riwayat. File belum ada -> []. File rusak -> [] (dan dicadangkan saat disimpan berikutnya)."""
    p = history_path()
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return [e for e in data if isinstance(e, dict)] if isinstance(data, list) else []
    except (ValueError, OSError):
        print(f"PERINGATAN: {p} tidak bisa dibaca (rusak?); riwayat dianggap kosong.")
        return []


def tokens(text) -> set:
    s = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode().lower()
    return {t for t in re.findall(r"[a-z0-9]+", s) if len(t) >= 2 and t not in _STOP}


def _flat(text) -> str:
    return " ".join(sorted(tokens(text)))


def is_similar(a, b) -> bool:
    """True bila dua topik/judul pada dasarnya sama (bukan sekadar mirip kata)."""
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return False
    if ta == tb:
        return True
    inter = len(ta & tb)
    small, large = sorted((len(ta), len(tb)))
    if small >= 2 and inter / small >= 0.75:      # topik pendek termuat hampir seluruhnya di topik lain
        return True
    if inter / len(ta | tb) >= 0.6:               # Jaccard
        return True
    if small == 1 and inter == 1 and large <= 2:  # mis. "pocong" vs "pocong lompat"
        return True
    return SequenceMatcher(None, _flat(a), _flat(b)).ratio() >= 0.88


def _keys(entry) -> list:
    return [str(entry.get(k) or "") for k in ("topic", "topic_en", "title", "wiki")]


def find_duplicate(names, entries=None):
    """Kembalikan entri riwayat yang sama dengan salah satu nama (topik/judul/artikel), atau None."""
    entries = load() if entries is None else entries
    names = [str(n) for n in names if str(n or "").strip()]
    for e in entries:
        for k in _keys(e):
            if k and any(is_similar(n, k) for n in names):
                return e
    return None


def avoid_list(theme=None, limit=80) -> list:
    """Daftar topik+judul yang sudah dipakai (terbaru dulu), untuk dimasukkan ke prompt model.
    Tema yang sama didahulukan karena paling mungkin bertabrakan."""
    entries = load()
    same = [e for e in entries if e.get("theme") == theme]
    other = [e for e in entries if e.get("theme") != theme]
    out, seen = [], set()
    for e in list(reversed(same)) + list(reversed(other))[:25]:
        for k in (e.get("topic"), e.get("title")):
            k = str(k or "").strip()
            if k and k.lower() not in seen:
                seen.add(k.lower())
                out.append(k)
    return out[:limit]


def recent_titles(theme, limit=30) -> list:
    return [str(e.get("title")) for e in reversed(load())
            if e.get("theme") == theme and e.get("title")][:limit]


def pick_region(theme, regions):
    """Pilih wilayah yang paling jarang dipakai untuk tema ini (acak di antara yang sama jarangnya)."""
    counts = {r: 0 for r in regions}
    for e in load():
        if e.get("theme") == theme and e.get("region") in counts:
            counts[e["region"]] += 1
    low = min(counts.values())
    return random.choice([r for r in regions if counts[r] == low])


def record(theme, topic, title, topic_en="", wiki="", region=""):
    """Tambahkan satu entri ke riwayat dan simpan."""
    p = history_path()
    entries = load()
    if p.exists() and not entries:   # kemungkinan file rusak: simpan cadangan sebelum menimpa
        try:
            raw = p.read_text(encoding="utf-8").strip()
            if raw and raw != "[]":
                p.with_suffix(".bak").write_text(raw, encoding="utf-8")
        except OSError:
            pass
    entries.append({
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "theme": theme, "topic": topic or "", "topic_en": topic_en or "",
        "title": title or "", "wiki": wiki or "", "region": region or "",
    })
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(entries[-MAX_ENTRIES:], ensure_ascii=False, indent=1), encoding="utf-8")
