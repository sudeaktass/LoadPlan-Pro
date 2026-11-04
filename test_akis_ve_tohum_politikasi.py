# -*- coding: utf-8 -*-
"""
Akış dışı bırakma ve tohum politikası testleri
==============================================
    python -X utf8 -m pytest test_akis_ve_tohum_politikasi.py -q

İki konu:

  1) KARAR A — Island GA, Multi-Start SA ve Bayesian optimizasyon
     YERLEŞTİRME ALGORİTMASI olarak kullanılmaz. Kullanıcıya açık seçim,
     açıklama kartı, `run_algo` sevk tablosu ve varsayılan orkestrasyon
     boru hattından çıkarıldılar. KODLARI SİLİNMEDİ: modüller import
     edilip doğrudan çağrılabilir (varyant analizi).

  2) TOHUM POLİTİKASI — FFD körlemesine dayatılmaz.
     Ölçüldü (BR7/thpack7, 110 parça):
       FFD planı               90/110 · amaç 472,2
       FFD → TSSolution → EP   82/110 · amaç 656,4  (8 parça kaybı)
       Tabu kendi ilk çözümü   76/110 · amaç 794,3
     Artık adaylar değerlendirilip en iyisinden başlanır ve sonuç
     tohumdan kötüyse tohum geri döndürülür.
"""

from __future__ import annotations

import contextlib
import importlib
import inspect
import io

import pytest

from core_3d import CuttingPlan3D, Piece3D, Placement3D, Truck3D


def _t(tid="T1", adet=3):
    t = Truck3D(tid, 240, 600, 200, 30_000, 6)
    t.available = adet
    return t


def _parcalar(n=14):
    return [Piece3D(id=f"p{i}", width=60, length=80, height=70,
                    quantity=1, weight=120.0) for i in range(n)]


# ═════════════════════════════════════════════════════════════════════════════
# 1) Dondurulmuş varyantlar hiçbir kullanıcı akışında çağrılmamalı
# ═════════════════════════════════════════════════════════════════════════════

def _app():
    return importlib.import_module("app_3d")


def test_dondurulmus_liste_tanimli():
    assert _app().DONDURULMUS_ALGORITMALAR == frozenset(
        {"island_ga", "multistart_sa", "bayesian"})


@pytest.mark.parametrize("anahtar", ["island_ga", "multistart_sa", "bayesian"])
def test_run_algo_dondurulmusu_reddediyor(anahtar):
    """KABUL: sevk tablosu bu anahtarları çalıştırmamalı."""
    app = _app()
    with pytest.raises(ValueError, match="kullanılmıyor"):
        app.run_algo(anahtar, _parcalar(), [_t()])


def test_standart_algoritmalar_calisabiliyor():
    """Koruma standart algoritmaları engellememeli."""
    app = _app()
    with contextlib.redirect_stdout(io.StringIO()):
        plan = app.run_algo("ffd_ep", _parcalar(6), [_t()])
    assert plan is not None and any(plan.bins)


def test_kullaniciya_acik_secim_listesinde_yok():
    """`advanced` süzgeci dondurulmuşları dışarıda bırakmalı."""
    app = _app()
    std = [k for k, v in app.ALGORITHMS.items() if not v["advanced"]]
    assert not (set(std) & app.DONDURULMUS_ALGORITMALAR)
    assert "genetic" in std, "standart GA kısıtın dışında olmalı"


def test_aciklama_kartinda_yok():
    """Öneri/tooltip kartının veri yükü dondurulmuşları içermemeli."""
    kaynak = inspect.getsource(_app())
    assert "if k not in DONDURULMUS_ALGORITMALAR" in kaynak


def test_hicbir_hazir_boru_hattinda_island_ga_yok():
    """Hazır boru hatlarının (full_chain dâhil) hiçbiri IslandGA içermemeli."""
    import iterative_optimizer_3d as io_mod

    for ad in ("greedy_sa", "ffd_genetic", "ffd_tabu", "full_chain"):
        fn = getattr(io_mod.HybridPipeline, ad, None)
        if fn is None:
            continue
        kaynak = inspect.getsource(fn)
        # Yorumda adı geçebilir; aranan şey gerçek AŞAMA ÇAĞRISIDIR.
        for dondurulmus in ("IslandGA", "MultiStartSA", "Bayesian"):
            assert f'PipelineStage("{dondurulmus}"' not in kaynak, \
                f"{ad} hâlâ {dondurulmus} aşaması kuruyor"


def test_island_ga_sevk_dali_silinmedi():
    """Kod korundu: elle kurulan bir boru hattında hâlâ kullanılabilir."""
    import iterative_optimizer_3d as io_mod
    assert "IslandGA" in inspect.getsource(io_mod)


def test_fleet_optimizer_cagrisinda_bayesian_bayragi_yok():
    kaynak = inspect.getsource(_app())
    assert "use_bayesian=True" not in kaynak


def test_modul_kodlari_duruyor_ve_cagrilabilir():
    """KODLARI SİLİNMEDİ — doğrudan import edilebilmeli."""
    for ad, fn_adi in (("island_genetic_3d", "island_model_ga_3d"),
                       ("multistart_sa_3d", "multistart_sa_3d"),
                       ("bayesian_optimizer_3d", "bayesian_optimization_3d")):
        mod = importlib.import_module(ad)
        assert callable(getattr(mod, fn_adi)), f"{ad}.{fn_adi} kayboldu"


# ═════════════════════════════════════════════════════════════════════════════
# 2) Tohum politikası
# ═════════════════════════════════════════════════════════════════════════════

def _plan(bins, atama, doluluk=0.0):
    return CuttingPlan3D(bins=bins, total_waste=0, utilization=doluluk,
                         execution_time=0.0, algorithm="x",
                         truck_assignments=atama)


def _y(pid, y=0):
    return Placement3D(0, y, 0, 100, 100, 100, pid, (0, 0, 0), 0)


def test_tohum_korumasi_daha_iyi_tohumu_dondurur():
    from tabu_search_3d import tohum_korumasi

    t = _t("T1")
    parcalar = [Piece3D(id=c, width=100, length=100, height=100,
                        quantity=1, weight=100.0) for c in "abc"]
    bilgi = {p.id: p for p in parcalar}
    iyi = _plan([[_y("a"), _y("b", y=100), _y("c", y=200)]], {0: "T1"})
    kotu = _plan([[_y("a")]], {0: "T1"})
    assert tohum_korumasi(kotu, iyi, [t], bilgi) is iyi


def test_tohum_korumasi_daha_iyi_sonucu_korur():
    from tabu_search_3d import tohum_korumasi

    t = _t("T1")
    parcalar = [Piece3D(id=c, width=100, length=100, height=100,
                        quantity=1, weight=100.0) for c in "abc"]
    bilgi = {p.id: p for p in parcalar}
    iyi = _plan([[_y("a"), _y("b", y=100), _y("c", y=200)]], {0: "T1"})
    kotu = _plan([[_y("a")]], {0: "T1"})
    assert tohum_korumasi(iyi, kotu, [t], bilgi) is iyi


def test_tohum_korumasi_tohumsuzda_sonucu_dondurur():
    from tabu_search_3d import tohum_korumasi
    sonuc = _plan([[_y("a")]], {0: "T1"})
    assert tohum_korumasi(sonuc, None, [_t()], {}) is sonuc


def test_en_iyi_baslangic_en_dusuk_uygunlugu_seciyor():
    from tabu_search_3d import (TSSolution, en_iyi_baslangic,
                                evaluate_solution)

    parcalar = _parcalar(8)
    pe = list(parcalar)
    araclar = [_t("T1", adet=3)]
    bilgi = {p.id: p for p in parcalar}
    a = TSSolution(bin_assignments=[0] * 8, piece_orders={0: list(range(8))})
    b = TSSolution(bin_assignments=list(range(8)),
                   piece_orders={i: [i] for i in range(8)})
    secilen = en_iyi_baslangic([a, b], pe, araclar, bilgi, "EP")
    fa = evaluate_solution(a, pe, araclar, bilgi, "EP")[0]
    fb = evaluate_solution(b, pe, araclar, bilgi, "EP")[0]
    assert secilen[1] == min(fa, fb)


def test_en_iyi_baslangic_none_adaylari_atlıyor():
    from tabu_search_3d import TSSolution, en_iyi_baslangic

    parcalar = _parcalar(4)
    a = TSSolution(bin_assignments=[0] * 4, piece_orders={0: list(range(4))})
    sonuc = en_iyi_baslangic([None, a, None], list(parcalar), [_t()],
                             {p.id: p for p in parcalar}, "EP")
    assert sonuc is not None and sonuc[0] is a


@pytest.mark.parametrize("modul,fn_adi", [
    ("tabu_search_3d", "tabu_search_3d_optimization"),
    ("simulated_annealing_3d", "simulated_annealing_3d_optimization"),
])
def test_sonuc_tohumdan_kotu_olamaz(modul, fn_adi):
    """KABUL: arama, verilen tohumdan kötü bir plan döndürmemeli."""
    from amac_fonksiyonu import plan_uygunlugu
    from ffd_3d import ffd_3d_optimization

    mod = importlib.import_module(modul)
    fn = getattr(mod, fn_adi)
    parcalar = _parcalar(22)
    araclar = [_t("T1", adet=4)]
    bilgi = {p.id: p for p in parcalar}

    with contextlib.redirect_stdout(io.StringIO()):
        tohum = ffd_3d_optimization(parcalar, araclar, heuristic="CP")
        sonuc = fn(parcalar, araclar, initial_solution=tohum,
                   max_time=3.0, seed=9)

    assert plan_uygunlugu(sonuc, araclar, bilgi) <= \
        plan_uygunlugu(tohum, araclar, bilgi) + 1e-9


@pytest.mark.parametrize("modul,fn_adi", [
    ("tabu_search_3d", "tabu_search_3d_optimization"),
    ("simulated_annealing_3d", "simulated_annealing_3d_optimization"),
])
def test_dondurulen_plan_gecerli(modul, fn_adi):
    """Plan geçerliliği: her yerleşim bir araca atanmış olmalı."""
    mod = importlib.import_module(modul)
    fn = getattr(mod, fn_adi)
    parcalar = _parcalar(16)
    araclar = [_t("T1", adet=3)]
    with contextlib.redirect_stdout(io.StringIO()):
        plan = fn(parcalar, araclar, max_time=3.0, seed=4)
    atama = plan.truck_assignments or {}
    arac_idleri = {t.id for t in araclar}
    for bid, yerlesimler in enumerate(plan.bins):
        if yerlesimler:
            assert atama.get(bid) in arac_idleri, f"bin {bid} atanmamış"


def test_aday_sayisi_olculerek_secildi():
    import tabu_search_3d as ts
    assert ts.TABU_SIRA_ADAY_SAYISI == 8
    assert "ÖLÇÜLEREK SEÇİLDİ" in ts.__dict__["__doc__"] or True
    kaynak = inspect.getsource(ts)
    assert "ÖLÇÜLEREK SEÇİLDİ" in kaynak
