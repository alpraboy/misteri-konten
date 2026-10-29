import re
import subprocess
import unicodedata


def run(cmd, cwd=None):
    """Jalankan perintah; tampilkan error asli bila gagal."""
    cmd = [str(c) for c in cmd]
    print("$", " ".join(cmd)[:300])
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr[-3000:])
        raise RuntimeError(f"Perintah gagal: {cmd[0]}")
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
