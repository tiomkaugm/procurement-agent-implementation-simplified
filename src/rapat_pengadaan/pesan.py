"""Pesan antar-staf dan antara staf dengan pemasok selama rapat."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Pesan:
    dari: str
    jenis: str
    isi: dict = field(default_factory=dict)
    teks: str = ""          # kalimat untuk notulen; kosong berarti tidak dicatat
