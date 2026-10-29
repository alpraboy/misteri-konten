"""Orkestrator: tema + (opsional) topik -> video.mp4, caption.txt, verify.md, thumbnail.jpg"""
import argparse
import json
import os
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
    if script["total_duration"] > 61:
        print("Catatan: narasi lebih dari 61 detik; tidak dipercepat otomatis agar tetap nyaman didengar.")

    has_footage_key = bool(os.environ.get("PIXABAY_API_KEY") or os.environ.get("PEXELS_API_KEY"))
    if not has_footage_key:  # tanpa key footage: semua adegan jadi ilustrasi
        for sc in script["scenes"]:
            if sc["visual"] == "footage":
                sc["visual"] = "illustration"
                sc["image_prompt"] = sc["image_prompt"] or ", ".join(sc["keywords"]) or "mysterious atmospheric scene"

    print("== 3/6 Ilustrasi ==")
    failed = illustrator.generate_all(script, cfg, work)
    for i in failed:  # ilustrasi gagal -> pakai footage sebagai cadangan
        if not has_footage_key:
            raise RuntimeError(f"Ilustrasi adegan {i} gagal dan tidak ada key footage sebagai cadangan.")
        script["scenes"][i]["visual"] = "footage"
        print(f"Adegan {i} dialihkan ke footage.")

    print("== 4/6 Footage ==")
    credits = footage.fetch_all(script, cfg, work)

    print("== 5/6 Cinematic typography & sound design ==")
    editor.plan_shots(script)
    impacts = []  # V5: tidak memakai impact-word atau SFX agresif
    captions.build_ass(script, cfg, work / "captions.ass")
    fxp = {"overlay": str((work / "overlay.png").resolve()), "speed_a": str((work / "speed_a.png").resolve()), "speed_b": str((work / "speed_b.png").resolve())}
    sfx = ""  # V5: sound effect dinonaktifkan; narasi + musik lembut saja

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

    verify = ["# Cek sebelum upload\n", f"Tema: {cfg['label']}  |  Topik: {script['topic']}\n"]
    verify.append("## Klaim yang perlu diverifikasi\n")
    verify += [f"- [ ] {c}" for c in script.get("claims_to_verify", [])] or ["- (tidak ada)"]
    verify.append("\n## Sumber yang dipakai agen\n")
    verify += [f"- {u}" for u in script.get("source_urls", [])] or ["- (tema fiksi/tanpa sumber)"]
    verify.append("\n## Kredit footage\n")
    verify += [f"- {c}" for c in credits]
    (out_dir / "verify.md").write_text("\n".join(verify) + "\n", encoding="utf-8")

    slim = {k: v for k, v in script.items() if k != "scenes"}
    slim["scenes"] = [
        {"narration": s["narration"], "visual": s["visual"], "image_prompt": s["image_prompt"],
         "keywords": s["keywords"], "motion": s["motion"], "impact_word": s["impact_word"],
         "onscreen": s["onscreen"], "duration": round(s["duration"], 2)}
        for s in script["scenes"]
    ]
    (out_dir / "script.json").write_text(json.dumps(slim, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\nSelesai: {out_dir}")


if __name__ == "__main__":
    main()
