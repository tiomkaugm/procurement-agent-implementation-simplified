"""Uji penerimaan: skenario laporan harus sama persis dengan Tabel 7.1 laporan _3, plus perilaku aturan rapat."""

from dataclasses import replace

import pytest

from rapat_pengadaan.biaya import REVISI_TERMIN
from rapat_pengadaan.pesan import Pesan
from rapat_pengadaan.rapat import (
    cetak_notulen, jalankan_rapat, putuskan_sendiri, rapat_aturan_tetap,
)
from rapat_pengadaan.skenario import load_scenario, sample_scenario
from rapat_pengadaan.staf import (
    ANGGARAN, KAS_MINUS, MENDESAK, Batch, Negosiator, Pemasok, StafKeuangan, StafPurchasing, kunci_rencana,
    muat_config,
)

S = load_scenario()
CFG = muat_config()
HASIL = jalankan_rapat(S)


def baris(h):
    """(rapat, usulan, total, sisa anggaran, kas terendah, bulan, keputusan) per usulan yang dihitung."""
    return [(e["rapat"], e["usulan"], e["cek"]["total"], e["cek"]["sisa_anggaran"], e["cek"]["kas_terendah"],
             e["cek"]["bulan_kas_terendah"], e["keputusan"]) for e in h.riwayat]


# ---- Tabel 7.1 ---------------------------------------------------------------------------------------------------
def test_tabel_71():
    assert baris(HASIL) == [
        (1, "1.000 B, bayar cepat", 99_710_000, 290_000, -19_710_000, 1, "berlaku"),
        (2, "1.000 B, jatuh tempo", 101_500_000, -1_500_000, -21_500_000, 2, "ditolak"),
        (2, "1.000 B, termin", 101_500_000, -1_500_000, -21_500_000, 3, "ditolak"),
        (2, "700 B + 300 A (cadangan), bayar cepat", 100_397_000, -397_000, -20_397_000, 2, "ditolak"),
        (2, "700 B + 300 B, bayar cepat", 99_710_000, 290_000, -19_710_000, 2, "berlaku"),
        # Rapat 3: batch 2 jatuh tempo / termin, lalu batch 1 jatuh tempo / termin.
        (3, "700 B bayar cepat + 300 B jatuh tempo", 100_247_000, -247_000, -20_247_000, 3, "ditolak"),
        (3, "700 B bayar cepat + 300 B termin", 100_247_000, -247_000, -20_247_000, 4, "ditolak"),
        (3, "700 B jatuh tempo + 300 B bayar cepat", 100_963_000, -963_000, -20_963_000, 2, "ditolak"),
        (3, "700 B termin + 300 B bayar cepat", 100_963_000, -963_000, -20_963_000, 3, "ditolak"),
    ]


def test_eskalasi_rapat_3():
    assert HASIL.eskalasi and not HASIL.setuju and HASIL.jumlah_rapat == 3 and HASIL.alasan_selesai == "buntu"
    lap = HASIL.laporan_eskalasi
    assert lap["kekurangan_kas"] == 19_710_000 and lap["bulan_kekurangan"] == 2
    assert lap["batas_bawah_kekurangan"] == 19_220_000
    assert lap["kelebihan_anggaran"] == 0 and lap["total"] == 99_710_000
    assert [(b.jumlah, b.vendor, b.harga) for b in lap["rencana"]] == [(700, "B", 89_500), (300, "B", 89_500)]
    teks = cetak_notulen(HASIL)
    assert "Rp19.710.000 di bulan 2" in teks and "Rp19.220.000" in teks
    assert "tambahan dana sebesar" not in teks


def test_k1():
    berlaku = [e for e in HASIL.riwayat if e["keputusan"] == "berlaku"][-1]
    assert berlaku["cek"]["saldo"][0] == 10_203_000


# ---- negosiasi ---------------------------------------------------------------------------------------------------
def test_negosiasi_b():
    n = Negosiator(CFG)
    h = n.tanggapi(Pesan("t", "negosiasi", {"pemasok": Pemasok(S.vendor("B"), CFG), "pesaing": None}))
    assert h.jenis == "sepakat" and h.isi["harga"] == 89_500
    assert h.isi["langkah"] == [(89_100, 90_000), (89_550, 89_500)]


def test_negosiasi_a():
    n = Negosiator(CFG)
    h = n.tanggapi(Pesan("t", "negosiasi", {"pemasok": Pemasok(S.vendor("A"), CFG), "pesaing": ("B", 102_000)}))
    assert h.isi["batas"] == 95_000 and h.isi["harga"] == 95_000
    assert [minta for _, minta in h.isi["langkah"]] == [100_000, 97_500, 95_000]


def test_harga_sepakat_tidak_ditawar_ulang():
    n = Negosiator(CFG)
    b = Pemasok(S.vendor("B"), CFG)
    n.tanggapi(Pesan("t", "negosiasi", {"pemasok": b, "pesaing": None}))
    h = n.tanggapi(Pesan("t", "negosiasi", {"pemasok": b, "pesaing": ("A", 1)}))
    assert h.isi["harga"] == 89_500 and h.isi["langkah"] == []


# ---- estimasi Purchasing ------------------------------------------------------------------------------------------
@pytest.mark.parametrize("batch,sepakat,hindari,harapan", [
    (Batch(1, 1000, 700), {}, set(), {"B": 102_000_000}),
    (Batch(1, 700, 700), {"B": 89_500}, set(), {"A": 74_900_000, "B": 71_050_000}),
    (Batch(2, 300, 0), {"B": 89_500}, {"B"}, {"A": 32_100_000}),
    (Batch(2, 300, 0), {"B": 89_500, "A": 95_000}, set(), {"B": 30_450_000}),
])
def test_estimasi(batch, sepakat, hindari, harapan):
    pem = {v.name: Pemasok(v, CFG) for v in S.vendors}
    p = StafPurchasing(S, pem).tanggapi(Pesan("t", "pilih_pemasok", {
        "batch": batch, "dikecualikan": set(), "harga_sepakat": sepakat, "hindari": hindari}))
    for n, x in harapan.items():
        assert p.isi["estimasi"][n] == x
    assert p.isi["vendor"] == min(harapan, key=harapan.get)


# ---- aturan umum --------------------------------------------------------------------------------------------------
def test_hitung_dulu_menolak_pelanggaran_baru():
    berlaku = {"pelanggaran": [KAS_MINUS], "kas_terendah": -100}
    assert not StafKeuangan.hitung_dulu({"pelanggaran": [KAS_MINUS, ANGGARAN], "kas_terendah": 0}, berlaku)
    assert not StafKeuangan.hitung_dulu({"pelanggaran": [KAS_MINUS], "kas_terendah": -101}, berlaku)
    assert StafKeuangan.hitung_dulu({"pelanggaran": [KAS_MINUS], "kas_terendah": -100}, berlaku)
    # Keputusan tim: usulan yang menghilangkan satu jenis pelanggaran tanpa menambah jenis baru diterima.
    berlaku2 = {"pelanggaran": [MENDESAK], "kas_terendah": 50}
    assert StafKeuangan.hitung_dulu({"pelanggaran": [], "kas_terendah": 10}, berlaku2)


def test_usulan_hapus_mendesak_diterima_walau_kas_turun():
    berlaku = {"pelanggaran": [MENDESAK], "kas_terendah": 65_000_000}
    # Tanpa pelanggaran baru, kas turun: diterima.
    assert StafKeuangan.hitung_dulu({"pelanggaran": [], "kas_terendah": 1_000}, berlaku)
    # Unit mendesak lebih berat daripada kas minus: tukar dengan kas minus diterima.
    assert StafKeuangan.hitung_dulu({"pelanggaran": [KAS_MINUS], "kas_terendah": -34_517_400}, berlaku)


def test_usulan_tambah_pelanggaran_lain_tetap_ditolak():
    berlaku = {"pelanggaran": [MENDESAK], "kas_terendah": 65_000_000}
    # Anggaran tetap batas keras, juga saat menukar unit mendesak.
    assert not StafKeuangan.hitung_dulu({"pelanggaran": [ANGGARAN], "kas_terendah": 1}, berlaku)
    assert not StafKeuangan.hitung_dulu({"pelanggaran": [KAS_MINUS, ANGGARAN], "kas_terendah": 1}, berlaku)
    # Tanpa unit mendesak di rencana berlaku, kas minus tetap pelanggaran baru.
    assert not StafKeuangan.hitung_dulu({"pelanggaran": [KAS_MINUS], "kas_terendah": -1},
                                        {"pelanggaran": [], "kas_terendah": 0})
    assert not StafKeuangan.hitung_dulu({"pelanggaran": [KAS_MINUS, ANGGARAN], "kas_terendah": 0},
                                        {"pelanggaran": [KAS_MINUS], "kas_terendah": -100})


def test_seed_27_tukar_mendesak_lalu_setuju():
    h = jalankan_rapat(sample_scenario(27))
    assert h.setuju and h.jumlah_rapat == 5
    assert h.riwayat[1]["keputusan"] == "berlaku" and h.riwayat[1]["cek"]["pelanggaran"] == [KAS_MINUS]


def test_tidak_mengulang_rencana_atau_usulan():
    for h in [HASIL] + [jalankan_rapat(sample_scenario(s)) for s in range(0, 500, 5)]:
        kunci = [kunci_rencana(e["rencana"]) for e in h.riwayat if e["rencana"] is not None]
        assert len(kunci) == len(set(kunci))
    # Rapat 3 skenario laporan tidak mengajukan ulang beli bertahap atau cadangan A.
    rapat3 = [e["usulan"] for e in HASIL.riwayat if e["rapat"] == 3]
    assert not any("A" in u for u in rapat3)


def test_termin_ditolak_jika_relasi_kurang():
    sc = replace(S, vendors=tuple(replace(v, relation=0.4) for v in S.vendors))
    h = jalankan_rapat(sc)
    ditolak = [e for e in h.riwayat if e["keputusan"] == "ditolak pemasok"]
    assert ditolak and all("menolak" in e["usulan"] for e in ditolak)
    assert not any(b.cara_bayar == REVISI_TERMIN
                   for e in h.riwayat if e["rencana"] for b in e["rencana"])
    assert Pemasok(sc.vendor("B"), CFG).tanggapi(Pesan("t", "minta_termin")).jenis == "tolak"
    assert Pemasok(S.vendor("B"), CFG).tanggapi(Pesan("t", "minta_termin")).jenis == "setuju"


def test_negosiasi_gagal_pindah_pemasok():
    # Lantai A dinaikkan di atas batas Negosiator (Rp95.000): cadangan A gagal, batch 2 pindah ke B.
    sc = replace(S, vendors=tuple(replace(v, floor_price=96_000) if v.name == "A" else v for v in S.vendors))
    h = jalankan_rapat(sc)
    teks = cetak_notulen(h)
    assert "negosiasi dengan A gagal" in teks
    assert not any(e["rencana"] and any(b.vendor == "A" for b in e["rencana"]) for e in h.riwayat)
    rencana2 = [e for e in h.riwayat if e["rapat"] == 2 and e["keputusan"] == "berlaku"][0]["rencana"]
    assert [b.vendor for b in rencana2] == ["B", "B"]


def test_acak_selesai_maksimal_6_rapat():
    for s in range(500):
        for f in (jalankan_rapat, rapat_aturan_tetap):
            assert 1 <= f(sample_scenario(s)).jumlah_rapat <= CFG["batas_rapat"]


def test_deterministik():
    for s in (0, 3, 42):
        for f in (jalankan_rapat, rapat_aturan_tetap, putuskan_sendiri):
            a, b = f(sample_scenario(s)), f(sample_scenario(s))
            assert a.notulen == b.notulen and baris(a) == baris(b)


# ---- kondisi pembanding -------------------------------------------------------------------------------------------
def test_tanpa_rapat_laporan():
    h = putuskan_sendiri(S)
    assert h.jumlah_rapat == 0 and not h.setuju and not h.eskalasi
    assert h.cek["total"] == 99_710_000 and h.cek["pelanggaran"] == [KAS_MINUS]


def test_aturan_tetap_laporan():
    h = rapat_aturan_tetap(S)
    assert h.eskalasi and h.alasan_selesai == "rencana berulang" and h.jumlah_rapat == 3
    assert h.riwayat[0]["cek"]["total"] == 100_200_000     # B pada harga penawaran Rp90.000, bayar cepat
    assert [b.vendor for b in h.rencana] == ["B", "A"]


def test_format_notulen():
    teks = cetak_notulen(HASIL)
    assert teks.startswith("[Rapat 1]\nStaf Permintaan : ")
    assert "Rp99.710.000" in teks and "5,41" in teks and "[Rapat 3]" in teks
