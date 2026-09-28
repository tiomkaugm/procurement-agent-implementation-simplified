"""Dashboard Streamlit: terbuka tanpa error dan menampilkan hasil yang benar."""

from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

APP = str(Path(__file__).resolve().parents[1] / "app" / "streamlit_app.py")


def buka():
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    assert not at.exception
    return at


def metrik(at) -> dict:
    return {m.label: m.value for m in at.metric}


def test_terbuka_default_laporan_eskalasi_3_rapat():
    at = buka()
    m = metrik(at)
    assert any("Eskalasi ke atasan" in w.value for w in at.warning)
    assert m["Jumlah rapat"] == "3"
    assert m["Total biaya"] == "Rp99.710.000"
    assert any("eskalasi ke atasan" in e.value for e in at.error)


def test_laporan_tanpa_rapat():
    at = buka()
    at.radio(key="kondisi").set_value("a")
    at.button(key="jalankan").click().run()
    assert not at.exception
    m = metrik(at)
    assert m["Jumlah rapat"] == "0"
    assert any("Gagal tanpa rapat" in e.value for e in at.error)


def test_skenario_acak_seed_3():
    at = buka()
    at.radio(key="skenario").set_value("Skenario acak").run()
    at.number_input(key="seed").set_value(3)
    at.button(key="jalankan").click().run()
    assert not at.exception
    assert any("seed 3" in s.value for s in at.subheader)


def test_tab_evaluasi_menampilkan_csv_atau_pesan():
    at = buka()
    csv = Path(APP).parents[1] / "runs" / "evaluasi_rapat.csv"
    if csv.exists():
        assert len(at.dataframe) >= 1
    else:
        assert any("belum dijalankan" in i.value for i in at.info)
