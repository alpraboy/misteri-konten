import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import publish

ENV_KEYS = ["YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN", "FB_PAGE_ID", "FB_PAGE_TOKEN",
            "TIKTOK_CLIENT_KEY", "TIKTOK_CLIENT_SECRET", "TIKTOK_REFRESH_TOKEN", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"]


class R:
    def __init__(self, code=200, body=None, text="", headers=None):
        self.status_code, self._b, self.text, self.headers = code, body if body is not None else {}, text or json.dumps(body or {}), headers or {}

    def json(self):
        return self._b


def clean_env(**extra):
    base = {k: "" for k in ENV_KEYS}
    base.update(extra)
    return patch.dict(os.environ, base)


def make_out(d, size=2048):
    out = Path(d) / "20261101-0000-legenda-tes"
    out.mkdir()
    (out / "video.mp4").write_bytes(b"\0" * size)
    (out / "caption.txt").write_text("Judul\n\nDeskripsi\n\n#misteri\n\nIlustrasi dibuat dengan AI.", encoding="utf-8")
    (out / "script.json").write_text(json.dumps({"title": "T" * 130, "hashtags": ["#misteri", "#horor"],
                                                  "claims_to_verify": ["klaim A", "klaim B"], "visual_style": "MYSTERY_VHS"}), encoding="utf-8")
    return out


class PublishTests(unittest.TestCase):
    def test_no_secrets_means_every_platform_is_skipped_without_any_http_call(self):
        with tempfile.TemporaryDirectory() as d, clean_env(), \
                patch.object(publish.requests, "post", side_effect=AssertionError("tidak boleh ada HTTP")):
            res = publish.run_all(make_out(d))
            self.assertTrue(all(res[k]["status"] == "skip" for k in ("YouTube", "Facebook", "TikTok", "Telegram")))
            self.assertTrue(any(Path(d).rglob("publish_report.md")))

    def test_youtube_uploads_private_with_ai_flag_shorts_tag_and_clipped_title(self):
        calls = []

        def fake_post(url, **kw):
            calls.append((url, kw))
            if "oauth2" in url:
                return R(200, {"access_token": "AT"})
            return R(200, {}, headers={"Location": "https://upload.example/abc"})

        def fake_put(url, **kw):
            calls.append((url, kw))
            return R(200, {"id": "VID123"})
        env = clean_env(YT_CLIENT_ID="a", YT_CLIENT_SECRET="b", YT_REFRESH_TOKEN="c")
        with tempfile.TemporaryDirectory() as d, env, patch.object(publish.requests, "post", fake_post), \
                patch.object(publish.requests, "put", fake_put):
            out = make_out(d)
            r = publish.youtube_private(out / "video.mp4", publish.load_meta(out))
        init_body = [kw["json"] for u, kw in calls if "uploadType=resumable" in u][0]
        self.assertEqual(r["status"], "ok")
        self.assertEqual(r["id"], "VID123")
        self.assertEqual(init_body["status"]["privacyStatus"], "private")
        self.assertTrue(init_body["status"]["containsSyntheticMedia"])
        self.assertFalse(init_body["status"]["selfDeclaredMadeForKids"])
        self.assertLessEqual(len(init_body["snippet"]["title"]), 100)
        self.assertIn("#Shorts", init_body["snippet"]["description"])
        self.assertEqual(init_body["snippet"]["tags"], ["misteri", "horor"])

    def test_youtube_retries_without_synthetic_flag_when_api_rejects_it(self):
        bodies = []

        def fake_post(url, **kw):
            if "oauth2" in url:
                return R(200, {"access_token": "AT"})
            bodies.append(kw["json"]["status"].copy())
            if "containsSyntheticMedia" in kw["json"]["status"]:
                return R(400, text="Invalid field containsSyntheticMedia")
            return R(200, {}, headers={"Location": "https://upload.example/abc"})
        with tempfile.TemporaryDirectory() as d, clean_env(YT_CLIENT_ID="a", YT_CLIENT_SECRET="b", YT_REFRESH_TOKEN="c"), \
                patch.object(publish.requests, "post", fake_post), patch.object(publish.requests, "put", lambda *a, **k: R(200, {"id": "V"})):
            out = make_out(d)
            r = publish.youtube_private(out / "video.mp4", publish.load_meta(out))
        self.assertEqual(len(bodies), 2)
        self.assertEqual(r["status"], "ok")
        self.assertIn("penanda konten AI", r["note"])

    def test_facebook_creates_reel_as_draft_using_three_steps_and_oauth_header(self):
        seen = []

        def fake_post(url, **kw):
            seen.append((url, kw))
            if "upload_phase" in str(kw.get("data", {})) and kw["data"]["upload_phase"] == "start":
                return R(200, {"video_id": "555", "upload_url": "https://rupload.facebook.com/video-upload/555"})
            if url.startswith("https://rupload"):
                return R(200, {"success": True})
            return R(200, {"success": True})
        with tempfile.TemporaryDirectory() as d, clean_env(FB_PAGE_ID="PG", FB_PAGE_TOKEN="TOK"), \
                patch.object(publish.requests, "post", fake_post):
            out = make_out(d, size=4096)
            r = publish.facebook_draft(out / "video.mp4", publish.load_meta(out))
        self.assertEqual(r["status"], "ok")
        self.assertEqual(len(seen), 3)
        up = seen[1][1]["headers"]
        self.assertEqual((up["Authorization"], up["offset"], up["file_size"]), ("OAuth TOK", "0", "4096"))
        fin = seen[2][1]["data"]
        self.assertEqual((fin["upload_phase"], fin["video_state"], fin["video_id"]), ("finish", "DRAFT", "555"))
        self.assertTrue(seen[0][0].endswith("/PG/video_reels"))

    def test_tiktok_chunk_plan_follows_size_rules(self):
        MB = publish.MB
        self.assertEqual(publish.tiktok_chunks(30 * MB), (30 * MB, 1))
        self.assertEqual(publish.tiktok_chunks(64 * MB), (64 * MB, 1))
        chunk, total = publish.tiktok_chunks(90 * MB)
        self.assertEqual((chunk, total), (32 * MB, 2))                    # potongan akhir menyerap sisa (<= 64 MB)
        last = 90 * MB - (total - 1) * chunk
        self.assertTrue(5 * MB <= chunk <= 64 * MB and last <= 128 * MB)

    def test_tiktok_inbox_flow_uploads_all_bytes_with_content_range(self):
        puts = []

        def fake_post(url, **kw):
            if "oauth/token" in url:
                return R(200, {"access_token": "AT", "refresh_token": "NEW"})
            return R(200, {"data": {"publish_id": "P1", "upload_url": "https://upload.tiktok/x"}})

        def fake_put(url, **kw):
            puts.append(kw["headers"]["Content-Range"])
            return R(201)
        with tempfile.TemporaryDirectory() as d, clean_env(TIKTOK_CLIENT_KEY="k", TIKTOK_CLIENT_SECRET="s", TIKTOK_REFRESH_TOKEN="old"), \
                patch.object(publish.requests, "post", fake_post), patch.object(publish.requests, "put", fake_put):
            out = make_out(d, size=5000)
            r = publish.tiktok_inbox(out / "video.mp4", publish.load_meta(out))
        self.assertEqual(r["status"], "ok")
        self.assertEqual(puts, ["bytes 0-4999/5000"])
        self.assertIn("refresh token baru", r["note"])

    def test_one_platform_failing_does_not_stop_the_others_and_telegram_reports_all(self):
        texts, docs = [], []

        def fake_post(url, **kw):
            if "api.telegram.org" in url and url.endswith("sendMessage"):
                texts.append(kw["data"]["text"])
                return R(200, {"ok": True})
            if "api.telegram.org" in url and url.endswith("sendDocument"):
                docs.append(kw["files"]["document"].name)
                return R(200, {"ok": True})
            if "video_reels" in url and kw.get("data", {}).get("upload_phase") == "start":
                return R(200, {"video_id": "1", "upload_url": "https://rupload.facebook.com/video-upload/1"})
            if "video_reels" in url or url.startswith("https://rupload"):
                return R(200, {"success": True})
            raise RuntimeError("YouTube down")
        env = clean_env(YT_CLIENT_ID="a", YT_CLIENT_SECRET="b", YT_REFRESH_TOKEN="c", FB_PAGE_ID="P", FB_PAGE_TOKEN="T",
                        TELEGRAM_BOT_TOKEN="tg", TELEGRAM_CHAT_ID="42")
        with tempfile.TemporaryDirectory() as d, env, patch.object(publish.requests, "post", fake_post):
            out = make_out(d)
            with patch.object(publish, "make_preview", return_value=out / "kirim-telegram.mp4"):
                (out / "kirim-telegram.mp4").write_bytes(b"v")
                res = publish.run_all(out)
        self.assertEqual(res["YouTube"]["status"], "gagal")
        self.assertEqual(res["Facebook"]["status"], "ok")
        self.assertEqual(res["TikTok"]["status"], "skip")
        self.assertIn("YouTube: GAGAL", texts[0])
        self.assertIn("klaim A", texts[0])                                  # klaim yang perlu dicek ikut dikirim
        self.assertIn("Facebook: OK", texts[0])
        self.assertIn("Posting manual untuk YouTube, TikTok", texts[0])
        self.assertTrue(texts[1].startswith("Teks siap tempel"))              # caption siap salin
        self.assertIn("Deskripsi", texts[1])
        self.assertEqual(len(docs), 1)                                        # file video dikirim sebagai dokumen

    def test_telegram_file_keeps_full_resolution_and_fits_bot_limit(self):
        import subprocess
        self.assertLessEqual(publish.target_bitrate(90) * 90 / 8, 47 * publish.MB)     # 90 dtk muat di 47 MB
        self.assertGreater(publish.target_bitrate(30), publish.target_bitrate(90))      # lebih pendek -> bitrate lebih tinggi
        self.assertLessEqual(publish.target_bitrate(5), 8_000_000)
        with tempfile.TemporaryDirectory() as d:
            src, out = Path(d) / "in.mp4", Path(d) / "out.mp4"
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=size=1080x1920:rate=30:duration=3",
                            "-f", "lavfi", "-i", "sine=f=300:d=3", "-pix_fmt", "yuv420p", "-shortest", str(src)], check=True)
            got = publish.make_preview(src, out)
            self.assertEqual(got, out)
            probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                                    "-of", "csv=p=0", str(out)], capture_output=True, text=True).stdout.strip()
            self.assertEqual(probe, "1080,1920")
            self.assertLess(out.stat().st_size, 49 * publish.MB)

    def test_latest_output_picks_newest_folder_with_video(self):
        with tempfile.TemporaryDirectory() as d:
            for name in ("20261030-1000-a", "20261101-0900-b"):
                (Path(d) / name).mkdir()
                (Path(d) / name / "video.mp4").write_bytes(b"x")
            (Path(d) / "20261102-0000-kosong").mkdir()
            self.assertEqual(publish.latest_output(d).name, "20261101-0900-b")

    def test_workflow_has_safe_post_step_and_secrets(self):
        wf = (ROOT / ".github" / "workflows" / "make-video.yml").read_text(encoding="utf-8")
        data = yaml.safe_load(wf)
        self.assertIn("post", data[True]["workflow_dispatch"]["inputs"])
        for key in ("YT_REFRESH_TOKEN", "FB_PAGE_TOKEN", "TIKTOK_REFRESH_TOKEN", "TELEGRAM_BOT_TOKEN"):
            self.assertIn(key, wf)
        steps = data["jobs"]["render"]["steps"]
        names = [s.get("name", "") for s in steps]
        self.assertLess(names.index("Buat video"), names.index("Posting aman (private/draf)"))
        self.assertLess(names.index("Posting aman (private/draf)"), names.index("Simpan hasil (unduh dari tab Artifacts)"))
        post = [s for s in steps if s.get("name") == "Posting aman (private/draf)"][0]
        self.assertTrue(post.get("continue-on-error"))


if __name__ == "__main__":
    unittest.main()
