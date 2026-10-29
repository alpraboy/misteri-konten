"""Orkestrator: tema + (opsional) topik -> video.mp4, caption.txt, verify.md, thumbnail.jpg"""
import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent))

import captions
import editor
import footage
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

    print("== 1/5 Skrip ==")
    script = script_agent.generate(args.theme, cfg, args.topic)

    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    out_dir = Path("output") / f"{stamp}-{args.theme}-{slugify(script['title'])}"
    out_dir.mkdir(parents=True, exist_ok=True)

    print("== 2/5 Suara ==")
    narration = voice.synthesize(script, cfg, work)

    print("== 3/5 Footage ==")
    credits = footage.fetch_all(script, cfg, work)

    print("== 4/5 Typography ==")
    captions.build_ass(script, cfg, work / "captions.ass")

    print("== 5/5 Render ==")
    video = out_dir / "video.mp4"
    editor.render(script, cfg, args.theme, narration, "captions.ass", work, video)

    # --- file pendukung untuk upload manual ---
    tags = " ".join(script.get("hashtags", []))
    caption_txt = (
        f"{script['title']}\n\n{script.get('caption', '')}\n\n"
        f"{cfg['disclaimer']}\n\n{tags}\n\nFootage: Pexels"
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
        {"narration": s["narration"], "keywords": s["keywords"],
         "onscreen": s["onscreen"], "duration": round(s["duration"], 2)}
        for s in script["scenes"]
    ]
    (out_dir / "script.json").write_text(json.dumps(slim, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\nSelesai: {out_dir}")


if __name__ == "__main__":
    main()
