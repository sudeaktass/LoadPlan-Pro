# -*- coding: utf-8 -*-
"""
Doluluk ölçüleri testleri (karar R-a)
======================================
    python -X utf8 -m pytest test_doluluk.py -q

Kabul ölçütleri (prompt, 21 Ekim 2026):
  * Ford F-MAX + Schmitz, 20.000 kg yük → U_W ≈ %77,65
  * Aynı araçta gerçek hacim 45,60 m³ → U_G ≈ %50,0, bağlayıcı = "Ağırlık"
  * Tek silindir → U_G / U_BB = π/4 ≈ 0,785
  * Yalnız kutu → U_G = U_BB
  * İki araçlı örnekte filo U_W = Σ kütle / Σ faydalı yük
    (araç oranlarının basit ortalamasından FARKLI)
  * Palet darası iki kez sayılmıyor
"""

from __future__ import annotations

import math

import pytest

import doluluk as dk
from core_3d import CuttingPlan3D, Piece3D, Placement3D, Truck3D
from filo_havuzu import eslesme_to_truck3d
from filo_modeli import eslesme_hesapla
from ornek_filo import ford_fmax_4x2, schmitz_scs_24l

CM3_M3 = 1_000_000.0          # 1 m³ = 1.000.000 cm³


def _arac() -> Truck3D:
    """Ford F-MAX 4x2 + Schmitz SCS 24/L → faydalı yük 25.757 kg."""
    return eslesme_to_truck3d(eslesme_hesapla(ford_fmax_4x2(),
                                              schmitz_scs_24l()))


def _plan(bins, atama):
    return CuttingPlan3D(bins=bins, total_waste=0, utilization=0.0,
                         execution_time=0.0, algorithm="test",
                         truck_assignments=dict(atama))


def _kutu(pid, w, l, h, agirlik):
    return Piece3D(id=pid, width=w, length=l, height=h, quantity=1,
                   weight=agirlik, shape="box")


def _silindir(pid, cap, h, agirlik):
    return Piece3D(id=pid, width=cap, length=cap, height=h, quantity=1,
                   weight=agirlik, shape="cylinder")


def _yerlesim(pid, p, x=0, y=0, z=0):
    return Placement3D(x, y, z, p.width, p.length, p.height, pid, (0, 0, 0), 0)


# ═════════════════════════════════════════════════════════════════════════════
# KABUL ÖLÇÜTÜ 1 — Ford + Schmitz, 20.000 kg
# ═════════════════════════════════════════════════════════════════════════════

def test_kabul_u_w_yuzde_77_65():
    """20.000 / 25.757 ≈ %77,65"""
    t = _arac()
    assert t.capacity == pytest.approx(25_757.0)
    p = _kutu("y", 200, 300, 200, 20_000.0)
    rapor = dk.plan_doluluk(_plan([[_yerlesim("y", p)]], {0: t.id}), [p], [t])
    assert rapor.u_w == pytest.approx(20_000.0 / 25_757.0, abs=1e-12)
    assert rapor.u_w == pytest.approx(0.7765, abs=0.0001)   # ≈ %77,65
    # Tam değer %77,6487 → bir ondalıkta %77,6 (yuvarlama)
    assert dk.yuzde(rapor.u_w) == "%77.6"
    assert dk.yuzde(rapor.u_w, 2) == "%77.65"


def test_kabul_u_g_yuzde_50_ve_baglayici_agirlik():
    """Gerçek hacim 45,60 m³ / 91,20 m³ ≈ %50 → bağlayıcı 'Ağırlık'."""
    t = _arac()
    arac_m3 = t.get_volume() / CM3_M3
    assert arac_m3 == pytest.approx(91.20, abs=0.05)

    # 45,60 m³'lük tek kutu: 240 × 950 × 200 cm = 45,60 m³
    p = _kutu("y", 240, 950, 200, 20_000.0)
    assert p.get_actual_volume() / CM3_M3 == pytest.approx(45.60, abs=0.01)

    rapor = dk.plan_doluluk(_plan([[_yerlesim("y", p)]], {0: t.id}), [p], [t])
    assert rapor.u_g == pytest.approx(0.50, abs=0.001)
    assert rapor.u_w == pytest.approx(0.7765, abs=0.0001)
    assert rapor.baglayici == dk.BAGLAYICI_AGIRLIK
    assert rapor.araclar[0].baglayici == "Ağırlık"


def test_hacim_baglayici_oldugunda():
    """Hafif ama hacimli yük → bağlayıcı 'Hacim'."""
    t = _arac()
    p = _kutu("y", 240, 1300, 260, 1_000.0)
    rapor = dk.plan_doluluk(_plan([[_yerlesim("y", p)]], {0: t.id}), [p], [t])
    assert rapor.u_g > rapor.u_w
    assert rapor.baglayici == dk.BAGLAYICI_HACIM


# ═════════════════════════════════════════════════════════════════════════════
# KABUL ÖLÇÜTÜ 2 — silindir ve kutu oranları
# ═════════════════════════════════════════════════════════════════════════════

def test_kabul_silindirde_ug_bolu_ubb_pi_bolu_4():
    """Silindirin gerçek hacmi dış kutusunun π/4'ü kadardır."""
    t = _arac()
    p = _silindir("s", 100, 150, 500.0)
    rapor = dk.plan_doluluk(_plan([[_yerlesim("s", p)]], {0: t.id}), [p], [t])
    a = rapor.araclar[0]
    assert a.u_g / a.u_bb == pytest.approx(math.pi / 4, abs=1e-9)
    assert a.u_g / a.u_bb == pytest.approx(0.785, abs=0.001)


def test_kabul_kutuda_ug_esittir_ubb():
    t = _arac()
    parcalar = [_kutu(f"k{i}", 100, 120, 110, 300.0) for i in range(4)]
    bins = [[_yerlesim(p.id, p, y=i * 120) for i, p in enumerate(parcalar)]]
    rapor = dk.plan_doluluk(_plan(bins, {0: t.id}), parcalar, [t])
    assert rapor.u_g == pytest.approx(rapor.u_bb)
    assert rapor.araclar[0].u_g == pytest.approx(rapor.araclar[0].u_bb)


# ═════════════════════════════════════════════════════════════════════════════
# KABUL ÖLÇÜTÜ 3 — filo toplamı = toplamların oranı (ortalama DEĞİL)
# ═════════════════════════════════════════════════════════════════════════════

def test_kabul_filo_toplami_ortalamadan_farkli():
    """Σ kütle / Σ faydalı yük ≠ araç oranlarının ortalaması."""
    buyuk = _arac()                                   # faydalı yük 25.757
    kucuk = Truck3D("KUCUK", 170, 260, 180, 5_000.0, 1)

    agir = _kutu("agir", 100, 100, 100, 20_000.0)     # büyük araçta
    hafif = _kutu("hafif", 50, 50, 50, 500.0)         # küçük araçta
    bins = [[_yerlesim("agir", agir)], [_yerlesim("hafif", hafif)]]
    rapor = dk.plan_doluluk(_plan(bins, {0: buyuk.id, 1: kucuk.id}),
                            [agir, hafif], [buyuk, kucuk])

    toplam = (20_000.0 + 500.0) / (25_757.0 + 5_000.0)
    assert rapor.u_w == pytest.approx(toplam, abs=1e-9)

    ortalama = ((20_000.0 / 25_757.0) + (500.0 / 5_000.0)) / 2
    assert rapor.u_w_ortalama == pytest.approx(ortalama, abs=1e-9)
    assert abs(rapor.u_w - rapor.u_w_ortalama) > 0.1, \
        "örnek, toplam oran ile ortalamanın ayrıştığını göstermeli"


def test_filo_u_g_de_toplamlarin_orani():
    t1, t2 = _arac(), Truck3D("KUCUK", 170, 260, 180, 5_000.0, 1)
    p1 = _kutu("a", 200, 300, 200, 100.0)
    p2 = _kutu("b", 100, 100, 100, 100.0)
    rapor = dk.plan_doluluk(
        _plan([[_yerlesim("a", p1)], [_yerlesim("b", p2)]],
              {0: t1.id, 1: t2.id}), [p1, p2], [t1, t2])
    beklenen = ((200 * 300 * 200 + 100 * 100 * 100)
                / (t1.get_volume() + t2.get_volume()))
    assert rapor.u_g == pytest.approx(beklenen)


# ═════════════════════════════════════════════════════════════════════════════
# KABUL ÖLÇÜTÜ 4 — palet darası iki kez sayılmıyor
# ═════════════════════════════════════════════════════════════════════════════

def test_kabul_palet_darasi_bir_kez_sayiliyor():
    """Hazır palet: dara zaten parça ağırlığına eklenmiş olarak gelir.

    app_3d._palet_render toplam ağırlığı (yük + palet) Yük Listesi'ne
    yazar; `Piece3D.weight` bu toplamdır. Doluluk modülü yalnız
    `piece.weight` toplar → dara BİR KEZ sayılır.
    """
    import palet_kutuphanesi as pk
    eur = pk.palet_bul("EUR")
    yuk_kg, palet_kg = 225.0, eur.bos_agirlik_kg          # 25 kg
    toplam, _, _ = pk.toplam_agirlik_kg(eur, yuk_kg)
    assert toplam == pytest.approx(250.0)

    t = _arac()
    parcalar = [_kutu(f"p{i}", 80, 120, 140, toplam) for i in range(4)]
    bins = [[_yerlesim(p.id, p, y=i * 120) for i, p in enumerate(parcalar)]]
    rapor = dk.plan_doluluk(_plan(bins, {0: t.id}), parcalar, [t])

    # 4 palet × 250 kg = 1.000 kg — dara ikinci kez EKLENMEZ
    assert rapor.toplam_yuk_kg == pytest.approx(4 * 250.0)
    assert rapor.toplam_yuk_kg != pytest.approx(4 * (250.0 + palet_kg))
    assert rapor.u_w == pytest.approx(1_000.0 / 25_757.0)


# ═════════════════════════════════════════════════════════════════════════════
# Bilinmeyen faydalı yük → "—"
# ═════════════════════════════════════════════════════════════════════════════

def test_faydali_yuk_bilinmiyorsa_u_w_none():
    t = Truck3D("ESKI", 240, 600, 200, 0.0, 1)        # kapasite tanımsız
    p = _kutu("x", 100, 100, 100, 500.0)
    rapor = dk.plan_doluluk(_plan([[_yerlesim("x", p)]], {0: t.id}), [p], [t])
    assert rapor.araclar[0].u_w is None
    assert rapor.u_w is None
    assert dk.yuzde(rapor.u_w) == "—"
    assert dk.yuzde(None) != "%0.0"


def test_bilinmeyen_arac_toplama_girmiyor():
    """Faydalı yükü bilinen ve bilinmeyen araç bir arada."""
    bilinen = _arac()
    bilinmeyen = Truck3D("ESKI", 240, 600, 200, 0.0, 1)
    p1 = _kutu("a", 100, 100, 100, 10_000.0)
    p2 = _kutu("b", 100, 100, 100, 9_999.0)
    rapor = dk.plan_doluluk(
        _plan([[_yerlesim("a", p1)], [_yerlesim("b", p2)]],
              {0: bilinen.id, 1: bilinmeyen.id}), [p1, p2],
        [bilinen, bilinmeyen])
    # Yalnız bilinen araç üzerinden
    assert rapor.u_w == pytest.approx(10_000.0 / 25_757.0)


def test_baglayici_u_w_bilinmiyorsa_hacim():
    t = Truck3D("ESKI", 240, 600, 200, 0.0, 1)
    p = _kutu("x", 100, 100, 100, 500.0)
    rapor = dk.plan_doluluk(_plan([[_yerlesim("x", p)]], {0: t.id}), [p], [t])
    assert rapor.baglayici == dk.BAGLAYICI_HACIM


# ═════════════════════════════════════════════════════════════════════════════
# Boş araçlar ve kenar durumlar
# ═════════════════════════════════════════════════════════════════════════════

def test_bos_arac_paydaya_girmiyor():
    t1, t2 = _arac(), _arac()
    t2.id = "BOS"
    p = _kutu("x", 240, 950, 200, 1_000.0)
    rapor = dk.plan_doluluk(_plan([[_yerlesim("x", p)], []],
                                  {0: t1.id, 1: t2.id}), [p], [t1, t2])
    assert rapor.arac_sayisi == 1
    assert rapor.u_g == pytest.approx(0.50, abs=0.001)


def test_bos_plan_none_donuyor():
    rapor = dk.plan_doluluk(None, [], [])
    assert rapor.araclar == []
    assert rapor.u_g is None and rapor.u_w is None
    assert rapor.baglayici is None


def test_en_dusuk_ve_ortalama():
    t1, t2 = _arac(), _arac()
    t2.id = "IKINCI"
    dolu = _kutu("a", 240, 1300, 260, 100.0)
    bos = _kutu("b", 50, 50, 50, 100.0)
    rapor = dk.plan_doluluk(
        _plan([[_yerlesim("a", dolu)], [_yerlesim("b", bos)]],
              {0: t1.id, 1: t2.id}), [dolu, bos], [t1, t2])
    assert rapor.u_g_en_dusuk < rapor.u_g_ortalama < rapor.araclar[0].u_g


def test_arac_satirlari_sutunlari():
    t = _arac()
    p = _kutu("x", 100, 100, 100, 500.0)
    satir = dk.arac_satirlari(
        dk.plan_doluluk(_plan([[_yerlesim("x", p)]], {0: t.id}), [p], [t]))[0]
    assert set(satir) == {"Araç", "Parça", "U_G (hacim)", "U_BB (dış kutu)",
                          "U_W (ağırlık)", "Bağlayıcı", "Yük (kg)",
                          "Faydalı yük (kg)"}
    assert satir["Araç"] == "54 ABC 123 + 54 XYZ 456"


# ═════════════════════════════════════════════════════════════════════════════
# U_G, mevcut plan.utilization ile AYNI kalmalı (4 Eylül kararı korunuyor)
# ═════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("sekil", ["box", "cylinder"])
def test_u_g_algoritmanin_hesabiyla_ayni(sekil):
    import contextlib
    import io as _io
    from ffd_3d import ffd_3d_optimization

    trucks = [Truck3D("Buyuk", 240, 600, 200, 24_000, 3)]
    if sekil == "box":
        parcalar = [_kutu(f"b{i}", 80, 120, 100, 200.0) for i in range(12)]
    else:
        parcalar = [_silindir(f"c{i}", 80, 100, 200.0) for i in range(12)]

    with contextlib.redirect_stdout(_io.StringIO()):
        plan = ffd_3d_optimization(parcalar, trucks)

    rapor = dk.plan_doluluk(plan, parcalar, trucks)
    assert rapor.u_g * 100.0 == pytest.approx(plan.utilization, abs=1e-6)
