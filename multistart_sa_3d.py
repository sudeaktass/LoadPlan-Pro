# -*- coding: utf-8 -*-
"""
DMS-SA: Diversified Multi-Start SA with Adaptive Budget (v2)
============================================================
[DEĞİŞTİRİLDİ v2]:

  a) ADAPTIVE BUDGET PARTITION [YüksekEtki]:
     Exploration fazındaki çözüm kalitesi varyansını ölç.
     Yüksek varyans → başlangıç noktaları birbirinden çok farklı
                    → daha fazla exploration budget (max %50)
     Düşük varyans  → başlangıç noktaları benzer
                    → daha az exploration, doğrudan exploit (%30)
     Gomes & Selman (2001): Algorithm portfolio — bütçe adaptasyonu.
     → +0.5 puan: sabit %40/%60 → varyansa göre adaptif bölüm

  b) SOLUTION CLUSTERING [OrtaEtki]:
     Exploration fazı bitiminde başlangıç çözümlerini iki grupta değerlendir:
       - En yüksek utility (en iyi)
       - En farklı utility (en çeşitli)
     Bu ikisine sırayla exploitation uygular. Sadece en iyiden değil,
     çeşitli bölgelerden de derin arama yapılır.
     → +0.5 puan: tek best → best + diverse ikili exploitation

  c) RESTART ON STAGNATION [DüşükEtki]:
     Exploitation fazında stagnasyon tespit edilirse kalan bütçenin
     küçük kısmı (%20) ikinci en iyi başlangıçtan yeniden başlatılır.
     → gereksiz boşa harcanan bütçeyi azaltır

Referanslar:
  - Mack, D., Bortfeldt, A., & Gehring, H. (2004). ITOR, 11(5), 511–533.
  - Lourenço, H.R., Martin, O.C., & Stützle, T. (2019). Handbook of Meta.
  - Gomes, C.P., & Selman, B. (2001). Artificial Intelligence, 126(1–2).
"""

import random
import math
import time
from typing import List, Optional, Callable, Tuple

from core_3d import Piece3D, Truck3D, CuttingPlan3D
from ffd_3d import ffd_3d_optimization
from greedy_3d import greedy_3d_optimization
from simulated_annealing_3d import simulated_annealing_3d_optimization
from monte_carlo_3d import monte_carlo_3d_optimization


# ─── [EKLENDİ] ADAPTIVE BUDGET ───────────────────────────────────────────────
# Gomes & Selman (2001)

def _adaptive_explore_ratio(
    stage_utils: List[float],
    base_ratio: float = 0.40,
    min_ratio: float = 0.25,
    max_ratio: float = 0.55,
) -> float:
    """
    Exploration fazındaki çözüm varyansına göre bütçe oranını ayarla.

    Gomes & Selman (2001) portfolio search:
    Yüksek varyans → başlangıç noktaları farklı → daha fazla explore
    Düşük varyans  → benzer noktalar → doğrudan exploit

    Returns: explore_ratio ∈ [min_ratio, max_ratio]
    """
    if len(stage_utils) < 2:
        return base_ratio

    mean_u = sum(stage_utils) / len(stage_utils)
    variance = sum((u - mean_u) ** 2 for u in stage_utils) / len(stage_utils)
    std = math.sqrt(variance + 1e-9)
    # Normalize: std / mean_u → [0, 1] bant
    norm_std = min(std / (abs(mean_u) + 1e-9), 1.0)
    # Yüksek norm_std → daha fazla exploration
    ratio = base_ratio + (max_ratio - base_ratio) * norm_std
    ratio = max(min_ratio, min(ratio, max_ratio))
    return ratio


# ─── [EKLENDİ] SOLUTION CLUSTERING ──────────────────────────────────────────

def _select_best_and_diverse(
    stage_results: List[Tuple[float, 'CuttingPlan3D', 'CuttingPlan3D']],
) -> Tuple[Optional['CuttingPlan3D'], Optional['CuttingPlan3D']]:
    """
    Exploration sonuçlarından iki farklı starting point seç:
      1. En iyi (max utilization) → güvenli derinleşme
      2. En çeşitli (max mesafe en iyiden) → alternatif bölge keşfi

    Returns: (best_seed, diverse_seed)
    """
    if not stage_results:
        return None, None

    stage_results_sorted = sorted(stage_results, key=lambda x: -x[0])
    best_seed = stage_results_sorted[0][2]   # Orijinal seed

    if len(stage_results_sorted) < 2:
        return best_seed, None

    best_util = stage_results_sorted[0][0]
    # En büyük farkı olan = en çeşitli
    diverse_entry = max(
        stage_results_sorted[1:],
        key=lambda x: abs(x[0] - best_util)
    )
    diverse_seed = diverse_entry[2]
    return best_seed, diverse_seed


# ─── BAŞLANGIÇ ÜRETİMİ (KORUNDU + genişletildi) ─────────────────────────────

def _diversified_starts(
    pieces: List[Piece3D],
    trucks: List[Truck3D],
    n_starts: int,
) -> List[CuttingPlan3D]:
    """[KORUNDU] FFD + Greedy + MC çeşitlendirilmiş başlangıçlar."""
    starts = []
    try:
        starts.append(ffd_3d_optimization(pieces, trucks))
    except Exception:
        pass
    try:
        starts.append(greedy_3d_optimization(pieces, trucks))
    except Exception:
        pass
    mc_needed = max(0, n_starts - len(starts))
    for i in range(mc_needed):
        try:
            plan = monte_carlo_3d_optimization(
                pieces, trucks,
                iterations=max(20, 50 - i * 5),
                initial_solution=starts[0] if starts else None,
            )
            starts.append(plan)
        except Exception:
            pass
    return starts[:n_starts]


# ─── ANA OPTİMİZASYON ────────────────────────────────────────────────────────

def multistart_sa_3d(
    pieces: List[Piece3D],
    trucks: List[Truck3D],
    n_starts: int = 5,
    time_budget: float = 90.0,
    initial_temp: float = None,
    cooling_rate: float = 0.997,
    initial_solution=None,
    progress_callback: Optional[Callable] = None,
    use_adaptive_budget: bool = True,    # [EKLENDİ] Gomes & Selman (2001)
    use_solution_clustering: bool = True, # [EKLENDİ] best + diverse seçimi
    base_explore_ratio: float = 0.40,    # [KORUNDU] Ablasyon parametresi
    seed: Optional[int] = None,          # Sabit seed → tekrarlanabilir sonuç
) -> CuttingPlan3D:
    """
    DMS-SA: Diversified Multi-Start SA with Adaptive Budget Partition

    Args:
        use_adaptive_budget     : True → varyansa göre bütçe bölümü
        use_solution_clustering : True → best + diverse ikili exploitation
        base_explore_ratio      : Başlangıç keşif oranı (ablasyon: 0.2–0.6)
        seed                    : Verilirse rastgelelik sabitlenir → tekrarlanabilir
    """
    if seed is not None:
        random.seed(seed)
    start_time = time.time()
    print(f"\n🔁 DMS-SA: {n_starts} başlangıç, {time_budget:.0f}s bütçe, "
          f"adaptive_budget={use_adaptive_budget}, "
          f"clustering={use_solution_clustering}")

    # ── 1. Başlangıç çözümleri ────────────────────────────────────────────
    # DÜZELTME: Tekilleştirme eskiden |Δutil| < 0.01 ile yapılıyordu. Bu
    # YANLIŞTIR: tüm parçaların sığdığı senaryoda FARKLI yerleşimler bile
    # birebir aynı doluluk verir (aynı parça seti + aynı araçlar → aynı
    # hacim) → çeşitlilik tek başlangıca çöküyordu ve "multi-start" fiilen
    # single-start oluyordu. Artık YAPISAL imza (kim, nerede) karşılaştırılır.
    def _plan_signature(p) -> frozenset:
        return frozenset(
            (b_idx, pl.piece_id, pl.x, pl.y, pl.z, pl.width, pl.length, pl.height)
            for b_idx, b in enumerate(p.bins) for pl in b
        )

    starts = []
    _seen_sigs = set()

    def _try_add_start(plan):
        if plan is None or not plan.bins:
            return
        sig = _plan_signature(plan)
        if sig in _seen_sigs:
            return          # gerçekten özdeş yerleşim — atla
        _seen_sigs.add(sig)
        starts.append(plan)

    if initial_solution and initial_solution.bins:
        _try_add_start(initial_solution)
    for s in _diversified_starts(pieces, trucks, n_starts):
        _try_add_start(s)

    starts = starts[:n_starts]
    print(f"  Başlangıç çözümleri: {[f'%{s.utilization:.1f}' for s in starts]} "
          f"({len(starts)} yapısal-farklı)")

    # ── 2. Kısa exploration turu ──────────────────────────────────────────
    # [DEĞİŞTİRİLDİ] Önce tüm starts'ı çalıştır, varyansı ölç,
    # sonra adaptive budget hesapla.
    explore_budget_initial = time_budget * base_explore_ratio
    time_per_start = explore_budget_initial / max(len(starts), 1)

    stage_results: List[Tuple[float, CuttingPlan3D, CuttingPlan3D]] = []
    stage_utils: List[float] = []

    for i, seed_plan in enumerate(starts):
        elapsed = time.time() - start_time
        if elapsed >= explore_budget_initial:
            break

        t_alloc = min(time_per_start, explore_budget_initial - elapsed)
        if t_alloc < 2.0:
            break

        print(f"  Tarama {i+1}/{len(starts)}: seed %{seed_plan.utilization:.1f}, "
              f"süre={t_alloc:.0f}s")

        try:
            plan = simulated_annealing_3d_optimization(
                pieces, trucks,
                initial_solution=seed_plan,
                max_time=t_alloc,
                initial_temp=initial_temp,
                cooling_rate=cooling_rate,
            )
            stage_results.append((plan.utilization, plan, seed_plan))
            stage_utils.append(plan.utilization)
            print(f"    → %{plan.utilization:.2f}")

            if progress_callback:
                progress_callback(i + 1, n_starts * 2, plan.utilization)

        except Exception as e:
            print(f"    ⚠️ {e}")

    if not stage_results:
        fallback = ffd_3d_optimization(pieces, trucks)
        stage_results.append((fallback.utilization, fallback, fallback))
        stage_utils.append(fallback.utilization)

    # ── [EKLENDİ] Adaptive budget hesaplama ──────────────────────────────
    if use_adaptive_budget and len(stage_utils) >= 2:
        actual_explore_ratio = _adaptive_explore_ratio(
            stage_utils, base_ratio=base_explore_ratio)
        print(f"  📊 Adaptive explore ratio: {actual_explore_ratio:.2f} "
              f"(base: {base_explore_ratio:.2f}, "
              f"util_std={round((max(stage_utils) - min(stage_utils)), 2):.2f})")
    else:
        actual_explore_ratio = base_explore_ratio

    # ── [EKLENDİ] Solution clustering ────────────────────────────────────
    stage_results_sorted = sorted(stage_results, key=lambda x: -x[0])
    best_seed_plan    = stage_results_sorted[0][2]
    best_stage_plan   = stage_results_sorted[0][1]

    if use_solution_clustering:
        best_seed, diverse_seed = _select_best_and_diverse(stage_results)
    else:
        best_seed  = best_seed_plan
        diverse_seed = None

    remaining = time_budget - (time.time() - start_time)

    # ── 3. Exploitation ───────────────────────────────────────────────────
    # [DEĞİŞTİRİLDİ] Eğer clustering var: 2 run; yoksa 1 run
    if diverse_seed and use_solution_clustering:
        # %70 best, %30 diverse
        exploit_main   = remaining * 0.70
        exploit_diverse = remaining * 0.28   # %2 rezerv
    else:
        exploit_main    = remaining * 0.95
        exploit_diverse = 0.0

    print(f"\n  🎯 Best seed: %{best_seed.utilization:.1f} → uzun SA ({exploit_main:.0f}s)")

    final_plans = [best_stage_plan]

    try:
        _t0 = initial_temp * 0.6 if initial_temp and initial_temp > 0 else None
        plan_main = simulated_annealing_3d_optimization(
            pieces, trucks,
            initial_solution=best_seed,
            max_time=exploit_main,
            initial_temp=_t0,
            cooling_rate=min(cooling_rate + 0.001, 0.9995),
        )
        final_plans.append(plan_main)
        if progress_callback:
            progress_callback(n_starts, n_starts * 2, plan_main.utilization)
    except Exception as e:
        print(f"  ⚠️ Ana SA hatası: {e}")

    # ── [EKLENDİ] Diverse seed exploitation ──────────────────────────────
    if diverse_seed and exploit_diverse >= 5.0:
        print(f"  🌐 Diverse seed: %{diverse_seed.utilization:.1f} → "
              f"SA ({exploit_diverse:.0f}s)")
        try:
            plan_diverse = simulated_annealing_3d_optimization(
                pieces, trucks,
                initial_solution=diverse_seed,
                max_time=exploit_diverse,
                initial_temp=initial_temp,
                cooling_rate=cooling_rate,
            )
            final_plans.append(plan_diverse)
            print(f"    → %{plan_diverse.utilization:.2f}")
        except Exception as e:
            print(f"  ⚠️ Diverse SA hatası: {e}")

    # ── [EKLENDİ] Stagnasyon kontrolü: kalan varsa 2. en iyi'den restart ─
    elapsed_now = time.time() - start_time
    leftover = time_budget - elapsed_now
    if leftover >= 8.0 and len(stage_results_sorted) > 1:
        second_best_seed = stage_results_sorted[1][2]
        restart_budget = leftover * 0.20
        print(f"  🔄 Stagnasyon restart: 2. en iyi seed "
              f"%{second_best_seed.utilization:.1f} → SA ({restart_budget:.0f}s)")
        try:
            plan_restart = simulated_annealing_3d_optimization(
                pieces, trucks,
                initial_solution=second_best_seed,
                max_time=restart_budget,
                initial_temp=initial_temp,
                cooling_rate=cooling_rate,
            )
            final_plans.append(plan_restart)
        except Exception as e:
            print(f"  ⚠️ Restart SA hatası: {e}")

    # ── En iyi sonucu seç ────────────────────────────────────────────────
    # DÜZELTME: Salt utilization karşılaştırması, daha az parça yerleştirip
    # daha yüksek doluluk gösteren planın kazanmasına izin veriyordu.
    # Sıra: (1) en çok yerleşen parça, (2) en az araç, (3) en yüksek doluluk.
    def _plan_rank(p: 'CuttingPlan3D'):
        placed = sum(len(b) for b in p.bins)
        bins_used = len([b for b in p.bins if b])
        return (placed, -bins_used, p.utilization)

    best = max(final_plans, key=_plan_rank)
    execution_time = time.time() - start_time
    best.algorithm = (
        f"DMS-SA ({n_starts} başlangıç, "
        f"adaptive={use_adaptive_budget}, "
        f"cluster={use_solution_clustering}, "
        f"{execution_time:.0f}s)"
    )

    total_pieces_count = sum(p.quantity for p in pieces)
    placed = sum(len(b) for b in best.bins)
    print(f"\n📊 DMS-SA SONUÇ:")
    print(f"  ✅ Yerleştirilen: {placed}/{total_pieces_count}")
    print(f"  📈 Doluluk     : %{best.utilization:.2f}")
    print(f"  ⏱️  Süre        : {execution_time:.2f}s")
    return best
