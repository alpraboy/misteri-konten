import sys, tempfile, unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import captions
import editor
import illustrator
import script_agent
import styles

THEMES = yaml.safe_load((ROOT / "config" / "themes.yml").read_text(encoding="utf-8"))
REQUIRED = ["label", "source", "voice", "rate", "tone", "topic_hint", "disclaimer", "style", "fallback_keywords"]
STYLE_REQ = ["font", "size", "title_size", "color", "accent_rgb", "accent_prompt", "uppercase", "grade"]


def fake_script(durs=(6.0, 7.0, 6.5, 7.2)):
    scenes, t = [], 0.0
    beats = ["hook", "clue", "reveal", "payoff"]
    for i, d in enumerate(durs):
        words = [{"text": w, "start": t + .3 + k * .4, "end": t + .3 + k * .4 + .35}
                 for k, w in enumerate("Malam itu kabut turun dan sosok hitam muncul".split())]
        scenes.append({"duration": d, "start": t, "words": words, "image": f"/tmp/x{i}.jpg",
                       "beat": beats[i], "motion": "zoom_in", "emphasis": ["kabut", "sosok"],
                       "impact_word": "sosok" if i == 2 else "", "onscreen": "Desa" if i else "",
                       "fx": ["fog"], "broll_clip": "/tmp/b.mp4" if i == 1 else None})
        t += d
    return {"scenes": scenes, "total_duration": t, "title": "Tes"}


class V7Tests(unittest.TestCase):
    def test_every_theme_is_complete(self):
        self.assertGreaterEqual(len(THEMES), 10)
        for key, cfg in THEMES.items():
            for k in REQUIRED:
                self.assertIn(k, cfg, f"{key} kurang '{k}'")
            for k in STYLE_REQ:
                self.assertIn(k, cfg["style"], f"{key}.style kurang '{k}'")
            self.assertIn(cfg["source"], ("wikipedia", "news", "none"))
            self.assertTrue(cfg["style"]["color"].startswith("&H00"))
            if cfg["source"] != "news":
                self.assertTrue(cfg.get("regions"), f"{key} butuh 'regions'")

    def test_kinetic_captions_have_emphasis_impact_and_safe_position(self):
        cfg = THEMES["horor_nusantara"]
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "c.ass"
            captions.build_ass(fake_script(), cfg, p)
            text = p.read_text(encoding="utf-8")
        self.assertIn("pos(540,1490)", text)           # subtitle di area aman
        self.assertIn("Style: Impact", text)
        self.assertIn("SOSOK", text)                    # kata raksasa
        self.assertIn("\\clip(", text)                  # label/judul terbuka dengan sapuan
        self.assertIn(cfg["style"]["color"], text)      # warna aksen dipakai

    def test_plan_shots_covers_scene_duration_and_varies(self):
        s = fake_script()
        editor.plan_shots(s)
        for sc in s["scenes"]:
            self.assertAlmostEqual(sum(x["dur"] for x in sc["shots"]), sc["duration"], places=3)
            names = [x["name"] for x in sc["shots"]]
            self.assertTrue(all(a != b for a, b in zip(names, names[1:])))
        self.assertTrue(s["scenes"][2]["shots"][0]["jolt"])   # sentakan di adegan reveal

    def test_inset_only_on_long_enough_scenes(self):
        s = fake_script()
        self.assertIsNotNone(editor.inset_window(s["scenes"][1]))
        self.assertIsNone(editor.inset_window(s["scenes"][0]))
        self.assertIsNone(editor.inset_window({"broll_clip": "x", "duration": 3.0}))

    def test_sfx_events_are_scheduled_inside_video(self):
        s = fake_script()
        editor.plan_shots(s)
        ev = editor.sfx_events(s, captions.impact_events(s), THEMES["horor_nusantara"])
        kinds = {k for k, _, _ in ev}
        self.assertTrue({"whoosh", "hit", "riser", "thump"} <= kinds)
        self.assertTrue(all(t > -2 and t < s["total_duration"] for _, t, _ in ev))

    def test_illustration_postprocess_makes_duotone_ink_look(self):
        from PIL import Image
        cfg = THEMES["cerita"]
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "a.png"
            Image.new("RGB", (64, 112), (200, 40, 60)).save(src)   # gambar berwarna penuh
            out = illustrator.postprocess(src, cfg)
            im = Image.open(out).convert("RGB")
            r, g, b = im.getpixel((10, 10))
            self.assertLess(max(r, g, b) - min(r, g, b), 60)       # hampir monokrom, bukan merah menyala

    def test_script_normalisation_keeps_footage_as_small_inset(self):
        cfg = THEMES["horor_nusantara"]
        scenes = [{"narration": f"Kalimat adegan nomor {i} tentang kabut dan sosok", "visual": "footage",
                   "image_prompt": "x", "keywords": ["a"], "motion": "bogus", "impact_word": "kabut",
                   "emphasis": ["kabut", "tidakada"], "fx": ["rain", "ufo"], "broll_keywords": ["old temple"],
                   "onscreen": "", "beat": "clue", "visual_role": "evidence"} for i in range(10)]
        data = {"title": "t", "scenes": scenes, "caption": "c", "hashtags": [], "claims_to_verify": []}
        words = " ".join(["kata"] * 160)
        for s in scenes:
            s["narration"] += " " + words[:60]
        orig = script_agent._gemini
        script_agent._gemini = lambda *a, **k: data
        try:
            out = script_agent.generate("horor_nusantara", dict(cfg, source="none"), "tes")
        finally:
            script_agent._gemini = orig
        sc = out["scenes"]
        self.assertTrue(all(s["visual"] == "illustration" for s in sc))
        self.assertEqual(sum(1 for s in sc if s["broll_keywords"]), 3)
        self.assertEqual(sc[0]["broll_keywords"], [])
        self.assertEqual(sc[-1]["broll_keywords"], [])
        self.assertLessEqual(sum(1 for s in sc if s["impact_word"]), 4)
        self.assertEqual(sc[1]["emphasis"], ["kabut"])
        self.assertIn(out["visual_style"], styles.STYLE_KEYS)
        self.assertEqual(sc[1]["fx"], styles.STYLES[out["visual_style"]]["style"]["fx_default"])


if __name__ == "__main__":
    unittest.main()
