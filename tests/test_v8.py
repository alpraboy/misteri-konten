import sys, tempfile, unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import board
import captions
import editor
import fx
import illustrator
import looks
import script_agent
import styles

THEMES = yaml.safe_load((ROOT / "config" / "themes.yml").read_text(encoding="utf-8"))
BASE = THEMES["horor_nusantara"]


def fake_script(look_scenes=4):
    scenes, t = [], 0.0
    beats = ["hook", "context", "reveal", "payoff"]
    for i in range(look_scenes):
        words = [{"text": w, "start": t + .3 + k * .4, "end": t + .3 + k * .4 + .35}
                 for k, w in enumerate("Rekaman itu berhenti tepat pukul tiga lewat".split())]
        scenes.append({"duration": 6.0, "start": t, "words": words, "beat": beats[i % 4], "motion": "zoom_in",
                       "emphasis": ["tiga"], "impact_word": "tiga" if i == 2 else "", "onscreen": "",
                       "fx": [], "broll_clip": None, "image": None, "narration": "x"})
        t += 6.0
    return {"scenes": scenes, "total_duration": t, "title": "Rekaman Pukul Tiga"}


class StyleTests(unittest.TestCase):
    def test_exactly_three_styles_and_valid_normalisation(self):
        self.assertEqual(sorted(styles.STYLES), ["MYSTERY_CONSPIRACY", "MYSTERY_VHS", "MYSTERY_WAYANG"])
        self.assertEqual(styles.normalize("vhs"), "MYSTERY_VHS")
        self.assertEqual(styles.normalize("wayang"), "MYSTERY_WAYANG")
        self.assertEqual(styles.normalize("ngawur", "horor_nusantara"), "MYSTERY_WAYANG")   # bawaan tema
        self.assertIn(styles.normalize(None, "tidak_ada"), styles.STYLE_KEYS)                # selalu salah satu
        for t in THEMES:
            self.assertIn(styles.DEFAULT_BY_THEME.get(t), styles.STYLE_KEYS, t)

    def test_styles_carry_templates_negatives_and_forbidden_words(self):
        for k, st in styles.STYLES.items():
            cfg = styles.apply(BASE, k)
            self.assertEqual(cfg["look"], st["look"])
            self.assertTrue(cfg["visual"]["prefix"] and cfg["visual"]["suffix"] and cfg["visual"]["negative"])
            self.assertIn("cute", cfg["visual"]["negative"])
        self.assertIn("modern", styles.STYLES["MYSTERY_WAYANG"]["negative"])
        self.assertIn("photorealistic face", styles.STYLES["MYSTERY_WAYANG"]["negative"])

    def test_prompt_builder_uses_style_template(self):
        cfg = styles.apply(BASE, "MYSTERY_WAYANG")
        p = illustrator.build_prompt({"character": ""}, cfg, {"image_prompt": "the guardian spirit of the southern sea"})
        self.assertTrue(p.startswith("Dark Javanese wayang kulit folklore horror"))
        self.assertIn("guardian spirit of the southern sea", p)
        self.assertIn("kelir", p)

    def test_forced_style_is_obeyed_and_prompt_says_so(self):
        seen = {}
        words = " ".join(["kata"] * 150)
        scenes = [{"narration": f"adegan {i} kabut sosok " + words[:70], "visual": "illustration", "image_prompt": "x",
                   "keywords": [], "broll_keywords": [], "motion": "zoom_in", "emphasis": [], "impact_word": "",
                   "onscreen": "", "beat": "clue", "visual_role": "evidence"} for i in range(10)]
        data = {"style": "MYSTERY_WAYANG", "title": "t", "scenes": scenes, "caption": "c", "hashtags": [], "claims_to_verify": []}

        def fake(prompt, *a, **k):
            seen.setdefault("p", prompt)
            return data
        orig = script_agent._gemini
        script_agent._gemini = fake
        try:
            out = script_agent.generate("cerita", dict(BASE, source="none"), "tes", style="vhs")
        finally:
            script_agent._gemini = orig
        self.assertEqual(out["visual_style"], "MYSTERY_VHS")          # dipaksa, model memilih style lain
        self.assertIn("SUDAH DITENTUKAN", seen["p"])

    def test_auto_style_prompt_lists_all_three(self):
        seen = {}
        words = " ".join(["kata"] * 150)
        scenes = [{"narration": f"adegan {i} " + words[:70], "visual": "illustration", "image_prompt": "x", "keywords": [],
                   "broll_keywords": [], "motion": "zoom_in", "emphasis": [], "impact_word": "", "onscreen": "",
                   "beat": "clue", "visual_role": "evidence"} for i in range(10)]
        data = {"style": "BUKAN_STYLE", "title": "t", "scenes": scenes, "caption": "c", "hashtags": [], "claims_to_verify": []}
        orig = script_agent._gemini
        script_agent._gemini = lambda prompt, *a, **k: (seen.setdefault("p", prompt), data)[1]
        try:
            out = script_agent.generate("legenda_urban", dict(BASE, source="none"), "tes", style="auto")
        finally:
            script_agent._gemini = orig
        for k in styles.STYLE_KEYS:
            self.assertIn(k, seen["p"])
        self.assertEqual(out["visual_style"], "MYSTERY_VHS")          # tidak valid -> bawaan tema


class LookTests(unittest.TestCase):
    def test_wayang_uses_only_three_ink_colours(self):
        from PIL import Image
        import numpy as np
        im = Image.effect_noise((64, 112), 90).convert("RGB")
        out = np.asarray(looks.wayang(im)).astype(int)
        self.assertTrue((out[..., 0] >= out[..., 1] - 2).all() and (out[..., 1] >= out[..., 2] - 2).all())   # hitam-merah-emas
        self.assertLess(out.reshape(-1, 3).max(axis=0)[1], 130)                                               # tidak ada putih/hijau

    def test_vhs_is_low_res_and_keeps_size(self):
        from PIL import Image
        im = Image.effect_noise((128, 224), 120).convert("RGB")
        out = looks.vhs(im, 1)
        self.assertEqual(out.size, im.size)
        import numpy as np
        a = np.asarray(out).astype(int)
        self.assertGreater(a[..., 1].mean(), a[..., 0].mean())       # idx 1 = night vision hijau


class EngineTests(unittest.TestCase):
    def test_vhs_hud_has_rec_and_ticking_timer(self):
        cfg = styles.apply(BASE, "MYSTERY_VHS")
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "c.ass"
            captions.build_ass(fake_script(), cfg, p)
            text = p.read_text(encoding="utf-8")
        self.assertIn("REC", text)
        self.assertIn("03:33:12 AM", text)
        self.assertIn("03:33:13 AM", text)
        self.assertIn("pos(540,1490)", text)

    def test_conspiracy_has_confidential_stamp_and_wayang_has_none(self):
        with tempfile.TemporaryDirectory() as d:
            for key, expect in (("MYSTERY_CONSPIRACY", True), ("MYSTERY_WAYANG", False)):
                p = Path(d) / f"{key}.ass"
                captions.build_ass(fake_script(), styles.apply(BASE, key), p)
                text = p.read_text(encoding="utf-8")
                self.assertEqual("CONFIDENTIAL" in text, expect, key)
                self.assertNotIn("03:33", text)

    def test_ambient_audio_profiles_differ_per_style(self):
        kinds = {k: {e[0] for e in fx.ambient_events(k, 60)} for k in ("vhs", "conspiracy", "wayang")}
        self.assertTrue({"step", "breath", "wail"} <= kinds["vhs"])
        self.assertIn("tick", kinds["conspiracy"])
        self.assertTrue({"gong", "crackle"} <= kinds["wayang"])
        self.assertTrue(any(k.startswith("bell") for k in kinds["wayang"]))

    def test_transition_sfx_follow_style(self):
        for key, kind in (("MYSTERY_VHS", "glitch"), ("MYSTERY_CONSPIRACY", "rustle")):
            cfg = styles.apply(BASE, key)
            s = fake_script(); editor.plan_shots(s)
            ev = editor.sfx_events(s, [], cfg)
            self.assertIn(kind, {e[0] for e in ev}, key)

    def test_board_composes_evidence_and_plans_following_pan(self):
        from PIL import Image
        cfg = styles.apply(BASE, "MYSTERY_CONSPIRACY")
        s = fake_script(5)
        with tempfile.TemporaryDirectory() as d:
            work = Path(d)
            for i, sc in enumerate(s["scenes"]):
                p = work / f"e{i}.jpg"
                Image.effect_noise((200, 300), 80).convert("RGB").save(p)
                sc["image"] = str(p)
            board.compose(s, cfg, work)
            for sc in s["scenes"]:
                self.assertEqual(Image.open(sc["image"]).size, (1024, 1792))
                for pt in sc["board_focus"].values():
                    self.assertTrue(all(-0.2 <= c <= 1.2 for c in pt))
            editor.plan_shots(s, 3.2)
            first = s["scenes"][1]["shots"][0]
            self.assertEqual(first["name"], "board_pan")
            self.assertIn("spec", first)

    def test_overlays_are_generated_only_for_the_chosen_style(self):
        with tempfile.TemporaryDirectory() as d:
            got = fx.make_overlays(Path(d), styles.apply(BASE, "MYSTERY_VHS"))
            self.assertEqual(sorted(got), ["scan", "tracking"])
            got = fx.make_overlays(Path(d) / "w", styles.apply(BASE, "MYSTERY_WAYANG"))
            self.assertEqual(sorted(got), ["batik", "dust", "smoke"])

    def test_workflow_offers_all_styles_and_themes(self):
        wf = yaml.safe_load((ROOT / ".github" / "workflows" / "make-video.yml").read_text(encoding="utf-8"))
        inputs = wf[True]["workflow_dispatch"]["inputs"]
        self.assertEqual(sorted(inputs["theme"]["options"]), sorted(THEMES))
        self.assertTrue({"auto", *styles.STYLE_KEYS} <= set(inputs["style"]["options"]))


if __name__ == "__main__":
    unittest.main()
