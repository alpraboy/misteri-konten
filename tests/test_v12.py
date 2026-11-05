import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import footage
import illustrator
import styles
import tts_gemini
import voice
from test_v9 import pcm_tone


class FakeResp:
    def __init__(self, code, text='{"error":"insufficient balance"}'):
        self.status_code, self.text, self.content = code, text, text.encode()
        self.headers = {"content-type": "application/json"}


class ImageQuotaTests(unittest.TestCase):
    def test_402_with_and_without_key_stops_further_requests_quickly(self):
        calls = []

        def fake_get(url, **kw):
            calls.append(url)
            return FakeResp(402)
        illustrator.QUOTA_EXHAUSTED = False
        illustrator.REMOTE_BROKEN = False
        with patch.dict(os.environ, {"POLLINATIONS_API_KEY": "k"}), patch.object(illustrator.requests, "get", fake_get), \
                patch.object(illustrator.time, "sleep", lambda s: None), tempfile.TemporaryDirectory() as d:
            self.assertIsNone(illustrator._fetch("p", 1, Path(d) / "a"))
            n = len(calls)
            self.assertTrue(illustrator.QUOTA_EXHAUSTED)
            self.assertIsNone(illustrator._fetch("p2", 2, Path(d) / "b"))
            self.assertEqual(len(calls), n)                         # adegan berikutnya tidak memanggil jaringan lagi
        illustrator.QUOTA_EXHAUSTED = False

    def test_failed_scenes_reuse_the_nearest_image_with_a_closer_opening_shot(self):
        script = {"scenes": [{"image": f"i{i}.jpg"} if i < 4 else {"image": None, "visual_role": "action"} for i in range(8)]}
        illustrator.reuse_nearest(script, [4, 5, 6, 7])
        donors = [script["scenes"][i]["image_reused_from"] for i in (4, 5, 6, 7)]
        self.assertEqual(donors, [3, 3, 3, 3])
        self.assertTrue(all(script["scenes"][i]["visual_role"] == "evidence" for i in (4, 5, 6, 7)))
        self.assertTrue(all(script["scenes"][i]["image"] == "i3.jpg" for i in (4, 5, 6, 7)))

    def test_nearest_donor_prefers_previous_scene_on_ties(self):
        script = {"scenes": [{"image": "a.jpg"}, {"image": None}, {"image": "c.jpg"}]}
        illustrator.reuse_nearest(script, [1])
        self.assertEqual(script["scenes"][1]["image"], "a.jpg")

    def test_if_no_image_at_all_it_stops_with_a_clear_message(self):
        with self.assertRaisesRegex(RuntimeError, "Semua ilustrasi AI gagal"):
            illustrator.reuse_nearest({"scenes": [{"image": None}, {"image": None}]}, [0, 1])


class FootageNonStrictTests(unittest.TestCase):
    def _script(self):
        return {"scenes": [{"visual": "footage", "keywords": [], "broll_keywords": []}]}

    def test_non_strict_marks_scene_for_reuse_instead_of_aborting(self):
        s = self._script()
        with patch.object(footage, "_provider", lambda: (lambda q, p: [], False)), patch.object(footage, "_choose", lambda *a: None), \
                tempfile.TemporaryDirectory() as d:
            footage.fetch_all(s, {}, Path(d), strict=False)
        self.assertTrue(s["scenes"][0]["footage_missing"])
        self.assertEqual(s["scenes"][0]["visual"], "illustration")

    def test_strict_mode_still_raises_like_before(self):
        with patch.object(footage, "_provider", lambda: (lambda q, p: [], False)), patch.object(footage, "_choose", lambda *a: None), \
                tempfile.TemporaryDirectory() as d:
            with self.assertRaises(RuntimeError):
                footage.fetch_all(self._script(), {}, Path(d))


class GeminiPaceTests(unittest.TestCase):
    def test_too_slow_gemini_narration_is_sped_up_and_word_times_follow(self):
        cfg = styles.apply({"voice": "id-ID-ArdiNeural", "rate": "-5%", "style": {}}, "MYSTERY_WAYANG")
        script = {"scenes": [{"narration": "a b c"} for _ in range(3)]}
        with tempfile.TemporaryDirectory() as d:
            work = Path(d)

            def fake_gemini(s, c, w):
                outs = []
                for i in range(3):
                    p = w / f"raw{i}.wav"
                    tts_gemini.write_wav(pcm_tone(40.0), 24000, p)
                    outs.append((p, [{"text": "a", "start": 2.0, "end": 2.5}]))
                return outs
            with patch.dict(os.environ, {"GEMINI_API_KEY": "k", "TTS_ENGINE": "auto"}), patch.object(voice, "_raw_gemini", fake_gemini):
                voice.synthesize(script, cfg, work)
        total = script["total_duration"]
        self.assertLess(total, 95)                                   # sebelumnya ~123 detik
        self.assertGreater(total, 75)                                # tidak dipercepat berlebihan
        speed = (3 * 40.45 + 3 * voice.PAD) / voice.GEMINI_TARGET
        self.assertAlmostEqual(script["scenes"][0]["words"][0]["start"], 2.0 / speed, delta=0.05)

    def test_normal_pace_gemini_narration_is_left_untouched(self):
        cfg = styles.apply({"voice": "id-ID-ArdiNeural", "rate": "-5%", "style": {}}, "MYSTERY_VHS")
        script = {"scenes": [{"narration": "a b c"} for _ in range(2)]}
        with tempfile.TemporaryDirectory() as d:
            def fake_gemini(s, c, w):
                outs = []
                for i in range(2):
                    p = w / f"raw{i}.wav"
                    tts_gemini.write_wav(pcm_tone(20.0), 24000, p)
                    outs.append((p, [{"text": "a", "start": 1.0, "end": 1.5}]))
                return outs
            with patch.dict(os.environ, {"GEMINI_API_KEY": "k", "TTS_ENGINE": "auto"}), patch.object(voice, "_raw_gemini", fake_gemini):
                voice.synthesize(script, cfg, Path(d))
        self.assertAlmostEqual(script["scenes"][0]["duration"], 20.45 + voice.PAD, delta=0.1)
        self.assertAlmostEqual(script["scenes"][0]["words"][0]["start"], 1.0, delta=1e-6)

    def test_gemini_style_prompts_no_longer_ask_for_slow_speech(self):
        for k, st in styles.STYLES.items():
            self.assertNotIn("slow", st["tts"]["style"].lower(), k)
            self.assertIn("natural pace", st["tts"]["style"], k)


if __name__ == "__main__":
    unittest.main()
