# -*- coding: utf-8 -*-
"""
Küçültme testleri (S18 — Kang & Park 2003, IFFD 2. adımı)
==========================================================
    python -X utf8 -m pytest test_kucultme.py -q
"""

from __future__ import annotations

import contextlib
import io

import pytest

from core_3d import Piece3D, Truck3D
from filo_havuzu import kucult
from filo_modeli import eslesme_hesapla
from filo_havuzu import eslesme_to_truck3d
from ornek_filo import ford_fmax_4x2, schmitz_scs_24l


@contextlib.contextmanager
def _sessiz():
    with contextlib.redirect_stdout(io.StringIO()):
        yield


def _filo():
    return [Truck3D("Buyuk", 240, 600, 200, 24_000, 2),
            Truck3D("Orta",  240, 420, 200, 16_000, 2),
            Truck3D("Kucuk", 170, 260, 180,  6_000, 2)]


def _plan_kur(trucks, bins, atama, pieces):
    from core_3d import CuttingPlan3D
    return CuttingPlan3D(bins=bins, total_waste=0, utilization=0.0,
                         execution_time=0.0, algorithm="test",
                         truck_assignments=dict(atama))


def _yerlesim(pid, x, y, z, w, l, h):
    from core_3d import Placement3D
    return Placement3D(x, y, z, w, l, h, pid, (0, 0, 0), 0)


def test_tek_parca_buyuk_aractan_kucuge_iniyor():
    """S18'in çıkış noktası: son araç tek parça için en büyüğünden açılıyor."""
    trucks = _filo()
    pieces = {"p": Piece3D(id="p", width=100, length=100, height=100,
                           quantity=1, weight=500)}
    plan = _plan_kur(trucks, [[_yerlesim("p", 0, 0, 0, 100, 100, 100)]],
                     {0: "Buyuk"}, pieces)
    assert kucult(plan, trucks, pieces) == 1
    assert plan.truck_assignments[0] == "Kucuk"


def test_sigmayan_tipe_kuculmuyor():
    """Yerleşimler küçük araca sığmıyorsa küçültme yapılmaz."""
    trucks = _filo()
    pieces = {"p": Piece3D(id="p", width=240, length=600, height=200,
                           quantity=1, weight=500)}
    plan = _plan_kur(trucks, [[_yerlesim("p", 0, 0, 0, 240, 600, 200)]],
                     {0: "Buyuk"}, pieces)
    assert kucult(plan, trucks, pieces) == 0
    assert plan.truck_assignments[0] == "Buyuk"


def test_agirlik_asilirsa_kuculmuyor():
    """Küçük araç hacmen alsa da kapasitesi yetmiyorsa küçültülmez."""
    trucks = _filo()
    pieces = {"p": Piece3D(id="p", width=100, length=100, height=100,
                           quantity=1, weight=20_000)}
    plan = _plan_kur(trucks, [[_yerlesim("p", 0, 0, 0, 100, 100, 100)]],
                     {0: "Buyuk"}, pieces)
    assert kucult(plan, trucks, pieces) == 0


def test_tavan_asilmiyor():
    """O tipten boş araç kalmadıysa küçültülmez."""
    trucks = [Truck3D("Buyuk", 240, 600, 200, 24_000, 2),
              Truck3D("Kucuk", 170, 260, 180, 6_000, 1)]
    pieces = {f"p{i}": Piece3D(id=f"p{i}", width=100, length=100, height=100,
                               quantity=1, weight=100) for i in range(2)}
    plan = _plan_kur(
        trucks,
        [[_yerlesim("p0", 0, 0, 0, 100, 100, 100)],
         [_yerlesim("p1", 0, 0, 0, 100, 100, 100)]],
        {0: "Kucuk", 1: "Buyuk"}, pieces)
    # Kucuk'tan yalnız 1 adet var ve zaten kullanılıyor → 2. bin inemez
    assert kucult(plan, trucks, pieces) == 0
    assert plan.truck_assignments[1] == "Buyuk"


def test_arac_sayisi_degismiyor():
    """Küçültme yalnız TİP değiştirir — K1'in 1. ölçütü korunur."""
    trucks = _filo()
    pieces = {f"p{i}": Piece3D(id=f"p{i}", width=100, length=100, height=100,
                               quantity=1, weight=100) for i in range(2)}
    plan = _plan_kur(
        trucks,
        [[_yerlesim("p0", 0, 0, 0, 100, 100, 100)],
         [_yerlesim("p1", 0, 0, 0, 100, 100, 100)]],
        {0: "Buyuk", 1: "Buyuk"}, pieces)
    once = len([b for b in plan.bins if b])
    kucult(plan, trucks, pieces)
    assert len([b for b in plan.bins if b]) == once


def test_doluluk_yeniden_hesaplaniyor():
    """Araç hacmi değiştiği için doluluk güncellenmeli."""
    trucks = _filo()
    pieces = {"p": Piece3D(id="p", width=100, length=100, height=100,
                           quantity=1, weight=500)}
    plan = _plan_kur(trucks, [[_yerlesim("p", 0, 0, 0, 100, 100, 100)]],
                     {0: "Buyuk"}, pieces)
    plan.utilization = 0.0
    kucult(plan, trucks, pieces)
    # 100³ / (170×260×180) ≈ %12,6  (Buyuk'ta %3,5 olurdu)
    beklenen = 1_000_000 / (170 * 260 * 180) * 100
    assert plan.utilization == pytest.approx(beklenen, abs=0.01)


def test_bos_bin_atlaniyor():
    trucks = _filo()
    plan = _plan_kur(trucks, [[]], {0: "Buyuk"}, {})
    assert kucult(plan, trucks, {}) == 0


def test_dingilli_aracta_gecersiz_kuculme_reddediliyor():
    """Küçültme dingil kontrolünü BOZAMAZ.

    Kurgu: iki dorse de aynı uzunlukta (yerleşimler ikisine de SIĞAR),
    ikincisi hacmen daha küçük ama kingpin izni çok düşük. Yerleşim
    büyük araçta geçerli, küçükte geçersiz → küçültme reddedilmeli.
    """
    from dingil_yuku import arac_dingil_raporu, cm_to_mm_cg

    buyuk = eslesme_to_truck3d(eslesme_hesapla(ford_fmax_4x2(),
                                               schmitz_scs_24l()))
    c2, d2 = ford_fmax_4x2(), schmitz_scs_24l()
    c2.cekici_id = c2.plaka = "34 BB 222"
    d2.dorse_id = d2.plaka = "34 DD 222"
    d2.ic_genislik_mm = 2_400.0          # hacmen daha küçük
    d2.ic_yukseklik_mm = 2_600.0
    d2.kingpin_izin_kg = 4_000.0         # ama kingpin izni çok düşük
    kucuk = eslesme_to_truck3d(eslesme_hesapla(c2, d2))
    assert kucuk.get_volume() < buyuk.get_volume()
    trucks = [buyuk, kucuk]

    # Yük dorse boyunca dağıtılmış → BÜYÜK araçta geçerli
    pieces = {f"p{i}": Piece3D(id=f"p{i}", width=110, length=120, height=110,
                               quantity=1, weight=2_000) for i in range(6)}
    bins = [[_yerlesim(f"p{i}", 0, 300 + i * 120, 0, 110, 120, 110)
             for i in range(6)]]
    yukler = [(2_000.0, cm_to_mm_cg(p.y, p.length)) for p in bins[0]]
    assert arac_dingil_raporu(buyuk.eslesme, yukler).gecerli, \
        "test kurgusu: büyük araçta geçerli olmalı"
    assert not arac_dingil_raporu(kucuk.eslesme, yukler).gecerli, \
        "test kurgusu: küçük araçta geçersiz olmalı"

    plan = _plan_kur(trucks, bins, {0: buyuk.id}, pieces)
    assert kucult(plan, trucks, pieces) == 0, "geçersiz küçültme yapılmamalı"
    assert plan.truck_assignments[0] == buyuk.id


def test_uctan_uca_ffd_kucultme_sonrasi_gecerli():
    """FFD planı küçültüldükten sonra hâlâ sığıyor olmalı."""
    from ffd_3d import ffd_3d_optimization
    trucks = _filo()
    pieces = [Piece3D(id="tek", width=100, length=100, height=100,
                      quantity=1, weight=300)]
    with _sessiz():
        plan = ffd_3d_optimization(pieces, trucks)
    assert plan.truck_assignments[0] == "Buyuk"      # açma sırası gereği

    pi = {p.id: p for p in pieces}
    assert kucult(plan, trucks, pi) == 1
    assert plan.truck_assignments[0] == "Kucuk"

    secilen = {t.id: t for t in trucks}["Kucuk"]
    for p in plan.bins[0]:
        assert p.x + p.width <= secilen.width
        assert p.y + p.length <= secilen.length
        assert p.z + p.height <= secilen.height
