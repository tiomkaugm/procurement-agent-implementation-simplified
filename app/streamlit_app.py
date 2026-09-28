"""Dashboard pemantauan rapat koordinasi pengadaan.

    streamlit run app/streamlit_app.py

Semua angka berasal dari fungsi di `src/rapat_pengadaan`; dashboard tidak menghitung atau menulis angka sendiri.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rapat_pengadaan.format import angka, desimal, rp  # noqa: E402
from rapat_pengadaan.rapat import KONDISI, cetak_notulen  # noqa: E402
from rapat_pengadaan.skenario import cash_diagnosis, composite_scores, load_scenario, sample_scenario  # noqa: E402
from rapat_pengadaan.staf import NAMA_CARA_BAYAR, NAMA_PELANGGARAN, label_rencana  # noqa: E402

NAMA_KONDISI = {
    "c": "Rapat dengan aturan reaksi konflik",
    "b": "Rapat dengan aturan tetap",
    "a": "Tanpa rapat",
}
EVALUASI_CSV = ROOT / "runs" / "evaluasi_rapat.csv"
EVALUASI_MD = ROOT / "runs" / "evaluasi_rapat.md"


@st.cache_data
def jalankan(seed: int | None, kondisi: str):
    sc = load_scenario() if seed is None else sample_scenario(seed)
    return sc, KONDISI[kondisi](sc)


def status(h) -> str:
    if h.setuju:
        return "Semua bagian setuju"
    if h.eskalasi:
        return "Eskalasi ke atasan"
    return "Gagal tanpa rapat"


def tabel_pemasok(sc) -> pd.DataFrame:
    skor = composite_scores(sc)
    return pd.DataFrame([{
        "Pemasok": v.name,
        "Harga penawaran": rp(v.list_price),
        "Transport": rp(v.transport),
        "Risiko": rp(v.risk),
        "Kualitas": v.quality,
        "Waktu kirim (hari)": v.lead_time,
        "Kapasitas": angka(v.capacity),
        "Diskon bayar cepat": f"{v.discount_pct}%",
        "Relasi": desimal(v.relation),
        "Skor SAW": desimal(skor[v.name]),
        "Lolos skor": "lolos" if skor[v.name] >= sc.min_composite_score else "gugur",
    } for v in sc.vendors])


def tabel_rencana(rencana) -> pd.DataFrame:
    return pd.DataFrame([{
        "Batch": i + 1,
        "Bulan": b.bulan,
        "Jumlah": angka(b.jumlah),
        "Unit mendesak": angka(b.mendesak),
        "Pemasok": (b.vendor or "tidak ada") + (" (cadangan)" if b.cadangan else ""),
        "Harga/unit": rp(b.harga) if b.harga is not None else "-",
        "Cara bayar": NAMA_CARA_BAYAR[b.cara_bayar],
    } for i, b in enumerate(rencana)])


def grafik_kas(sc, cek: dict, judul: str) -> go.Figure:
    bulan = [f"Bulan {i}" for i in range(1, len(cek["saldo"]) + 1)]
    fig = go.Figure()
    fig.add_bar(x=bulan, y=cek["saldo"], name="Saldo kas",
                marker_color=["#c0392b" if x < 0 else "#2e86c1" for x in cek["saldo"]],
                text=[rp(x) for x in cek["saldo"]], textposition="outside")
    fig.add_hline(y=0, line_color="black", line_width=1)
    fig.add_hline(y=sc.min_cash, line_dash="dash", line_color="#e67e22",
                  annotation_text=f"Batas minimum {rp(sc.min_cash)}", annotation_position="top left")
    fig.update_layout(title=judul, height=320, margin=dict(t=50, b=20, l=20, r=20), showlegend=False,
                      yaxis_title="Rupiah")
    return fig


def tampil_notulen(h) -> None:
    judul = None
    for j, pembicara, teks in h.notulen:
        if j != judul:
            st.markdown(f"#### {j}")
            judul = j
        if "eskalasi" in pembicara:
            st.error(f"**{pembicara}** : {teks}", icon="⚠️")
        elif pembicara == "Hasil":
            st.info(f"**Hasil** : {teks}")
        else:
            st.markdown(f"**{pembicara}** : {teks}")


def tampil_per_rapat(sc, h) -> None:
    nomor = sorted({e["rapat"] for e in h.riwayat})
    for n in nomor:
        entri = [e for e in h.riwayat if e["rapat"] == n]
        with st.expander("Tanpa rapat" if n == 0 else f"Rapat {n}", expanded=(n == nomor[-1])):
            for i, e in enumerate(entri, start=1):
                st.markdown(f"**Usulan {i}: {e['usulan']}** — keputusan: *{e['keputusan']}*")
                if e["rencana"] is None:
                    continue
                cek = e["cek"]
                kiri, kanan = st.columns([3, 2])
                with kiri:
                    st.dataframe(tabel_rencana(e["rencana"]), hide_index=True, width="stretch")
                    sisa = cek["sisa_anggaran"]
                    st.markdown(
                        f"Total {rp(cek['total'])} · "
                        + (f"sisa anggaran {rp(sisa)}" if sisa >= 0 else f"anggaran lebih {rp(-sisa)}")
                        + f" · kas terendah {rp(cek['kas_terendah'])} (bulan {cek['bulan_kas_terendah']})")
                    if cek["pelanggaran"]:
                        st.warning("Pelanggaran: " + ", ".join(NAMA_PELANGGARAN[p] for p in cek["pelanggaran"]))
                    else:
                        st.success("Tidak ada pelanggaran.")
                    if cek["peringatan_kas_minimum"]:
                        st.caption(f"Peringatan: kas di bawah batas minimum {rp(sc.min_cash)}.")
                with kanan:
                    st.plotly_chart(grafik_kas(sc, cek, "Saldo kas per bulan"), width="stretch",
                                    key=f"kas-{n}-{i}")
                st.divider()


def tampil_evaluasi() -> None:
    if not EVALUASI_CSV.exists():
        st.info("Evaluasi belum dijalankan. Jalankan `python scripts/evaluasi_rapat.py` lalu muat ulang halaman.")
        return
    st.dataframe(pd.read_csv(EVALUASI_CSV), hide_index=True, width="stretch")
    if EVALUASI_MD.exists():
        st.markdown(EVALUASI_MD.read_text(encoding="utf-8"))
    png = ROOT / "runs" / "evaluasi_rapat.png"
    if png.exists():
        st.image(str(png))


def main() -> None:
    st.set_page_config(page_title="Rapat Koordinasi Pengadaan", layout="wide")
    st.title("Rapat koordinasi pengadaan")
    st.caption("Staf Permintaan, Staf Purchasing, Negosiator, dan Staf Keuangan berkoordinasi lewat rapat. "
               "Setiap keputusan berupa aturan yang bisa ditelusuri.")

    with st.sidebar:
        st.header("Pengaturan")
        pilihan = st.radio("Skenario", ["Skenario laporan (Bab 6)", "Skenario acak"], key="skenario")
        seed = None
        if pilihan == "Skenario acak":
            seed = int(st.number_input("Seed (0-499)", min_value=0, max_value=499, value=0, step=1, key="seed"))
        kondisi = st.radio("Kondisi", list(NAMA_KONDISI), format_func=NAMA_KONDISI.get, key="kondisi")
        if st.button("Jalankan", type="primary", key="jalankan"):
            st.session_state["pilihan"] = (seed, kondisi)

    if "pilihan" not in st.session_state:
        st.session_state["pilihan"] = (None, "c")
    seed, kondisi = st.session_state["pilihan"]
    sc, h = jalankan(seed, kondisi)

    nama = "skenario laporan" if seed is None else f"skenario acak seed {seed}"
    st.subheader(f"{NAMA_KONDISI[kondisi]} · {nama}")

    tab_rapat, tab_data, tab_eval = st.tabs(["Jalannya rapat", "Data skenario", "Evaluasi"])
    with tab_rapat:
        teks_status = f"**Status akhir: {status(h)}** · jumlah rapat {h.jumlah_rapat}"
        if h.setuju:
            st.success(teks_status)
        elif h.eskalasi:
            st.warning(teks_status)
        else:
            st.error(teks_status)
        k = st.columns(4)
        k[0].metric("Jumlah rapat", h.jumlah_rapat)
        k[1].metric("Total biaya", rp(h.cek["total"]))
        k[2].metric("Sisa anggaran", rp(h.cek["sisa_anggaran"]))
        k[3].metric(f"Kas terendah (bulan {h.cek['bulan_kas_terendah']})", rp(h.cek["kas_terendah"]))
        st.markdown(f"**Rencana akhir:** {label_rencana(h.rencana)}")
        st.download_button("Unduh notulen (.txt)", cetak_notulen(h), file_name=f"notulen_{kondisi}_"
                           f"{'laporan' if seed is None else f'seed{seed}'}.txt", mime="text/plain")

        st.markdown("### Notulen")
        tampil_notulen(h)
        st.markdown("### Rincian per rapat")
        tampil_per_rapat(sc, h)

    with tab_data:
        st.markdown("### Pemasok")
        st.dataframe(tabel_pemasok(sc), hide_index=True, width="stretch")
        st.caption(f"Ambang lolos skor SAW {desimal(sc.min_composite_score)}. Harga lantai pemasok tidak "
                   "ditampilkan karena tidak diketahui Negosiator.")
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("### Kebutuhan")
            st.dataframe(pd.DataFrame([
                {"Butir": "Jumlah permintaan", "Nilai": f"{angka(sc.quantity)} unit"},
                {"Butir": "Unit mendesak", "Nilai": f"{angka(sc.urgent_quantity)} unit"},
                {"Butir": "Tenggat", "Nilai": f"{sc.deadline_days} hari"},
                {"Butir": "Anggaran", "Nilai": rp(sc.budget)},
            ]), hide_index=True, width="stretch")
        with c2:
            st.markdown("### Kas")
            st.dataframe(pd.DataFrame([{
                "Bulan": i + 1, "Kas masuk": rp(masuk), "Kebutuhan lain": rp(lain),
            } for i, (masuk, lain) in enumerate(zip(sc.inflows, sc.other_needs))]), hide_index=True,
                width="stretch")
            st.markdown(f"Kas awal {rp(sc.initial_cash)} · batas minimum {rp(sc.min_cash)}")
        d = cash_diagnosis(sc)
        if d["infeasible"]:
            st.error(f"Skenario ini terbukti tidak mungkin: kas kurang minimal {rp(d['shortfall'])} "
                     "bahkan dengan harga termurah yang mungkin.")
        else:
            st.caption("Diagnosis kas: batas bawah tagihan masih tertutup kas sepanjang horizon "
                       "(ini tidak menjamin rapat bisa setuju).")

    with tab_eval:
        tampil_evaluasi()


main()
