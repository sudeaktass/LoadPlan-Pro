# -*- coding: utf-8 -*-
"""
Lift-Top (ayarlanabilir tavan) testleri
========================================
    python -X utf8 -m pytest test_lift_top.py -q

Kabul ölçütü (Sude, 21 Ekim 2026):
  İkinci bir araç açılması gerektiğinde, birinci aracın tavanı
  `yukseklik_max` sınırına kadar otomatik yükseltilerek 2. araç
  engellenebilmeli.

İnisiyatif akışı:
  1. Parça açık araçlara sığmadı
  2. Yeni araç açmadan ÖNCE tavan kaldırılıp tekrar denenir
  3. Sığdıysa aktif yükseklik güncellenir, kayda geçer
  4. Sığmadıysa tavan eski hâline iner, yeni araç açılır
"""

from __future__ import annotations

import contextlib
import io

import pytest

import filo_havuzu as fh
from core_3d import Piece3D, Truck3D
from filo_havuzu import eslesme_to_truck3d
from filo_modeli import eslesme_hesapla
from ornek_filo import ford_fmax_4x2, schmitz_scs_24l


@contextlib.contextmanager
def _sessiz():
    with contextlib.redirect_stdout(io.StringIO()):
        yield


@contextlib.contextmanager
def _lift(acik: bool):
    """LIFT_TOP_ACIK bayrağını geçici olarak değiştirir."""
    eski = fh.LIFT_TOP_ACIK
    fh.LIFT_TOP_ACIK = acik
    try:
        yield
    finally:
        fh.LIFT_TOP_ACIK = eski


def _filo(lift: bool, n: int = 3, ic_h: float = 2_750.0,
          max_h: float = 2_850.0, dis_h=None):
    araclar = []
    for i in range(n):
        c, d = ford_fmax_4x2(), schmitz_scs_24l()
        c.cekici_id = c.plaka = f"34 C {i:03d}"
        d.dorse_id = d.plaka = f"34 D {i:03d}"
        d.ic_yukseklik_mm = ic_h
        if lift:
            d.ayarlanabilir_tavan = True
            d.yukseklik_max_mm = max_h
        if dis_h is not None:
            d.dis_yukseklik_mm = dis_h
        araclar.append(eslesme_to_truck3d(eslesme_hesapla(c, d)))
    return araclar


def _parcalar(n=50, h=93):
    """93 cm: 275 cm'e 2 kat, 285 cm'e 3 kat sığar."""
    return [Piece3D(id=f"p{i}", width=110, length=120, height=h,
                    quantity=1, weight=300.0) for i in range(n)]


# ═════════════════════════════════════════════════════════════════════════════
# Veri modeli
# ═════════════════════════════════════════════════════════════════════════════

def test_varsayilan_arac_sabit_tavanli():
    """Eski davranış korunmalı: alanlar yoksa tavan kaldırılamaz."""
    t = Truck3D("A", 240, 600, 200, 24_000, 4)
    assert t.yukseklik_min is None and t.yukseklik_max is None
    assert t.tavan_ayarlanabilir is False
    assert t.tavan_yukseltildi is False
    assert t.aktif_yukseklik == 200


def test_dorse_tavan_payi():
    d = schmitz_scs_24l()
    assert d.tavan_payi_mm == 0.0            # varsayılan: sabit tavan
    d.ayarlanabilir_tavan = True
    d.yukseklik_max_mm = 2_850.0
    assert d.yukseklik_min_mm == 2_700.0
    assert d.tavan_payi_mm == 150.0


def test_kopru_yukseklikleri_tasiyor():
    t = _filo(lift=True, n=1)[0]
    assert t.height == 275 and t.yukseklik_min == 275
    assert t.yukseklik_max == 285
    assert t.tavan_ayarlanabilir


def test_kopru_sabit_tavanda_none():
    t = _filo(lift=False, n=1)[0]
    assert t.yukseklik_max is None
    assert not t.tavan_ayarlanabilir


# ═════════════════════════════════════════════════════════════════════════════
# Motor: tavanı yükselt / indir
# ═════════════════════════════════════════════════════════════════════════════

def test_motor_tavani_yukseltiyor_ve_indiriyor():
    from extreme_points_3d import create_packing_engine
    p = Piece3D(id="x", width=100, length=100, height=100, quantity=1,
                weight=10.0)
    m = create_packing_engine(240, 600, 275, piece_info={"x": p})
    assert m.height == 275
    assert m.tavani_yukselt(285) is True
    assert m.height == 285
    assert m.tavani_yukselt(280) is False       # yalnız büyütür
    assert m.tavani_indir(275) is True
    assert m.height == 275


def test_motor_yerlesimin_altina_inmiyor():
    """Yerleştirilmiş parça tavanın altında kalmalı."""
    from extreme_points_3d import create_packing_engine
    p = Piece3D(id="x", width=100, length=100, height=280, quantity=1,
                weight=10.0)
    m = create_packing_engine(240, 600, 275, piece_info={"x": p})
    m.tavani_yukselt(285)
    sonuc = m.find_best_position_3d("x", 100, 100, 280)
    assert sonuc is not None
    m.place_piece_3d("x", sonuc)
    assert m.tavani_indir(275) is False         # 280 cm'lik parça var
    assert m.height == 285


# ═════════════════════════════════════════════════════════════════════════════
# KABUL ÖLÇÜTÜ — ikinci araç engelleniyor
# ═════════════════════════════════════════════════════════════════════════════

def _kos(fn, lift: bool):
    t = _filo(lift)
    with _lift(lift), _sessiz():
        plan = fn(_parcalar(), t)
    return plan, t


@pytest.mark.parametrize("ad", ["FFD", "Greedy"])
def test_kabul_ikinci_arac_engelleniyor(ad):
    from ffd_3d import ffd_3d_optimization
    from greedy_3d import greedy_3d_optimization
    fn = {"FFD": ffd_3d_optimization, "Greedy": greedy_3d_optimization}[ad]

    plan_kapali, _ = _kos(fn, lift=False)
    plan_acik, t_acik = _kos(fn, lift=True)

    arac_kapali = len([b for b in plan_kapali.bins if b])
    arac_acik = len([b for b in plan_acik.bins if b])

    assert arac_kapali == 2, f"{ad}: test kurgusu 2 araç gerektirmeli"
    assert arac_acik == 1, f"{ad}: tavan kaldırılarak 2. araç önlenmeliydi"
    # Hiçbir parça düşmemeli
    assert sum(len(b) for b in plan_acik.bins) == 50
    # Ve tavan gerçekten kaldırılmış olmalı
    assert [x.id for x in t_acik if x.tavan_yukseltildi]
    assert t_acik[0].height == 285


def test_lift_top_kapaliyken_davranis_degismiyor():
    """Bayrak kapalıyken sonuç, özellik hiç yokmuş gibi olmalı."""
    from ffd_3d import ffd_3d_optimization
    t_sabit = _filo(lift=False)
    t_lift = _filo(lift=True)
    with _lift(False), _sessiz():
        a = ffd_3d_optimization(_parcalar(), t_sabit)
        b = ffd_3d_optimization(_parcalar(), t_lift)
    assert len([x for x in a.bins if x]) == len([x for x in b.bins if x])
    assert all(not x.tavan_yukseltildi for x in t_lift)


# ═════════════════════════════════════════════════════════════════════════════
# Yasal sınır: KTY md.128 azami yükseklik 4,00 m
# ═════════════════════════════════════════════════════════════════════════════

def test_dis_yukseklik_sinirini_asan_yukseltme_reddediliyor():
    from filo_havuzu import tavan_yukseltilebilir_mi
    # Dış yükseklik 3.950 mm; 10 cm kaldırınca 4.050 mm > 4.000 mm
    t = _filo(lift=True, n=1, dis_h=3_950.0)[0]
    with _lift(True):
        uygun, gerekce = tavan_yukseltilebilir_mi(t)
    assert uygun is False
    assert "4000 mm" in gerekce.replace(".", "") or "KTY" in gerekce


def test_dis_yukseklik_sinir_altinda_izin_veriliyor():
    from filo_havuzu import tavan_yukseltilebilir_mi
    t = _filo(lift=True, n=1, dis_h=3_800.0)[0]   # +100 mm = 3.900 < 4.000
    with _lift(True):
        uygun, _ = tavan_yukseltilebilir_mi(t)
    assert uygun is True


def test_dis_yukseklik_bilinmiyorsa_engellenmiyor():
    """Veri yoksa yükseltme yapılır (uyarı arayüzde gösterilir)."""
    from filo_havuzu import tavan_yukseltilebilir_mi
    t = _filo(lift=True, n=1)[0]
    with _lift(True):
        uygun, _ = tavan_yukseltilebilir_mi(t)
    assert uygun is True


def test_zaten_yukseltilmis_arac_tekrar_yukseltilmiyor():
    from filo_havuzu import tavan_yukseltilebilir_mi
    t = _filo(lift=True, n=1)[0]
    t.tavan_yukseltildi = True
    with _lift(True):
        uygun, gerekce = tavan_yukseltilebilir_mi(t)
    assert uygun is False and "zaten" in gerekce


def test_bayrak_kapaliyken_izin_yok():
    from filo_havuzu import tavan_yukseltilebilir_mi
    t = _filo(lift=True, n=1)[0]
    with _lift(False):
        uygun, gerekce = tavan_yukseltilebilir_mi(t)
    assert uygun is False and "kapalı" in gerekce


# ═════════════════════════════════════════════════════════════════════════════
# Doluluk: payda aktif yükseklikten
# ═════════════════════════════════════════════════════════════════════════════

def test_doluluk_paydasi_aktif_yukseklikten():
    """Tavan kaldırılınca hacim de büyür; doluluk yapay düşmez."""
    t = _filo(lift=True, n=1)[0]
    once = t.get_volume()
    t.height = 285
    assert t.get_volume() > once
    assert t.get_volume() == 248 * 1362 * 285
