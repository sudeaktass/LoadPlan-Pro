# -*- coding: utf-8 -*-
"""
3D Bin Packing — Algoritma Karşılaştırma Modülü

Tüm algoritmaları birleştirir ve 3 modda sunar:
  • Hızlı Mod    → Greedy (EP)
  • Standart Mod  → FFD (EP) + Layer Building + Tabu Search
  • Gelişmiş Mod  → Tüm algoritmalar + Monte Carlo + GA

Akademik Dayanaklar:
  Greedy/FFD     : Lodi vd. (2002), Crainic vd. (2008)
  Layer Building : George & Robinson (1980), Pisinger (2002)
  Tabu Search    : Lodi vd. (2004), Crainic vd. (2009)
  Sim. Annealing : Mack vd. (2004)
"""

from typing import List, Dict, Optional
from dataclasses import dataclass

from core_3d import Piece3D, Truck3D, CuttingPlan3D


@dataclass
class ComparisonResult:
    """Algoritma karşılaştırma sonucu"""
    results: Dict[str, CuttingPlan3D]
    best_algorithm: str
    best_utilization: float
    summary: str


def run_quick_mode(
    pieces: List[Piece3D],
    trucks: List[Truck3D],
    engine: str = 'EP'
) -> CuttingPlan3D:
    """
    Hızlı Mod — Greedy (EP)
    Küçük/acil yükler için, < 1 saniye
    """
    from greedy_3d import greedy_3d_optimization
    return greedy_3d_optimization(pieces, trucks, engine=engine)


def run_standard_mode(
    pieces: List[Piece3D],
    trucks: List[Truck3D],
    engine: str = 'EP',
    ts_time: float = 30.0,
    delivery_order: Optional[List[str]] = None
) -> ComparisonResult:
    """
    Standart Mod — FFD + Layer Building + Tabu Search
    Günlük operasyonlar için, 30–60 saniye
    """
    from ffd_3d import ffd_3d_optimization
    from layer_building_3d import layer_building_3d_optimization
    from tabu_search_3d import tabu_search_3d_optimization

    results = {}

    # 1. FFD (EP) — hızlı başlangıç
    print("\n" + "=" * 60)
    print("1️⃣  FFD (Extreme Points)")
    print("=" * 60)
    ffd_result = ffd_3d_optimization(pieces, trucks, engine=engine)
    results['FFD (EP)'] = ffd_result

    # 2. Layer Building — operatör dostu
    print("\n" + "=" * 60)
    print("2️⃣  Layer Building")
    print("=" * 60)
    lb_result = layer_building_3d_optimization(
        pieces, trucks,
        layer_strategy='adaptive',
        delivery_order=delivery_order
    )
    results['Layer Building'] = lb_result

    # 3. Tabu Search — FFD çözümünü iyileştir
    print("\n" + "=" * 60)
    print("3️⃣  Tabu Search (FFD üzerine iyileştirme)")
    print("=" * 60)
    ts_result = tabu_search_3d_optimization(
        pieces, trucks,
        initial_solution=ffd_result,
        max_time=ts_time,
        engine=engine
    )
    results['Tabu Search'] = ts_result

    # En iyi sonucu bul
    best_algo = max(results.keys(), key=lambda k: results[k].utilization)
    best_util = results[best_algo].utilization

    summary = _build_summary(results)

    return ComparisonResult(
        results=results,
        best_algorithm=best_algo,
        best_utilization=best_util,
        summary=summary
    )


# ============================================================================
# PARALEL ÇALIŞMA İÇİN YARDIMCI FONKSİYONLAR  [HATA-9]
# ============================================================================
# NOT: multiprocessing.Pool için worker fonksiyonları modül düzeyinde
# tanımlanmalıdır (lambda veya iç fonksiyon pickle edilemez).

def _run_layer_building(args):
    """Paralel worker — Layer Building."""
    pieces, trucks, delivery_order = args
    try:
        from layer_building_3d import layer_building_3d_optimization
        result = layer_building_3d_optimization(
            pieces, trucks,
            layer_strategy="adaptive",
            delivery_order=delivery_order
        )
        print(f"  ✅ Layer Building tamamlandı: %{result.utilization:.1f}")
        return "Layer Building", result
    except Exception as e:
        print(f"  ⚠️ Layer Building hatası: {e}")
        return "Layer Building", None


def _run_tabu_search(args):
    """Paralel worker — Tabu Search."""
    pieces, trucks, ffd_result, ts_time, engine = args
    try:
        from tabu_search_3d import tabu_search_3d_optimization
        result = tabu_search_3d_optimization(
            pieces, trucks,
            initial_solution=ffd_result,
            max_time=ts_time,
            engine=engine
        )
        print(f"  ✅ Tabu Search tamamlandı: %{result.utilization:.1f}")
        return "Tabu Search", result
    except Exception as e:
        print(f"  ⚠️ Tabu Search hatası: {e}")
        return "Tabu Search", None


def _run_sa(args):
    """Paralel worker — Simulated Annealing."""
    pieces, trucks, ffd_result, sa_time, engine = args
    try:
        from simulated_annealing_3d import simulated_annealing_3d_optimization
        result = simulated_annealing_3d_optimization(
            pieces, trucks,
            initial_solution=ffd_result,
            max_time=sa_time,
            engine=engine
        )
        print(f"  ✅ SA tamamlandı: %{result.utilization:.1f}")
        return "SA (Hybrid)", result
    except Exception as e:
        print(f"  ⚠️ SA hatası: {e}")
        return "SA (Hybrid)", None


def _run_monte_carlo(args):
    """Paralel worker — Monte Carlo."""
    pieces, trucks = args
    try:
        from monte_carlo_3d import monte_carlo_3d_optimization
        result = monte_carlo_3d_optimization(pieces, trucks)
        print(f"  ✅ Monte Carlo tamamlandı: %{result.utilization:.1f}")
        return "Monte Carlo", result
    except Exception as e:
        print(f"  ⚠️ Monte Carlo hatası: {e}")
        return "Monte Carlo", None


def _run_genetic(args):
    """Paralel worker — Genetic Algorithm."""
    pieces, trucks, ffd_result = args
    try:
        from genetic_3d import genetic_3d_optimization
        result = genetic_3d_optimization(
            pieces, trucks,
            initial_solution=ffd_result
        )
        print(f"  ✅ GA tamamlandı: %{result.utilization:.1f}")
        return "Genetic", result
    except Exception as e:
        print(f"  ⚠️ GA hatası: {e}")
        return "Genetic", None


def _run_island_ga(args):
    """
    Paralel worker — Island Genetic Algorithm.
    FIX-O3: Büyük problemlerde standart GA'ya göre daha iyi çeşitlilik.
    island_genetic_3d.py mevcut; comparison_3d'ye entegre edilmiyordu.
    """
    pieces, trucks, ffd_result = args
    try:
        from island_genetic_3d import island_model_ga_3d
        total_pieces = sum(p.quantity for p in pieces)
        # Küçük problemlerde Island GA overhead'i yüksek — atla
        if total_pieces < 12:
            return "Island GA", None
        result = island_model_ga_3d(
            pieces, trucks,
            n_islands=4,
            island_population=20,
            generations=60,
            initial_solution=ffd_result,
        )
        print(f"  ✅ Island GA tamamlandı: %{result.utilization:.1f}")
        return "Island GA", result
    except Exception as e:
        print(f"  ⚠️ Island GA hatası: {e}")
        return "Island GA", None


def run_advanced_mode(
    pieces: List[Piece3D],
    trucks: List[Truck3D],
    engine: str = "EP",
    ts_time: float = 30.0,
    sa_time: float = 30.0,
    delivery_order: Optional[List[str]] = None,
    parallel: bool = True,
    max_workers: int = 4,
) -> ComparisonResult:
    """
    Gelişmiş Mod — Tüm algoritmalar (paralel çalışma desteğiyle).

    DÜZELTME (HATA-9 — Paralel Çalışma):
    Orijinal kod algoritmaları sıralı çalıştırıyordu. 4 algoritmanın
    her biri 30-60 saniye → toplam 2-4 dakika.

    YENİ YAKLAŞIM:
      1. FFD: Seed olarak kullanıldığı için senkron (< 1s).
      2. Layer Building, Tabu Search, SA, Monte Carlo, GA: paralel.

    Paralel çalışma önce ProcessPoolExecutor, başarısız olursa
    ThreadPoolExecutor kullanır (Streamlit uyumluluğu için).
    Tek çekirdekte çalıştırırken parallel=False kullanın.

    Args:
        parallel:    False → sıralı çalışma (eski davranış)
        max_workers: Paralel iş parçacığı sayısı
    """
    import concurrent.futures
    import time as _time

    from ffd_3d import ffd_3d_optimization

    results: Dict[str, CuttingPlan3D] = {}

    # ── Adım 1: FFD (hızlı seed — her zaman senkron) ─────────────────
    print("\n" + "=" * 60)
    print("1️⃣  FFD (EP) — seed")
    print("=" * 60)
    ffd = ffd_3d_optimization(pieces, trucks, engine=engine)
    results["FFD (EP)"] = ffd
    print(f"  FFD: %{ffd.utilization:.1f}, {ffd.execution_time:.2f}s")

    # ── Adım 2: Kalan algoritmalar (paralel veya sıralı) ─────────────
    tasks = [
        (_run_layer_building,  (pieces, trucks, delivery_order)),
        (_run_tabu_search,     (pieces, trucks, ffd, ts_time, engine)),
        (_run_sa,              (pieces, trucks, ffd, sa_time, engine)),
        (_run_monte_carlo,     (pieces, trucks)),
        (_run_genetic,         (pieces, trucks, ffd)),
        (_run_island_ga,       (pieces, trucks, ffd)),   # FIX-O3: Island GA eklendi
    ]

    if parallel:
        print(f"\n🔀 Paralel mod — {len(tasks)} algoritma eş zamanlı başlatıldı")
        t0 = _time.time()

        # ProcessPoolExecutor önce dene (gerçek paralelizm)
        # Streamlit / fork problemi varsa ThreadPoolExecutor'a geç
        executor_cls = concurrent.futures.ThreadPoolExecutor  # güvenli varsayılan
        try:
            import multiprocessing
            if multiprocessing.get_start_method(allow_none=True) != "spawn":
                # fork-safe ortamda ProcessPoolExecutor kullan
                executor_cls = concurrent.futures.ProcessPoolExecutor
        except Exception:
            pass

        futures = {}
        try:
            with executor_cls(max_workers=min(max_workers, len(tasks))) as executor:
                for fn, args in tasks:
                    future = executor.submit(fn, args)
                    futures[future] = fn.__name__

                for future in concurrent.futures.as_completed(futures):
                    try:
                        name, plan = future.result(timeout=max(ts_time, sa_time) + 30)
                        if plan is not None:
                            results[name] = plan
                    except Exception as e:
                        print(f"  ⚠️ {futures[future]} sonuç alınamadı: {e}")

        except Exception as e:
            print(f"  ⚠️ Paralel çalışma hatası ({e}), sıralı moda geçiliyor...")
            parallel = False   # fallback

        if parallel:
            elapsed = _time.time() - t0
            print(f"  ⏱️ Paralel tamamlandı: {elapsed:.1f}s")

    if not parallel:
        # ── Sıralı mod (eski davranış, fallback) ─────────────────────
        for fn, args in tasks:
            name, plan = fn(args)
            if plan is not None:
                results[name] = plan

    # ── Sonuç ─────────────────────────────────────────────────────────
    if not results:
        results["FFD (EP)"] = ffd   # en azından FFD var

    best_algo = max(results.keys(), key=lambda k: results[k].utilization)
    best_util = results[best_algo].utilization
    summary   = _build_summary(results)

    return ComparisonResult(
        results=results,
        best_algorithm=best_algo,
        best_utilization=best_util,
        summary=summary
    )


def _build_summary(results: Dict[str, CuttingPlan3D]) -> str:
    """Karşılaştırma özet tablosu"""
    lines = [
        "\n" + "=" * 70,
        "📊 ALGORİTMA KARŞILAŞTIRMA SONUÇLARI",
        "=" * 70,
        f"{'Algoritma':<25} {'Bin':>5} {'Doluluk':>10} {'Süre':>10} {'Atık':>12}",
        "-" * 70,
    ]

    for name, plan in sorted(results.items(),
                              key=lambda x: -x[1].utilization):
        n_bins = len([b for b in plan.bins if b])
        lines.append(
            f"{name:<25} {n_bins:>5} "
            f"{plan.utilization:>9.1f}% "
            f"{plan.execution_time:>9.2f}s "
            f"{plan.total_waste:>11.0f}"
        )

    # En iyi
    best = max(results.items(), key=lambda x: x[1].utilization)
    lines.append("-" * 70)
    lines.append(f"🏆 En İyi: {best[0]} (%{best[1].utilization:.1f})")
    lines.append("=" * 70)

    return "\n".join(lines)
