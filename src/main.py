"""Orkestrator: tema + (opsional) topik -> video.mp4, caption.txt, verify.md, thumbnail.jpg"""
import argparse
import json
import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent))

import captions
import editor
import footage
import fx
import illustrator
import script_agent
import voice
from util import slugify


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--theme", required=True, choices=["sejarah", "cerita", "berita"])
    ap.add_argument("--topic", default="", help="kosongkan agar agen memilih sendiri")
    args = ap.parse_args()

    cfg = yaml.safe_load(Path("config/themes.yml").read_text(encoding="utf-8"))[args.theme]

    work = Path("work")
    if work.exists():
        shutil.rmtree(work)
    work.mkdir()

    print("== 1/6 Skrip & storyboard ==")
    script = script_agent.generate(args.theme, cfg, args.topic)

    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    out_dir = Path("output") / f"{stamp}-{args.theme}-{slugify(script['title'])}"
    out_dir.mkdir(parents=True, exist_ok=True)

    print("== 2/6 Suara ==")
    rate = cfg["rate"]
    narration = voice.synthesize(script, cfg, work, rate)
    actual_duration = float(script.get("total_duration", 0))
    duration_status = "PASS" if 60 <= actual_duration <= 90 else "REVIEW"
    if duration_status != "PASS":
        print(f"PERINGATAN DURASI: {actual_duration:.1f}s di luar target v6 60-90s; tidak dipercepat otomatis.")

    has_footage_key = bool(os.environ.get("PIXABAY_API_KEY") or os.environ.get("PEXELS_API_KEY"))
    if not has_footage_key:  # tanpa key footage: semua adegan jadi ilustrasi
        for sc in script["scenes"]:
            if sc["visual"] == "footage":
                sc["visual"] = "illustration"
                sc["image_prompt"] = sc["image_prompt"] or ", ".join(sc["keywords"]) or "mysterious atmospheric scene"

    print("== 3/6 Ilustrasi ==")
    failed = illustrator.generate_all(script, cfg, work)
    for i in failed:
        if not has_footage_key:
            raise RuntimeError(
                f"Ilustrasi AI adegan {i} gagal dan tidak ada API footage sebagai cadangan. "
                "Tambahkan secret PIXABAY_API_KEY atau PEXELS_API_KEY di GitHub Actions. "
                "Tidak ada visual lokal yang akan dibuat."
            )
        script["scenes"][i]["visual"] = "footage"
        print(f"Adegan {i} dialihkan ke stock footage karena ilustrasi AI gagal.")

    print("== 4/6 Footage ==")
    credits = footage.fetch_all(script, cfg, work)

    print("== 5/6 Cinematic typography & sound design ==")
    editor.plan_shots(script)
    impacts = []  # V6: tanpa SFX agresif; retensi dibangun dari cerita dan visual
    captions.build_ass(script, cfg, work / "captions.ass")
    fxp = {"overlay": str((work / "overlay.png").resolve()), "speed_a": str((work / "speed_a.png").resolve()), "speed_b": str((work / "speed_b.png").resolve())}
    sfx = ""  # V6: sound effect dinonaktifkan; narasi + musik lembut saja

    print("== 6/6 Render ==")
    video = out_dir / "video.mp4"
    editor.render(script, cfg, args.theme, narration, "captions.ass", work, video, fxp, sfx)

    # --- file pendukung untuk upload manual ---
    tags = " ".join(script.get("hashtags", []))
    caption_txt = (
        f"{script['title']}\n\n{script.get('caption', '')}\n\n"
        f"{cfg['disclaimer']}\n\n{tags}\n\nIlustrasi dibuat dengan AI. Footage: Pixabay/Pexels"
    )
    (out_dir / "caption.txt").write_text(caption_txt, encoding="utf-8")

    verify = ["# Validasi sumber sebelum upload\n", f"Tema: {cfg['label']}  |  Topik: {script['topic']}\n",
              f"Durasi audio: {actual_duration:.1f} detik | Target 60-90 detik: {duration_status}\n"]
    verify.append("## Status visual\n")
    fallback_scenes = [i for i, sc in enumerate(script.get("scenes", [])) if sc.get("image_fallback")]
    if fallback_scenes:
        verify.append(f"PERINGATAN: adegan dengan fallback visual lokal (bukan gambar AI spesifik): {', '.join(map(str, fallback_scenes))}. Ganti visual ini sebelum upload bila membutuhkan ilustrasi literal.\n")
    else:
        verify.append("Visual lokal dinonaktifkan. Adegan menggunakan AI image atau stock footage; kegagalan keduanya menghentikan render.\n")
    verify.append("## Status validasi otomatis\n")
    verify.append("Validasi otomatis memeriksa keberadaan sumber, konsistensi metadata, dan kemiripan kata kunci; ini BUKAN verifikasi kebenaran fakta. Klaim faktual tetap wajib diperiksa manusia pada sumber asli.\n")
    source_text = (script.get("source_evidence") or "").lower()
    claims = [] if cfg.get("source") == "none" else script.get("claims_to_verify", [])
    if cfg.get("source") == "none":
        verify.append("Tema ini diklasifikasikan sebagai fiksi/legenda. Pastikan caption dan narasi menyebutnya sebagai fiksi/legenda, bukan fakta sejarah terverifikasi.\n")
    if claims:
        for claim in claims:
            tokens = [t.lower() for t in re.findall(r"[A-Za-zÀ-ÿ0-9]{4,}", claim)]
            hits = [t for t in tokens if t in source_text]
            status = "ada kecocokan kata di bahan sumber; cek konteks asli" if hits else "tidak ditemukan kecocokan langsung; wajib cek sumber / revisi klaim"
            verify.append(f"- [ ] **{claim}** — {status}.\n")
    else:
        verify.append("- Tidak ada klaim yang ditandai oleh model; tetap periksa narasi faktual secara manual.\n")
    verify.append("\n## Klaim yang perlu diverifikasi\n")
    verify += [f"- [ ] {c}" for c in claims] or ["- (tidak ada)"]
    verify.append("\n## Sumber yang dipakai agen\n")
    verify += [f"- {u}" for u in script.get("source_urls", [])] or ["- (tema fiksi/tanpa sumber)"]
    verify.append("\n## Kredit footage\n")
    verify += [f"- {c}" for c in credits]
    (out_dir / "verify.md").write_text("\n".join(verify) + "\n", encoding="utf-8")

    # Retention QA: deterministic checks to help the creator review pacing before upload.
    scene_count = len(script.get("scenes", []))
    word_count = sum(len(str(sc.get("narration", "")).split()) for sc in script.get("scenes", []))
    hook_words = len(str(script.get("scenes", [{}])[0].get("narration", "")).split()) if scene_count else 0
    retention = [
        "# Retention QA — pemeriksaan sebelum upload", "",
        f"- Durasi audio: {actual_duration:.1f}s (target 60-90s: {duration_status})",
        f"- Jumlah adegan: {scene_count} (target 9-12: {'PASS' if 9 <= scene_count <= 12 else 'REVIEW'})",
        f"- Jumlah kata narasi: {word_count} (target 145-175: {'PASS' if 145 <= word_count <= 175 else 'REVIEW'})",
        f"- Hook pembuka: {hook_words} kata (ideal ringkas, 8-24 kata: {'PASS' if 8 <= hook_words <= 24 else 'REVIEW'})",
        "", "## Struktur adegan", "",
    ]
    for i, sc in enumerate(script.get("scenes", []), 1):
        retention.append(f"{i:02d}. [{sc.get('beat', 'clue')}] {sc.get('narration', '').strip()}")
    retention += ["", "## Checklist kreator", "",
                  "- [ ] Hook menyampaikan detail spesifik, bukan clickbait kosong.",
                  "- [ ] Setiap adegan menambah fakta/petunjuk baru.",
                  "- [ ] Pengungkapan menjawab pertanyaan yang dijanjikan hook.",
                  "- [ ] Semua klaim faktual cocok dengan sumber primer/tepercaya.",
                  "- [ ] Subtitle aman dari UI platform dan mudah dibaca.",
                  "- [ ] Musik tidak menutupi narasi; cek hasil render sampai selesai."]
    (out_dir / "retention_report.md").write_text("\n".join(retention) + "\n", encoding="utf-8")

    slim = {k: v for k, v in script.items() if k not in ("scenes", "source_evidence")}
    slim["scenes"] = [
        {"narration": s["narration"], "visual": s["visual"], "image_prompt": s["image_prompt"],
         "keywords": s["keywords"], "motion": s["motion"], "impact_word": s["impact_word"],
         "onscreen": s["onscreen"], "beat": s.get("beat", "clue"),
         "visual_role": s.get("visual_role", "establishing"), "image_fallback": bool(s.get("image_fallback", False)), "duration": round(s["duration"], 2)}
        for s in script["scenes"]
    ]
    (out_dir / "script.json").write_text(json.dumps(slim, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\nSelesai: {out_dir}")


if __name__ == "__main__":
    main()
