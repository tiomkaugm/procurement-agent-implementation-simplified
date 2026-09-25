"""Loop rapat koordinasi (Subbab 5.2 dan 5.4) dan dua kondisi pembanding (Subbab 7.4).

jalankan_rapat(sc)      : kondisi (c), rapat dengan aturan reaksi konflik dan aturan hitung dulu sebelum dipakai.
rapat_aturan_tetap(sc)  : kondisi (b), rapat diulang tetapi setiap staf selalu memakai pilihan yang sama.
putuskan_sendiri(sc)    : kondisi (a), tanpa rapat; setiap bagian memutuskan sekali.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field

from .biaya import BAYAR_CEPAT, BAYAR_JATUH_TEMPO, REVISI_TERMIN
from .pesan import Pesan
from .skenario import Scenario
from .staf import (
    ANGGARAN, BELI_BERTAHAP, BELI_SEMUA_SEKARANG, KAS_MINUS, MENDESAK, NAMA_PELANGGARAN, Batch,
    Negosiator, Pemasok, StafKeuangan, StafPermintaan, StafPurchasing, kunci_rencana, label_rencana, muat_config,
    salin,
)


@dataclass
class HasilRapat:
    kondisi: str
    setuju: bool
    eskalasi: bool
    jumlah_rapat: int
    rencana: list[Batch]
    cek: dict
    notulen: list[tuple[str, str, str]] = field(default_factory=list)   # (judul rapat, pembicara, teks)
    riwayat: list[dict] = field(default_factory=list)                   # satu entri per usulan yang dihitung
    laporan_eskalasi: dict | None = None
    alasan_selesai: str = ""


@dataclass
class Usulan:
    staf: str
    kunci: tuple                     # catatan opsi
    rencana: list[Batch] | None      # None: usulan gagal sebelum dihitung (mis. pemasok menolak termin)
    keterangan: str = ""


class _Rapat:
    """Menyimpan staf, pemasok, notulen, dan catatan opsi selama satu rangkaian rapat."""

    def __init__(self, sc: Scenario, cfg: dict | None, kondisi: str):
        self.sc = sc
        self.cfg = cfg or muat_config()
        self.kondisi = kondisi
        self.pemasok = {v.name: Pemasok(v, self.cfg) for v in sc.vendors}
        self.permintaan = StafPermintaan(sc)
        self.purchasing = StafPurchasing(sc, self.pemasok)
        self.negosiator = Negosiator(self.cfg)
        self.keuangan = StafKeuangan(sc, self.pemasok)
        self.notulen: list[tuple[str, str, str]] = []
        self.riwayat: list[dict] = []
        self.judul = ""
        self.rapat_ke = 0
        self.bicara: set[str] = set()           # staf yang sudah bicara di rapat ini
        self.dicoba: set[tuple] = set()         # catatan opsi
        self.rencana_dilihat: set[tuple] = set()
        self.umumkan = True

    # ---- notulen --------------------------------------------------------------------------------------------
    def catat(self, pesan: Pesan) -> Pesan:
        if pesan.teks:
            self.notulen.append((self.judul, pesan.dari, pesan.teks))
            self.bicara.add(pesan.dari)
        return pesan

    def hasil(self, teks: str) -> None:
        self.notulen.append((self.judul, "Hasil", teks))

    def mulai_rapat(self, n: int, judul: str | None = None) -> None:
        self.rapat_ke = n
        self.judul = judul or f"Rapat {n}"
        self.bicara = set()
        self.umumkan = True

    def simpan(self, staf: str, rencana: list[Batch], cek: dict | None, keputusan: str, usulan: str = "") -> None:
        self.riwayat.append({
            "rapat": self.rapat_ke, "staf": staf, "usulan": usulan or (label_rencana(rencana) if rencana else ""),
            "rencana": salin(rencana) if rencana else None, "cek": cek, "keputusan": keputusan,
        })

    # ---- Purchasing + Negosiator mengisi satu batch ---------------------------------------------------------
    def isi_batch(self, batch: Batch, hindari: set[str] = frozenset(), hanya: list[str] | None = None,
                  mode_nego: str = "konsesi") -> bool:
        """Purchasing memilih pemasok (Contract Net), Negosiator menawar. Negosiasi gagal -> pemasok dikecualikan
        dan Purchasing memilih pemasok berikutnya. Mengembalikan False jika tidak ada pemasok."""
        dikecualikan: set[str] = set()
        while True:
            pilih = self.catat(self.purchasing.tanggapi(Pesan("Rapat", "pilih_pemasok", {
                "batch": batch, "dikecualikan": dikecualikan, "harga_sepakat": self.negosiator.harga_sepakat,
                "hindari": set(hindari), "hanya": hanya, "umumkan": self.umumkan,
            })))
            self.umumkan = False
            vendor = pilih.isi["vendor"]
            if vendor is None:
                batch.vendor = batch.harga = None
                return False
            nego = self.catat(self.negosiator.tanggapi(Pesan(self.purchasing.nama, "negosiasi", {
                "pemasok": self.pemasok[vendor], "pesaing": pilih.isi["pesaing"], "mode": mode_nego,
            })))
            if nego.jenis == "sepakat":
                batch.vendor, batch.harga, batch.cadangan = vendor, nego.isi["harga"], bool(hindari)
                return True
            dikecualikan.add(vendor)

    def isi_rencana(self, aksi: str, cadangan: bool, mode_nego: str = "konsesi") -> list[Batch]:
        """Rencana baru dari aksi Staf Permintaan. Batch kedua memakai pemasok cadangan kalau `cadangan`."""
        rencana = self.permintaan.batch(aksi)
        for i, b in enumerate(rencana):
            if i > 0 and cadangan:
                dipakai = {x.vendor for x in rencana[:i] if x.vendor}
                if not self.isi_batch(b, hindari=dipakai, mode_nego=mode_nego):
                    self.isi_batch(b, mode_nego=mode_nego)          # tidak ada cadangan: pakai termurah
            else:
                self.isi_batch(b, mode_nego=mode_nego)
        return rencana

    # ---- usulan per jenis konflik (kondisi c) ---------------------------------------------------------------
    def usulan_kas_minus(self, berlaku: list[Batch]) -> Iterator[Usulan]:
        # 1. Staf Keuangan mengganti cara bayar satu batch per usulan, dari batch terakhir ke batch pertama.
        for i in reversed(range(len(berlaku))):
            b = berlaku[i]
            if b.vendor is None:
                continue
            for cara in (BAYAR_JATUH_TEMPO, REVISI_TERMIN):
                if b.cara_bayar == cara:
                    continue
                baru = salin(berlaku)
                baru[i].cara_bayar = cara
                kunci = ("cara_bayar", kunci_rencana(baru))
                if cara == REVISI_TERMIN and not self.keuangan.minta_termin(b.vendor):
                    relasi = self.sc.vendor(b.vendor).relation
                    yield Usulan(self.keuangan.nama, kunci, None,
                                 f"Termin batch {i + 1} ke {b.vendor}: {b.vendor} menolak (relasi "
                                 f"{str(relasi).replace('.', ',')} < "
                                 f"{str(self.cfg['termin']['relasi_minimum']).replace('.', ',')}).")
                    continue
                yield Usulan(self.keuangan.nama, kunci, baru)
        # 2. Staf Permintaan mengusulkan beli bertahap.
        yield from self.usulan_bertahap()

    def usulan_bertahap(self) -> Iterator[Usulan]:
        kunci = ("cara_beli", BELI_BERTAHAP)
        if not self.permintaan.bisa_bertahap() or kunci in self.dicoba:
            return
        self.dicoba.add(kunci)
        self.catat(self.permintaan.tanggapi(Pesan("Rapat", "usul_bertahap")))
        rencana = self.permintaan.batch(BELI_BERTAHAP)
        self.isi_batch(rencana[0])
        dipakai = {rencana[0].vendor} if rencana[0].vendor else set()
        # Cadangan dulu (catatan risiko 6.3.1).
        cadangan = salin(rencana)
        if self.isi_batch(cadangan[1], hindari=dipakai):
            yield Usulan(self.permintaan.nama, ("bertahap", "cadangan"), cadangan)
            teks_lepas = "Cadangan {} saya lepas.".format(cadangan[1].vendor)
        else:
            teks_lepas = ""
        # Lepas cadangan: batch kedua ke pemasok termurah.
        lepas = salin(rencana)
        if teks_lepas:
            self.catat(Pesan(self.purchasing.nama, "lepas_cadangan", {}, teks_lepas))
        self.isi_batch(lepas[1])
        yield Usulan(self.purchasing.nama, ("bertahap", "lepas_cadangan"), lepas)

    def usulan_anggaran(self, berlaku: list[Batch]) -> Iterator[Usulan]:
        # 1. Negosiator menawar ulang pemasok yang belum pernah sepakat harga.
        for i, b in enumerate(berlaku):
            if b.vendor is None or b.vendor in self.negosiator.harga_sepakat:
                continue
            baru = salin(berlaku)
            nego = self.catat(self.negosiator.tanggapi(Pesan("Rapat", "negosiasi", {
                "pemasok": self.pemasok[b.vendor], "pesaing": None})))
            if nego.jenis == "sepakat":
                baru[i].harga = nego.isi["harga"]
                yield Usulan(self.negosiator.nama, ("tawar_ulang", i, b.vendor), baru)
        # 2. Pemasok alternatif yang total biayanya lebih murah untuk batch yang sama.
        for i, b in enumerate(berlaku):
            if b.vendor is None:
                continue
            for alt in self.alternatif_lebih_murah(b):
                baru = salin(berlaku)
                if self.isi_batch(baru[i], hanya=[alt]):
                    baru[i].cara_bayar = b.cara_bayar
                    yield Usulan(self.negosiator.nama, ("alternatif", i, alt, kunci_rencana(berlaku)), baru)

    def alternatif_lebih_murah(self, b: Batch) -> list[str]:
        """Pemasok lolos lain yang estimasi per unitnya lebih murah dari biaya per unit batch sekarang."""
        penawaran = self.purchasing.umumkan(b)
        lolos, _ = self.purchasing.saring(b, penawaran, set())
        sepakat = self.negosiator.harga_sepakat
        sekarang = self.purchasing.per_unit(penawaran[b.vendor], b.harga)
        est = {n: self.purchasing.per_unit(penawaran[n], sepakat.get(n, penawaran[n]["harga"])) for n in lolos}
        return sorted((n for n in lolos if n != b.vendor and est[n] < sekarang), key=lambda n: (est[n], n))

    def usulan_mendesak(self, berlaku: list[Batch]) -> Iterator[Usulan]:
        # 1. Staf Permintaan mengubah pembagian batch.
        yield from self.usulan_bertahap()
        # 2. Staf Purchasing mengganti pemasok batch mendesak.
        for i, b in enumerate(berlaku):
            terlambat = b.vendor is None or self.sc.vendor(b.vendor).lead_time > self.sc.deadline_days
            if b.mendesak == 0 or not terlambat:
                continue
            baru = salin(berlaku)
            hindari = {b.vendor} if b.vendor else set()
            if self.isi_batch(baru[i], hindari=hindari):
                baru[i].cadangan = False
                yield Usulan(self.purchasing.nama, ("ganti_pemasok_mendesak", i, baru[i].vendor), baru)

    def semua_usulan(self, berlaku: list[Batch], cek: dict) -> Iterator[Usulan]:
        """Urutan tetap: kas minus, anggaran terlampaui, unit mendesak (Tabel 5.2)."""
        if KAS_MINUS in cek["pelanggaran"]:
            yield from self.usulan_kas_minus(berlaku)
        if ANGGARAN in cek["pelanggaran"]:
            yield from self.usulan_anggaran(berlaku)
        if MENDESAK in cek["pelanggaran"]:
            yield from self.usulan_mendesak(berlaku)

    # ---- penutup rapat --------------------------------------------------------------------------------------
    def teks_hasil(self, cek: dict, rencana: list[Batch]) -> str:
        konflik = []
        for p in cek["pelanggaran"]:
            s = NAMA_PELANGGARAN[p]
            if p == KAS_MINUS:
                s += f" di bulan {cek['bulan_kas_terendah']}"
            konflik.append(s)
        return f"Konflik {', '.join(konflik)}. Rencana berlaku: {label_rencana(rencana)}."

    def tutup_buntu(self, cek: dict) -> None:
        """Staf yang belum bicara menyampaikan bahwa tidak ada usulan lagi."""
        if self.negosiator.nama not in self.bicara:
            if ANGGARAN in cek["pelanggaran"]:
                teks = "Harga pemasok di rencana sudah disepakati dan tidak ada pemasok alternatif yang lebih murah."
            else:
                teks = "Anggaran masih aman. Harga yang sudah disepakati tidak saya tawar ulang."
            self.catat(Pesan(self.negosiator.nama, "tidak_ada_usulan", {}, teks))
        if self.permintaan.nama not in self.bicara:
            self.catat(self.permintaan.tanggapi(Pesan("Rapat", "tidak_ada_usulan")))

    def eskalasi(self, rencana: list[Batch], cek: dict) -> dict:
        return self.catat(self.keuangan.tanggapi(Pesan("Rapat", "eskalasi", {"rencana": rencana, "cek": cek}))).isi


# --------------------------------------------------------------------------------------------------------------
def jalankan_rapat(sc: Scenario, cfg: dict | None = None) -> HasilRapat:
    """Kondisi (c): rapat koordinasi dengan aturan reaksi konflik (Subbab 5.4)."""
    r = _Rapat(sc, cfg, "c")
    batas = r.cfg["batas_rapat"]

    # Rapat 1
    r.mulai_rapat(1)
    usul = r.catat(r.permintaan.tanggapi(Pesan("Rapat", "buka_rapat")))
    r.dicoba.add(("cara_beli", usul.isi["aksi"]))
    berlaku = r.isi_rencana(usul.isi["aksi"], cadangan=False)
    cek = r.catat(r.keuangan.tanggapi(Pesan("Rapat", "periksa", {"rencana": berlaku}))).isi["cek"]
    r.rencana_dilihat.add(kunci_rencana(berlaku))
    r.simpan(r.permintaan.nama, berlaku, cek, "berlaku")

    n = 1
    while True:
        if not cek["pelanggaran"]:
            r.hasil(f"Semua bagian setuju. Rencana: {label_rencana(berlaku)}.")
            return HasilRapat("c", True, False, n, berlaku, cek, r.notulen, r.riwayat, None, "semua setuju")
        r.hasil(r.teks_hasil(cek, berlaku))
        if n == batas:
            r.hasil(f"Batas {batas} rapat tercapai.")
            lap = r.eskalasi(berlaku, cek)
            return HasilRapat("c", False, True, n, berlaku, cek, r.notulen, r.riwayat, lap, "batas rapat")

        n += 1
        r.mulai_rapat(n)
        diterima = False
        for u in r.semua_usulan(berlaku, cek):
            if u.kunci in r.dicoba:
                continue
            r.dicoba.add(u.kunci)
            if u.rencana is None:                   # ditolak sebelum dihitung
                r.catat(Pesan(r.keuangan.nama, "ditolak", {}, u.keterangan))
                r.simpan(u.staf, [], None, "ditolak pemasok", u.keterangan)
                continue
            k = kunci_rencana(u.rencana)
            if k in r.rencana_dilihat:              # rencana yang sama persis tidak diulang
                continue
            r.rencana_dilihat.add(k)
            jawab = r.catat(r.keuangan.tanggapi(Pesan("Rapat", "hitung_usulan",
                                                      {"rencana": u.rencana, "cek_berlaku": cek})))
            if jawab.jenis == "diterima":
                r.simpan(u.staf, u.rencana, jawab.isi["cek"], "berlaku")
                berlaku, cek = u.rencana, jawab.isi["cek"]
                diterima = True
                break
            r.simpan(u.staf, u.rencana, jawab.isi["cek"], "ditolak")

        if not diterima:
            r.tutup_buntu(cek)
            r.hasil("Semua opsi sudah dicoba. Rapat buntu.")
            lap = r.eskalasi(berlaku, cek)
            return HasilRapat("c", False, True, n, berlaku, cek, r.notulen, r.riwayat, lap, "buntu")


def rapat_aturan_tetap(sc: Scenario, cfg: dict | None = None) -> HasilRapat:
    """Kondisi (b): rapat diulang, tetapi setiap staf selalu memakai pilihan yang sama.

    Rapat 1 beli semua, mulai rapat 2 selalu beli bertahap (kalau bisa). Purchasing memilih termurah plus cadangan
    untuk batch kedua. Negosiator selalu menerima harga penawaran. Keuangan selalu bayar cepat. Berhenti kalau semua
    setuju, kalau rencana sama persis dengan rapat sebelumnya (eskalasi), atau setelah batas rapat (eskalasi).
    """
    r = _Rapat(sc, cfg, "b")
    batas = r.cfg["batas_rapat"]
    sebelumnya = None
    for n in range(1, batas + 1):
        r.mulai_rapat(n)
        if n == 1:
            aksi = r.catat(r.permintaan.tanggapi(Pesan("Rapat", "buka_rapat"))).isi["aksi"]
        elif r.permintaan.bisa_bertahap():
            aksi = r.catat(r.permintaan.tanggapi(Pesan("Rapat", "usul_bertahap"))).isi["aksi"]
        else:
            aksi = BELI_SEMUA_SEKARANG
        rencana = r.isi_rencana(aksi, cadangan=True, mode_nego="terima_penawaran")
        cek = r.catat(r.keuangan.tanggapi(Pesan("Rapat", "periksa", {"rencana": rencana}))).isi["cek"]
        r.simpan(r.permintaan.nama, rencana, cek, "berlaku")
        if not cek["pelanggaran"]:
            r.hasil(f"Semua bagian setuju. Rencana: {label_rencana(rencana)}.")
            return HasilRapat("b", True, False, n, rencana, cek, r.notulen, r.riwayat, None, "semua setuju")
        r.hasil(r.teks_hasil(cek, rencana))
        if kunci_rencana(rencana) == sebelumnya:
            r.hasil("Rencana sama persis dengan rapat sebelumnya.")
            lap = r.eskalasi(rencana, cek)
            return HasilRapat("b", False, True, n, rencana, cek, r.notulen, r.riwayat, lap, "rencana berulang")
        sebelumnya = kunci_rencana(rencana)
    r.hasil(f"Batas {batas} rapat tercapai.")
    lap = r.eskalasi(rencana, cek)
    return HasilRapat("b", False, True, batas, rencana, cek, r.notulen, r.riwayat, lap, "batas rapat")


def putuskan_sendiri(sc: Scenario, cfg: dict | None = None) -> HasilRapat:
    """Kondisi (a): tanpa rapat. Beli semua sekarang, pemasok termurah yang lolos, Negosiator tetap menawar,
    Keuangan bayar cepat jika ada diskon (selain itu jatuh tempo). Diperiksa sekali tanpa perbaikan."""
    r = _Rapat(sc, cfg, "a")
    r.mulai_rapat(0, "Tanpa rapat")
    aksi = r.catat(r.permintaan.tanggapi(Pesan("Rapat", "buka_rapat"))).isi["aksi"]
    rencana = r.isi_rencana(aksi, cadangan=False)
    for b in rencana:
        if b.vendor is not None:
            b.cara_bayar = BAYAR_CEPAT if sc.vendor(b.vendor).discount_pct > 0 else BAYAR_JATUH_TEMPO
    cek = r.catat(r.keuangan.tanggapi(Pesan("Rapat", "periksa", {"rencana": rencana}))).isi["cek"]
    r.simpan(r.permintaan.nama, rencana, cek, "berlaku")
    setuju = not cek["pelanggaran"]
    r.hasil("Semua pemeriksaan lolos." if setuju else r.teks_hasil(cek, rencana) + " Tidak ada perbaikan.")
    return HasilRapat("a", setuju, False, 0, rencana, cek, r.notulen, r.riwayat, None,
                      "semua setuju" if setuju else "gagal tanpa rapat")


KONDISI = {"a": putuskan_sendiri, "b": rapat_aturan_tetap, "c": jalankan_rapat}


def cetak_notulen(hasil: HasilRapat) -> str:
    """Notulen teks, dikelompokkan per rapat: `[Rapat n]` lalu `Nama Staf : kalimat`."""
    baris, judul = [], None
    for j, pembicara, teks in hasil.notulen:
        if j != judul:
            if judul is not None:
                baris.append("")
            baris.append(f"[{j}]")
            judul = j
        baris.append(f"{pembicara} : {teks}")
    return "\n".join(baris)
