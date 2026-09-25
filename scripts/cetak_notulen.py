"""Cetak notulen rapat.

    python scripts/cetak_notulen.py                  # skenario laporan, kondisi c
    python scripts/cetak_notulen.py --seed 3 --kondisi b
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rapat_pengadaan.format import rp  # noqa: E402
from rapat_pengadaan.rapat import KONDISI, cetak_notulen  # noqa: E402
from rapat_pengadaan.skenario import load_scenario, sample_scenario  # noqa: E402

NAMA_KONDISI = {"a": "tanpa rapat", "b": "rapat dengan aturan tetap", "c": "rapat dengan aturan reaksi konflik"}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=None, help="skenario acak 0-499 (default: skenario laporan)")
    ap.add_argument("--kondisi", choices="abc", default="c")
    a = ap.parse_args()

    sc = load_scenario() if a.seed is None else sample_scenario(a.seed)
    h = KONDISI[a.kondisi](sc)
    nama = "skenario laporan" if a.seed is None else f"skenario acak seed {a.seed}"
    print(f"# Notulen {nama}, kondisi ({a.kondisi}) {NAMA_KONDISI[a.kondisi]}\n")
    print(cetak_notulen(h))
    status = "semua bagian setuju" if h.setuju else ("eskalasi" if h.eskalasi else "gagal tanpa rapat")
    print(f"\nStatus: {status}; jumlah rapat {h.jumlah_rapat}; total {rp(h.cek['total'])}; "
          f"sisa anggaran {rp(h.cek['sisa_anggaran'])}; kas terendah {rp(h.cek['kas_terendah'])} "
          f"(bulan {h.cek['bulan_kas_terendah']}).")


if __name__ == "__main__":
    main()
