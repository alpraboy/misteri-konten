"""Uji riwayat topik: agen tidak boleh mengulang topik/judul yang sudah pernah dibuat."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import history  # noqa: E402
import script_agent  # noqa: E402
import sources  # noqa: E402


class HistoryBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "history.json"
        self.env = patch.dict(os.environ, {"HISTORY_FILE": str(self.path)})
        self.env.start()
        script_agent._TOPIC_EN.clear()
        script_agent._TOPIC_REGION.clear()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()


class Similarity(unittest.TestCase):
    def test_sama_walau_susunan_beda(self):
        self.assertTrue(history.is_similar("Segitiga Bermuda", "Misteri Segitiga Bermuda"))
        self.assertTrue(history.is_similar("Kuntilanak Jembatan Ancol", "kisah kuntilanak di jembatan ancol"))

    def test_topik_pendek_termuat_di_judul_panjang(self):
        self.assertTrue(history.is_similar("Segitiga Bermuda", "Hilangnya Kapal di Segitiga Bermuda"))

    def test_topik_berbeda_tidak_dianggap_sama(self):
        self.assertFalse(history.is_similar("Segitiga Bermuda", "Kapal Mary Celeste"))
        self.assertFalse(history.is_similar("Kuntilanak Jembatan Ancol", "Genderuwo Hutan Jati"))
        self.assertFalse(history.is_similar("Candi Sukuh", "Candi Borobudur"))

    def test_kosong_bukan_duplikat(self):
        self.assertFalse(history.is_similar("", "apa saja"))
        self.assertFalse(history.is_similar("misteri", "kisah"))   # hanya kata umum


class Storage(HistoryBase):
    def test_simpan_dan_baca(self):
        history.record("sejarah", "Segitiga Bermuda", "Kapal yang Lenyap", "Bermuda Triangle", "Segitiga Bermuda", "Amerika")
        e = history.load()
        self.assertEqual(len(e), 1)
        self.assertEqual(e[0]["title"], "Kapal yang Lenyap")
        self.assertIsNotNone(history.find_duplicate(["bermuda triangle"]))
        self.assertIsNotNone(history.find_duplicate(["Kapal yang lenyap di laut"]))
        self.assertIsNone(history.find_duplicate(["Mary Celeste"]))

    def test_file_belum_ada_atau_rusak_tidak_crash(self):
        self.assertEqual(history.load(), [])
        self.path.write_text("{bukan json", encoding="utf-8")
        self.assertEqual(history.load(), [])
        history.record("cerita", "Pocong Sawah", "Pocong di Pematang")   # tidak boleh error; file rusak dicadangkan
        self.assertEqual(len(history.load()), 1)
        self.assertTrue(self.path.with_suffix(".bak").exists())

    def test_pick_region_memilih_yang_paling_jarang(self):
        for _ in range(3):
            history.record("sejarah", "x", "y", region="Eropa")
        history.record("sejarah", "x2", "y2", region="Asia")
        picks = {history.pick_region("sejarah", ["Eropa", "Asia", "Mesir"]) for _ in range(20)}
        self.assertEqual(picks, {"Mesir"})

    def test_batas_jumlah_entri(self):
        with patch.object(history, "MAX_ENTRIES", 5):
            for i in range(8):
                history.record("cerita", f"topik{i}", f"judul{i}")
        self.assertEqual(len(history.load()), 5)


class PickTopic(HistoryBase):
    CFG = {"source": "wikipedia", "topic_hint": "misteri sejarah", "regions": ["Eropa", "Asia"]}

    def test_melewati_usulan_yang_sudah_pernah_dibuat(self):
        history.record("sejarah", "Segitiga Bermuda", "Kapal yang Lenyap", "Bermuda Triangle")
        reply = {"candidates": [{"topic": "Misteri Segitiga Bermuda", "topic_en": "Bermuda Triangle"},
                                {"topic": "Kapal Mary Celeste", "topic_en": "Mary Celeste"}]}
        with patch.object(script_agent, "_gemini", return_value=reply):
            self.assertEqual(script_agent._pick_topic("sejarah", self.CFG, ""), "Kapal Mary Celeste")
        self.assertEqual(script_agent._TOPIC_EN["Kapal Mary Celeste"], "Mary Celeste")

    def test_riwayat_ikut_dikirim_ke_prompt(self):
        history.record("sejarah", "Segitiga Bermuda", "Kapal yang Lenyap")
        seen = {}

        def fake(prompt, temperature=0.9):
            seen["p"] = prompt
            return {"candidates": [{"topic": "Candi Sukuh", "topic_en": "Sukuh"}]}
        with patch.object(script_agent, "_gemini", fake):
            script_agent._pick_topic("sejarah", self.CFG, "")
        self.assertIn("Segitiga Bermuda", seen["p"])

    def test_semua_usulan_duplikat_berhenti_dengan_pesan_jelas(self):
        history.record("sejarah", "Segitiga Bermuda", "Kapal yang Lenyap")
        reply = {"candidates": [{"topic": "Segitiga Bermuda", "topic_en": ""}]}
        calls = []

        def fake(*a, **k):
            calls.append(1)
            return reply
        with patch.object(script_agent, "_gemini", fake):
            with self.assertRaisesRegex(RuntimeError, "topik baru"):
                script_agent._pick_topic("sejarah", self.CFG, "")
        self.assertEqual(len(calls), 3)

    def test_topik_manual_tetap_dipakai_dengan_peringatan(self):
        history.record("sejarah", "Segitiga Bermuda", "Kapal yang Lenyap")
        self.assertEqual(script_agent._pick_topic("sejarah", self.CFG, "Segitiga Bermuda"), "Segitiga Bermuda")

    def test_format_lama_satu_topik_masih_diterima(self):
        with patch.object(script_agent, "_gemini", return_value={"topic": "Candi Sukuh", "topic_en": "Sukuh"}):
            self.assertEqual(script_agent._pick_topic("sejarah", self.CFG, ""), "Candi Sukuh")


class GenerateDedup(HistoryBase):
    def _data(self, title):
        scenes = [{"narration": f"Kalimat adegan nomor {i} " + " ".join(["kata"] * 11), "visual": "illustration",
                   "image_prompt": "x", "keywords": [], "motion": "zoom_in", "impact_word": "", "emphasis": [],
                   "broll_keywords": [], "onscreen": "", "beat": "clue", "visual_role": "evidence"} for i in range(10)]
        return {"title": title, "scenes": scenes, "caption": "c", "hashtags": [], "claims_to_verify": []}

    def test_artikel_wikipedia_yang_sudah_dipakai_diganti_topik_lain(self):
        history.record("sejarah", "Segitiga Bermuda", "Kapal yang Lenyap", wiki="Segitiga Bermuda")
        cfg = {"source": "wikipedia", "topic_hint": "h", "regions": ["Eropa"], "label": "L", "tone": "t"}
        picks = iter(["Bermuda Triangle", "Mary Celeste"])
        arts = {"Bermuda Triangle": ("Segitiga Bermuda", "teks", "u1"), "Mary Celeste": ("Mary Celeste", "teks2", "u2")}
        with patch.object(script_agent, "_pick_topic", side_effect=lambda *a, **k: next(picks)), \
                patch.object(sources, "wikipedia_context", side_effect=lambda q, **k: arts[q]), \
                patch.object(script_agent, "_gemini", return_value=self._data("Kapal Tanpa Awak")):
            out = script_agent.generate("sejarah", cfg)
        self.assertEqual(out["wiki_title"], "Mary Celeste")
        self.assertEqual(out["topic"], "Mary Celeste")

    def test_judul_mirip_membuat_ulang_satu_kali(self):
        history.record("berita", "", "Cahaya Aneh di Langit Bandung")
        cfg = {"source": "none", "topic_hint": "h", "regions": ["Jawa"], "label": "L", "tone": "t"}
        titles = iter([self._data("Cahaya Aneh di Langit Bandung"), self._data("Suara dari Gua Pawon")])
        prompts = []
        with patch.object(script_agent, "_pick_topic", return_value="Bandung"), \
                patch.object(script_agent, "_gemini", side_effect=lambda p, *a, **k: (prompts.append(p), next(titles))[1]):
            out = script_agent.generate("berita", cfg)
        self.assertEqual(out["title"], "Suara dari Gua Pawon")
        self.assertEqual(len(prompts), 2)                      # tepat satu kali buat ulang
        self.assertIn("Cahaya Aneh di Langit Bandung", prompts[1])

    def test_judul_lama_dikirim_ke_prompt(self):
        history.record("cerita", "Pocong Sawah", "Pocong di Pematang")
        cfg = {"source": "none", "topic_hint": "h", "regions": ["Jawa"], "label": "L", "tone": "t"}
        seen = []
        with patch.object(script_agent, "_pick_topic", return_value="Genderuwo"), \
                patch.object(script_agent, "_gemini", side_effect=lambda p, *a, **k: (seen.append(p), self._data("Genderuwo Hutan Jati"))[1]):
            script_agent.generate("cerita", cfg)
        self.assertIn("Pocong di Pematang", seen[0])


if __name__ == "__main__":
    unittest.main()
