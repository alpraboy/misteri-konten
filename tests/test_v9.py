import array
import base64
import math
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import styles
import tts_gemini
import voice


def pcm_tone(seconds=1.6, rate=24000, lead=0.25):
    a = array.array("h")
    for i in range(int(rate * (lead + seconds + 0.2))):
        t = i / rate
        on = lead <= t <= lead + seconds
        a.append(int(9000 * math.sin(2 * math.pi * 220 * t)) if on else 0)
    return a.tobytes()


class FakeResp:
    def __init__(self, code, body=None, text=""):
        self.status_code, self._b, self.text = code, body, text or str(body)

    def json(self):
        return self._b


def ok_resp(pcm, rate=24000):
    return FakeResp(200, {"candidates": [{"content": {"parts": [{"inlineData": {
        "mimeType": f"audio/L16;codec=pcm;rate={rate}", "data": base64.b64encode(pcm).decode()}}]}}]})


class GeminiTTSTests(unittest.TestCase):
    def test_extract_reads_both_json_casings_and_rate(self):
        pcm = pcm_tone()
        got, rate = tts_gemini._extract(ok_resp(pcm, 22050).json())
        self.assertEqual((got, rate), (pcm, 22050))
        snake = {"candidates": [{"content": {"parts": [{"inline_data": {"mime_type": "audio/L16", "data": base64.b64encode(pcm).decode()}}]}}]}
        self.assertEqual(tts_gemini._extract(snake)[1], 24000)       # tanpa rate -> 24 kHz
        with self.assertRaises(ValueError):
            tts_gemini._extract({"candidates": []})

    def test_discovers_working_model_and_request_shape_then_reuses_it(self):
        calls = []

        def fake_post(url, headers=None, json=None, timeout=None):
            calls.append((url, "prebuiltVoiceConfig" in str(json)))
            if "gemini-2.5-flash-preview-tts" in url:
                return FakeResp(404, text="model not found")
            if "gemini-3.1" in url and "prebuiltVoiceConfig" in str(json):
                return FakeResp(400, text="unknown field")
            return ok_resp(pcm_tone())
        with patch.object(tts_gemini.requests, "post", fake_post), tempfile.TemporaryDirectory() as d:
            eng = tts_gemini.GeminiTTS("Charon", "Say slowly", key="k", gap=0)
            words = eng.synthesize("Halo dunia yang gelap", Path(d) / "a.wav")
            first_calls = len(calls)
            eng.synthesize("Kalimat kedua", Path(d) / "b.wav")
        self.assertEqual(eng.working[0], "gemini-3.1-flash-tts-preview")
        self.assertEqual(eng.working[1], "speech")
        self.assertEqual(len(calls) - first_calls, 1)                  # panggilan berikutnya langsung ke kombinasi yang jalan
        self.assertEqual(len(words), 4)

    def test_daily_quota_or_missing_free_tier_raises_unavailable(self):
        body = '{"error": {"code": 429, "message": "Quota exceeded ... GenerateRequestsPerDayPerProjectPerModel limit: 0"}}'
        with patch.object(tts_gemini.requests, "post", lambda *a, **k: FakeResp(429, text=body)):
            eng = tts_gemini.GeminiTTS("Kore", "", key="k", gap=0)
            with self.assertRaises(tts_gemini.TTSUnavailable):
                eng.synthesize("tes", Path(tempfile.gettempdir()) / "x.wav")

    def test_rejected_key_raises_unavailable(self):
        with patch.object(tts_gemini.requests, "post", lambda *a, **k: FakeResp(403, text="API key not valid")):
            with self.assertRaises(tts_gemini.TTSUnavailable):
                tts_gemini.GeminiTTS("Kore", "", key="k", gap=0).synthesize("tes", Path(tempfile.gettempdir()) / "x.wav")

    def test_word_times_stay_inside_detected_speech_and_increase(self):
        pcm = pcm_tone(seconds=2.0, lead=0.4)
        start, end = tts_gemini.speech_span(pcm, 24000)
        self.assertAlmostEqual(start, 0.35, delta=0.1)
        self.assertAlmostEqual(end, 2.52, delta=0.2)
        words = tts_gemini.estimate_words("Malam itu, kabut turun perlahan. Lalu sunyi", start, end)
        self.assertEqual(len(words), 7)
        self.assertTrue(all(a["end"] <= b["start"] + 1e-6 for a, b in zip(words, words[1:])))
        self.assertGreaterEqual(words[0]["start"], start - 1e-6)
        self.assertLessEqual(words[-1]["end"], end + 1e-6)

    def test_instruction_read_aloud_triggers_retry_without_style(self):
        seen = []

        def fake_post(url, headers=None, json=None, timeout=None):
            text = json["contents"][0]["parts"][0]["text"]
            seen.append(text)
            return ok_resp(pcm_tone(8.0) if text.startswith("Say") else pcm_tone(1.0))
        with patch.object(tts_gemini.requests, "post", fake_post), tempfile.TemporaryDirectory() as d:
            eng = tts_gemini.GeminiTTS("Kore", "Say softly", key="k", gap=0)
            eng.synthesize("Halo dunia", Path(d) / "a.wav")
        self.assertEqual(len(seen), 2)
        self.assertEqual(seen[1], "Halo dunia")


class VoiceEngineTests(unittest.TestCase):
    def _script(self):
        return {"scenes": [{"narration": "Malam itu kabut turun."}, {"narration": "Lalu semuanya sunyi."}]}

    def test_every_style_has_a_gemini_voice_and_style_prompt(self):
        for k, st in styles.STYLES.items():
            cfg = styles.apply({"voice": "id-ID-ArdiNeural", "rate": "-5%", "style": {}}, k)
            self.assertTrue(cfg["tts"]["voice"] and cfg["tts"]["style"].startswith("Say in Indonesian"), k)

    def test_gemini_success_is_used_for_all_scenes(self):
        def fake_post(url, headers=None, json=None, timeout=None):
            return ok_resp(pcm_tone(1.2))
        cfg = styles.apply({"voice": "id-ID-ArdiNeural", "rate": "-5%", "style": {}}, "MYSTERY_VHS")
        with patch.dict(os.environ, {"GEMINI_API_KEY": "k", "TTS_ENGINE": "auto", "GEMINI_TTS_GAP": "0"}), \
                patch.object(tts_gemini.requests, "post", fake_post), tempfile.TemporaryDirectory() as d:
            s = self._script()
            out = voice.synthesize(s, cfg, Path(d))
            self.assertTrue(out.exists())
        self.assertTrue(all(sc["duration"] > 1.5 for sc in s["scenes"]))
        self.assertGreater(s["scenes"][1]["start"], 1.5)
        self.assertGreater(s["scenes"][1]["words"][0]["start"], s["scenes"][1]["start"])

    def test_gemini_failure_falls_back_to_edge_for_all_scenes(self):
        cfg = styles.apply({"voice": "id-ID-ArdiNeural", "rate": "-5%", "style": {}}, "MYSTERY_WAYANG")
        with tempfile.TemporaryDirectory() as d:
            work = Path(d)
            edge_calls = []

            def fake_edge(script, cfg_, work_, rate):
                edge_calls.append(1)
                outs = []
                for i in range(len(script["scenes"])):
                    p = work_ / f"e{i}.wav"
                    tts_gemini.write_wav(pcm_tone(1.0), 24000, p)
                    outs.append((p, []))
                return outs
            with patch.dict(os.environ, {"GEMINI_API_KEY": "k", "TTS_ENGINE": "auto"}), \
                    patch.object(voice, "_raw_gemini", side_effect=tts_gemini.TTSUnavailable("kuota habis")), \
                    patch.object(voice, "_raw_edge", fake_edge):
                s = self._script()
                voice.synthesize(s, cfg, work)
        self.assertEqual(len(edge_calls), 1)
        self.assertEqual(len(s["scenes"][0]["words"]), 4)           # kata dibagi rata bila tak ada timestamp

    def test_forced_gemini_engine_raises_instead_of_silently_switching(self):
        cfg = styles.apply({"voice": "id-ID-ArdiNeural", "rate": "-5%", "style": {}}, "MYSTERY_VHS")
        with patch.dict(os.environ, {"GEMINI_API_KEY": "k", "TTS_ENGINE": "gemini"}), \
                patch.object(voice, "_raw_gemini", side_effect=tts_gemini.TTSUnavailable("x")):
            with self.assertRaises(tts_gemini.TTSUnavailable):
                voice.synthesize(self._script(), cfg, Path(tempfile.mkdtemp()))

    def test_edge_only_when_engine_is_edge_or_no_key(self):
        cfg = styles.apply({"voice": "id-ID-ArdiNeural", "rate": "-5%", "style": {}}, "MYSTERY_VHS")
        with tempfile.TemporaryDirectory() as d:
            work = Path(d)

            def fake_edge(script, cfg_, work_, rate):
                outs = []
                for i in range(len(script["scenes"])):
                    p = work_ / f"e{i}.wav"
                    tts_gemini.write_wav(pcm_tone(1.0), 24000, p)
                    outs.append((p, []))
                return outs
            with patch.dict(os.environ, {"TTS_ENGINE": "edge", "GEMINI_API_KEY": "k"}), \
                    patch.object(voice, "_raw_gemini", side_effect=AssertionError("tidak boleh dipanggil")), \
                    patch.object(voice, "_raw_edge", fake_edge):
                s = self._script()
                voice.synthesize(s, cfg, work)
        self.assertEqual(len(s["scenes"]), 2)
        self.assertTrue(all(sc["duration"] > 1.0 for sc in s["scenes"]))


class ProsodyAndFxTests(unittest.TestCase):
    def test_prosody_gets_slower_and_lower_as_story_gets_tense(self):
        base = ("-10%", "-6Hz")
        hook = voice._prosody(*base, "hook")
        reveal = voice._prosody(*base, "reveal")
        self.assertEqual(voice._prosody(*base, None), ("-10%", "-6Hz"))
        self.assertLess(int(reveal[0][:-1]), int(hook[0][:-1]))
        self.assertLess(int(reveal[1][:-2]), int(hook[1][:-2]))
        self.assertEqual(voice._prosody("-44%", "-39Hz", "reveal"), ("-45%", "-40Hz"))   # dibatasi

    def _run_and_capture(self, used_gemini):
        cfg = styles.apply({"voice": "id-ID-ArdiNeural", "rate": "-5%", "style": {}}, "MYSTERY_WAYANG")
        seen = []
        real_run = voice.run

        def spy(cmd, cwd=None):
            seen.append([str(c) for c in cmd])
            return real_run(cmd, cwd=cwd)

        def fake_edge(script, cfg_, work_, rate):
            outs = []
            for i in range(len(script["scenes"])):
                p = work_ / f"e{i}.wav"
                tts_gemini.write_wav(pcm_tone(1.0), 24000, p)
                outs.append((p, []))
            return outs
        with tempfile.TemporaryDirectory() as d, patch.object(voice, "run", spy), \
                patch.object(voice, "_raw_edge", fake_edge), \
                patch.dict(os.environ, {"GEMINI_API_KEY": "k" if used_gemini else "", "TTS_ENGINE": "auto"}), \
                patch.object(voice, "_raw_gemini", lambda s, c, w: fake_edge(s, c, w, None)):
            voice.synthesize({"scenes": [{"narration": "Satu dua tiga."}]}, cfg, Path(d))
        af = [c[c.index("-af") + 1] for c in seen if "-af" in c]
        return af[0]

    def test_horror_voice_fx_only_on_edge_path(self):
        self.assertIn("aecho", self._run_and_capture(used_gemini=False))        # Edge: efek style dipakai
        self.assertNotIn("aecho", self._run_and_capture(used_gemini=True))      # Gemini: suara apa adanya

    def test_voice_fx_can_be_disabled_and_every_style_has_a_valid_chain(self):
        for k in styles.STYLE_KEYS:
            fx = styles.apply({"voice": "x", "rate": "0%", "style": {}}, k)["voice_fx"]
            self.assertTrue(fx.startswith("aresample=44100"), k)
            r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "sine=f=220:d=0.6",
                                "-af", fx, "-f", "null", "-"], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, f"{k}: {r.stderr[-200:]}")


if __name__ == "__main__":
    unittest.main()
