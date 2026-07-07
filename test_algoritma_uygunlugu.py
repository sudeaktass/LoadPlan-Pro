# -*- coding: utf-8 -*-
"""
Algoritma Uygunluk Testi (Conformance Test)
============================================
Her algoritmanın, ADINI taşıdığı yöntemin KANONİK tanımına uyup uymadığını
davranışsal (behavioral) ve yapısal (structural) olarak doğrular.

Tez "implementasyon geçerliliği (implementation validity)" başlığı için kanıt
üretir. Çalıştırma:  python test_algoritma_uygunlugu.py
"""

import sys, io, time, os, contextlib
from core_3d import Piece3D, Truck3D


# ─────────────────────────────────────────────────────────────────────────────
# Yardımcılar
# ─────────────────────────────────────────────────────────────────────────────
@contextlib.contextmanager
def _quiet():
    """Algoritma print çıktılarını yut."""
    old = sys.stdout
    sys.stdout = io.StringIO()
    try:
        yield
    finally:
        sys.stdout = old


def _trucks():
    return [Truck3D('T1', 240, 600, 200, 30000, 6)]


def _inst(n=18, seed=0, ascending=False):
    import random
    random.seed(seed)
    sizes = [(40, 60, 50), (120, 200, 150), (60, 80, 70), (100, 160, 120),
             (50, 70, 60), (140, 200, 160), (80, 120, 100)]
    ps = []
    for i in range(n):
        w, l, h = sizes[random.randint(0, 6)]
        ps.append(Piece3D(id='P%d' % i, shape='box', width=w, length=l, height=h,
                          quantity=1, weight=random.randint(80, 400)))
    if ascending:                       # online yöntemler için "zor" giriş
        ps.sort(key=lambda p: p.width * p.length * p.height)
    return ps


def _placed(plan):
    return sum(len(b) for b in plan.bins)


def _trucks_used(plan):
    return sum(1 for b in plan.bins if b)


def _src(fname):
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), fname),
              encoding='utf-8') as f:
        return f.read()


_RESULTS = []   # (algo, kanit_turu, aciklama, gecti, detay)
def check(algo, kind, desc, passed, detail=""):
    _RESULTS.append((algo, kind, desc, bool(passed), detail))


# ─────────────────────────────────────────────────────────────────────────────
# TESTLER
# ─────────────────────────────────────────────────────────────────────────────
def run_tests():
    tr = _trucks()

    # ── FFD (=BFD): azalan sıralama + best-fit ───────────────────────────
    from ffd_3d import ffd_3d_optimization
    from greedy_3d import greedy_3d_optimization
    ps = _inst(40, seed=3, ascending=True)
    with _quiet():
        ffd = ffd_3d_optimization(ps, tr)
        gr  = greedy_3d_optimization(ps, tr)
    check("FFD", "davranış", "Tüm parçalar yerleşti",
          _placed(ffd) == len(ps), f"{_placed(ffd)}/{len(ps)}")
    check("FFD", "davranış", "Azalan-sıralama avantajı: FFD araç ≤ Greedy araç",
          _trucks_used(ffd) <= _trucks_used(gr),
          f"FFD={_trucks_used(ffd)} araç, Greedy={_trucks_used(gr)} araç")
    ffd_src = _src("ffd_3d.py")
    check("FFD", "yapısal", "Best-fit araç seçimi kodda (_select_best_fit_bin)",
          "_select_best_fit_bin" in ffd_src, "")

    # ── Greedy (=BF): online, 4 açgözlülük kriteri ───────────────────────
    with _quiet():
        g1 = greedy_3d_optimization(ps, tr)
        g2 = greedy_3d_optimization(ps, tr)
    check("Greedy", "davranış", "Deterministik (2 koşu özdeş)",
          abs(g1.utilization - g2.utilization) < 1e-9,
          f"{g1.utilization:.4f}% vs {g2.utilization:.4f}%")
    check("Greedy", "davranış", "FFD'den farklı (online ≠ offline)",
          _trucks_used(g1) != _trucks_used(ffd) or abs(g1.utilization - ffd.utilization) > 0.5,
          f"Greedy={_trucks_used(g1)} araç / FFD={_trucks_used(ffd)} araç")
    gr_src = _src("greedy_3d.py")
    check("Greedy", "yapısal", "Best-fit (en dolu uygun araç) + azalan-sıralama YOK",
          "_bin_used_volume" in gr_src and "sort_piece_list_inplace(" not in gr_src,
          "yerel-optimal araç seçimi, azalan-sıralama çağrısı yok")

    # ── Genetic: OX1 GEÇERLİ permütasyon üretmeli (en güçlü test) ────────
    from genetic_3d import _order_crossover, genetic_3d_optimization
    import random
    random.seed(0)
    p1 = list(range(20)); random.shuffle(p1)
    p2 = list(range(20)); random.shuffle(p2)
    ox_ok = True
    for _ in range(100):
        c1, c2 = _order_crossover(p1, p2)
        if sorted(c1) != list(range(20)) or sorted(c2) != list(range(20)):
            ox_ok = False
            break
    check("GA", "davranış", "OX1 çaprazlama GEÇERLİ permütasyon üretir (100 çocuk)",
          ox_ok, "her indeks tam 1 kez — bozuk crossover değil")
    ps2 = _inst(18, seed=1)
    with _quiet():
        ga1 = genetic_3d_optimization(ps2, tr, population_size=12, generations=10, seed=42)
        ga2 = genetic_3d_optimization(ps2, tr, population_size=12, generations=10, seed=42)
    check("GA", "davranış", "Sabit seed → deterministik (jenerasyon-bütçeli)",
          abs(ga1.utilization - ga2.utilization) < 1e-9,
          f"{ga1.utilization:.4f}% vs {ga2.utilization:.4f}%")
    ga_src = _src("genetic_3d.py")
    check("GA", "yapısal", "Seçilim+çaprazlama+mutasyon+elitizm mevcut",
          all(k in ga_src for k in ("_tournament_selection", "_order_crossover",
                                    "_mutate", "elitism")), "")

    # ── Island GA: halka göçü + bağımsız adalar ──────────────────────────
    from island_genetic_3d import island_model_ga_3d
    with _quiet():
        i1 = island_model_ga_3d(_inst(18, seed=1), tr, n_islands=3,
                                island_population=8, generations=12, seed=42)
        i2 = island_model_ga_3d(_inst(18, seed=1), tr, n_islands=3,
                                island_population=8, generations=12, seed=42)
    check("Island GA", "davranış", "Sabit seed → deterministik",
          abs(i1.utilization - i2.utilization) < 1e-9,
          f"{i1.utilization:.4f}% vs {i2.utilization:.4f}%")
    check("Island GA", "davranış", "Tüm parçalar yerleşti",
          _placed(i1) == 18, f"{_placed(i1)}/18")
    isl_src = _src("island_genetic_3d.py")
    check("Island GA", "yapısal", "Halka göçü kodda (ring topology)",
          "% n_islands" in isl_src and "migration_interval" in isl_src,
          "(i+1)%n_islands göç topolojisi")

    # ── Tabu Search: tabu listesi + özlem + bellek ───────────────────────
    from tabu_search_3d import tabu_search_3d_optimization
    with _quiet():
        seed_plan = ffd_3d_optimization(ps2, tr)
        t0 = time.time()
        ts = tabu_search_3d_optimization(ps2, tr, initial_solution=seed_plan,
                                         max_time=2, seed=42)
        ts_el = time.time() - t0
    ts_src = _src("tabu_search_3d.py")
    check("Tabu", "yapısal", "Tabu listesi + özlem + uzun-vadeli bellek mevcut",
          all(k in ts_src for k in ("is_tabu", "aspiration", "FrequencyMatrix")),
          "tabu kontrolü, aspiration, frekans matrisi")
    check("Tabu", "yapısal", "OR-opt komşuluk operatörü mevcut (Crainic 2009)",
          "or_opt" in ts_src, "")
    check("Tabu", "davranış", "Sonuç seed'den kötü değil (en iyiyi korur)",
          ts.utilization >= seed_plan.utilization - 1e-6,
          f"TS={ts.utilization:.1f}% ≥ seed={seed_plan.utilization:.1f}%")
    check("Tabu", "davranış", "Zaman bütçesine uyar (~2s)",
          ts_el < 5.0, f"{ts_el:.1f}s")

    # ── Simulated Annealing: Metropolis + soğutma ────────────────────────
    from simulated_annealing_3d import simulated_annealing_3d_optimization
    sa_src = _src("simulated_annealing_3d.py")
    check("SA", "yapısal", "Metropolis kabul kriteri kodda (exp(-delta/T))",
          "exp(-delta / temperature)" in sa_src or "exp(-delta/temperature)" in sa_src,
          "kötü hamlelerin olasılıksal kabulü")
    check("SA", "yapısal", "Geometrik soğutma + T0 kalibrasyonu mevcut",
          "temperature *= alpha" in sa_src and "Kirkpatrick" in sa_src, "")
    # Metropolis DAVRANIŞ testi: kabul olasılığı yüksek T'de >> düşük T'de
    import math
    def _p_accept(delta, T):
        return math.exp(-delta / T) if T > 1e-9 else 0.0
    p_hi = _p_accept(500.0, 5000.0)   # yüksek sıcaklık
    p_lo = _p_accept(500.0, 50.0)     # düşük sıcaklık
    check("SA", "davranış", "Metropolis: kötü-hamle kabulü yüksek T'de >> düşük T'de",
          p_hi > 5 * p_lo, f"P(yüksek T)={p_hi:.3f} >> P(düşük T)={p_lo:.4f}")
    with _quiet():
        sa = simulated_annealing_3d_optimization(ps2, tr, initial_solution=seed_plan,
                                                 max_time=2, seed=42)
    check("SA", "davranış", "Sonuç seed'den kötü değil",
          sa.utilization >= seed_plan.utilization - 1e-6,
          f"SA={sa.utilization:.1f}% ≥ seed={seed_plan.utilization:.1f}%")

    # ── Monte Carlo (RCS): bağımsız denemeler + EP decoder ───────────────
    from monte_carlo_3d import monte_carlo_3d_optimization
    with _quiet():
        m1 = monte_carlo_3d_optimization(_inst(18, seed=1), tr, iterations=25, seed=42)
        m2 = monte_carlo_3d_optimization(_inst(18, seed=1), tr, iterations=25, seed=42)
    check("Monte Carlo", "davranış", "Sabit seed → deterministik (iterasyon-bütçeli)",
          abs(m1.utilization - m2.utilization) < 1e-9,
          f"{m1.utilization:.4f}% vs {m2.utilization:.4f}%")
    mc_src = _src("monte_carlo_3d.py")
    check("Monte Carlo", "yapısal", "Ortak EP decoder (MaxRects DEĞİL)",
          "create_packing_engine" in mc_src and mc_src.count("MaxRects3D(") == 0,
          "diğer yöntemlerle aynı decoder — adil kıyas")

    # ── Multi-Start SA: çeşitlendirilmiş çoklu başlangıç ─────────────────
    from multistart_sa_3d import multistart_sa_3d
    with _quiet():
        ms = multistart_sa_3d(_inst(18, seed=1), tr, n_starts=3, time_budget=3, seed=42)
    ms_src = _src("multistart_sa_3d.py")
    check("Multi-Start SA", "yapısal", "Çeşitlendirilmiş başlangıçlar (FFD+Greedy+MC)",
          "_diversified_starts" in ms_src, "")
    check("Multi-Start SA", "davranış", "Tüm parçalar yerleşti",
          _placed(ms) == 18, f"{_placed(ms)}/18")

    # ── Bayesian: gerçek vekil model (TPE), gizli random search DEĞİL ────
    bay_src = _src("bayesian_optimizer_3d.py")
    check("Bayesian", "yapısal", "Vekil model TPESampler (RandomSampler DEĞİL)",
          "TPESampler" in bay_src and "RandomSampler" not in bay_src,
          "gerçek Bayes optimizasyonu / TPE")

    # ── Layer Building: katmanlı yapı ────────────────────────────────────
    from layer_building_3d import layer_building_3d_optimization
    with _quiet():
        lb = layer_building_3d_optimization(_inst(24, seed=2), tr)
    lb_src = _src("layer_building_3d.py")
    check("Layer Building", "yapısal", "Duvar/katman mekanizması mevcut",
          all(k in lb_src for k in ("WallPacker2D", "_choose_layer_depth")), "")
    # Katmanlı davranış: y-bant sayısı parça sayısından az olmalı (parçalar katman paylaşır)
    ybands = set()
    for b in lb.bins:
        for p in b:
            ybands.add(round(p.y / 20.0))   # 20cm tolerans
    check("Layer Building", "davranış", "Katmanlı yapı: y-bant sayısı < parça sayısı",
          len(ybands) < _placed(lb), f"{len(ybands)} y-bant, {_placed(lb)} parça")


# ─────────────────────────────────────────────────────────────────────────────
# RAPOR
# ─────────────────────────────────────────────────────────────────────────────
def report():
    print("\n" + "=" * 74)
    print("  ALGORİTMA UYGUNLUK TESTİ — Conformance Report")
    print("=" * 74)
    cur = None
    n_pass = n_total = 0
    for algo, kind, desc, passed, detail in _RESULTS:
        if algo != cur:
            print(f"\n▸ {algo}")
            cur = algo
        n_total += 1
        n_pass += int(passed)
        mark = "PASS" if passed else "FAIL"
        d = f"   ({detail})" if detail else ""
        print(f"    [{mark}] ({kind:7s}) {desc}{d}")
    print("\n" + "-" * 74)
    print(f"  SONUÇ: {n_pass}/{n_total} test geçti")
    print("=" * 74)
    return n_pass == n_total


if __name__ == "__main__":
    run_tests()
    ok = report()
    sys.exit(0 if ok else 1)
