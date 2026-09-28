# Rapat koordinasi pengadaan (Kelompok 2, Agen Cerdas Enterprise)

Sistem multi-agen **berbasis aturan** sesuai laporan `Revisi Laporan Procurement_3.docx` (Bab 5-7). Empat staf
(Staf Permintaan, Staf Purchasing, Negosiator, Staf Keuangan) berkoordinasi lewat rapat; pemasok A, B, C berada di
luar sistem. Tidak ada ML, DL, maupun RL: tidak ada pelatihan, model, atau neural network. Setiap keputusan adalah
aturan if-else yang bisa dihitung dengan kalkulator.

## Instalasi

```bash
/opt/homebrew/bin/python3.14 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

## Perintah

| Perintah | Isi |
|---|---|
| `.venv/bin/pytest -q` | Semua test (angka Bab 6, Tabel 7.1, perilaku aturan rapat) |
| `.venv/bin/python scripts/cetak_notulen.py` | Notulen skenario laporan (kondisi c) |
| `.venv/bin/python scripts/cetak_notulen.py --seed 3 --kondisi b` | Notulen skenario acak, kondisi a/b/c |
| `.venv/bin/python scripts/evaluasi_rapat.py` | Evaluasi 500 skenario (Subbab 7.4) ke `runs/evaluasi_rapat.*` |
| `.venv/bin/streamlit run app/streamlit_app.py` | Dashboard pemantauan rapat (notulen, rencana per usulan, grafik kas, tab evaluasi) |

## Struktur

| File | Isi |
|---|---|
| `config/skenario_laporan.yaml` | Data Subbab 6.1 dan asumsi Tabel 6.1 |
| `config/skenario_acak.yaml` | Rentang Tabel 7.2 |
| `config/rapat.yaml` | Parameter aturan rapat (asumsi tim) |
| `src/rapat_pengadaan/biaya.py` | Rumus biaya dan kas (`payment_schedule`, `cash_balances`) |
| `src/rapat_pengadaan/skenario.py` | `load_scenario`, `sample_scenario(seed)`, `composite_scores` (SAW), `cash_diagnosis` |
| `src/rapat_pengadaan/staf.py` | `StafPermintaan`, `StafPurchasing`, `Negosiator`, `StafKeuangan`, `Pemasok` (method `tanggapi(pesan)`) |
| `app/streamlit_app.py` | Dashboard Streamlit; semua angka dari fungsi di `src/`, evaluasi dibaca dari `runs/` |
| `src/rapat_pengadaan/rapat.py` | Loop rapat: `jalankan_rapat` (c), `rapat_aturan_tetap` (b), `putuskan_sendiri` (a), `cetak_notulen` |

## Kondisi evaluasi (Subbab 7.4)

- **(a) Tanpa rapat**: beli semua sekarang, pemasok termurah yang lolos, Negosiator menawar, bayar cepat jika ada
  diskon (selain itu jatuh tempo). Diperiksa sekali.
- **(b) Aturan tetap**: rapat 1 beli semua, mulai rapat 2 beli bertahap; cadangan untuk batch 2; Negosiator menerima
  harga penawaran; selalu bayar cepat. Berhenti kalau setuju, rencana berulang, atau 6 rapat.
- **(c) Aturan reaksi konflik**: Tabel 5.2 dengan aturan hitung dulu, catatan opsi, dan batas 6 rapat.

Asumsi dan interpretasi tim ada di `DECISIONS.md`.
