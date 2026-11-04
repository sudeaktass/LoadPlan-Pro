# -*- coding: utf-8 -*-
"""
Tohum ve ölçek testleri
=======================
    python -X utf8 -m pytest test_tohum_ve_olcek.py -q

İki hata 22 Ekim 2026'da bulundu; ikisi de "iki farklı ölçekteki sayıyı
karşılaştırmak" sınıfından:

  A1) Monte Carlo'da tohum `utilization` (yüzde) ile, denemeler
      `-packing_objective` ile puanlanıyordu. Tohum hiç yenilenmiyordu.
  A2) SA'nın başlangıç sıcaklığı arayüzde 1000 sabitti. Amaç fonksiyonu
      ~20 mertebesine indiğinde bu "her hamleyi kabul et" demek oluyor;
      tavlama rastgele yürüyüşe dönüyordu.

Bu testler ikisinin de geri gelmesini engeller.
"""

from __future__ import annotations

import math

import pytest

from core_3d import CuttingPlan3D, Piece3D, Placement3D, Truck3D


def _t(tid="T1", en=248, boy=1362, yuk=270, kap=25_000):
    return Truck3D(tid, en, boy, yuk, kap, 4)


def _p(pid, kg=100.0):
    return Piece3D(id=pid, width=100, length=100, height=100,
                   quantity=1, weight=kg)


def _y(pid, y=0):
    return Placement3D(0, y, 0, 100, 100, 100, pid, (0, 0, 0), 0)


def _plan(yerlesimler, doluluk=54.7):
    return CuttingPlan3D(bins=[yerlesimler], total_waste=0,
                         utilization=doluluk, execution_time=0.0,
                         algorithm="tohum", truck_assignments={0: "T1"})


# ═════════════════════════════════════════════════════════════════════════════
# A1 — Monte Carlo tohumu arama skoruyla AYNI ölçekte olmalı
# ═════════════════════════════════════════════════════════════════════════════

def test_tohum_skoru_deneme_skoruyla_ayni_fonksiyondan():
    """KABUL: tohum ve denemeler aynı fonksiyonla puanlanmalı."""
    from monte_carlo_3d import _plan_skoru, calculate_trial_score_3d

    t = _t()
    parcalar = [_p("a"), _p("b")]
    bilgi = {p.id: p for p in parcalar}
    yerlesimler = [_y("a"), _y("b", y=100)]

    tohum = _plan_skoru(_plan(yerlesimler), [t], bilgi)
    deneme = calculate_trial_score_3d({0: yerlesimler}, {0: "T1"}, [t], 0, bilgi)
    assert tohum == deneme


def test_tohum_skoru_yuzde_degil():
    """Eski hata: tohum `utilization` (0-100) ile puanlanıyordu."""
    from monte_carlo_3d import _plan_skoru

    t = _t()
    parcalar = [_p("a")]
    plan = _plan([_y("a")], doluluk=54.7)
    skor = _plan_skoru(plan, [t], {p.id: p for p in parcalar})
    assert skor != pytest.approx(54.7), "tohum hâlâ yüzdeyle puanlanıyor"
    assert skor < 0, "ortak amaç DÜŞÜK=iyi; işaret çevrilince negatif olmalı"


def test_daha_iyi_plan_daha_yuksek_tohum_skoru():
    from monte_carlo_3d import _plan_skoru

    t1, t2 = _t("T1"), _t("T2")
    parcalar = [_p("a"), _p("b")]
    bilgi = {p.id: p for p in parcalar}

    tek = CuttingPlan3D(bins=[[_y("a"), _y("b", y=100)]], total_waste=0,
                        utilization=0, execution_time=0.0, algorithm="x",
                        truck_assignments={0: "T1"})
    cift = CuttingPlan3D(bins=[[_y("a")], [_y("b")]], total_waste=0,
                         utilization=0, execution_time=0.0, algorithm="x",
                         truck_assignments={0: "T1", 1: "T2"})
    assert _plan_skoru(tek, [t1, t2], bilgi) > _plan_skoru(cift, [t1, t2], bilgi)


def test_bos_tohum_sonsuz_kucuk():
    from monte_carlo_3d import _plan_skoru
    assert _plan_skoru(None, [_t()], {}) == float("-inf")
    assert _plan_skoru(_plan([]), [_t()], {}) == float("-inf")


def test_tohumlu_mc_tohumu_gecebiliyor():
    """KABUL: FFD tohumuyla başlayan MC, aramayı boşa harcamamalı.

    Kasten KÖTÜ bir tohum veriyoruz (hepsi tek araca tıkışık değil,
    gereksiz ikinci araç açılmış). MC bunu geçebilmeli.
    """
    import contextlib
    import io

    from monte_carlo_3d import _plan_skoru, monte_carlo_3d_optimization

    t1, t2 = _t("T1"), _t("T2")
    parcalar = [_p(f"p{i}") for i in range(6)]
    bilgi = {p.id: p for p in parcalar}
    kotu_tohum = CuttingPlan3D(
        bins=[[_y("p0")], [_y("p1")]], total_waste=0, utilization=1.0,
        execution_time=0.0, algorithm="kotu",
        truck_assignments={0: "T1", 1: "T2"})

    with contextlib.redirect_stdout(io.StringIO()):
        sonuc = monte_carlo_3d_optimization(
            parcalar, [t1, t2], iterations=25, seed=1,
            initial_solution=kotu_tohum)

    assert _plan_skoru(sonuc, [t1, t2], bilgi) > _plan_skoru(
        kotu_tohum, [t1, t2], bilgi), "MC kötü tohumu bile geçemedi"


# ═════════════════════════════════════════════════════════════════════════════
# A2 — SA başlangıç sıcaklığı amaç ölçeğine uymalı
# ═════════════════════════════════════════════════════════════════════════════

def test_sicaklik_sifirsa_otomatik_kalibrasyon_calisir():
    """initial_temp=0 → Kirkpatrick kalibrasyonu devreye girmeli."""
    import inspect

    import simulated_annealing_3d as sa
    kaynak = inspect.getsource(sa.simulated_annealing_3d_optimization)
    assert "Auto T0" in kaynak
    assert "math.log(0.80)" in kaynak or "log(0.80)" in kaynak


def test_uygulama_varsayilani_otomatik():
    """KABUL: arayüz artık elle 1000 geçmiyor, 0 (otomatik) geçiyor."""
    import inspect

    import app_3d
    kaynak = inspect.getsource(app_3d)
    assert 'kw.get("sa_temp", 0.0)' in kaynak, \
        "SA sıcaklığı hâlâ elle sabit geçiliyor"
    assert 'kw.get("sa_temp",1000.0)' not in kaynak
    assert "sa_temp=1000.0" not in kaynak


def test_yuksek_sicaklik_her_hamleyi_kabul_eder():
    """Hatanın NEDENİNİ sabitleyen test — ölçek uyumsuzluğu.

    Yeni amaç fonksiyonunda tipik fark ~1; T=1000'de kabul olasılığı
    neredeyse 1, yani tavlama rastgele yürüyüşe döner.
    """
    tipik_fark = 1.0
    assert math.exp(-tipik_fark / 1000.0) > 0.99      # eski varsayılan
    assert math.exp(-tipik_fark / 2.0) < 0.65         # ölçeğe uygun T
