import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import publish


class R:
    status_code, text = 200, "{}"

    def json(self):
        return {}


class TelegramButtonTests(unittest.TestCase):
    def test_keyboard_has_tiktok_facebook_and_optional_youtube_dashboard(self):
        res = {"YouTube": {"status": "ok", "url": "https://studio.youtube.com/video/V/edit"}}
        with patch.dict(os.environ, {"DASHBOARD_URL": "", "GITHUB_REPOSITORY_OWNER": "BudiX"}):
            kb = publish.keyboard({}, res)["inline_keyboard"]
        flat = {b["text"]: b["url"] for row in kb for b in row}
        self.assertTrue(any("YouTube Studio" in t for t in flat))
        self.assertIn("https://www.tiktok.com/", flat.values())
        self.assertIn("https://www.facebook.com/reels/create", flat.values())
        self.assertIn("https://budix.github.io/agen-misteri-info/dashboard.html", flat.values())   # huruf kecil, sesuai GitHub Pages
        self.assertTrue(all(u.startswith("https://") for u in flat.values()))                        # Telegram hanya menerima tautan web

    def test_no_youtube_button_when_upload_failed_and_no_dashboard_without_owner(self):
        with patch.dict(os.environ, {"DASHBOARD_URL": "", "GITHUB_REPOSITORY_OWNER": ""}):
            kb = publish.keyboard({}, {"YouTube": {"status": "gagal", "note": "x"}})["inline_keyboard"]
        texts = [b["text"] for row in kb for b in row]
        self.assertFalse(any("YouTube" in t for t in texts))
        self.assertFalse(any("Buat video lagi" in t for t in texts))
        self.assertEqual(len(texts), 2)

    def test_explicit_dashboard_url_wins(self):
        with patch.dict(os.environ, {"DASHBOARD_URL": "https://x.example/d.html", "GITHUB_REPOSITORY_OWNER": "a"}):
            self.assertEqual(publish.dashboard_url(), "https://x.example/d.html")

    def test_telegram_sends_buttons_and_tap_to_copy_caption_with_html_escaped(self):
        sent = []

        def fake_post(url, **kw):
            sent.append((url.rsplit("/", 1)[-1], kw.get("data", {})))
            return R()
        meta = {"title": "T", "caption": "Judul <b>&</b>\n#misteri", "claims": [], "style": "MYSTERY_VHS"}
        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "t", "TELEGRAM_CHAT_ID": "1", "GITHUB_REPOSITORY_OWNER": "budi"}), \
                patch.object(publish.requests, "post", fake_post):
            out = publish.telegram(meta, {"YouTube": {"status": "skip"}}, None)
        self.assertEqual(out["status"], "ok")
        summary, caption = sent[0][1], sent[1][1]
        self.assertIn("inline_keyboard", json.loads(summary["reply_markup"]))
        self.assertIn("Bagikan", summary["text"])
        self.assertEqual(caption["parse_mode"], "HTML")
        self.assertIn("<code>Judul &lt;b&gt;&amp;&lt;/b&gt;", caption["text"])       # karakter khusus aman bagi HTML Telegram


@unittest.skipUnless(shutil.which("node") and (ROOT / "site").exists(), "node atau folder site tidak tersedia")
class DashboardTests(unittest.TestCase):
    def test_dashboard_logic_and_simulated_ui_pass_in_node(self):
        r = subprocess.run(["node", str(ROOT / "tests" / "dashboard_test.js")], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("DASHBOARD_OK", r.stdout)

    def test_dashboard_files_are_complete_and_manifest_matches(self):
        site = ROOT / "site"
        for f in ("dashboard.html", "dashboard-core.js", "manifest.webmanifest", "icon-192.png", "icon-512.png"):
            self.assertTrue((site / f).exists(), f)
        man = json.loads((site / "manifest.webmanifest").read_text(encoding="utf-8"))
        self.assertEqual(man["start_url"], "./dashboard.html")
        self.assertTrue(all((site / i["src"]).exists() for i in man["icons"]))
        html = (site / "dashboard.html").read_text(encoding="utf-8")
        self.assertNotIn("github_pat_", html.replace('placeholder="github_pat_..."', ""))   # tidak ada token tertanam


if __name__ == "__main__":
    unittest.main()
