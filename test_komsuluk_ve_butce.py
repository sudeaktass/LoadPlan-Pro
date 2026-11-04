# -*- coding: utf-8 -*-
"""
Komşuluk ve süre bütçesi testleri
=================================
    python -X utf8 -m pytest test_komsuluk_ve_butce.py -q

22 Ekim 2026'daki ölçümlü incelemede bulunan kök neden:

  Tabu'nun üç operatörü (transfer/swap/or-opt) ve SA'nın üç operatörü
  (relocate/swap/cycle_shift) YALNIZ BİNLER ARASI çalışıyordu. Tek
  konteynerli örneklerde (kıyas kümesinin tamamı) hedef bin listesi boş
  kalıyor ve:
    * Tabu  : komşuluk tamamen boş → 78.343 yineleme, 0 komşu, 0 iyileşme
    * SA    : relocate DEĞİŞTİRİLMEMİŞ kopya döndürüyor → tüm deltalar 0
              → Kirkpatrick kalibrasyonu yedek değere düşüyor (T0=1000)
  İkisi de hiçbir arama yapmıyordu; bu yüzden aynı çözümü üretiyorlardı.

Çözüm: bin-İÇİ yükleme sırası operatörü. `evaluate_solution` her bin'in
`piece_orders` dizisini yerleştirme sırası olarak kullanır.
Dayanak: Eley (2002), EJOR 141:393-409 — açgözlü çözümü iyileştirmek
için "farklı ürün yükleme sıralarını" araştıran ağaç araması.

SA ile Tabu'nun ayrımı KORUNDU: ikisi de aynı hamle türlerini kullanır,
ayrım arama denetimindedir (Metropolis ↔ tabu belleği + aspirasyon).
"""

from __future__ import annotations

import contextlib
import inspect
import io
import time

from core_3d import Piece3D, Truck3D
from tabu_search_3d import TSSolution, generate_neighbors


def _tek_arac(adet=1):
    t = Truck3D("T1", 240, 600, 200, 30_000, 6)
    t.available = adet
    return [t]


def _parcalar(n=12):
    return [Piece3D(id=f"p{i}", width=60, length=80, height=70,
                    quantity=1, weight=120.0) for i in range(n)]


def _tek_binli_cozum(n=12):
    return TSSolution(bin_assignments=[0] * n,
                      piece_orders={0: list(range(n))})


# ═════════════════════════════════════════════════════════════════════════════
# Tabu — tek binde komşuluk artık BOŞ DEĞİL
# ═════════════════════════════════════════════════════════════════════════════

def test_tek_binde_komsuluk_bos_degil():
    """KABUL: tek konteynerli örnekte Tabu komşu üretebilmeli."""
    komsular = generate_neighbors(
        _tek_binli_cozum(), _parcalar(), tabu_list=[], current_iter=0,
        max_bins=1)
    assert komsular, "tek binde komşuluk hâlâ boş"


def test_tek_binde_uretilen_komsular_gercekten_farkli():
    """Üretilen komşu, mevcut çözümden FARKLI bir sıra taşımalı."""
    cozum = _tek_binli_cozum()
    komsular = generate_neighbors(cozum, _parcalar(), [], 0, max_bins=1)
    farkli = [k for k, _, _ in komsular
              if k.piece_orders[0] != cozum.piece_orders[0]]
    assert farkli, "komşular mevcut çözümün aynısı"


def test_sira_operatoru_atamalari_bozmuyor():
    """Bin-içi sıra değişimi parçayı başka bine TAŞIMAZ."""
    cozum = _tek_binli_cozum()
    for yeni, hamle, _ in generate_neighbors(cozum, _parcalar(), [], 0,
                                             max_bins=1):
        assert yeni.bin_assignments == cozum.bin_assignments
        assert hamle.move_type == "reorder"
        assert hamle.from_bin == hamle.to_bin


def test_sira_operatoru_parcalari_kaybetmiyor():
    cozum = _tek_binli_cozum()
    for yeni, _, _ in generate_neighbors(cozum, _parcalar(), [], 0,
                                         max_bins=1):
        assert sorted(yeni.piece_orders[0]) == sorted(cozum.piece_orders[0])


def test_cok_binde_eski_operatorler_korundu():
    """Çok binli örnekte transfer/swap/or-opt hâlâ üretiliyor."""
    cozum = TSSolution(bin_assignments=[0] * 6 + [1] * 6,
                       piece_orders={0: list(range(6)), 1: list(range(6, 12))})
    turler = {h.move_type for _, h, _ in
              generate_neighbors(cozum, _parcalar(), [], 0, max_bins=3)}
    assert {"transfer", "swap"} & turler, f"eski operatörler kayboldu: {turler}"


# ═════════════════════════════════════════════════════════════════════════════
# SA — komşu artık mevcut çözümün aynısı değil
# ═════════════════════════════════════════════════════════════════════════════

def test_sa_tek_binde_degismis_komsu_uretiyor():
    """KABUL: eskiden relocate değiştirilmemiş kopya döndürüyordu."""
    from simulated_annealing_3d import _generate_neighbor

    cozum = _tek_binli_cozum()
    farkli = 0
    for _ in range(30):
        k = _generate_neighbor(cozum, _parcalar(), max_bins=1, operator="relocate")
        if k.piece_orders[0] != cozum.piece_orders[0]:
            farkli += 1
    assert farkli > 0, "SA tek binde hâlâ aynı çözümü döndürüyor"


def test_sa_reorder_operatoru_var():
    from simulated_annealing_3d import _reorder_neighbor

    cozum = _tek_binli_cozum()
    yeni = _reorder_neighbor(cozum)
    assert yeni is not None
    assert yeni.piece_orders[0] != cozum.piece_orders[0]
    assert sorted(yeni.piece_orders[0]) == sorted(cozum.piece_orders[0])


def test_sa_tek_parcada_reorder_none():
    """Sıra değiştirecek ikinci parça yoksa None — patlamamalı."""
    from simulated_annealing_3d import _reorder_neighbor
    assert _reorder_neighbor(
        TSSolution(bin_assignments=[0], piece_orders={0: [0]})) is None


def test_sa_operator_kumesi_reorder_iceriyor():
    import simulated_annealing_3d as sa
    kaynak = inspect.getsource(sa)
    assert "'reorder'" in kaynak
    assert "'relocate', 'swap', 'cycle_shift', 'reorder'" in kaynak


# ═════════════════════════════════════════════════════════════════════════════
# SA ile Tabu'nun AYRIMI korunmalı (yapay fark değil, kanonik fark)
# ═════════════════════════════════════════════════════════════════════════════

def test_sa_metropolis_tabu_bellek_kullaniyor():
    """Ayrım arama denetiminde: Metropolis ↔ tabu belleği + aspirasyon."""
    import simulated_annealing_3d as sa
    import tabu_search_3d as ts

    sa_kaynak = inspect.getsource(sa.simulated_annealing_3d_optimization)
    ts_kaynak = inspect.getsource(ts.tabu_search_3d_optimization)

    assert "math.exp" in sa_kaynak          # Metropolis kabulü
    assert "tabu_list" in ts_kaynak         # kısa süreli bellek
    assert "aspiration" in ts_kaynak.lower()
    assert "freq_matrix" in ts_kaynak       # uzun süreli çeşitlendirme
    assert "tabu_list" not in sa_kaynak     # SA'da bellek YOK


def test_sa_tek_komsu_tabu_aday_listesi():
    """SA tek komşu üretir, Tabu aday listesi — kanonik ayrım."""
    import simulated_annealing_3d as sa
    assert inspect.signature(sa._generate_neighbor).return_annotation \
        is not None
    komsular = generate_neighbors(_tek_binli_cozum(), _parcalar(), [], 0,
                                  max_bins=1)
    assert isinstance(komsular, list) and len(komsular) > 1


# ═════════════════════════════════════════════════════════════════════════════
# SA — sıcaklık kalibrasyonu bütçeli olmalı
# ═════════════════════════════════════════════════════════════════════════════

def test_kalibrasyon_butceli():
    import simulated_annealing_3d as sa
    kaynak = inspect.getsource(sa.simulated_annealing_3d_optimization)
    assert "_kalib_butce" in kaynak
    assert "max_time * 0.20" in kaynak


def test_sa_asil_donguye_ulasiyor():
    """KABUL: kalibrasyon bütçenin tamamını yememeli.

    Ölçüldü: düzeltmeden önce 138 parçalık örnekte 50 kalibrasyon örneği
    4 sn bütçenin tamamını tüketiyor, tavlama döngüsü hiç çalışmıyordu.
    """
    from simulated_annealing_3d import simulated_annealing_3d_optimization

    parcalar = [Piece3D(id=f"p{i}", width=60, length=80, height=70,
                        quantity=1, weight=120.0) for i in range(60)]
    with contextlib.redirect_stdout(io.StringIO()) as cikti:
        simulated_annealing_3d_optimization(
            parcalar, _tek_arac(adet=3), max_time=4.0, seed=3)
    log = cikti.getvalue()
    assert "Auto T0" in log
    assert "iter" in log, "tavlama döngüsü hiç çalışmadı"


def test_sa_butceye_yakin_kaliyor():
    from simulated_annealing_3d import simulated_annealing_3d_optimization

    parcalar = [Piece3D(id=f"p{i}", width=60, length=80, height=70,
                        quantity=1, weight=120.0) for i in range(40)]
    butce = 3.0
    bas = time.time()
    with contextlib.redirect_stdout(io.StringIO()):
        simulated_annealing_3d_optimization(
            parcalar, _tek_arac(adet=3), max_time=butce, seed=5)
    assert time.time() - bas <= butce * 2.0


# ═════════════════════════════════════════════════════════════════════════════
# Deterministik tohum davranışı — değişiklikler bunu bozmamalı
# ═════════════════════════════════════════════════════════════════════════════

def _iz(plan):
    return tuple(sorted((b, pl.piece_id, pl.x, pl.y, pl.z)
                        for b, pls in enumerate(plan.bins) for pl in pls))


def test_tabu_sabit_seed_tekrarlanabilir():
    from tabu_search_3d import tabu_search_3d_optimization

    parcalar = _parcalar(20)
    sonuc = []
    for _ in range(2):
        with contextlib.redirect_stdout(io.StringIO()):
            sonuc.append(_iz(tabu_search_3d_optimization(
                parcalar, _tek_arac(adet=3), max_time=2.0, seed=11)))
    assert sonuc[0] == sonuc[1]


def test_sa_sabit_seed_tekrarlanabilir():
    from simulated_annealing_3d import simulated_annealing_3d_optimization

    parcalar = _parcalar(20)
    sonuc = []
    for _ in range(2):
        with contextlib.redirect_stdout(io.StringIO()):
            sonuc.append(_iz(simulated_annealing_3d_optimization(
                parcalar, _tek_arac(adet=3), max_time=2.0, seed=11)))
    assert sonuc[0] == sonuc[1]


# ═════════════════════════════════════════════════════════════════════════════
# Denetim betiğinin "tohumdan kötü" ölçütü
# ═════════════════════════════════════════════════════════════════════════════

def test_denetim_uyarisi_ortak_amaca_bakiyor():
    """KABUL: uyarı U_G'ye değil, algoritmaların optimize ettiği ölçüye."""
    import os
    yol = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "deney", "scripts", "algoritma_denetimi.py")
    kaynak = open(yol, encoding="utf-8").read()
    assert "_plan_amaci" in kaynak
    assert "plan_uygunlugu" in kaynak
    assert 'if fark < -0.01:\n                isaret = "  ← TOHUMDAN KÖTÜ"' \
        not in kaynak


def test_denetim_plan_amaci_ortak_olcuyle_ayni():
    import os
    import sys
    yol = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "deney", "scripts")
    if yol not in sys.path:
        sys.path.insert(0, yol)
    import importlib
    ad = importlib.import_module("algoritma_denetimi")

    from amac_fonksiyonu import plan_uygunlugu
    from ffd_3d import ffd_3d_optimization

    parcalar = _parcalar(8)
    araclar = _tek_arac(adet=2)
    with contextlib.redirect_stdout(io.StringIO()):
        plan = ffd_3d_optimization(parcalar, araclar)
    assert ad._plan_amaci(plan, parcalar, araclar) == plan_uygunlugu(
        plan, araclar, {p.id: p for p in parcalar})


# ═════════════════════════════════════════════════════════════════════════════
# Ada GA — göç mekanizması zaman bütçesinde de çalışmalı
# ═════════════════════════════════════════════════════════════════════════════

def test_ada_ga_zaman_butcesinde_goc_yapiyor():
    """KABUL: göç, Ada GA'yı standart GA'dan ayıran tek mekanizmadır.

    Ölçüldü: tetikleyici yalnız nesil sayısıydı; 4 sn bütçede ancak 2
    nesil tamamlandığı için `migration_interval=10` ile GÖÇ HİÇ
    OLMUYORDU (0 göç) ve Ada GA fiilen GA'ya çöküyordu.
    """
    from island_genetic_3d import island_genetic_3d_optimization

    sayac = {"n": 0}
    parcalar = [Piece3D(id=f"p{i}", width=60, length=80, height=70,
                        quantity=1, weight=120.0) for i in range(35)]
    with contextlib.redirect_stdout(io.StringIO()):
        island_genetic_3d_optimization(
            parcalar, _tek_arac(adet=3), n_islands=3, island_population=8,
            generations=10 ** 7, max_time=4.0, seed=1001,
            migration_callback=lambda *a: sayac.__setitem__("n", sayac["n"] + 1))
    assert sayac["n"] > 0, "zaman bütçeli koşuda hiç göç olmadı"


def test_ada_ga_butcesiz_kosuda_nesil_tetikleyicisi_korundu():
    """max_time <= 0 ise eski (yalnız nesil) davranış sürmeli."""
    import inspect

    import island_genetic_3d as iga
    kaynak = inspect.getsource(iga.island_genetic_3d_optimization)
    assert "_nesil_tetik" in kaynak and "_sure_tetik" in kaynak
    assert "if max_time > 0 and n_islands > 1:" in kaynak


def test_ada_ga_tek_adada_goc_yok():
    """n_islands == 1 ise göç tetiklenmemeli."""
    from island_genetic_3d import island_genetic_3d_optimization

    sayac = {"n": 0}
    parcalar = [Piece3D(id=f"p{i}", width=60, length=80, height=70,
                        quantity=1, weight=120.0) for i in range(12)]
    with contextlib.redirect_stdout(io.StringIO()):
        island_genetic_3d_optimization(
            parcalar, _tek_arac(adet=2), n_islands=1, island_population=6,
            generations=10 ** 7, max_time=2.0, seed=5,
            migration_callback=lambda *a: sayac.__setitem__("n", sayac["n"] + 1))
    assert sayac["n"] == 0
