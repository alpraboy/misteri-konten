import re
import subprocess
import unicodedata


def run(cmd, cwd=None):
    """Jalankan perintah; bila gagal tampilkan error asli (tanpa baris progres ffmpeg)."""
    cmd = [str(c) for c in cmd]
    print("$", " ".join(cmd)[:300])
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        lines = [
            ln for ln in r.stderr.replace("\r", "\n").split("\n")
            if ln.strip() and not ln.startswith("frame=")
        ]
        print(f"=== GAGAL (kode keluar {r.returncode}) ===")
        print("\n".join(lines[-40:]))
        raise RuntimeError(f"Perintah gagal: {cmd[0]} (kode {r.returncode})")
    return r.stdout


def duration(path):
    """Durasi file media dalam detik (via ffprobe)."""
    out = run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=nw=1:nk=1", path,
    ])
    return float(out.strip())


def slugify(text, maxlen=40):
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text[:maxlen].strip("-") or "video"
