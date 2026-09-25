"""Rumus biaya dan kas (Subbab 6.3-6.5). Semua uang dalam rupiah bulat (int).

Nama fungsi mengikuti spesifikasi (payment_schedule, cash_balances, ...)."""

from __future__ import annotations

# Cara bayar yang dipilih Staf Keuangan.
BAYAR_CEPAT = "bayar_cepat"              # barang dibayar di bulan batch, dengan diskon kalau ada
BAYAR_JATUH_TEMPO = "bayar_jatuh_tempo"  # barang dibayar bulan berikutnya, tanpa diskon
REVISI_TERMIN = "revisi_termin"          # 50% bulan +1, 50% bulan +2, tanpa diskon
CARA_BAYAR = (BAYAR_CEPAT, BAYAR_JATUH_TEMPO, REVISI_TERMIN)


def goods_value(jumlah: int, harga: int) -> int:
    """Nilai barang sebelum diskon."""
    return jumlah * harga


def discount_amount(nilai: int, persen: int) -> int:
    """Diskon bayar cepat, hanya pada nilai barang, dibulatkan ke rupiah terdekat (setengah ke atas)."""
    return (nilai * persen + 50) // 100


def logistics_cost(jumlah: int, transport: int, risiko: int) -> int:
    """Transport (c1) dan risiko (c2), selalu dibayar di bulan batch."""
    return jumlah * (transport + risiko)


def batch_total(jumlah: int, harga: int, transport: int, risiko: int, persen_diskon: int = 0) -> int:
    """C = q * (p * (1 - d) + c1 + c2)."""
    nilai = goods_value(jumlah, harga)
    return nilai - discount_amount(nilai, persen_diskon) + logistics_cost(jumlah, transport, risiko)


def payment_schedule(
    cara: str, bulan: int, jumlah: int, harga: int, transport: int, risiko: int, persen_diskon: int = 0,
) -> dict[int, int]:
    """{bulan: jumlah dibayar} untuk satu batch yang dibeli di `bulan` (mulai 1)."""
    nilai = goods_value(jumlah, harga)
    tambahan = logistics_cost(jumlah, transport, risiko)
    if cara == BAYAR_CEPAT:
        return {bulan: nilai - discount_amount(nilai, persen_diskon) + tambahan}
    if cara == BAYAR_JATUH_TEMPO:
        return {bulan: tambahan, bulan + 1: nilai}
    if cara == REVISI_TERMIN:
        pertama = nilai // 2
        return {bulan: tambahan, bulan + 1: pertama, bulan + 2: nilai - pertama}
    raise ValueError(f"cara bayar tidak dikenal: {cara}")


def cash_balances(kas_awal: int, kas_masuk: list[int] | tuple[int, ...], kebutuhan_lain: list[int] | tuple[int, ...],
              pembayaran: dict[int, int]) -> list[int]:
    """Saldo akhir tiap bulan 1..horizon: K_m = K_{m-1} + masuk_m - bayar_m - kebutuhan_lain_m."""
    saldo, kas = [], kas_awal
    for bulan, (masuk, lain) in enumerate(zip(kas_masuk, kebutuhan_lain), start=1):
        kas = kas + masuk - pembayaran.get(bulan, 0) - lain
        saldo.append(kas)
    return saldo
