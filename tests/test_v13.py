"""Uji cadangan gambar Gemini (tanpa internet: semua respons dipalsukan)."""
import base64
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import illustrator  # noqa: E402
from PIL import Image  # noqa: E402


class Resp:
    def __init__(self, status=200, payload=None, text=""):
        self.status_code, self._p, self.text = status, payload, text

    def json(self):
        return self._p


def _png_b64(size=(640, 640)):
    buf = io.BytesIO()
    Image.new("RGB", size, (90, 40, 40)).save(buf, "PNG")
    return base64.b64encode(buf.getvalue()).decode()


def _ok():
    return Resp(200, {"candidates": [{"content": {"parts": [{"text": "ok"}, {"inlineData": {"mimeType": "image/png", "data": _png_b64()}}]}}]})


class GeminiFallback(unittest.TestCase):
    def setUp(self):
        illustrator.GEMINI_BROKEN = False
        illustrator.CF_BROKEN = False
        illustrator.HF_BROKEN = False
        illustrator.REMOTE_BROKEN = False
        illustrator.QUOTA_EXHAUSTED = False

    def test_gambar_dibuat_dan_dipaksa_9_16(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "k"}), patch.object(illustrator.requests, "post", lambda *a, **k: _ok()), \
                tempfile.TemporaryDirectory() as d:
            p = illustrator._fetch_gemini("prompt", 1, Path(d) / "a", "blur")
            self.assertIsNotNone(p)
            self.assertEqual(Image.open(p).size, (illustrator.W, illustrator.H))

    def test_tanpa_key_dilewati(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": ""}), tempfile.TemporaryDirectory() as d:
            self.assertIsNone(illustrator._fetch_gemini("p", 1, Path(d) / "a"))

    def test_kuota_habis_memutus_sisa_adegan(self):
        calls = []

        def fake_post(*a, **k):
            calls.append(1)
            return Resp(429, text="quota")

        with patch.dict(os.environ, {"GEMINI_API_KEY": "k"}), patch.object(illustrator.requests, "post", fake_post), \
                patch.object(illustrator.time, "sleep", lambda s: None), tempfile.TemporaryDirectory() as d:
            self.assertIsNone(illustrator._fetch_gemini("p", 1, Path(d) / "a"))
            n = len(calls)
            self.assertTrue(illustrator.GEMINI_BROKEN)
            self.assertIsNone(illustrator._fetch_gemini("p", 2, Path(d) / "b"))
            self.assertEqual(len(calls), n)   # tidak memanggil lagi

    def test_nama_model_404_lanjut_ke_model_berikutnya(self):
        seq = [Resp(404, text="no model"), _ok()]
        with patch.dict(os.environ, {"GEMINI_API_KEY": "k"}), patch.object(illustrator.requests, "post", lambda *a, **k: seq.pop(0)), \
                tempfile.TemporaryDirectory() as d:
            self.assertIsNotNone(illustrator._fetch_gemini("p", 1, Path(d) / "a"))

    def test_rantai_pollinations_gagal_lalu_gemini(self):
        with patch.object(illustrator, "_fetch", lambda *a, **k: None), \
                patch.object(illustrator, "_fetch_gemini", lambda *a, **k: Path("x.png")):
            self.assertEqual(illustrator._fetch_any("p", 1, Path("a")), Path("x.png"))

    def test_pollinations_berhasil_gemini_tidak_dipanggil(self):
        def boom(*a, **k):
            raise AssertionError("Gemini tidak boleh dipanggil")
        with patch.object(illustrator, "_fetch", lambda *a, **k: Path("p.png")), patch.object(illustrator, "_fetch_gemini", boom):
            self.assertEqual(illustrator._fetch_any("p", 1, Path("a")), Path("p.png"))


class CloudflareHF(unittest.TestCase):
    def setUp(self):
        illustrator.CF_BROKEN = False
        illustrator.HF_BROKEN = False

    def test_cloudflare_ok_dan_9_16(self):
        resp = Resp(200, {"result": {"image": _png_b64()}, "success": True})
        env = {"CLOUDFLARE_ACCOUNT_ID": "a", "CLOUDFLARE_API_TOKEN": "t"}
        with patch.dict(os.environ, env), patch.object(illustrator.requests, "post", lambda *a, **k: resp), \
                tempfile.TemporaryDirectory() as d:
            p = illustrator._fetch_cloudflare("p", 1, Path(d) / "a")
            self.assertEqual(Image.open(p).size, (illustrator.W, illustrator.H))

    def test_cloudflare_tanpa_secret_dilewati(self):
        with patch.dict(os.environ, {"CLOUDFLARE_ACCOUNT_ID": "", "CLOUDFLARE_API_TOKEN": ""}), tempfile.TemporaryDirectory() as d:
            self.assertIsNone(illustrator._fetch_cloudflare("p", 1, Path(d) / "a"))

    def test_cloudflare_jatah_habis_memutus(self):
        calls = []

        def fake(*a, **k):
            calls.append(1)
            return Resp(429, text="limit")

        env = {"CLOUDFLARE_ACCOUNT_ID": "a", "CLOUDFLARE_API_TOKEN": "t"}
        with patch.dict(os.environ, env), patch.object(illustrator.requests, "post", fake), tempfile.TemporaryDirectory() as d:
            self.assertIsNone(illustrator._fetch_cloudflare("p", 1, Path(d) / "a"))
            self.assertIsNone(illustrator._fetch_cloudflare("p", 2, Path(d) / "b"))
            self.assertEqual(len(calls), 1)
            self.assertTrue(illustrator.CF_BROKEN)

    def test_hf_tanpa_token_dilewati(self):
        with patch.dict(os.environ, {"HF_TOKEN": ""}), tempfile.TemporaryDirectory() as d:
            self.assertIsNone(illustrator._fetch_hf("p", 1, Path(d) / "a"))

    def test_hf_error_tidak_menghentikan_render(self):
        with patch.dict(os.environ, {"HF_TOKEN": "x"}), tempfile.TemporaryDirectory() as d:
            import types
            fake_mod = types.ModuleType("huggingface_hub")

            class Boom:
                def __init__(self, *a, **k):
                    pass

                def text_to_image(self, *a, **k):
                    raise RuntimeError("kredit habis")
            fake_mod.InferenceClient = Boom
            with patch.dict(sys.modules, {"huggingface_hub": fake_mod}):
                self.assertIsNone(illustrator._fetch_hf("p", 1, Path(d) / "a"))
            self.assertTrue(illustrator.HF_BROKEN)

    def test_urutan_rantai(self):
        order = []

        def mk(name, ret=None):
            def f(*a, **k):
                order.append(name)
                return ret
            return f
        with patch.object(illustrator, "_fetch", mk("poll")), patch.object(illustrator, "_fetch_cloudflare", mk("cf")), \
                patch.object(illustrator, "_fetch_gemini", mk("gem")), patch.object(illustrator, "_fetch_hf", mk("hf", Path("h.png"))):
            self.assertEqual(illustrator._fetch_any("p", 1, Path("a")), Path("h.png"))
        self.assertEqual(order, ["poll", "cf", "gem", "hf"])


class FootageFallback(unittest.TestCase):
    def test_keywords_kosong_diturunkan_dari_image_prompt(self):
        import footage
        qs = footage.fallback_queries({"keywords": [], "broll_keywords": [],
                                       "image_prompt": "abandoned colonial hospital corridor, dramatic shadows, eerie fog"})
        self.assertTrue(qs)
        self.assertIn("abandoned", qs[0])

    def test_keywords_asli_didahulukan(self):
        import footage
        self.assertEqual(footage.fallback_queries({"keywords": ["old temple"], "image_prompt": "x"}), ["old temple"])
        self.assertEqual(footage.fallback_queries({"keywords": [], "broll_keywords": ["foggy forest"]}), ["foggy forest"])


if __name__ == "__main__":
    unittest.main()
