"""Mengulang angka Bab 6 laporan _3 dari rumus biaya dan kas."""

import pytest

from rapat_pengadaan.biaya import (
    BAYAR_CEPAT, BAYAR_JATUH_TEMPO, REVISI_TERMIN, batch_total, cash_balances, discount_amount, payment_schedule,
)
from rapat_pengadaan.skenario import cash_diagnosis, composite_scores, load_scenario

S = load_scenario()
A, B, C = S.vendor("A"), S.vendor("B"), S.vendor("C")


def total(v, qty, price=None, disc=0):
    return batch_total(qty, price or v.list_price, v.transport, v.risk, disc)


def test_ctotal_harga_penawaran_631():
    assert total(A, 1000) == 107_000_000
    assert total(B, 1000) == 102_000_000
    assert total(A, 800) + total(B, 200) == 106_000_000


def test_skor_saw_62():
    s = composite_scores(S)
    assert round(s["A"], 2) == 6.60
    assert round(s["B"], 2) == 7.19
    assert round(s["C"], 2) == 5.41
    assert [n for n, x in s.items() if x >= S.min_composite_score] == ["A", "B"]


def test_total_1000_b_bayar_cepat_64():
    assert discount_amount(89_500_000, 2) == 1_790_000
    assert total(B, 1000, 89_500, 2) == 99_710_000


def test_kas_65():
    bayar = payment_schedule(BAYAR_CEPAT, 1, 1000, 89_500, B.transport, B.risk, 2)
    assert cash_balances(S.initial_cash, S.inflows, S.other_needs, bayar)[0] == -19_710_000


def test_beli_bertahap_65():
    assert total(B, 700, 89_500) == 71_050_000
    assert total(A, 300) == 32_100_000
    b700 = total(B, 700, 89_500, 2)
    a300 = total(A, 300, 95_000)
    assert b700 == 69_797_000 and a300 == 30_600_000
    bayar = {1: b700, 2: a300}
    k = cash_balances(S.initial_cash, S.inflows, S.other_needs, bayar)
    assert k[0] == 10_203_000 and k[1] == -20_397_000
    assert b700 + a300 == 100_397_000


@pytest.mark.parametrize("cara,bulan_minus", [(BAYAR_JATUH_TEMPO, 2), (REVISI_TERMIN, 3)])
def test_jatuh_tempo_dan_termin_rapat2(cara, bulan_minus):
    bayar = payment_schedule(cara, 1, 1000, 89_500, B.transport, B.risk, B.discount_pct)
    assert sum(bayar.values()) == 101_500_000
    k = cash_balances(S.initial_cash, S.inflows, S.other_needs, bayar)
    assert k[0] == 68_000_000
    assert min(k) == -21_500_000 and k.index(min(k)) + 1 == bulan_minus


def test_batas_bawah_72():
    d = cash_diagnosis(S)
    assert d["vendor"] == "B" and d["lower_bound"] == 99_220_000 and d["available"] == 80_000_000
    assert d["shortfall"] == 19_220_000 and d["infeasible"]
