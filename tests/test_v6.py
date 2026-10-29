import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import captions
import editor
import script_agent
from unittest.mock import patch


class CinematicV6Tests(unittest.TestCase):
    def test_long_scene_splits_into_multiple_shots(self):
        script = {"scenes": [{
            "image": "fake.png", "duration": 11.0, "start": 0.0,
            "motion": "zoom_in", "beat": "reveal", "visual_role": "evidence",
        }]}
        editor.plan_shots(script)
        shots = script["scenes"][0]["shots"]
        self.assertGreaterEqual(len(shots), 2)
        self.assertEqual(shots[0]["name"], "close_top")
        self.assertAlmostEqual(sum(s["dur"] for s in shots), 11.0, places=2)

    def test_ass_contains_progress_and_story_beats(self):
        script = {
            "title": "Uji Misteri", "total_duration": 8.0,
            "scenes": [
                {"start": 0.0, "duration": 4.0, "beat": "hook", "onscreen": "", "words": [
                    {"text": "Lihat", "start": 0.1, "end": 0.4},
                    {"text": "detail", "start": 0.4, "end": 0.8},
                ]},
                {"start": 4.0, "duration": 4.0, "beat": "reveal", "onscreen": "BUKTI BARU", "words": [
                    {"text": "Ada", "start": 4.1, "end": 4.4},
                    {"text": "jawaban", "start": 4.4, "end": 4.9},
                ]},
            ],
        }
        cfg = {"style": {"font": "DejaVu Sans", "size": 40, "title_size": 48,
                          "color": "&H0000B0FF&", "uppercase": False}}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "captions.ass"
            captions.build_ass(script, cfg, path)
            ass = path.read_text(encoding="utf-8")
        self.assertIn("PERTANYAAN", ass)
        self.assertIn("PENGUNGKAPAN", ass)
        self.assertIn("\\p1", ass)
        self.assertIn("BUKTI BARU", ass)

    def test_semantic_shot_roles(self):
        script = {"scenes": [
            {"image": "one.png", "duration": 6.0, "start": 0, "visual_role": "comparison", "beat": "complication", "motion": "pan_left"},
            {"image": "two.png", "duration": 6.0, "start": 6, "visual_role": "closing", "beat": "payoff", "motion": "zoom_in"},
        ]}
        editor.plan_shots(script)
        self.assertEqual(script["scenes"][0]["shots"][0]["name"], "wide_out")
        self.assertEqual(script["scenes"][1]["shots"][0]["name"], "wide_out")

    def test_fact_theme_stops_when_source_missing(self):
        cfg = {"source": "wikipedia", "topic_hint": "misteri sejarah", "regions": ["Indonesia"]}
        with patch.object(script_agent, "_pick_topic", return_value="topik tidak ditemukan"), \
             patch.object(script_agent.sources, "wikipedia_context", return_value=None), \
             patch.object(script_agent, "_gemini") as gemini:
            with self.assertRaisesRegex(RuntimeError, "Sumber Wikipedia tidak ditemukan"):
                script_agent.generate("sejarah", cfg, "topik tidak ditemukan")
            gemini.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
