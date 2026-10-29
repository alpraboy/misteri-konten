# Agen Misteri Cinematic v6 — Retention Engine (Sejarah / Cerita / Berita)

Pipeline video vertikal 9:16 dengan target durasi 60–90 detik, cinematic + motion graphics, hook terstruktur, dan laporan QA retensi. Berjalan di GitHub Actions.
Upload ke YouTube/TikTok dilakukan manual oleh Anda.

## Setup (sekali saja)
1. Buat repo GitHub, unggah semua isi folder ini.
2. Settings > Secrets and variables > Actions > New repository secret:
   - `GEMINI_API_KEY` : gratis di https://aistudio.google.com/apikey
   - `PIXABAY_API_KEY` : gratis, lihat di https://pixabay.com/api/docs/ setelah login
   - (opsional) `PEXELS_API_KEY` : pendaftaran key baru Pexels sedang dijeda
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
- `script.json`    skrip lengkap + beat/visual role
- `retention_report.md` cek ritme, hook, struktur cerita, dan checklist upload

## Kustomisasi
- Gaya per tema (suara, warna, font, grade): `config/themes.yml`
- Model Gemini: env `GEMINI_MODEL` (default `gemini-flash-latest`)

## Catatan
- Selalu baca `verify.md` sebelum upload, terutama tema sejarah & berita.
- Tema cerita adalah fiksi/legenda; disclaimer otomatis masuk caption.

## Gaya visual (fondasi v2)
Komik tinta hitam-putih + satu warna aksen per tema. Tiap video: ilustrasi AI per adegan
(Pollinations, tanpa key), maksimal 2 adegan footage Pixabay sebagai variasi.
Tokoh dibuat per cerita, gayanya sama. Typography: judul "stiker komik" + subtitle pop beraksen.
- Batas anonim Pollinations ~1 gambar / 15 detik, jadi tahap ilustrasi memakan beberapa menit.
- Bila ilustrasi gagal, adegan itu otomatis memakai footage (butuh PIXABAY_API_KEY).
- Opsional: secret `POLLINATIONS_API_KEY` / `POLLINATIONS_MODEL` bila ingin mengatur model atau batas.

## Cinematic Retention Engine (v6)
- **A — Cinematic documentary:** komposisi bidikan punya fungsi (establishing wide, medium untuk aksi, close-up hanya untuk detail penting); gerakan kamera sangat halus dengan zoom/pan kecil, durasi bidikan lebih panjang.
- **B — Visual mengikuti cerita:** prompt storyboard diarahkan untuk menggambarkan isi narasi secara spesifik. Setiap adegan menambahkan informasi visual baru, menjaga konsistensi palet, era, cuaca dan tokoh, serta memakai transisi dissolve yang tenang.
- **C — Identitas Agen Misteri:** penanda brand kecil, judul pembuka sederhana, subtitle stabil tanpa efek memantul, dan penutup ringkas. Tipografi tidak lagi membanting atau bergetar.
- Tidak ada whoosh/hit, kilatan putih, garis kecepatan, getaran kamera, atau noise film. Hanya narasi dan musik latar lembut (jika tersedia); musik otomatis diredam saat narasi.
- Tempo suara dibuat lebih santai dan jeda antarscene diperpanjang. Target v6 adalah 60–90 detik. Jika durasi di luar rentang, rapikan naskah; jangan memaksa narasi dipercepat.
- Gambar lebih baik bila memakai key gratis dari https://enter.pollinations.ai: simpan sebagai secret `POLLINATIONS_API_KEY` (model default `flux`).

### Catatan V6
- Subtitle/brand/title dirender melalui ASS. Pastikan font Montserrat dan DejaVu tersedia di runner.
- Musik bersifat opsional. Jika folder `assets/music/` kosong, render menggunakan narasi saja.
- Output belum dianggap teruji sampai satu render penuh berhasil di GitHub Actions; periksa Artifact, sinkronisasi subtitle, dan audio sebelum upload.


### Retention Engine v6
- Target narasi 145–175 kata, 9–12 adegan, target audio 60–90 detik. Durasi aktual diukur setelah TTS; di luar target ditandai REVIEW dan tidak dipercepat paksa.
- Story beats: hook → context → clue → complication → reveal → payoff. Hook harus spesifik dan payoff harus menjawab janji pembuka.
- Visual cinematic + motion graphics terkendali: label beat, penanda progres adegan, komposisi berbasis peran visual, subtitle di area lebih aman.
- `verify.md` menampilkan kecocokan kata dengan bahan sumber sebagai sinyal awal, bukan bukti kebenaran. Periksa klaim faktual secara manual pada sumber asli sebelum unggah.
- `retention_report.md` membantu pemeriksaan editorial; data retensi penonton sesungguhnya hanya tersedia dari analitik platform setelah video diterbitkan.
- Target 60–90 detik adalah sasaran, bukan jaminan. TTS, jeda, dan panjang kalimat dapat memengaruhi durasi akhir.


### Pemulihan saat layanan ilustrasi bermasalah
Jika API ilustrasi membalas HTTP 5xx atau koneksi berulang kali gagal, v6 menghentikan percobaan berulang dan membuat kartu visual cinematic lokal agar render dapat berlanjut. Kartu ini bukan ilustrasi AI spesifik; `verify.md` dan `script.json` menandai adegan fallback agar kreator bisa menggantinya sebelum upload. Untuk gambar AI sesuai prompt, jalankan ulang ketika layanan ilustrasi pulih atau gunakan penyedia gambar lain.
