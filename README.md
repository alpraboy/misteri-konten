# Agen Konten Misteri (Sejarah / Cerita / Berita)

Pipeline video vertikal 60 detik yang berjalan penuh di GitHub Actions.
Upload ke YouTube/TikTok dilakukan manual oleh Anda.

## Setup (sekali saja)
1. Buat repo GitHub, unggah semua isi folder ini.
2. Settings > Secrets and variables > Actions > New repository secret:
   - `GEMINI_API_KEY` : gratis di https://aistudio.google.com/apikey
   - `PEXELS_API_KEY` : gratis di https://www.pexels.com/api/
3. (Disarankan) Taruh 2-3 musik bebas royalti (.mp3) di `assets/music/`
   atau per tema: `assets/music/sejarah/`, `assets/music/cerita/`, `assets/music/berita/`.

## Menjalankan
Tab **Actions** > **Buat Video Misteri** > **Run workflow** > pilih tema, isi topik (boleh kosong).
Setelah selesai, unduh **Artifacts** di bagian bawah halaman run.

## Isi hasil
- `video.mp4`      video 1080x1920
- `caption.txt`    judul, deskripsi, hashtag, disclaimer
- `verify.md`      klaim yang harus dicek + sumber + kredit footage
- `thumbnail.jpg`  frame awal (bisa dipakai/ditimpa)
- `script.json`    skrip lengkap

## Kustomisasi
- Gaya per tema (suara, warna, font, grade): `config/themes.yml`
- Model Gemini: env `GEMINI_MODEL` (default `gemini-2.5-flash`)

## Catatan
- Selalu baca `verify.md` sebelum upload, terutama tema sejarah & berita.
- Tema cerita adalah fiksi/legenda; disclaimer otomatis masuk caption.
