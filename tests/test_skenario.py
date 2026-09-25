"""Skenario acak: deterministik dan di dalam rentang Tabel 7.2."""

from rapat_pengadaan.skenario import sample_scenario


def test_seed_sama_skenario_sama():
    assert sample_scenario(7) == sample_scenario(7)
    assert sample_scenario(7) != sample_scenario(8)


def test_rentang_tabel_72():
    for seed in range(500):
        sc = sample_scenario(seed)
        assert 600 <= sc.quantity <= 1400
        assert 0.5 * sc.quantity - 1 <= sc.urgent_quantity <= 0.8 * sc.quantity + 1
        assert 6 <= sc.deadline_days <= 14
        assert 100_000 * sc.quantity <= sc.budget <= 125_000 * sc.quantity
        assert 125_000_000 <= sc.initial_cash <= 230_000_000
        assert 0 <= sc.other_needs[0] <= 80_000_000 and sc.other_needs[1:] == (0, 0, 0)
        assert sc.inflows[0] == 0 and all(0 <= x <= 80_000_000 for x in sc.inflows[1:])
        assert all(0.4 <= v.relation <= 0.9 and v.floor_price <= v.list_price for v in sc.vendors)
