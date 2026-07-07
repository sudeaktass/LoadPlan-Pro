# -*- coding: utf-8 -*-
"""
Island Model Genetic Algorithm 3D
==================================
K bağımsız ada, her biri kendi GA'sını yürütür. Ring migration.

Yeni GA'nın index-based Individual yapısını ve _pack_individual'ı kullanır.
Sonunda assert: yerleştirilen + yerleşmeyen == toplam.
"""

import random
import time
from typing import List, Dict, Tuple, Optional

from core_3d import Piece3D, Truck3D, CuttingPlan3D, Placement3D
from genetic_3d import (
    Individual,
    _evaluate_individual,
    _create_initial_population,
    _tournament_selection,
    _order_crossover,
    _mutate,
)


def _actual_used_volume(placement, piece_info):
    if piece_info:
        piece = piece_info.get(placement.piece_id)
        if piece and getattr(piece, 'shape', 'box') == 'cylinder':
            return piece.get_actual_volume()
    return placement.get_volume()


def island_genetic_3d_optimization(
    pieces: List[Piece3D],
    trucks: List[Truck3D],
    n_islands: int = 4,
    island_population: int = 10,
    generations: int = 50,
    migration_interval: int = 10,
    migration_rate: int = 1,
    crossover_rate: float = 0.8,
    mutation_rate: float = 0.2,
    initial_solution=None,
    progress_callback=None,
    max_time: float = 0.0,   # 0 = sınırsız (yalnız jenerasyon); >0 = zaman bütçesi (sn)
    seed: Optional[int] = None,   # Sabit seed → tekrarlanabilir sonuç
    # API uyumu
    use_adaptive_migration: bool = False,
    use_heterogeneous_ops: bool = False,
    use_convergence_restart: bool = False,
    diversity_restart_threshold: float = 0.10,
) -> CuttingPlan3D:
    """K-island GA with ring migration. seed verilirse tekrarlanabilir."""
    if seed is not None:
        random.seed(seed)
    start_time = time.time()
    piece_info = {p.id: p for p in pieces}

    pieces_expanded: List[Piece3D] = []
    for piece in pieces:
        pieces_expanded.extend([piece] * piece.quantity)
    total_pieces = len(pieces_expanded)

    if total_pieces == 0 or not trucks:
        return CuttingPlan3D([], 0, 0, 0, "Island GA", {})

    if use_heterogeneous_ops and n_islands > 1:
        island_mut_rates = [
            0.05 + (0.45 * i / (n_islands - 1)) for i in range(n_islands)
        ]
    else:
        island_mut_rates = [mutation_rate] * n_islands

    print(f"🏝️ Island GA: {total_pieces} palet, {n_islands} ada × "
          f"{island_population} pop, {generations} gen")

    islands: List[List[Individual]] = []
    for _ in range(n_islands):
        islands.append(_create_initial_population(pieces_expanded, island_population))

    best_score = float('-inf')
    best_plan_data = None
    fitness_cache: Dict[Tuple[int, ...], Tuple[float, dict]] = {}

    for gen in range(generations):
        # Zaman bütçesi kontrolü — adil karşılaştırma için erken sonlanma
        if max_time > 0 and (time.time() - start_time) >= max_time:
            print(f"  ⏱️ Island GA zaman bütçesi doldu (gen {gen}/{generations})")
            break
        # Her ada bağımsız evrim
        for island_idx in range(n_islands):
            pop = islands[island_idx]
            mut_rate = island_mut_rates[island_idx]
            scored = []
            for ind in pop:
                key = tuple(ind)
                if key in fitness_cache:
                    score, plan_data = fitness_cache[key]
                else:
                    score, plan_data = _evaluate_individual(
                        ind, pieces_expanded, trucks, piece_info)
                    fitness_cache[key] = (score, plan_data)
                scored.append((score, ind, plan_data))
                if score > best_score:
                    best_score = score
                    best_plan_data = plan_data

            scored.sort(key=lambda x: x[0], reverse=True)

            new_pop = [scored[0][1]]
            if len(scored) > 1:
                new_pop.append(scored[1][1])
            while len(new_pop) < island_population:
                p1 = _tournament_selection(scored, 3)
                p2 = _tournament_selection(scored, 3)
                if random.random() < crossover_rate:
                    c1, c2 = _order_crossover(p1, p2)
                else:
                    c1, c2 = list(p1), list(p2)
                if random.random() < mut_rate:
                    c1 = _mutate(c1)
                if random.random() < mut_rate:
                    c2 = _mutate(c2)
                new_pop.append(c1)
                if len(new_pop) < island_population:
                    new_pop.append(c2)
            islands[island_idx] = new_pop

        # Ring migration
        if (gen + 1) % migration_interval == 0 and n_islands > 1:
            migrants_per_island = []
            for pop in islands:
                scored_pop = []
                for ind in pop:
                    s = fitness_cache.get(tuple(ind), (float('-inf'), None))[0]
                    scored_pop.append((s, ind))
                scored_pop.sort(key=lambda x: -x[0])
                migrants_per_island.append([ind for _, ind in scored_pop[:migration_rate]])

            for i in range(n_islands):
                target = (i + 1) % n_islands
                for m in migrants_per_island[i]:
                    worst_idx = 0
                    worst_score = float('inf')
                    for j, ind in enumerate(islands[target]):
                        s = fitness_cache.get(tuple(ind), (float('inf'), None))[0]
                        if s < worst_score:
                            worst_score = s
                            worst_idx = j
                    islands[target][worst_idx] = m

        if progress_callback:
            progress_callback(gen + 1, generations, best_score)
        if (gen + 1) % 10 == 0:
            unfit = best_plan_data.get('unfitted', '?') if best_plan_data else '?'
            print(f"  Gen {gen+1}/{generations} | Skor: {best_score:.1f} | unfit: {unfit}")

    execution_time = time.time() - start_time

    if best_plan_data is None:
        print("❌ Island GA: çözüm bulunamadı")
        return CuttingPlan3D([], 0, 0, 0, "Island GA", {})

    placements_by_bin = best_plan_data['placements_by_bin']
    truck_assignments = best_plan_data['truck_assignments']
    unfitted_count = best_plan_data['unfitted']

    total_volume = 0
    used_volume = 0
    for bin_id, placements in placements_by_bin.items():
        truck_id = truck_assignments[bin_id]
        truck = next(t for t in trucks if t.id == truck_id)
        total_volume += truck.get_volume()
        used_volume += sum(_actual_used_volume(p, piece_info) for p in placements)

    max_bin = max(placements_by_bin.keys()) if placements_by_bin else 0
    bins_list = [placements_by_bin.get(i, []) for i in range(max_bin + 1)]
    utilization = (used_volume / total_volume * 100) if total_volume > 0 else 0
    num_trucks = len([b for b in bins_list if b])

    print(f"\n📊 Island GA SONUÇ:")
    print(f"  ✅ Yerleştirilen: {sum(len(b) for b in bins_list)}/{total_pieces}")
    print(f"  🚛 Kamyonet    : {num_trucks}")
    print(f"  📊 Kullanım    : %{utilization:.1f}")
    print(f"  ⏱️  Süre        : {execution_time:.2f}s")

    _placed = sum(len(b) for b in bins_list)
    assert _placed + unfitted_count == total_pieces, (
        f"Island GA: placed({_placed}) + unfitted({unfitted_count}) "
        f"!= total({total_pieces})"
    )

    return CuttingPlan3D(
        bins=bins_list,
        total_waste=total_volume - used_volume,
        utilization=utilization,
        execution_time=execution_time,
        algorithm=f"Island GA ({n_islands} ada)",
        truck_assignments=truck_assignments,
        unfitted_pieces=[],
    )


# app_3d.py uyumluluk alias'ı
island_model_ga_3d = island_genetic_3d_optimization
