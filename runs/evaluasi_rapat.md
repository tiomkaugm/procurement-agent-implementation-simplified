# Hasil evaluasi pada 500 skenario acak (seed 0-499)

| Metrik | Tanpa rapat | Aturan tetap | Aturan reaksi |
|---|---|---|---|
| Semua bagian setuju (%) | 50,4 | 72,8 | 81,2 |
| Pelanggaran anggaran (%) | 5,6 | 9,0 | 5,6 |
| Pelanggaran kas (%) | 8,6 | 7,8 | 1,2 |
| Unit mendesak terpenuhi (%) | 63,8 | 89,2 | 88,0 |
| Biaya rata-rata (juta Rp) | 88,94 | 100,90 | 99,05 |
| Rata-rata jumlah rapat | 0,00 | 1,78 | 1,70 |
| Eskalasi (%) | 0,0 | 27,2 | 18,8 |

Catatan:
- Biaya rata-rata dihitung dari rencana akhir yang semua batch-nya punya pemasok: Tanpa rapat n = 319, Aturan tetap n = 446, Aturan reaksi n = 440. Karena n berbeda, biaya rata-rata antar kondisi tidak dihitung pada skenario yang sama.
- Skenario yang terbukti tidak mungkin menurut `cash_diagnosis` (kas sepanjang horizon kurang dari tagihan termurah yang mungkin): 0 dari 500. Eskalasi pada skenario itu: Tanpa rapat 0, Aturan tetap 0, Aturan reaksi 0.
- Skenario tanpa pemasok yang lolos skor, cukup cepat, dan sanggup memasok semua unit mendesak sekaligus: 54 dari 500 (beli bertahap tidak mengubah jumlah unit mendesak, jadi unit mendesak skenario ini tidak bisa dipenuhi oleh aturan mana pun).
- Dibuat dengan `python scripts/evaluasi_rapat.py`; lihat `evaluasi_rapat.meta.json`.
