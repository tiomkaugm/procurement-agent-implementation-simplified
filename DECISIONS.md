# Keputusan dan asumsi

Laporan `Revisi Laporan Procurement_3.docx` adalah spesifikasi. Semua yang tidak tertulis di laporan dicatat di sini.

## Asal kode

- Proyek ini ditulis baru, tanpa riwayat dan tanpa import dari repo MARL lama.
- Rumus biaya/kas dan generator skenario acak ditulis ulang supaya hasilnya identik dengan versi lama:
  seed 0-499 menghasilkan skenario, skor SAW, dan `cash_diagnosis` yang sama persis (dicek sekali terhadap repo lama
  pada 25 Sep 2026). Rentangnya sama dengan Tabel 7.2 laporan.

## Asumsi tim (Tabel 6.1, `config/`)

| Asumsi | Nilai | File |
|---|---|---|
| Harga lantai | A 95.000, B 89.000, C 108.000 | `skenario_laporan.yaml` |
| Reputasi | A 7,00, B 8,45, C 2,55 | `skenario_laporan.yaml` |
| Ambang skor SAW | 6,00 | `skenario_laporan.yaml` |
| Relasi pemasok skenario laporan | 0,6 | `skenario_laporan.yaml` |
| Horizon kas | 4 bulan, tanpa kas masuk | `skenario_laporan.yaml` |
| Batas rapat | 6 | `rapat.yaml` |
| Konsesi | tawaran awal 0,99 × P, naik 0,005 × P, pemasok turun 0,5 × (P − lantai) per langkah | `rapat.yaml` |
| Termin | 50% bulan +1, 50% bulan +2, tanpa diskon; pemasok setuju jika relasi ≥ 0,5 | `rapat.yaml`, `biaya.py` |
| Jatuh tempo | barang dibayar bulan +1, tanpa diskon | `biaya.py` |
| Transport dan risiko | selalu dibayar di bulan batch | `biaya.py` |

## Interpretasi aturan

1. **Hitung dulu sebelum dipakai (keputusan tim, 25 Sep 2026).** Usulan ditolak jika menambah jenis pelanggaran.
   Usulan yang **menghilangkan** satu jenis pelanggaran tanpa menambah jenis baru langsung diterima. Selain itu,
   usulan diterima jika kas terendahnya ≥ kas terendah rencana berlaku. Alasan: rencana yang batch mendesaknya tanpa
   pemasok tidak membayar apa pun, jadi kasnya selalu "lebih baik" dan usulan beli bertahap yang memperbaiki unit
   mendesak selalu ditolak. Pada 500 skenario, versi literal memberi setuju 288 dan unit mendesak terpenuhi 319
   (sama dengan tanpa rapat); versi ini memberi 385 dan 416. Tabel 7.1 sama persis di kedua versi.
   **Perlu satu kalimat tambahan di Subbab 5.4 laporan.**
1b. **Unit mendesak lebih berat daripada kas minus (keputusan tim, 28 Sep 2026).** Usulan yang memenuhi unit
   mendesak dan satu-satunya pelanggaran barunya kas minus tetap diterima. Anggaran terlampaui tetap batas keras:
   usulan yang menambah anggaran terlampaui ditolak. Alasan: pada 30 skenario, usulan beli bertahap yang memenuhi
   unit mendesak ditolak karena menimbulkan kas minus, padahal kas minus masih bisa dicoba ditutup di rapat
   berikutnya (menggeser pembayaran ke bulan dengan kas masuk) atau dibawa ke atasan, sedangkan unit mendesak yang
   terlambat menghentikan produksi. Simulasi sebelum perubahan: setuju 77,0% -> 81,2%, unit mendesak terpenuhi
   83,2% -> 88,0%, pelanggaran kas 0,6% -> 1,2%, eskalasi 23,0% -> 18,8%; 21 skenario jadi setuju, tidak ada yang
   jadi tidak setuju. Varian yang juga membolehkan anggaran terlampaui memberi setuju yang sama (81,2%) tetapi
   pelanggaran anggaran naik ke 6,8%, jadi tidak dipakai. Tabel 7.1 tetap sama persis.
   **Perlu kalimat tambahan di Subbab 5.4 laporan (urutan berat pelanggaran).**
2. **Pembulatan** tawaran dan konsesi: setengah ke atas (bukan pembulatan bankir Python).
3. **Satu pemasok per batch.** Tidak ada pembagian satu batch ke dua pemasok.
4. **Harga setara pesaing** memakai harga penawaran pesaing (bukan harga yang sudah disepakati dengannya), seperti
   hitungan batas A = 102.000 − 7.000 = 95.000 di Subbab 6.5.
5. **Negosiasi gagal** jika tawaran sudah di batas dan pemasok menyatakan sudah di harga lantai. Dalam praktik ini
   hanya terjadi pada pemasok cadangan, karena pemasok termurah selalu punya batas = harga penawarannya.
6. **Reaksi kas minus**: Keuangan mengganti cara bayar satu batch per usulan (batch terakhir ke pertama, jatuh tempo
   lalu termin, dibanding rencana berlaku). Kembali ke bayar cepat tidak diusulkan. Setelah itu beli bertahap.
7. **Reaksi anggaran**: menawar ulang hanya pemasok yang belum pernah sepakat. Pada kondisi (c) semua pemasok di
   rencana sudah sepakat, jadi reaksi ini praktis tidak pernah dipakai. Pemasok alternatif hanya diminta jika
   estimasi per unitnya (harga sepakat atau penawaran + transport + risiko) lebih murah dari biaya per unit batch
   sekarang.
8. **Reaksi unit mendesak**: Staf Permintaan mengusulkan beli bertahap (jika belum dicoba), lalu Purchasing mencari
   pemasok lain untuk batch mendesak.
9. **`tunda_semua`** ada sebagai aksi (Tabel 5.1) tetapi tidak diusulkan oleh aturan Tabel 5.2, karena selalu melanggar
   tenggat unit mendesak.
10. **Batch tanpa pemasok.** Batch mendesak tanpa pemasok = pelanggaran unit mendesak. Batch tidak mendesak tanpa
    pemasok dicatat sebagai pelanggaran `batch_tanpa_pemasok` (tidak disebut di laporan) supaya rencana yang tidak
    membeli semua barang tidak dianggap setuju. Tidak ada reaksi khusus untuk pelanggaran ini.
11. **Catatan opsi** menyimpan setiap usulan (termasuk yang ditolak pemasok) dan setiap rencana yang pernah dihitung.
    Rencana yang sama persis tidak dihitung ulang.
12. **Kondisi (b)**: Negosiator menerima harga penawaran (harga daftar, mis. B Rp90.000). Rapat yang menghasilkan
    rencana sama persis dengan rapat sebelumnya ikut dihitung dalam jumlah rapat (skenario laporan: 3 rapat).
13. **Biaya rata-rata** dihitung hanya dari rencana akhir yang semua batch-nya punya pemasok (n disebut di
    `runs/evaluasi_rapat.md`).

## Catatan hasil

- Sebelum keputusan 1b, (b) memenuhi unit mendesak lebih sering daripada (c) (89,2% lawan 83,2%). Penyebabnya
  syarat "tidak ada jenis pelanggaran baru": beli bertahap memperbaiki unit mendesak tetapi menimbulkan kas minus
  (24 skenario), anggaran terlampaui (5), atau keduanya (2). Di 30 skenario itu (b) juga berakhir eskalasi.
  Keputusan 1b menutup bagian kas minus; sisa selisihnya berasal dari usulan yang melampaui anggaran.
