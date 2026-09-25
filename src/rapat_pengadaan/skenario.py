"""Data skenario (Subbab 6.1, Tabel 6.1, Tabel 7.2), skor SAW (6.2), dan batas bawah kas (7.2)."""

from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path

import yaml

from .biaya import batch_total

CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"


@dataclass(frozen=True)
class Vendor:
    name: str
    list_price: int         # harga penawaran (harga daftar)
    transport: int
    risk: int
    quality: int            # 0-10
    lead_time: int          # hari
    capacity: int           # unit
    floor_price: int        # harga lantai, tidak diketahui Negosiator
    discount_pct: int       # diskon bayar cepat, persen
    reputation: float       # 0-10
    relation: float         # 0-1


@dataclass(frozen=True)
class Scenario:
    quantity: int
    urgent_quantity: int
    budget: int
    deadline_days: int
    vendors: tuple[Vendor, ...]
    initial_cash: int
    other_needs: tuple[int, ...]    # per bulan
    inflows: tuple[int, ...]        # per bulan
    min_cash: int
    min_composite_score: float
    score_weights: dict[str, float]

    @property
    def horizon(self) -> int:
        return len(self.other_needs)

    def vendor(self, name: str) -> Vendor:
        return next(v for v in self.vendors if v.name == name)


def _read_yaml(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_scenario(path: str | Path = CONFIG_DIR / "skenario_laporan.yaml") -> Scenario:
    """Skenario laporan (Subbab 6.1)."""
    d = _read_yaml(Path(path))
    vendors = tuple(
        Vendor(name=name, list_price=v["harga_penawaran"], transport=v["transport"], risk=v["risiko"],
               quality=v["kualitas"], lead_time=v["waktu_kirim"], capacity=v["kapasitas"],
               floor_price=v["harga_lantai"], discount_pct=v["diskon_persen"], reputation=v["reputasi"],
               relation=v["relasi"])
        for name, v in d["pemasok"].items()
    )
    b = d["skor"]["bobot"]
    return Scenario(
        quantity=d["permintaan"]["jumlah"],
        urgent_quantity=d["permintaan"]["unit_mendesak"],
        budget=d["permintaan"]["anggaran"],
        deadline_days=d["permintaan"]["tenggat_hari"],
        vendors=vendors,
        initial_cash=d["kas"]["awal"],
        other_needs=tuple(d["kas"]["kebutuhan_lain"]),
        inflows=tuple(d["kas"]["masuk"]),
        min_cash=d["kas"]["batas_minimum"],
        min_composite_score=d["skor"]["ambang"],
        score_weights={"quality": b["kualitas"], "delivery": b["waktu"], "reputation": b["reputasi"],
                       "price": b["harga"]},
    )


def composite_scores(scenario: Scenario) -> dict[str, float]:
    """Skor SAW per pemasok, 0-10 (6.2). Dihitung atas semua pemasok."""
    w = scenario.score_weights
    prices = [v.list_price for v in scenario.vendors]
    p_min, p_max = min(prices), max(prices)
    scores = {}
    for v in scenario.vendors:
        delivery = min(10.0, max(0.0, 10 * (1 - v.lead_time / scenario.deadline_days)))
        price = 10.0 if p_max == p_min else 10 * (p_max - v.list_price) / (p_max - p_min)
        scores[v.name] = (w["quality"] * v.quality + w["delivery"] * delivery
                          + w["reputation"] * v.reputation + w["price"] * price)
    return scores


def cash_diagnosis(scenario: Scenario) -> dict[str, int | str | bool]:
    """Batas bawah kekurangan kas (Subbab 7.2).

    Tagihan termurah yang mungkin = seluruh permintaan dari pemasok termurah pada harga lantai dengan diskon bayar
    cepat (kapasitas, waktu kirim, dan skor diabaikan, jadi benar-benar batas bawah). Semua pembayaran jatuh di dalam
    horizon, jadi kalau kas sepanjang horizon kurang dari tagihan itu, bulan terakhir pasti minus.
    `infeasible` True membuktikan skenario tidak mungkin disetujui; False tidak membuktikan apa-apa.
    """
    def bill(v: Vendor) -> int:
        return batch_total(scenario.quantity, v.floor_price, v.transport, v.risk, v.discount_pct)

    cheapest = min(scenario.vendors, key=bill)
    available = scenario.initial_cash + sum(scenario.inflows) - sum(scenario.other_needs)
    lower_bound = bill(cheapest)
    return {"vendor": cheapest.name, "lower_bound": lower_bound, "available": available,
            "shortfall": max(0, lower_bound - available), "infeasible": lower_bound > available}


def sample_scenario(seed: int, config_path: str | Path = CONFIG_DIR / "skenario_acak.yaml") -> Scenario:
    """Skenario acak di sekitar skenario laporan (Tabel 7.2). Seed sama, skenario sama.

    Urutan pengambilan angka acak sengaja dijaga tetap supaya seed N selalu memberi skenario yang sama.
    """
    rng = random.Random(seed)
    cfg = _read_yaml(Path(config_path))
    base = load_scenario()
    jitter = cfg["gangguan_pemasok"]

    def j(x: int, minimum: int = 1) -> int:
        return max(minimum, round(x * rng.uniform(1 - jitter, 1 + jitter)))

    vendors = []
    for v in base.vendors:
        f = rng.uniform(1 - jitter, 1 + jitter)   # faktor sama untuk harga penawaran dan lantai: lantai <= penawaran
        transport = j(v.transport)
        risk = j(v.risk)
        lead_time = j(v.lead_time)
        capacity = j(v.capacity)
        relation = round(rng.uniform(*cfg["relasi"]), 2)
        vendors.append(Vendor(
            name=v.name, list_price=round(v.list_price * f), transport=transport, risk=risk,
            quality=v.quality, lead_time=lead_time, capacity=capacity, floor_price=round(v.floor_price * f),
            discount_pct=v.discount_pct, reputation=v.reputation, relation=relation,
        ))

    quantity = rng.randint(*cfg["jumlah"])
    urgent = round(quantity * rng.uniform(*cfg["porsi_mendesak"]))
    budget = quantity * rng.randrange(cfg["anggaran_per_unit"][0], cfg["anggaran_per_unit"][1] + 1, 1000)
    deadline = rng.randint(*cfg["tenggat_hari"])
    initial_cash = rng.randrange(cfg["kas_awal"][0], cfg["kas_awal"][1] + 1, 1_000_000)
    need1 = rng.randrange(cfg["kebutuhan_lain_bulan1"][0], cfg["kebutuhan_lain_bulan1"][1] + 1, 1_000_000)
    inflows = (0,) + tuple(
        rng.randrange(cfg["kas_masuk_bulan2_4"][0], cfg["kas_masuk_bulan2_4"][1] + 1, 1_000_000) for _ in range(3)
    )
    return Scenario(
        quantity=quantity, urgent_quantity=urgent, budget=budget, deadline_days=deadline, vendors=tuple(vendors),
        initial_cash=initial_cash, other_needs=(need1, 0, 0, 0), inflows=inflows, min_cash=cfg["batas_minimum"],
        min_composite_score=base.min_composite_score, score_weights=base.score_weights,
    )
