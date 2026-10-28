# Cara pakai Scholarship Intelligence Agent

Panduan langkah demi langkah dalam bahasa Indonesia: menyiapkan, mengisi dan memperbarui katalog beasiswa, memeriksa
kualitasnya, dan memakai mesin ini sebagai pelamar. Semua perintah dijalankan dari folder repo:

```bash
cd ~/Scholarship-Intelligence-Agent
python3 -m scholarship_agent <perintah> [opsi]
```

Setiap perintah mencetak JSON. Kalau gagal, keluarannya `{"error": ..., "type": ...}` dengan kode keluar 1.
`python3 -m scholarship_agent <perintah> --help` menampilkan semua opsi sebuah perintah.

## 1. Yang dibutuhkan

| Perlu | Untuk apa | Wajib? |
|---|---|---|
| Python 3.10 atau lebih baru | semuanya; tidak ada langkah instalasi, hanya pustaka bawaan | ya |
| Docker Desktop | SearXNG lokal untuk pencarian web gratis (bagian 3.3) | tidak |
| Playwright + Chromium (`SCHOLAR_BROWSER=playwright`) | membaca halaman yang isinya baru muncul lewat JavaScript | tidak |
| `pypdf` | membaca PDF lebih baik | tidak |
| Kunci API Anthropic | pemeriksa kedua dan terjemahan dengan Claude (berbayar, mati sampai dinyalakan) | tidak |

## 2. Di mana datanya

| Lokasi | Isi | Catatan |
|---|---|---|
| `data/catalog.db` | katalog beasiswa publik: catatan, tenggat, bukti kutipan, cache halaman | tidak di-commit |
| `data/private/private.db` | profil, lamaran, dokumen, akun; terenkripsi AES-256-GCM | tidak di-commit |
| `data/private/keys.json` | kunci enkripsi (dibuat otomatis, mode 0600) | **cadangkan**; kalau hilang, data pribadi tidak bisa dibuka |
| `scholarship_agent/sources.json` | daftar sumber resmi yang dibaca crawler | di-commit |
| `.env.local` | pengaturan rahasia (kunci API, Supabase) | tidak di-commit; jangan dibagikan |

Folder data lain bisa dipakai dengan `SCHOLAR_DATA_DIR=/jalan/ke/folder`.

## 3. Mengambil data (mengisi katalog)

Ada empat cara, dari yang paling dapat dipercaya. Semuanya mematuhi `robots.txt` dan membatasi kecepatan per situs.

### 3.1 Dari daftar sumber resmi

```bash
python3 -m scholarship_agent discover --no-search                       # semua sumber di sources.json
python3 -m scholarship_agent discover --no-search --countries DE,NL      # hanya sumber negara tertentu
python3 -m scholarship_agent discover --no-search --sources de-daad,uk-chevening   # id dari sources.json
python3 -m scholarship_agent discover --resume <JOB>                    # lanjutkan yang terputus
```

Halaman yang tidak berubah dilewati, jadi menjalankannya lagi tetap cepat.

### 3.2 Dari dataset terstruktur (adapter)

```bash
python3 -m scholarship_agent adapter daad --details           # DAAD (Jerman)
python3 -m scholarship_agent adapter campusfrance --details   # Campus France
python3 -m scholarship_agent adapter grants_at --details      # OeAD (Austria)
python3 -m scholarship_agent adapter nsp_india --details      # National Scholarship Portal (India)
python3 -m scholarship_agent adapter erasmus_mundus           # program Erasmus Mundus
python3 -m scholarship_agent adapter euraxess                 # lowongan riset EURAXESS
```

`--details` membaca halaman detail tiap program (lebih lengkap, lebih lama). Menjalankan ulang sebuah adapter mengganti
catatan miliknya sendiri, jadi aman diulang. `--limit 20` untuk mencoba sedikit dulu.

### 3.3 Pencarian web per negara (SearXNG, gratis)

```bash
open -a Docker                                   # nyalakan Docker Desktop dulu (macOS)
deploy/searxng/start.sh                          # SearXNG di http://127.0.0.1:8080
export SEARCH_PROVIDER=searxng SEARXNG_URL=http://127.0.0.1:8080
python3 -m scholarship_agent search-check        # satu pencarian percobaan
python3 -m scholarship_agent search-health       # mesin pencari mana yang siap atau sedang istirahat
python3 -m scholarship_agent strategy-plan --countries ID,VN                     # lihat rencana kuerinya
python3 -m scholarship_agent strategy-run --countries ID,VN --queries-per-country 4 --fetch-per-query 4
python3 -m scholarship_agent strategy-run --resume <JOB>                         # lanjutkan dari titik simpan
deploy/searxng/stop.sh                           # matikan SearXNG
```

Tanpa `--countries`, strategi berjalan untuk semua negara (lama: berjam-jam). Mesin pencari kadang membatasi; strategi
berhenti sendiri dan bisa dilanjutkan dengan `--resume`.

### 3.4 Menambah sumber baru

```bash
python3 -m scholarship_agent provider-candidates          # domain yang menghasilkan beasiswa tapi belum terdaftar
python3 -m scholarship_agent provider-review contoh.ac.id --accept --note "situs resmi kampus"
python3 -m scholarship_agent sources --check              # cek semua sumber masih bisa dibuka
```

### 3.5 Memperbarui data yang sudah ada

```bash
python3 -m scholarship_agent refresh --plan               # lihat dulu apa yang akan dibaca ulang
python3 -m scholarship_agent refresh --limit 300          # baca ulang catatan yang paling perlu diperbarui
```

Tenggat yang sudah lewat, siklus tahunan, dan syarat yang berubah diperbarui dari halaman resminya.

```bash
python3 -m scholarship_agent describe                     # isi deskripsi program dari halaman yang sudah tersimpan
```

Deskripsi ("ini program apa") diambil dari kata-kata halaman resmi sendiri; pembacaan halaman berikutnya mengisi sisanya.

### 3.6 Pemeriksa kedua dengan Claude (berbayar, pilihan)

Pemeriksa kedua membaca ulang halaman resmi dan menandai nilai yang meragukan. Tanpa izin eksplisit setiap permintaan
hanya diperkirakan biayanya, tidak dikirim. Untuk menyalakannya dengan batas biaya:

```bash
env -u ANTHROPIC_AUTH_TOKEN -u ANTHROPIC_BASE_URL bash -c 'set -a; . ./.env.local; set +a;
  export AI_PROVIDER=anthropic ANTHROPIC_ALLOW_PAID=1 ANTHROPIC_MODEL=claude-haiku-5-5 \
    ANTHROPIC_MAX_ESTIMATED_COST_USD=0.20 ANTHROPIC_MAX_REQUESTS_PER_RUN=600 ANTHROPIC_MAX_TOKENS=1500;
  python3 -m scholarship_agent check --limit 100'
python3 -m scholarship_agent ai-usage                     # biaya yang sudah terpakai
```

Biaya kira-kira USD 0,0005 per halaman dengan Haiku; proses berhenti sendiri saat batas tercapai. `--refresh` membaca
ulang catatan yang sudah pernah diperiksa. Terjemahan judul dan isi ke bahasa Inggris: `translate --limit N` dengan
pengaturan yang sama (juga berbayar).

### 3.7 Proses yang lama

Pengambilan data bisa berjam-jam. Jalankan di latar belakang agar tidak berhenti saat terminal ditutup:

```bash
nohup python3 -m scholarship_agent discover --no-search > crawl.json 2> crawl.err &
tail -f crawl.err                                         # pantau
```

Jangan menjalankan dua crawl yang menulis ke katalog yang sama sekaligus; yang kedua menunggu giliran (WAL), jadi
lambat.

## 4. Melihat isi katalog

```bash
python3 -m scholarship_agent stats                        # jumlah catatan, yang dibuka, per negara
python3 -m scholarship_agent coverage                     # negara yang sudah dan belum dicari
python3 -m scholarship_agent coverage-quality             # celah per negara, bahasa, kategori
python3 -m scholarship_agent search --text erasmus --level master          # juga --country DE, --status open
python3 -m scholarship_agent show <id>                    # satu catatan lengkap dengan bukti kutipannya
python3 -m scholarship_agent catalog-audit                # pemeriksaan mutu seluruh katalog
python3 -m scholarship_agent run-report                   # ditemukan / diambil / terverifikasi per crawl
```

`<id>` bisa berupa id (`sch_f73ade952e4a`), awal id, atau potongan judul yang unik.

## 5. Memakai sebagai pelamar (lewat perintah)

### 5.1 Profil

Simpan profil dalam berkas JSON, misalnya `profil.json`:

```json
{
  "name": "Rina Putri",
  "phone": "+6281234567890",
  "citizenships": ["ID"],
  "residence_country": "ID",
  "education": [{"degree": "bachelor", "field": "Computer Science", "institution": "Universitas Indonesia",
                 "country": "ID", "end": "2024-07", "gpa": 3.6, "gpa_scale": 4}],
  "tests": [{"test": "IELTS", "score": 7.0, "date": "2025-03"}],
  "experience": [{"kind": "leadership", "title": "Volunteer coordinator", "organization": "PMI Depok",
                  "start": "2023-01", "end": "2023-12", "description": "Led 12 volunteers for 300 flood victims."}],
  "achievements": ["2023 · First prize, national essay competition"],
  "target_levels": ["master"],
  "disciplines": ["Computer Science"],
  "preferred_countries": ["DE", "NL"],
  "funding_need": "full"
}
```

```bash
python3 -m scholarship_agent setup --file profil.json
python3 -m scholarship_agent setup --set preferred_countries='["DE","NL","SE"]'   # ubah satu bagian
python3 -m scholarship_agent profile                                              # lihat yang tersimpan
```

### 5.2 Mencari dan mencocokkan

```bash
python3 -m scholarship_agent rank --top 20                # beasiswa paling cocok untuk profil
python3 -m scholarship_agent match <id>                   # alasan lolos / tidak lolos per syarat
python3 -m scholarship_agent funding <id>                 # apa yang ditanggung, perkiraan biaya
python3 -m scholarship_agent verify <id>                  # cocokkan lagi dengan halaman resminya sekarang
```

### 5.3 Rencana, dokumen, dan unduhan

```bash
python3 -m scholarship_agent plan <id>                    # checklist dokumen dan jadwal
python3 -m scholarship_agent prepare <id>                 # CV, ringkasan, dan dokumen yang diminta
python3 -m scholarship_agent prepare <id> --kinds motivation_letter,research_proposal
python3 -m scholarship_agent export <id> motivation_letter --format pdf --out ./dokumen
python3 -m scholarship_agent review <id>                  # pemeriksaan sebelum mengirim
```

Surat dan esai berupa kerangka berisi tips menulis dan bagian `[YOU WRITE: ...]` yang Anda isi sendiri. Pemeriksa
menandai klaim yang tidak ada di profil, frasa klise, dan frasa yang terdengar seperti tulisan mesin. Format unduhan:
`pdf`, `docx`, atau `md`.

### 5.4 Melacak lamaran dan tenggat

```bash
python3 -m scholarship_agent track <id> --status shortlisted
python3 -m scholarship_agent track <id> --item "Passport" --item-status done
python3 -m scholarship_agent track                        # semua lamaran
python3 -m scholarship_agent deadlines --days 60 --tracked
python3 -m scholarship_agent reminders --ics tenggat.ics  # buka di Kalender; tidak ada yang dikirim
python3 -m scholarship_agent outcome <id> accepted --lessons "wawancara fokus ke rencana riset"
python3 -m scholarship_agent report
```

### 5.5 Data pribadi Anda

```bash
python3 -m scholarship_agent export-data > data-saya.json  # salinan semua data pribadi
python3 -m scholarship_agent delete-data --yes             # hapus profil dan semua data pribadi
python3 -m scholarship_agent security-status               # enkripsi aktif? berapa akun?
```

## 6. Memeriksa mutu dan menguji

```bash
python3 -m unittest discover -s tests -t .                # semua tes (sekitar 700, kurang dari 20 detik)
python3 tests/devpool.py --compare <hasil-sebelumnya.json> # ukur akurasi pembacaan pada halaman berlabel
python3 -m scholarship_agent quality                      # ringkasan mutu pembacaan
python3 -m scholarship_agent heldout --set a              # uji pada set yang tidak pernah dipakai melatih aturan
```

Aturan pembacaan baru hanya dipertahankan kalau total nilai benchmark naik dan tidak ada set yang turun.

## 7. Masalah yang sering muncul

| Gejala | Penyebab dan solusi |
|---|---|
| `search-check` gagal | Docker atau SearXNG belum jalan: `open -a Docker`, tunggu sebentar, lalu `deploy/searxng/start.sh` |
| strategi berhenti dengan "cooling down" | mesin pencari sedang membatasi; tunggu, lalu `strategy-run --resume <JOB>` |
| sangat lambat atau "database is locked" | dua proses menulis bersamaan; tunggu satu selesai |
| pemeriksa kedua tidak memanggil Claude | `ANTHROPIC_ALLOW_PAID=1` atau batas biaya belum diisi (sengaja: tanpa itu hanya perkiraan) |
| data pribadi tidak bisa dibuka | `data/private/keys.json` hilang atau berbeda; pulihkan dari cadangan |

Referensi teknis lengkap (bahasa Inggris): [docs/scholarship-agent/README.md](scholarship-agent/README.md), pencarian:
[SEARCH.md](scholarship-agent/SEARCH.md), API: [API.md](scholarship-agent/API.md).
