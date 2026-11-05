# Agen Misteri v8: 3 Style Editing

Video vertikal 9:16 (target 60-90 detik) yang dirender otomatis di GitHub Actions.
Upload ke YouTube/TikTok tetap manual oleh Anda.

## Agen editing: HANYA 3 style, WAJIB memilih satu
Pilih di workflow (kolom **style**): `auto` = agen memilih sendiri berdasarkan tujuan video, atau paksa salah satu.

| Kode | Dipakai untuk | Ciri |
|---|---|---|
| `MYSTERY_VHS` | membuat takut, ketakutan personal, rekaman bocor, POV orang pertama | CCTV 240p, noise & tracking rusak, HUD REC + timer 03:33 AM, night-vision hijau, shaky cam |
| `MYSTERY_CONSPIRACY` | curiga, menghubungkan titik, hal yang ditutupi | papan gabus, foto arsip, pin, benang merah, stempel CONFIDENTIAL, lampu gantung bergoyang |
| `MYSTERY_WAYANG` | sakral, leluhur, ritual, makhluk penjaga | siluet wayang di kelir, tiga warna (arang, merah membara, emas pudar), asap kemenyan, batik, gerak patah-patah |

Template prompt gambar, negative prompt, palet, tipografi, efek bergerak, dan profil audio tiap style
ada di `src/styles.py` (ubah di sana bila ingin menyetel).

## Setup (sekali saja)
1. Unggah semua isi folder ini ke repo GitHub; folder `.github` dibuat/diedit lewat web GitHub.
2. Settings > Secrets and variables > Actions:
   - `GEMINI_API_KEY` (wajib), `POLLINATIONS_API_KEY` (disarankan: model flux + negative prompt),
   - `PIXABAY_API_KEY` (b-roll inset & cadangan), `PEXELS_API_KEY` (opsional).
3. (Opsional) musik bebas royalti `.mp3` di `assets/music/`. Tanpa musik, video tetap punya suara latar buatan kode.

## Menjalankan
Actions > **Buat Video Misteri** > Run workflow > pilih tema, style, (topik boleh kosong) > Run.
Unduh hasil di **Artifacts**. Log akan menulis `STYLE TERPILIH: ...` beserta alasannya.

## Tema isi konten (`config/themes.yml`)
| Kunci | Nama | Sumber fakta |
|---|---|---|
| `sejarah` | Sejarah Misteri | Wikipedia |
| `cerita` | Cerita Misteri | Fiksi/legenda |
| `berita` | Berita Misteri | Google News |
| `horor_nusantara` | Horor Nusantara | Fiksi/legenda |
| `legenda_urban` | Legenda Urban | Fiksi/legenda |
| `kasus_tak_terpecahkan` | Kasus Tak Terpecahkan | Wikipedia |
| `ufo_uap` | UFO & Fenomena Langit | Wikipedia |
| `kriptid` | Makhluk Misterius (Kriptid) | Wikipedia |
| `tempat_angker` | Tempat Angker & Terlarang | Wikipedia |
| `peradaban_hilang` | Peradaban Hilang & Situs Kuno | Wikipedia |
| `artefak_terkutuk` | Artefak & Benda Terkutuk | Wikipedia |
| `fenomena_alam` | Fenomena Alam Misterius | Wikipedia |

## Suara VO (Gemini TTS)
- Narasi memakai **Gemini TTS** (key `GEMINI_API_KEY` yang sama) dengan suara & gaya berbeda per style:
  VHS = `Enceladus` (berbisik), Konspirasi = `Charon` (tenang, curiga), Wayang = `Algenib` (berat, kuno).
  Ganti nama suara/gaya di `src/styles.py` (bagian `"tts"`). Contoh suara lain: Orus, Fenrir (laki-laki);
  Gacrux, Achernar, Kore, Sulafat (perempuan).
- Bila Gemini TTS tidak tersedia (kuota/tier gratis/model), **seluruh video otomatis memakai Edge-TTS** agar suara
  tidak tercampur. Log menulis `Suara: Gemini TTS ...` atau `Gemini TTS tidak dipakai: <alasan>`.
- Edge-TTS memakai tempo dan nada tetap per style (seperti v8 awal). Dua fitur opsional, **mati secara bawaan**:
  `BEAT_PROSODY=1` (tempo/nada ikut tahap cerita) dan `VOICE_FX=1` (efek suara per style: rekaman jadul, mikrofon dekat, gema).
- Gemini TTS tidak memberi waktu per kata; subtitle disinkronkan dengan perkiraan panjang kata.
- Env opsional: `TTS_ENGINE` (`auto` | `gemini` | `edge`), `GEMINI_TTS_MODEL`, `GEMINI_TTS_VOICE`, `GEMINI_TTS_STYLE`.

## Posting otomatis (mode aman: private / draf)
Setelah video jadi, langkah **Posting aman** mengunggah ke platform yang secret-nya terisi. Anda cek lalu publish sendiri.
| Platform | Hasil | Secret yang dibutuhkan |
|---|---|---|
| YouTube | video **private** + penanda konten AI + #Shorts | `YT_CLIENT_ID`, `YT_CLIENT_SECRET`, `YT_REFRESH_TOKEN` |
| Facebook | **Reel DRAFT** di Page | `FB_PAGE_ID`, `FB_PAGE_TOKEN` |
| TikTok | **draf di kotak masuk** TikTok | `TIKTOK_CLIENT_KEY`, `TIKTOK_CLIENT_SECRET`, `TIKTOK_REFRESH_TOKEN` |
| Telegram | ringkasan + teks caption siap tempel + **file video 1080x1920 siap unggah manual** (opsional) | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` |
- **Tanpa akun developer:** bila Facebook/TikTok belum disambungkan, Telegram tetap mengirim file video dan caption
  sehingga Anda tinggal mengunggah manual (sekitar 1 menit).
- Platform tanpa secret dilewati; satu platform gagal tidak menghentikan yang lain. Pilih `post: tidak` di workflow untuk menonaktifkan.
- Aturan platform: YouTube mengunci unggahan API yang belum diaudit sebagai private; TikTok membatasi aplikasi belum diaudit ke private/draf.
  Karena itu mode aman ini sesuai aturan, dan publish tetap Anda lakukan manual setelah cek `verify.md`.
- Laporan hasil ada di `publish_report.md` (Artifacts).

## Dashboard HP (tanpa membuka GitHub)
Folder `site/` berisi halaman `dashboard.html` (pilih tema/style/topik, tombol Buat Video, status run, batalkan run).
Unggah 5 file di dalamnya ke repo situs publik (`agen-misteri-info`) agar tampil di `https://NAMA.github.io/agen-misteri-info/dashboard.html`.
Token GitHub (fine-grained, hanya repo ini, izin Actions: Read and write) disimpan hanya di HP Anda.
Pesan Telegram punya tombol: YouTube Studio, TikTok, Facebook Reels, dan Buat video lagi (membuka dashboard).

## Catatan jujur
- Gambar berasal dari AI gratis (still), bukan video AI. Gerak dibuat oleh mesin editing (kamera, overlay, glitch).
- Template prompt Anda untuk video-AI dipakai sebagai prompt gambar; teks (REC, timer, stempel) digambar oleh editor agar tidak rusak.
- Wayang tidak memakai footage modern. VHS dan konspirasi boleh memakai inset b-roll kecil di maksimal 3 adegan.
- Baca `verify.md` sebelum upload (klaim, sumber, kredit). Jadwal harian dinonaktifkan secara bawaan.
- Unit test berjalan sebelum render; bila gagal, workflow berhenti dengan pesan error jelas.
