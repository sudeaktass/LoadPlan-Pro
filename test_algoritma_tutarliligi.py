# -*- coding: utf-8 -*-
"""
Algoritmalar arası tutarlılık testleri
======================================
    python -X utf8 -m pytest test_algoritma_tutarliligi.py -q

22 Ekim 2026'daki yapısal incelemede bulunan üç tutarsızlık:

  S1) Hazır bir planı puanlama ölçüsü her modülde FARKLIYDI.
      monte_carlo_3d ve multistart_sa_3d `plan.utilization` (yüzde)
      kullanıyordu; arama ise `packing_objective` optimize ediyordu.
      Tek kaynak: `amac_fonksiyonu.plan_uygunlugu`.

  S2) Multi-Start SA aşama sonuçlarını ve nihai planı doluluğa göre
      seçiyordu. Daha çok araç kullanan ama doluluğu yüksek bir plan
      kazanabiliyordu — K1'in birinci ölçütüne aykırı.

  S3) Tabu `range(max_iterations)` ile duruyordu; varsayılan 200 yineleme
      zaman bütçesinden çok önce doluyordu (ölçüldü: 4 sn bütçede 0,1 sn).
      Zaman bütçeli karşılaştırma adil değildi.
"""

from __future__ import annotations

import inspect

from core_3d import CuttingPlan3D, Piece3D, Placement3D, Truck3D


def _t(tid="T1", en=248, boy=1362, yuk=270, kap=25_000):
    return Truck3D(tid, en, boy, yuk, kap, 4)


def _p(pid, kg=100.0):
    return Piece3D(id=pid, width=100, length=100, height=100,
                   quantity=1, weight=kg)


def _y(pid, y=0):
    return Placement3D(0, y, 0, 100, 100, 100, pid, (0, 0, 0), 0)


def _plan(bins, atama, doluluk=0.0, dusen=None):
    return CuttingPlan3D(bins=bins, total_waste=0, utilization=doluluk,
                         execution_time=0.0, algorithm="x",
                         truck_assignments=atama,
                         unfitted_pieces=dusen or [])


# ═════════════════════════════════════════════════════════════════════════════
# S1 — tek resmî ölçü
# ═════════════════════════════════════════════════════════════════════════════

def test_plan_uygunlugu_packing_objective_ile_ayni():
    from amac_fonksiyonu import plan_uygunlugu
    from core_3d import packing_objective

    t = _t()
    parcalar = [_p("a"), _p("b")]
    bilgi = {p.id: p for p in parcalar}
    bins, atama = [[_y("a"), _y("b", y=100)]], {0: "T1"}

    beklenen, _ = packing_objective(bins, atama, [t], bilgi)
    assert plan_uygunlugu(_plan(bins, atama), [t], bilgi) == beklenen


def test_plan_uygunlugu_dusen_parcalari_sayiyor():
    """Yerleşmeyen parça cezalandırılmalı — sayı PLANDAN gelir.

    (22 Ekim 2026'da düzeltildi: önce `unfitted_pieces` alanına
    bakılıyordu; o alanı yalnız bazı algoritmalar doldurduğu için ölçü
    algoritmalar arasında karşılaştırılamıyordu. Bkz. S5 testleri.)
    """
    from amac_fonksiyonu import plan_uygunlugu

    t = _t()
    parcalar = [_p("a"), _p("b")]
    bilgi = {p.id: p for p in parcalar}
    hepsi = plan_uygunlugu(
        _plan([[_y("a"), _y("b", y=100)]], {0: "T1"}), [t], bilgi)
    eksik = plan_uygunlugu(_plan([[_y("a")]], {0: "T1"}), [t], bilgi)
    assert eksik > hepsi


def test_plan_uygunlugu_bos_plan_sonsuz():
    from amac_fonksiyonu import plan_uygunlugu
    assert plan_uygunlugu(None, [_t()], {}) == float("inf")
    assert plan_uygunlugu(_plan([], {}), [_t()], {}) == float("inf")
    assert plan_uygunlugu(_plan([[]], {0: "T1"}), [_t()], {}) == float("inf")


def test_mc_skoru_tek_kaynaktan_geliyor():
    """monte_carlo artık kendi ölçüsünü tutmuyor, işaretini çeviriyor."""
    from amac_fonksiyonu import plan_uygunlugu
    from monte_carlo_3d import _plan_skoru

    t = _t()
    parcalar = [_p("a")]
    bilgi = {p.id: p for p in parcalar}
    plan = _plan([[_y("a")]], {0: "T1"}, doluluk=54.7)
    assert _plan_skoru(plan, [t], bilgi) == -plan_uygunlugu(plan, [t], bilgi)


def test_multistart_artik_doluluga_gore_secmiyor():
    import multistart_sa_3d as ms
    kaynak = inspect.getsource(ms.multistart_sa_3d)
    assert "plan_uygunlugu" in kaynak
    assert "stage_results.append((plan.utilization" not in kaynak
    assert "max(final_plans, key=_plan_rank)" not in kaynak


# ═════════════════════════════════════════════════════════════════════════════
# S2 — az araç, yüksek doluluğu yener
# ═════════════════════════════════════════════════════════════════════════════

def test_az_arac_yuksek_dolulugu_yener():
    """KABUL: seçim ölçüsü K1'e uymalı.

    A: 1 araç, doluluk düşük · B: 2 araç, doluluk yüksek.
    Eski ölçü (doluluk) B'yi seçerdi; ortak ölçü A'yı seçmeli.
    """
    from amac_fonksiyonu import plan_uygunlugu

    buyuk = _t("BUYUK", en=1000, boy=1000, yuk=1000)
    k1 = _t("K1", en=100, boy=100, yuk=550)
    k2 = _t("K2", en=100, boy=100, yuk=550)
    parcalar = [_p("a"), _p("b")]
    bilgi = {p.id: p for p in parcalar}

    tek = _plan([[_y("a"), _y("b", y=100)]], {0: "BUYUK"}, doluluk=0.2)
    cift = _plan([[_y("a")], [_y("b")]], {0: "K1", 1: "K2"}, doluluk=90.0)

    araclar = [buyuk, k1, k2]
    assert plan_uygunlugu(tek, araclar, bilgi) < \
        plan_uygunlugu(cift, araclar, bilgi)
    # Eski ölçü ters karar verirdi — tutarsızlığın kanıtı
    assert cift.utilization > tek.utilization


def test_secim_olcusu_arama_olcusuyle_ayni():
    """Dış seçim ile iç aramanın hedefi aynı fonksiyondan gelmeli."""
    from amac_fonksiyonu import plan_uygunlugu
    from core_3d import packing_objective

    t1, t2 = _t("T1"), _t("T2")
    parcalar = [_p("a"), _p("b")]
    bilgi = {p.id: p for p in parcalar}
    adaylar = [
        _plan([[_y("a"), _y("b", y=100)]], {0: "T1"}),
        _plan([[_y("a")], [_y("b")]], {0: "T1", 1: "T2"}),
    ]
    secilen = min(adaylar, key=lambda p: plan_uygunlugu(p, [t1, t2], bilgi))
    en_iyi_amac = min(
        adaylar,
        key=lambda p: packing_objective(p.bins, p.truck_assignments,
                                        [t1, t2], bilgi)[0])
    assert secilen is en_iyi_amac


# ═════════════════════════════════════════════════════════════════════════════
# S3 — Tabu zaman bütçesini kullanmalı
# ═════════════════════════════════════════════════════════════════════════════

def test_tabu_zaman_butcesi_yineleme_sinirini_asiyor():
    """KABUL: max_time verilince yineleme sayısı sınır olmamalı."""
    import tabu_search_3d as ts
    kaynak = inspect.getsource(ts.tabu_search_3d_optimization)
    assert "yineleme_siniri" in kaynak
    assert "for iteration in range(max_iterations):" not in kaynak


def test_tabu_butcesiz_cagri_eski_davranis():
    """max_time <= 0 ise yineleme sayısı yine sınırdır (geriye uyum)."""
    import tabu_search_3d as ts
    kaynak = inspect.getsource(ts.tabu_search_3d_optimization)
    assert "max_iterations if max_time <= 0" in kaynak


def test_tabu_butceyi_gercekten_kullaniyor():
    """Davranışsal: 3 sn bütçe verilince en az yarısı harcanmalı.

    Eskiden 200 yineleme çok erken doluyor ve Tabu bütçenin ~%3'ünü
    kullanıyordu.
    """
    import contextlib
    import io
    import time

    from tabu_search_3d import tabu_search_3d_optimization

    parcalar = [Piece3D(id=f"p{i}", width=60, length=80, height=70,
                        quantity=1, weight=120.0) for i in range(40)]
    araclar = [_t("T1", 240, 600, 200, 30_000)]
    araclar[0].available = 6

    butce = 3.0
    bas = time.time()
    with contextlib.redirect_stdout(io.StringIO()):
        tabu_search_3d_optimization(parcalar, araclar, max_time=butce, seed=7)
    gecen = time.time() - bas
    assert gecen >= butce * 0.5, (
        f"Tabu {butce} sn bütçenin yalnız {gecen:.2f} sn'sini kullandı")


# ═════════════════════════════════════════════════════════════════════════════
# Ortak giriş/çıkış sözleşmesi — yapısal değişiklikler bunu bozmamalı
# ═════════════════════════════════════════════════════════════════════════════

def test_metasezgisellerin_imzasi_korunuyor():
    """Dış arayüz değişmedi: pieces, trucks, initial_solution, seed."""
    import genetic_3d
    import monte_carlo_3d
    import simulated_annealing_3d
    import tabu_search_3d

    for fn in (tabu_search_3d.tabu_search_3d_optimization,
               simulated_annealing_3d.simulated_annealing_3d_optimization,
               genetic_3d.genetic_3d_optimization,
               monte_carlo_3d.monte_carlo_3d_optimization):
        par = inspect.signature(fn).parameters
        assert "pieces" in par and "trucks" in par
        assert "initial_solution" in par, fn.__name__
        assert "seed" in par, fn.__name__


def test_tabu_max_iterations_hala_kabul_ediliyor():
    import inspect

    from tabu_search_3d import tabu_search_3d_optimization
    assert "max_iterations" in inspect.signature(
        tabu_search_3d_optimization).parameters


# ═════════════════════════════════════════════════════════════════════════════
# S4 — Multi-Start SA zaman bütçesine uymalı
# ═════════════════════════════════════════════════════════════════════════════

def test_baslangic_uretimi_butceli():
    """Başlangıç çözümü üretimi artık süre sınırı kabul ediyor."""
    import multistart_sa_3d as ms
    par = inspect.signature(ms._diversified_starts).parameters
    assert "kalan_sure" in par
    assert par["kalan_sure"].default is None     # geriye uyum


def test_baslangic_uretimi_sure_dolunca_duruyor():
    import multistart_sa_3d as ms

    parcalar = [Piece3D(id=f"p{i}", width=60, length=80, height=70,
                        quantity=1, weight=120.0) for i in range(25)]
    t = _t("T1", 240, 600, 200, 30_000)
    t.available = 5
    import contextlib
    import io as _io
    with contextlib.redirect_stdout(_io.StringIO()):
        hizli = ms._diversified_starts(parcalar, [t], 4, kalan_sure=0.0)
    assert len(hizli) <= 1, "süre sıfırken ek başlangıç üretilmemeli"


def test_multistart_butceyi_asmiyor():
    """KABUL: 6 sn bütçe verilince toplam süre makul kalmalı.

    Ölçüldü: düzeltmeden önce 4 sn bütçede 8,2-17,3 sn sürüyordu.
    """
    import contextlib
    import io as _io
    import time

    from multistart_sa_3d import multistart_sa_3d

    parcalar = [Piece3D(id=f"p{i}", width=60, length=80, height=70,
                        quantity=1, weight=120.0) for i in range(45)]
    t = _t("T1", 240, 600, 200, 30_000)
    t.available = 6

    butce = 6.0
    bas = time.time()
    with contextlib.redirect_stdout(_io.StringIO()):
        plan = multistart_sa_3d(parcalar, [t], n_starts=4, time_budget=butce)
    gecen = time.time() - bas
    assert plan is not None and plan.bins
    assert gecen <= butce * 2.5, (
        f"{butce} sn bütçede {gecen:.1f} sn sürdü")


# ═════════════════════════════════════════════════════════════════════════════
# S5 — yerleşmeyen parça PLANDAN hesaplanmalı, alandan okunmamalı
# ═════════════════════════════════════════════════════════════════════════════

def test_dusen_parca_plandan_hesaplaniyor():
    """KABUL: `unfitted_pieces` alanını yalnız bazı algoritmalar doldurur.

    Ölçüldü (BR7, 110 parça): alana güvenilince 84/110 yerleştiren Tabu,
    90/110 yerleştiren FFD'den İYİ görünüyordu (12,3 < 472,2).
    """
    from amac_fonksiyonu import plan_uygunlugu

    t = _t()
    parcalar = [_p("a"), _p("b"), _p("c")]
    bilgi = {p.id: p for p in parcalar}
    bins, atama = [[_y("a"), _y("b", y=100)]], {0: "T1"}   # c yerleşmedi

    # Alanı dolduran algoritma
    dolduran = _plan(bins, atama, dusen=[parcalar[2]])
    # Alanı doldurmayan algoritma — AYNI yerleşim
    doldurmayan = _plan(bins, atama, dusen=None)

    assert plan_uygunlugu(dolduran, [t], bilgi) == \
        plan_uygunlugu(doldurmayan, [t], bilgi), \
        "alanı doldurmayan algoritma haksız avantaj alıyor"


def test_daha_cok_yerlestiren_plan_daha_iyi():
    from amac_fonksiyonu import plan_uygunlugu

    t = _t()
    parcalar = [_p("a"), _p("b"), _p("c")]
    bilgi = {p.id: p for p in parcalar}
    iki = _plan([[_y("a"), _y("b", y=100)]], {0: "T1"}, dusen=None)
    uc = _plan([[_y("a"), _y("b", y=100), _y("c", y=200)]], {0: "T1"},
               dusen=None)
    assert plan_uygunlugu(uc, [t], bilgi) < plan_uygunlugu(iki, [t], bilgi)


def test_adet_alani_dikkate_aliniyor():
    """quantity > 1 olan parça, adedi kadar sayılmalı."""
    from amac_fonksiyonu import plan_uygunlugu

    t = _t()
    cok = Piece3D(id="a", width=100, length=100, height=100,
                  quantity=3, weight=100.0)
    bilgi = {"a": cok}
    bir_tane = _plan([[_y("a")]], {0: "T1"}, dusen=None)
    uc_tane = _plan([[_y("a"), _y("a", y=100), _y("a", y=200)]],
                    {0: "T1"}, dusen=None)
    assert plan_uygunlugu(uc_tane, [t], bilgi) < \
        plan_uygunlugu(bir_tane, [t], bilgi)
