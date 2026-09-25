"""Format angka untuk notulen: pemisah ribuan titik, desimal koma."""

from __future__ import annotations


def angka(x: int) -> str:
    """1000 -> '1.000', -19710000 -> '−19.710.000'."""
    s = f"{abs(int(x)):,}".replace(",", ".")
    return f"−{s}" if x < 0 else s


def rp(x: int) -> str:
    """89500 -> 'Rp89.500', -19710000 -> '−Rp19.710.000'."""
    s = f"{abs(int(x)):,}".replace(",", ".")
    return f"−Rp{s}" if x < 0 else f"Rp{s}"


def desimal(x: float, digit: int = 2) -> str:
    """5.41 -> '5,41'."""
    return f"{x:.{digit}f}".replace(".", ",")


def daftar(nama: list[str]) -> str:
    """['A', 'B', 'C'] -> 'A, B, dan C'."""
    if len(nama) <= 1:
        return "".join(nama)
    if len(nama) == 2:
        return f"{nama[0]} dan {nama[1]}"
    return ", ".join(nama[:-1]) + f", dan {nama[-1]}"
