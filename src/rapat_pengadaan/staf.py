"""Empat staf pengadaan dan pemasok (Bab 5 dan Bab 6 laporan _3).

Setiap staf punya method `tanggapi(pesan)` yang mengembalikan `Pesan` berisi hasil kerja dan kalimat notulen.
Semua keputusan berupa aturan if-else yang bisa dihitung dengan kalkulator. Tidak ada model atau pelatihan.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from fractions import Fraction
from pathlib import Path

import yaml

from .biaya import BAYAR_CEPAT, BAYAR_JATUH_TEMPO, REVISI_TERMIN, cash_balances, payment_schedule
from .format import angka, daftar, desimal, rp
from .pesan import Pesan
from .skenario import CONFIG_DIR, Scenario, Vendor, cash_diagnosis, composite_scores

# Aksi Staf Permintaan.
BELI_SEMUA_SEKARANG = "beli_semua_sekarang"
BELI_BERTAHAP = "beli_bertahap"
TUNDA_SEMUA = "tunda_semua"   # ada di Tabel 5.1, tetapi tidak diusulkan oleh aturan Tabel 5.2 (lihat DECISIONS.md)

NAMA_CARA_BAYAR = {BAYAR_CEPAT: "bayar cepat", BAYAR_JATUH_TEMPO: "jatuh tempo", REVISI_TERMIN: "termin"}

# Jenis pelanggaran, dalam urutan reaksi rapat (Subbab 5.4).
KAS_MINUS = "kas_minus"
ANGGARAN = "anggaran_terlampaui"
MENDESAK = "unit_mendesak"
TANPA_PEMASOK = "batch_tanpa_pemasok"
NAMA_PELANGGARAN = {
    KAS_MINUS: "kas minus",
    ANGGARAN: "anggaran terlampaui",
    MENDESAK: "unit mendesak tidak terpenuhi",
    TANPA_PEMASOK: "batch tanpa pemasok",
}

PERMINTAAN, PURCHASING, NEGOSIATOR, KEUANGAN = "Staf Permintaan", "Staf Purchasing", "Negosiator", "Staf Keuangan"


def muat_config(path: str | Path = CONFIG_DIR / "rapat.yaml") -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def bulat(x: Fraction) -> int:
    """Pembulatan setengah ke atas (tidak memakai pembulatan bankir bawaan Python)."""
    return int((x + Fraction(1, 2)) // 1)


def pecahan(x: float) -> Fraction:
    return Fraction(str(x))


@dataclass
class Batch:
    bulan: int
    jumlah: int
    mendesak: int                   # jumlah unit mendesak di batch ini
    vendor: str | None = None
    harga: int | None = None        # harga per unit yang disepakati
    cara_bayar: str = BAYAR_CEPAT
    cadangan: bool = False

    def kunci(self) -> tuple:
        return (self.bulan, self.jumlah, self.vendor, self.harga, self.cara_bayar)


def kunci_rencana(rencana: list[Batch]) -> tuple:
    return tuple(b.kunci() for b in rencana)


def salin(rencana: list[Batch]) -> list[Batch]:
    return [replace(b) for b in rencana]


def label_rencana(rencana: list[Batch]) -> str:
    """Contoh: '1.000 B, bayar cepat' atau '700 B + 300 A (cadangan), bayar cepat'."""
    bagian = [f"{angka(b.jumlah)} {b.vendor or 'tanpa pemasok'}{' (cadangan)' if b.cadangan else ''}"
              for b in rencana]
    cara = {b.cara_bayar for b in rencana}
    if len(cara) == 1:
        return " + ".join(bagian) + f", {NAMA_CARA_BAYAR[cara.pop()]}"
    return " + ".join(f"{s} {NAMA_CARA_BAYAR[b.cara_bayar]}" for s, b in zip(bagian, rencana))


# --------------------------------------------------------------------------------------------------------------
class Pemasok:
    """Pemasok di luar sistem: menjawab pengumuman kebutuhan, tawaran harga, dan permintaan termin."""

    def __init__(self, vendor: Vendor, cfg: dict):
        self.v = vendor
        self.nama = vendor.name
        self.konsesi = bulat(pecahan(cfg["negosiasi"]["konsesi_pemasok"]) * (vendor.list_price - vendor.floor_price))
        self.relasi_minimum = cfg["termin"]["relasi_minimum"]

    def harga_minta(self, langkah: int) -> int:
        """Langkah k: max(harga lantai, harga penawaran - k x konsesi)."""
        return max(self.v.floor_price, self.v.list_price - langkah * self.konsesi)

    def tanggapi(self, pesan: Pesan) -> Pesan:
        if pesan.jenis == "pengumuman":
            v = self.v
            return Pesan(self.nama, "penawaran", {
                "harga": v.list_price, "transport": v.transport, "risiko": v.risk, "kapasitas": v.capacity,
                "waktu_kirim": v.lead_time, "diskon_persen": v.discount_pct,
            })
        if pesan.jenis == "tawaran":
            minta = self.harga_minta(pesan.isi["langkah"])
            if minta <= pesan.isi["harga"]:
                return Pesan(self.nama, "sepakat", {"harga": minta})
            # "bertahan": harga lantai sudah tercapai, pemasok tidak bisa turun lagi.
            return Pesan(self.nama, "minta", {"harga": minta, "bertahan": minta == self.v.floor_price})
        if pesan.jenis == "minta_termin":
            setuju = self.v.relation >= self.relasi_minimum
            return Pesan(self.nama, "setuju" if setuju else "tolak", {"relasi": self.v.relation})
        raise ValueError(f"pemasok tidak mengerti pesan {pesan.jenis}")


# --------------------------------------------------------------------------------------------------------------
class StafPermintaan:
    """Agen 01. Menyampaikan kebutuhan dan mengusulkan cara beli."""

    nama = PERMINTAAN

    def __init__(self, sc: Scenario):
        self.sc = sc

    def batch(self, aksi: str) -> list[Batch]:
        q, u = self.sc.quantity, self.sc.urgent_quantity
        if aksi == BELI_SEMUA_SEKARANG:
            return [Batch(1, q, u)]
        if aksi == BELI_BERTAHAP:
            return [Batch(1, u, u), Batch(2, q - u, 0)]
        if aksi == TUNDA_SEMUA:
            return [Batch(2, q, u)]
        raise ValueError(aksi)

    def bisa_bertahap(self) -> bool:
        return 0 < self.sc.urgent_quantity < self.sc.quantity

    def tanggapi(self, pesan: Pesan) -> Pesan:
        sc = self.sc
        q, u = sc.quantity, sc.urgent_quantity
        if pesan.jenis == "buka_rapat":
            teks = (f"Butuh {angka(q)} unit bahan X. {angka(u)} unit harus datang dalam {sc.deadline_days} hari, "
                    f"{angka(q - u)} unit bisa menunggu bulan depan. Usul: beli semua sekarang.")
            return Pesan(self.nama, "usulan", {"aksi": BELI_SEMUA_SEKARANG}, teks)
        if pesan.jenis == "usul_bertahap":
            teks = (f"Kalau begitu, {angka(q - u)} unit yang tidak mendesak kita beli bulan depan. "
                    "Usul: beli bertahap.")
            return Pesan(self.nama, "usulan", {"aksi": BELI_BERTAHAP}, teks)
        if pesan.jenis == "tidak_ada_usulan":
            if self.bisa_bertahap():
                teks = f"{angka(u)} unit tetap harus datang tepat waktu. Tidak ada yang bisa dikurangi."
            else:
                teks = f"Semua {angka(q)} unit mendesak. Pembagian batch tidak bisa diubah."
            return Pesan(self.nama, "tidak_ada_usulan", {}, teks)
        raise ValueError(f"{self.nama} tidak mengerti pesan {pesan.jenis}")


# --------------------------------------------------------------------------------------------------------------
class StafPurchasing:
    """Agen 02. Contract Net Protocol: umumkan kebutuhan, terima penawaran, saring dengan SAW, pilih termurah."""

    nama = PURCHASING

    def __init__(self, sc: Scenario, pemasok: dict[str, Pemasok]):
        self.sc = sc
        self.pemasok = pemasok
        self.skor = composite_scores(sc)

    def umumkan(self, batch: Batch) -> dict[str, dict]:
        pesan = Pesan(self.nama, "pengumuman", {"jumlah": batch.jumlah, "tenggat": self.sc.deadline_days})
        return {n: p.tanggapi(pesan).isi for n, p in self.pemasok.items()}

    def saring(self, batch: Batch, penawaran: dict[str, dict], dikecualikan: set[str]) -> tuple[list[str], dict]:
        """Kembalikan (pemasok lolos, {pemasok: alasan gugur})."""
        sc = self.sc
        lolos, gugur = [], {}
        for n, p in penawaran.items():
            if self.skor[n] < sc.min_composite_score:
                gugur[n] = f"{n} tidak lolos (skor {desimal(self.skor[n])} < {desimal(sc.min_composite_score)})"
            elif p["kapasitas"] < batch.jumlah:
                gugur[n] = f"{n} tidak sanggup (kapasitas {angka(p['kapasitas'])} < {angka(batch.jumlah)} unit)"
            elif batch.bulan == 1 and batch.mendesak > 0 and p["waktu_kirim"] > sc.deadline_days:
                gugur[n] = f"{n} terlambat (waktu kirim {p['waktu_kirim']} > tenggat {sc.deadline_days} hari)"
            elif n in dikecualikan:
                gugur[n] = f"{n} dikecualikan (negosiasi gagal)"
            else:
                lolos.append(n)
        return lolos, gugur

    @staticmethod
    def per_unit(p: dict, harga: int) -> int:
        return harga + p["transport"] + p["risiko"]

    def tanggapi(self, pesan: Pesan) -> Pesan:
        if pesan.jenis != "pilih_pemasok":
            raise ValueError(f"{self.nama} tidak mengerti pesan {pesan.jenis}")
        batch: Batch = pesan.isi["batch"]
        sepakat: dict[str, int] = pesan.isi["harga_sepakat"]
        hindari: set[str] = pesan.isi.get("hindari", set())
        kandidat_khusus: list[str] | None = pesan.isi.get("hanya")    # pemasok alternatif tertentu
        penawaran = self.umumkan(batch)
        lolos, gugur = self.saring(batch, penawaran, pesan.isi["dikecualikan"])
        estimasi = {n: batch.jumlah * self.per_unit(penawaran[n], sepakat.get(n, penawaran[n]["harga"]))
                    for n in lolos}
        kandidat = [n for n in lolos if n not in hindari]
        if kandidat_khusus is not None:
            kandidat = [n for n in kandidat if n in kandidat_khusus]
        pilih = min(kandidat, key=lambda n: (estimasi[n], n)) if kandidat else None

        pesaing = None
        if pilih is not None:
            lain = [n for n in lolos if n != pilih]
            if lain:
                n = min(lain, key=lambda n: (self.per_unit(penawaran[n], penawaran[n]["harga"]), n))
                pesaing = (n, self.per_unit(penawaran[n], penawaran[n]["harga"]))

        kalimat = []
        if pesan.isi.get("umumkan"):
            kalimat.append(f"Minta penawaran ke {daftar(list(penawaran))}.")
        kalimat += [gugur[n] + "." for n in sorted(gugur)]
        if pilih is None:
            if hindari and not kandidat:
                kalimat.append("Tidak ada pemasok lain yang bisa jadi cadangan.")
            else:
                kalimat.append("Tidak ada pemasok yang bisa dipilih.")
        else:
            rincian = lambda n: (f"{angka(batch.jumlah)} × {angka(estimasi[n] // batch.jumlah)} "
                                 f"= {rp(estimasi[n])}")
            if len(lolos) > 1 and not hindari and kandidat_khusus is None:
                kalimat.append("Estimasi " + ", ".join(f"{n} {rincian(n)}" for n in sorted(lolos)) + ".")
                kalimat.append(f"Pilih {pilih}.")
            elif hindari:
                kalimat.append(f"Saya usulkan {pilih} sebagai cadangan, estimasi {rincian(pilih)}.")
            elif kandidat_khusus is not None:
                kalimat.append(f"Minta {pilih} sebagai pemasok alternatif, estimasi {rincian(pilih)}.")
            else:
                kalimat.append(f"Pilih {pilih}, estimasi {rincian(pilih)}.")
        return Pesan(self.nama, "pilihan", {
            "vendor": pilih, "estimasi": estimasi, "lolos": lolos, "gugur": gugur, "pesaing": pesaing,
            "penawaran": penawaran,
        }, " ".join(kalimat))


# --------------------------------------------------------------------------------------------------------------
class Negosiator:
    """Agen 03. Konsesi bertahap (Subbab 6.4). Tidak mengetahui harga lantai pemasok."""

    nama = NEGOSIATOR

    def __init__(self, cfg: dict):
        n = cfg["negosiasi"]
        self.f_awal = pecahan(n["tawaran_awal"])
        self.f_naik = pecahan(n["kenaikan"])
        self.harga_sepakat: dict[str, int] = {}     # tidak ditawar ulang

    def tanggapi(self, pesan: Pesan) -> Pesan:
        if pesan.jenis != "negosiasi":
            raise ValueError(f"{self.nama} tidak mengerti pesan {pesan.jenis}")
        pemasok: Pemasok = pesan.isi["pemasok"]
        nama = pemasok.nama
        if nama in self.harga_sepakat:
            h = self.harga_sepakat[nama]
            return Pesan(self.nama, "sepakat", {"harga": h, "langkah": []},
                         f"Harga {nama} tetap {rp(h)} karena sudah disepakati.")
        penawaran = pemasok.tanggapi(Pesan(self.nama, "pengumuman", {})).isi
        p = penawaran["harga"]

        if pesan.isi.get("mode") == "terima_penawaran":     # kondisi (b): selalu menerima harga penawaran
            self.harga_sepakat[nama] = p
            return Pesan(self.nama, "sepakat", {"harga": p, "langkah": []},
                         f"Terima harga penawaran {nama} {rp(p)} tanpa menawar.")

        batas, catatan_batas = p, ""
        pesaing = pesan.isi.get("pesaing")
        if pesaing is not None:
            setara = pesaing[1] - penawaran["transport"] - penawaran["risiko"]
            if setara < p:
                batas, catatan_batas = setara, f" (setara total biaya {pesaing[0]})"
        awal = min(bulat(self.f_awal * p), batas)
        naik = bulat(self.f_naik * p)

        langkah, k = [], 0
        kalimat = [f"{nama} menawarkan {rp(p)}, batas saya {rp(batas)}{catatan_batas}."]
        while True:
            tawaran = min(awal + k * naik, batas)
            jawab = pemasok.tanggapi(Pesan(self.nama, "tawaran", {"langkah": k, "harga": tawaran}))
            minta = jawab.isi["harga"]
            langkah.append((tawaran, minta))
            aku = "Saya buka" if k == 0 else ("Saya naik ke" if tawaran > langkah[-2][0] else "Saya tetap")
            if jawab.jenis == "sepakat":
                kalimat.append(f"{aku} {rp(tawaran)}, {nama} minta {rp(minta)}. Sepakat {rp(minta)} per unit.")
                self.harga_sepakat[nama] = minta
                return Pesan(self.nama, "sepakat", {"harga": minta, "langkah": langkah, "batas": batas},
                             " ".join(kalimat))
            kalimat.append(f"{aku} {rp(tawaran)}, {nama} minta {rp(minta)}.")
            if tawaran == batas and jawab.isi["bertahan"]:
                kalimat.append(f"Tidak bertemu, negosiasi dengan {nama} gagal.")
                return Pesan(self.nama, "gagal", {"langkah": langkah, "batas": batas}, " ".join(kalimat))
            k += 1


# --------------------------------------------------------------------------------------------------------------
class StafKeuangan:
    """Agen 04. Memilih cara bayar, memeriksa rencana (if-else Subbab 6.5), menilai usulan, dan eskalasi."""

    nama = KEUANGAN

    def __init__(self, sc: Scenario, pemasok: dict[str, Pemasok]):
        self.sc = sc
        self.pemasok = pemasok

    # ---- pemeriksaan ----------------------------------------------------------------------------------------
    def periksa(self, rencana: list[Batch]) -> dict:
        sc = self.sc
        bayar: dict[int, int] = {}
        for b in rencana:
            if b.vendor is None:
                continue
            v = sc.vendor(b.vendor)
            for bulan, x in payment_schedule(b.cara_bayar, b.bulan, b.jumlah, b.harga, v.transport, v.risk,
                                             v.discount_pct).items():
                bayar[bulan] = bayar.get(bulan, 0) + x
        if bayar and max(bayar) > sc.horizon:
            raise ValueError("pembayaran jatuh di luar horizon kas")
        saldo = cash_balances(sc.initial_cash, sc.inflows, sc.other_needs, bayar)
        total = sum(bayar.values())
        kas_terendah = min(saldo)
        pelanggaran = []
        if kas_terendah < 0:
            pelanggaran.append(KAS_MINUS)
        if total > sc.budget:
            pelanggaran.append(ANGGARAN)
        if any(b.mendesak > 0 and (b.vendor is None or sc.vendor(b.vendor).lead_time > sc.deadline_days)
               for b in rencana):
            pelanggaran.append(MENDESAK)
        if any(b.mendesak == 0 and b.vendor is None for b in rencana):
            pelanggaran.append(TANPA_PEMASOK)
        return {
            "total": total, "sisa_anggaran": sc.budget - total, "saldo": saldo, "pembayaran": bayar,
            "kas_terendah": kas_terendah, "bulan_kas_terendah": saldo.index(kas_terendah) + 1,
            "pelanggaran": pelanggaran, "peringatan_kas_minimum": kas_terendah < sc.min_cash,
            "lengkap": all(b.vendor is not None for b in rencana),
        }

    @staticmethod
    def hitung_dulu(cek: dict, cek_berlaku: dict) -> bool:
        """Usulan diterima jika tidak ada jenis pelanggaran baru DAN kas terendah tidak lebih buruk.

        Keputusan tim (DECISIONS.md):
        - usulan yang menghilangkan satu jenis pelanggaran tanpa menambah jenis baru langsung diterima;
        - unit mendesak lebih berat daripada kas minus: usulan yang memenuhi unit mendesak dan hanya menambah
          kas minus diterima (kekurangan kas dicoba ditutup di rapat berikutnya, atau dibawa ke atasan).
        """
        if StafKeuangan.tukar_mendesak(cek, cek_berlaku):
            return True
        usulan, berlaku = set(cek["pelanggaran"]), set(cek_berlaku["pelanggaran"])
        if usulan - berlaku:
            return False
        if usulan < berlaku:
            return True
        return cek["kas_terendah"] >= cek_berlaku["kas_terendah"]

    @staticmethod
    def tukar_mendesak(cek: dict, cek_berlaku: dict) -> bool:
        """Unit mendesak teratasi dan satu-satunya pelanggaran baru adalah kas minus."""
        usulan, berlaku = set(cek["pelanggaran"]), set(cek_berlaku["pelanggaran"])
        return MENDESAK in berlaku and MENDESAK not in usulan and usulan - berlaku == {KAS_MINUS}

    def ringkas(self, cek: dict) -> str:
        sisa = cek["sisa_anggaran"]
        anggaran = f"sisa anggaran {rp(sisa)}" if sisa >= 0 else f"anggaran lebih {rp(-sisa)}"
        return (f"Total {rp(cek['total'])}, {anggaran}. Kas terendah {rp(cek['kas_terendah'])} "
                f"(bulan {cek['bulan_kas_terendah']}).")

    # ---- cara bayar -----------------------------------------------------------------------------------------
    def minta_termin(self, vendor: str) -> bool:
        return self.pemasok[vendor].tanggapi(Pesan(self.nama, "minta_termin")).jenis == "setuju"

    # ---- pesan ----------------------------------------------------------------------------------------------
    def tanggapi(self, pesan: Pesan) -> Pesan:
        if pesan.jenis == "periksa":            # rencana rapat 1 atau tanpa rapat: diperiksa langsung
            rencana = pesan.isi["rencana"]
            cek = self.periksa(rencana)
            kalimat = [f"Rencana {label_rencana(rencana)}: {self.ringkas(cek)}"]
            if cek["pelanggaran"]:
                kalimat.append("Saya belum bisa setuju: "
                               + ", ".join(NAMA_PELANGGARAN[p] for p in cek["pelanggaran"]) + ".")
            else:
                kalimat.append("Saya setuju.")
            if cek["peringatan_kas_minimum"]:
                kalimat.append(f"Catatan: kas di bawah batas minimum {rp(self.sc.min_cash)}.")
            return Pesan(self.nama, "hasil_periksa", {"cek": cek}, " ".join(kalimat))

        if pesan.jenis == "hitung_usulan":      # aturan hitung dulu sebelum dipakai
            rencana, cek_berlaku = pesan.isi["rencana"], pesan.isi["cek_berlaku"]
            cek = self.periksa(rencana)
            terima = self.hitung_dulu(cek, cek_berlaku)
            kalimat = [f"Usulan {label_rencana(rencana)}: {self.ringkas(cek)}"]
            if terima and self.tukar_mendesak(cek, cek_berlaku):
                kalimat.append("Saya terima: unit mendesak lebih penting. Kas jadi minus, akan kita cari "
                               "jalan keluarnya di rapat berikutnya.")
            elif terima and set(cek["pelanggaran"]) < set(cek_berlaku["pelanggaran"]):
                hilang = [NAMA_PELANGGARAN[p] for p in cek_berlaku["pelanggaran"] if p not in cek["pelanggaran"]]
                kalimat.append(f"Saya terima: {', '.join(hilang)} teratasi dan tidak ada pelanggaran baru.")
            elif terima:
                kalimat.append("Saya terima: tidak ada pelanggaran baru dan kas tidak lebih buruk.")
            else:
                alasan = [NAMA_PELANGGARAN[p] for p in cek["pelanggaran"] if p not in cek_berlaku["pelanggaran"]]
                if cek["kas_terendah"] < cek_berlaku["kas_terendah"]:
                    alasan.append("kas lebih buruk")
                kalimat.append("Saya tolak: " + ", ".join(alasan) + ".")
            return Pesan(self.nama, "diterima" if terima else "ditolak", {"cek": cek}, " ".join(kalimat))

        if pesan.jenis == "eskalasi":
            return self.eskalasi(pesan.isi["rencana"], pesan.isi["cek"])
        raise ValueError(f"{self.nama} tidak mengerti pesan {pesan.jenis}")

    def eskalasi(self, rencana: list[Batch], cek: dict) -> Pesan:
        """Laporan ke atasan. Tidak menyebut besar tambahan dana; keputusan itu ada pada atasan."""
        sisa = cek["sisa_anggaran"]
        kalimat = [f"Rencana terakhir yang disepakati adalah {label_rencana(rencana)}."]
        if sisa >= 0:
            kalimat.append(f"Total {rp(cek['total'])}, masih di bawah anggaran.")
        else:
            kalimat.append(f"Total {rp(cek['total'])}, anggaran lebih {rp(-sisa)}.")
        isi = {"rencana": salin(rencana), "total": cek["total"], "kelebihan_anggaran": max(0, -sisa),
               "kekurangan_kas": max(0, -cek["kas_terendah"]),
               "bulan_kekurangan": cek["bulan_kas_terendah"] if cek["kas_terendah"] < 0 else None,
               "pelanggaran": list(cek["pelanggaran"]), "batas_bawah_kekurangan": None}
        if cek["kas_terendah"] < 0:
            kalimat.append(f"Kas kurang {rp(-cek['kas_terendah'])} di bulan {cek['bulan_kas_terendah']}.")
        if MENDESAK in cek["pelanggaran"]:
            kalimat.append("Unit mendesak tidak bisa dipenuhi tepat waktu.")
        if TANPA_PEMASOK in cek["pelanggaran"]:
            kalimat.append("Ada batch yang tidak mendapat pemasok.")
        diag = cash_diagnosis(self.sc)
        if diag["infeasible"]:
            isi["batas_bawah_kekurangan"] = diag["shortfall"]
            kalimat.append(f"Dengan harga termurah yang mungkin pun, kas kurang minimal {rp(diag['shortfall'])}.")
        kalimat.append("Perlu keputusan atasan: tambahan dana, pengurangan jumlah pembelian, atau pelonggaran batas.")
        return Pesan(f"{self.nama} (eskalasi ke atasan)", "eskalasi", isi, " ".join(kalimat))
