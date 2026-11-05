"""Posting mode AMAN: video diunggah sebagai private/draf, Anda cek lalu publish sendiri.

  YouTube   -> private (+ penanda konten sintetis)           butuh YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN
  Facebook  -> Reel berstatus DRAFT di Page                  butuh FB_PAGE_ID, FB_PAGE_TOKEN
  TikTok    -> draf di kotak masuk TikTok (Inbox)            butuh TIKTOK_CLIENT_KEY, TIKTOK_CLIENT_SECRET, TIKTOK_REFRESH_TOKEN
  Telegram  -> ringkasan + pratinjau video ke ponsel Anda    butuh TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

Platform tanpa secret dilewati. Kegagalan satu platform tidak menghentikan yang lain
(PUBLISH_STRICT=1 membuat workflow gagal bila ada yang gagal).
"""
import html
import json
import math
import os
import subprocess
import sys
from pathlib import Path

import requests

FB_VERSION = os.environ.get("FB_GRAPH_VERSION", "v23.0")
MB = 1024 * 1024


# ------------------------------------------------------------------ util
def _env(*names):
    vals = [os.environ.get(n, "").strip() for n in names]
    return vals if all(vals) else None


def _short(text, n=300):
    return str(text).replace("\n", " ")[:n]


def latest_output(root="output"):
    dirs = sorted((p for p in Path(root).glob("*") if (p / "video.mp4").exists()), key=lambda p: p.name)
    if not dirs:
        raise FileNotFoundError("Tidak ada folder output berisi video.mp4")
    return dirs[-1]


def load_meta(out_dir: Path):
    script = {}
    if (out_dir / "script.json").exists():
        script = json.loads((out_dir / "script.json").read_text(encoding="utf-8"))
    caption = (out_dir / "caption.txt").read_text(encoding="utf-8") if (out_dir / "caption.txt").exists() else ""
    title = (script.get("title") or "Misteri").strip()
    tags = [t.lstrip("#").strip() for t in script.get("hashtags", []) if t.strip()]
    return {"title": title, "caption": caption.strip(), "tags": tags, "claims": script.get("claims_to_verify", []),
            "reused": script.get("image_reused", []),
            "style": script.get("visual_style", ""), "duration": None}


def clip_tags(tags, limit=450):
    out, used = [], 0
    for t in tags:
        if used + len(t) + 1 > limit:
            break
        out.append(t)
        used += len(t) + 1
    return out


# ------------------------------------------------------------------ YouTube (private)
def youtube_private(video: Path, meta):
    creds = _env("YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN")
    if not creds:
        return {"status": "skip", "note": "secret YouTube belum diisi"}
    cid, secret, refresh = creds
    r = requests.post("https://oauth2.googleapis.com/token", data={
        "client_id": cid, "client_secret": secret, "refresh_token": refresh, "grant_type": "refresh_token"}, timeout=30)
    if r.status_code != 200:
        return {"status": "gagal", "note": f"token ditolak ({r.status_code}): {_short(r.text)}"}
    access = r.json()["access_token"]

    desc = meta["caption"]
    if "#Shorts" not in desc:
        desc += "\n\n#Shorts"
    body = {
        "snippet": {"title": meta["title"][:100], "description": desc[:4900], "tags": clip_tags(meta["tags"]),
                    "categoryId": "24", "defaultLanguage": "id", "defaultAudioLanguage": "id"},
        "status": {"privacyStatus": "private", "selfDeclaredMadeForKids": False, "containsSyntheticMedia": True},
    }
    size = video.stat().st_size
    headers = {"Authorization": f"Bearer {access}", "Content-Type": "application/json; charset=UTF-8",
               "X-Upload-Content-Type": "video/mp4", "X-Upload-Content-Length": str(size)}
    url = "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status"
    r = requests.post(url, headers=headers, json=body, timeout=60)
    if r.status_code == 400 and "containsSyntheticMedia" in r.text:   # bidang belum dikenal -> ulangi tanpa itu
        body["status"].pop("containsSyntheticMedia")
        r = requests.post(url, headers=headers, json=body, timeout=60)
        meta["yt_note"] = "penanda konten AI harus dicentang manual di YouTube Studio"
    if r.status_code != 200 or not r.headers.get("Location"):
        return {"status": "gagal", "note": f"sesi unggah gagal ({r.status_code}): {_short(r.text)}"}
    with open(video, "rb") as f:
        up = requests.put(r.headers["Location"], data=f, timeout=(30, 1800),
                          headers={"Content-Type": "video/mp4", "Content-Length": str(size)})
    if up.status_code not in (200, 201):
        return {"status": "gagal", "note": f"unggah gagal ({up.status_code}): {_short(up.text)}"}
    vid = up.json().get("id", "")
    return {"status": "ok", "id": vid, "url": f"https://studio.youtube.com/video/{vid}/edit",
            "note": "private; buka YouTube Studio, cek, lalu ubah ke Public. " + meta.get("yt_note", "")}


# ------------------------------------------------------------------ Facebook (Reel DRAFT)
def facebook_draft(video: Path, meta):
    creds = _env("FB_PAGE_ID", "FB_PAGE_TOKEN")
    if not creds:
        return {"status": "skip", "note": "secret Facebook belum diisi"}
    page, token = creds
    base = f"https://graph.facebook.com/{FB_VERSION}/{page}/video_reels"
    r = requests.post(base, data={"upload_phase": "start", "access_token": token}, timeout=60)
    if r.status_code != 200 or "video_id" not in r.json():
        return {"status": "gagal", "note": f"mulai unggah gagal ({r.status_code}): {_short(r.text)}"}
    vid, upload_url = r.json()["video_id"], r.json().get("upload_url") or f"https://rupload.facebook.com/video-upload/{r.json()['video_id']}"
    size = video.stat().st_size
    with open(video, "rb") as f:
        up = requests.post(upload_url, data=f, timeout=(30, 1800), headers={
            "Authorization": f"OAuth {token}", "offset": "0", "file_size": str(size)})
    if up.status_code != 200:
        return {"status": "gagal", "note": f"unggah byte gagal ({up.status_code}): {_short(up.text)}"}
    fin = requests.post(base, data={
        "upload_phase": "finish", "video_id": vid, "video_state": "DRAFT",
        "title": meta["title"][:100], "description": meta["caption"][:2000], "access_token": token}, timeout=60)
    if fin.status_code != 200:
        return {"status": "gagal", "note": f"finalisasi gagal ({fin.status_code}): {_short(fin.text)}"}
    return {"status": "ok", "id": vid, "url": "https://business.facebook.com/latest/content_posting",
            "note": "Reel berstatus DRAFT; buka Meta Business Suite > Konten > Draf, cek, lalu publish."}


# ------------------------------------------------------------------ TikTok (draf di Inbox)
def tiktok_chunks(size):
    """Rencana potongan unggah TikTok: <=64MB satu potong; lebih besar dibagi 32MB, sisa digabung ke potongan akhir."""
    if size <= 64 * MB:
        return size, 1
    chunk = 32 * MB
    return chunk, max(1, size // chunk)


def tiktok_inbox(video: Path, meta):
    creds = _env("TIKTOK_CLIENT_KEY", "TIKTOK_CLIENT_SECRET", "TIKTOK_REFRESH_TOKEN")
    if not creds:
        return {"status": "skip", "note": "secret TikTok belum diisi"}
    key, secret, refresh = creds
    r = requests.post("https://open.tiktokapis.com/v2/oauth/token/", data={
        "client_key": key, "client_secret": secret, "grant_type": "refresh_token", "refresh_token": refresh},
        headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=30)
    if r.status_code != 200 or "access_token" not in r.json():
        return {"status": "gagal", "note": f"token ditolak ({r.status_code}): {_short(r.text)}"}
    access = r.json()["access_token"]
    note = ""
    if r.json().get("refresh_token") and r.json()["refresh_token"] != refresh:
        note = " PERINGATAN: TikTok mengeluarkan refresh token baru; perbarui secret TIKTOK_REFRESH_TOKEN."

    size = video.stat().st_size
    chunk, total = tiktok_chunks(size)
    init = requests.post("https://open.tiktokapis.com/v2/post/publish/inbox/video/init/", timeout=60,
                         headers={"Authorization": f"Bearer {access}", "Content-Type": "application/json; charset=UTF-8"},
                         json={"source_info": {"source": "FILE_UPLOAD", "video_size": size,
                                               "chunk_size": chunk, "total_chunk_count": total}})
    data = (init.json() or {}).get("data") or {}
    if init.status_code != 200 or not data.get("upload_url"):
        return {"status": "gagal", "note": f"init gagal ({init.status_code}): {_short(init.text)}"}
    with open(video, "rb") as f:
        for i in range(total):
            start = i * chunk
            end = size - 1 if i == total - 1 else start + chunk - 1
            f.seek(start)
            blob = f.read(end - start + 1)
            up = requests.put(data["upload_url"], data=blob, timeout=(30, 1800), headers={
                "Content-Type": "video/mp4", "Content-Length": str(len(blob)),
                "Content-Range": f"bytes {start}-{end}/{size}"})
            if up.status_code not in (200, 201, 206):
                return {"status": "gagal", "note": f"unggah potongan {i + 1}/{total} gagal ({up.status_code}): {_short(up.text)}"}
    return {"status": "ok", "id": data.get("publish_id", ""), "url": "",
            "note": "draf masuk kotak masuk TikTok; buka aplikasi TikTok (notifikasi), aktifkan label konten AI, lalu posting dalam 24 jam." + note}


# ------------------------------------------------------------------ Telegram
def _duration(video: Path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(video)],
                       capture_output=True, text=True)
    try:
        return max(float(r.stdout.strip()), 1.0)
    except ValueError:
        return 60.0


def target_bitrate(duration, limit_mb=47.0, audio_kbps=128):
    """Bitrate video (bit/s) agar file <= limit_mb: tetap 1080x1920, kualitas setinggi yang muat."""
    total = limit_mb * MB * 8 / max(duration, 1.0)
    return int(min(8_000_000, max(900_000, total - audio_kbps * 1000)))


def make_preview(video: Path, out: Path):
    """File siap-unggah manual (TikTok/Facebook) yang muat di bot Telegram (<50 MB), resolusi penuh."""
    dur = _duration(video)
    for limit in (47.0, 40.0, 33.0):
        tb = target_bitrate(dur, limit)
        r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(video),
                            "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease",
                            "-c:v", "libx264", "-preset", "veryfast", "-b:v", str(tb),
                            "-maxrate", str(int(tb * 1.12)), "-bufsize", str(tb * 2),
                            "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(out)],
                           capture_output=True, text=True)
        if r.returncode == 0 and out.exists() and out.stat().st_size < 49 * MB:
            return out
    return None


def dashboard_url():
    """Alamat dashboard HP: env DASHBOARD_URL, atau diturunkan dari pemilik repo (GitHub Pages)."""
    url = os.environ.get("DASHBOARD_URL", "").strip()
    if url:
        return url
    owner = os.environ.get("GITHUB_REPOSITORY_OWNER", "").strip().lower()
    return f"https://{owner}.github.io/agen-misteri-info/dashboard.html" if owner else ""


def keyboard(meta, results):
    """Tombol di bawah pesan Telegram (tautan https saja; tidak perlu server)."""
    rows = []
    yt = results.get("YouTube", {})
    if yt.get("status") == "ok" and yt.get("url"):
        rows.append([{"text": "\u25B6\uFE0F Buka YouTube Studio", "url": yt["url"]}])
    rows.append([{"text": "\U0001F3B5 Buka TikTok", "url": "https://www.tiktok.com/"},
                 {"text": "\U0001F4D8 Facebook Reels", "url": "https://www.facebook.com/reels/create"}])
    dash = dashboard_url()
    if dash:
        rows.append([{"text": "\U0001F3AC Buat video lagi", "url": dash}])
    return {"inline_keyboard": rows}


def summary_text(meta, results):
    icon = {"ok": "OK", "gagal": "GAGAL", "skip": "dilewati"}
    lines = [f"Video siap dicek: {meta['title']}", f"Style: {meta.get('style') or '-'}", ""]
    for name, r in results.items():
        lines.append(f"- {name}: {icon.get(r['status'], r['status'])}. {r.get('note', '')}".strip())
        if r.get("url"):
            lines.append(f"  {r['url']}")
    if meta.get("reused"):
        lines += ["", "Catatan: gambar adegan " + ", ".join(map(str, meta["reused"]))
                  + " dipakai ulang karena saldo/kuota gambar habis."]
    if meta.get("claims"):
        lines += ["", "Klaim yang perlu dicek sebelum publish:"] + [f"* {c}" for c in meta["claims"][:6]]
    skipped = [n for n, r in results.items() if r["status"] != "ok"]
    if skipped:
        lines += ["", f"Posting manual untuk {', '.join(skipped)}: pakai file video dan teks caption yang dikirim sesudah pesan ini."]
    lines += ["", "Cara tercepat posting manual: ketuk file video di bawah > Bagikan (Share) > pilih TikTok / Facebook. "
                  "Tempel caption dari pesan berikutnya (ketuk teks untuk menyalin).",
              "Cek juga verify.md di Artifacts. Aktifkan label konten AI di platform bila diminta."]
    return "\n".join(lines)[:3900]


def telegram(meta, results, preview: Path | None):
    creds = _env("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID")
    if not creds:
        return {"status": "skip", "note": "secret Telegram belum diisi"}
    token, chat = creds
    api = f"https://api.telegram.org/bot{token}"

    def send(text, **extra):
        data = {"chat_id": chat, "text": text[:4000], "disable_web_page_preview": "true"}
        data.update(extra)
        return requests.post(f"{api}/sendMessage", data=data, timeout=30)
    r = send(summary_text(meta, results), reply_markup=json.dumps(keyboard(meta, results)))
    if r.status_code != 200:
        return {"status": "gagal", "note": f"sendMessage {r.status_code}: {_short(r.text, 120)}"}
    if meta.get("caption"):   # teks siap salin untuk posting manual TikTok/Facebook
        # <code> = ketuk untuk menyalin seluruh teks di Telegram HP
        send("Teks siap tempel (TikTok / Facebook), ketuk teks untuk menyalin:\n\n<code>"
             + html.escape(meta["caption"][:3600]) + "</code>", parse_mode="HTML")
    if preview:
        with open(preview, "rb") as f:
            v = requests.post(f"{api}/sendDocument", data={
                "chat_id": chat, "caption": "File video siap unggah manual (1080x1920). Simpan lalu unggah ke TikTok/Facebook."},
                files={"document": f}, timeout=(30, 900))
        if v.status_code != 200:
            return {"status": "ok", "note": f"teks terkirim, file video gagal ({v.status_code})"}
    return {"status": "ok", "note": "terkirim"}


# ------------------------------------------------------------------ orkestrasi
def run_all(out_dir: Path):
    meta = load_meta(out_dir)
    video = out_dir / "video.mp4"
    results = {}
    for name, fn in (("YouTube", youtube_private), ("Facebook", facebook_draft), ("TikTok", tiktok_inbox)):
        try:
            results[name] = fn(video, meta)
        except Exception as e:   # satu platform gagal tidak menghentikan yang lain
            results[name] = {"status": "gagal", "note": f"{type(e).__name__}: {_short(e, 200)}"}
        print(f"{name}: {results[name]['status']} - {results[name].get('note', '')}")
    preview = None
    if _env("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
        preview = make_preview(video, out_dir / "kirim-telegram.mp4")
    tg = telegram(meta, results, preview)
    print(f"Telegram: {tg['status']} - {tg.get('note', '')}")
    if preview and preview.exists():
        preview.unlink()
    results["Telegram"] = tg
    lines = ["# Laporan posting (mode aman: private/draf)\n"]
    for name, r in results.items():
        lines.append(f"- **{name}**: {r['status']}. {r.get('note', '')} {r.get('url', '')}")
    (out_dir / "publish_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return results


def main():
    out_dir = latest_output(sys.argv[1] if len(sys.argv) > 1 else "output")
    print(f"Memposting dari: {out_dir}")
    results = run_all(out_dir)
    failed = [n for n, r in results.items() if r["status"] == "gagal"]
    if failed and os.environ.get("PUBLISH_STRICT") == "1":
        sys.exit(f"Posting gagal: {', '.join(failed)}")
    if not any(r["status"] == "ok" for n, r in results.items() if n != "Telegram"):
        print("Tidak ada platform yang aktif/berhasil (secret belum diisi?). Video tetap tersedia di Artifacts.")


if __name__ == "__main__":
    main()
