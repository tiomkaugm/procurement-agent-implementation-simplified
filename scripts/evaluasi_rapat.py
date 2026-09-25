"""Evaluasi Subbab 7.4: tiga kondisi pada 500 skenario acak (seed 0-499).

    python scripts/evaluasi_rapat.py [--n 500]

Hasil: runs/evaluasi_rapat.csv, .md, .png, .meta.json.
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rapat_pengadaan.rapat import KONDISI  # noqa: E402
from rapat_pengadaan.skenario import cash_diagnosis, composite_scores, sample_scenario  # noqa: E402
from rapat_pengadaan.staf import ANGGARAN, KAS_MINUS, MENDESAK  # noqa: E402

KOLOM = {"a": "Tanpa rapat", "b": "Aturan tetap", "c": "Aturan reaksi"}
# Urutan baris sama dengan Tabel 7.3 laporan.
BARIS = [
    ("setuju_pct", "Semua bagian setuju (%)"),
    ("pelanggaran_anggaran_pct", "Pelanggaran anggaran (%)"),
    ("pelanggaran_kas_pct", "Pelanggaran kas (%)"),
    ("unit_mendesak_terpenuhi_pct", "Unit mendesak terpenuhi (%)"),
    ("biaya_rata_juta", "Biaya rata-rata (juta Rp)"),
    ("rata_jumlah_rapat", "Rata-rata jumlah rapat"),
    ("eskalasi_pct", "Eskalasi (%)"),
]


def mendesak_mungkin(sc) -> bool:
    """Ada pemasok yang lolos skor, cukup cepat, dan sanggup memasok semua unit mendesak."""
    skor = composite_scores(sc)
    return any(skor[v.name] >= sc.min_composite_score and v.lead_time <= sc.deadline_days
               and v.capacity >= sc.urgent_quantity for v in sc.vendors)


def evaluasi(n: int) -> tuple[dict, dict]:
    hasil = {k: [] for k in KONDISI}
    diag = {"infeasible_kas": 0, "mendesak_tidak_mungkin": 0}
    for seed in range(n):
        sc = sample_scenario(seed)
        diag["infeasible_kas"] += cash_diagnosis(sc)["infeasible"]
        diag["mendesak_tidak_mungkin"] += not mendesak_mungkin(sc)
        for k, f in KONDISI.items():
            hasil[k].append(f(sc))

    metrik = {}
    for k, hs in hasil.items():
        lengkap = [h for h in hs if h.cek["lengkap"]]
        pct = lambda xs: round(100 * sum(xs) / len(hs), 1)
        metrik[k] = {
            "setuju_pct": pct(h.setuju for h in hs),
            "pelanggaran_anggaran_pct": pct(ANGGARAN in h.cek["pelanggaran"] for h in hs),
            "pelanggaran_kas_pct": pct(KAS_MINUS in h.cek["pelanggaran"] for h in hs),
            "unit_mendesak_terpenuhi_pct": pct(MENDESAK not in h.cek["pelanggaran"] for h in hs),
            "biaya_rata_juta": round(sum(h.cek["total"] for h in lengkap) / len(lengkap) / 1e6, 2),
            "n_biaya": len(lengkap),
            "rata_jumlah_rapat": round(sum(h.jumlah_rapat for h in hs) / len(hs), 2),
            "eskalasi_pct": pct(h.eskalasi for h in hs),
        }
    infeasible = [s for s in range(n) if cash_diagnosis(sample_scenario(s))["infeasible"]]
    for k in KONDISI:
        diag[f"eskalasi_pada_infeasible_{k}"] = sum(hasil[k][s].eskalasi for s in infeasible)
    return metrik, diag


DIGIT = {"biaya_rata_juta": 2, "rata_jumlah_rapat": 2}


def koma(x, digit: int = 1) -> str:
    return f"{x:.{digit}f}".replace(".", ",")


def tulis(metrik: dict, diag: dict, n: int, out: Path, perintah: str) -> None:
    out.mkdir(exist_ok=True)
    with open(out / "evaluasi_rapat.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["metrik"] + [KOLOM[k] for k in KONDISI])
        for key, _ in BARIS + [("n_biaya", "")]:
            w.writerow([key] + [metrik[k][key] for k in KONDISI])

    lines = [f"# Hasil evaluasi pada {n} skenario acak (seed 0-{n - 1})", "",
             "| Metrik | " + " | ".join(KOLOM.values()) + " |", "|---|" + "---|" * len(KOLOM)]
    for key, label in BARIS:
        lines.append(f"| {label} | " + " | ".join(koma(metrik[k][key], DIGIT.get(key, 1)) for k in KONDISI) + " |")
    lines += ["", "Catatan:",
              "- Biaya rata-rata dihitung dari rencana akhir yang semua batch-nya punya pemasok: "
              + ", ".join(f"{KOLOM[k]} n = {metrik[k]['n_biaya']}" for k in KONDISI)
              + ". Karena n berbeda, biaya rata-rata antar kondisi tidak dihitung pada skenario yang sama.",
              f"- Skenario yang terbukti tidak mungkin menurut `cash_diagnosis` (kas sepanjang horizon kurang dari "
              f"tagihan termurah yang mungkin): {diag['infeasible_kas']} dari {n}. Eskalasi pada skenario itu: "
              + ", ".join(f"{KOLOM[k]} {diag[f'eskalasi_pada_infeasible_{k}']}" for k in KONDISI) + ".",
              f"- Skenario tanpa pemasok yang lolos skor, cukup cepat, dan sanggup memasok semua unit mendesak "
              f"sekaligus: {diag['mendesak_tidak_mungkin']} dari {n} (beli bertahap tidak mengubah jumlah unit "
              "mendesak, jadi unit mendesak skenario ini tidak bisa dipenuhi oleh aturan mana pun).",
              f"- Dibuat dengan `{perintah}`; lihat `evaluasi_rapat.meta.json`."]
    (out / "evaluasi_rapat.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    pct_rows = [r for r in BARIS if r[0].endswith("_pct")]
    fig, ax = plt.subplots(figsize=(9, 4.5))
    lebar = 0.26
    for i, k in enumerate(KONDISI):
        xs = [j + (i - 1) * lebar for j in range(len(pct_rows))]
        ys = [metrik[k][key] for key, _ in pct_rows]
        ax.bar(xs, ys, lebar, label=KOLOM[k])
        for x, y in zip(xs, ys):
            ax.text(x, y + 1, koma(y), ha="center", fontsize=7)
    ax.set_xticks(range(len(pct_rows)), [lbl.replace(" (%)", "") for _, lbl in pct_rows], fontsize=8)
    ax.set_ylabel("% skenario")
    ax.set_ylim(0, 110)
    ax.set_title(f"Evaluasi rapat koordinasi pada {n} skenario acak")
    ax.legend(fontsize=8)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(out / "evaluasi_rapat.png", dpi=150)

    def git(*args):
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    meta = {"commit": git("rev-parse", "HEAD"), "working_tree_bersih": git("status", "--porcelain") == "",
            "perintah": perintah, "tanggal": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "n_skenario": n, "seed": [0, n - 1], "diagnosis": diag}
    (out / "evaluasi_rapat.meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n", type=int, default=500)
    a = ap.parse_args()
    metrik, diag = evaluasi(a.n)
    tulis(metrik, diag, a.n, ROOT / "runs", "python " + " ".join(sys.argv))
    print((ROOT / "runs" / "evaluasi_rapat.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
