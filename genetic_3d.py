# -*- coding: utf-8 -*-
"""
Genetic Algorithm 3D — Index-Based Order GA
============================================
Individual = List[int] (index permütasyonu pieces_expanded üzerinde).

Eski sürüm Individual = List[Piece3D] kullanıyordu. quantity > 1 olan
parçalar piece_list.extend([piece] * piece.quantity) ile aynı nesne
referansı olarak ekleniyordu — OX1 crossover'da id(x) tabanlı set işlemi
tüm duplicate'ları siliyor, 16 parçadan 4'ü kalıyordu.

Yeni sürüm: pieces_expanded[i] = i'inci parça örneği. Individual = [0,5,3,...].
Tüm crossover/mutation index'ler üzerinde çalışır → her örnek korunur.

Sonunda assert: yerleştirilen + yerleşmeyen == toplam.
"""

import os
import random
import time
from typing import List, Dict, Tuple, Optional

from core_3d import (
    check_stacking_rules,
    Piece3D, Truck3D, Placement3D, CuttingPlan3D,
    get_all_rotations_3d
)
from extreme_points_3d import create_packing_engine
from priority_utils import priority_violation_penalty, priority_sort_key

Individual = List[int]   # Index permütasyonu pieces_expanded üzerinde


def _actual_used_volume(placement, piece_info):
    if piece_info:
        piece = piece_info.get(placement.piece_id)
        if piece and getattr(piece, 'shape', 'box') == 'cylinder':
            return piece.get_actual_volume()
    return placement.get_volume()


# ─── PACK: FFD pattern üzerinden index permütasyonu ─────────────────────────

def _pack_individual(
    individual: Individual,
    pieces_expanded: List[Piece3D],
    trucks: List[Truck3D],
    piece_info: Dict,
    engine: str = "EP",
    heuristic: str = "CP",
) -> Tuple[Dict[int, List[Placement3D]], Dict[int, str], List[Piece3D]]:
    """FFD pattern: her parça için açık bin'leri sırayla dene, sığmazsa yeni bin.

    Döndürülen 3. eleman yerleşmeyen PARÇA LİSTESİ'dir (eski sürüm yalnız
    sayı döndürüyordu; CuttingPlan3D.unfitted_pieces boş kalıyordu)."""
    trucks_sorted = sorted(trucks, key=lambda t: t.get_volume())
    open_bins: Dict[int, dict] = {}
    placements_by_bin: Dict[int, List[Placement3D]] = {}
    truck_assignments: Dict[int, str] = {}
    truck_used_count: Dict[str, int] = {t.id: 0 for t in trucks}
    unfitted: List[Piece3D] = []

    def open_new_bin() -> Optional[int]:
        for truck in trucks_sorted:
            if truck_used_count[truck.id] < truck.available:
                bid = len(open_bins)
                truck_used_count[truck.id] += 1
                packer = create_packing_engine(
                    truck.width, truck.length, truck.height,
                    engine=engine, heuristic=heuristic,
                    truck=truck, piece_info=piece_info
                )
                open_bins[bid] = {'truck': truck, 'packer': packer}
                placements_by_bin[bid] = []
                truck_assignments[bid] = truck.id
                return bid
        return None

    def place_in_bin(bin_id: int, piece: Piece3D) -> bool:
        packer = open_bins[bin_id]['packer']
        rotations = get_all_rotations_3d(piece)
        if not rotations:
            rotations = [(piece.width, piece.length, piece.height, (0, 0, 0))]
        for w, l, h, _rot in rotations:
            result = packer.find_best_position_3d(
                piece.id, w, l, h,
                allow_rotation=False, respect_gravity=True
            )
            if result:
                rx, ry, rz, rw, rl, rh, rrot = result
                cand = Placement3D(rx, ry, rz, rw, rl, rh, piece.id, rrot, bin_id)
                valid, _ = check_stacking_rules(
                    cand, piece, packer.placements, piece_info)
                if not valid:
                    continue
                packer.place_piece_3d(piece.id, result)
                last = packer.placements[-1]
                last.bin_id = bin_id
                placements_by_bin[bin_id].append(last)
                return True
        return False

    if open_new_bin() is None:
        return {}, {}, [pieces_expanded[i] for i in individual]

    for idx in individual:
        piece = pieces_expanded[idx]
        placed = False
        for bin_id in list(open_bins.keys()):
            if place_in_bin(bin_id, piece):
                placed = True
                break
        if not placed:
            new_bin_id = open_new_bin()
            if new_bin_id is not None and place_in_bin(new_bin_id, piece):
                placed = True
        if not placed:
            unfitted.append(piece)

    return placements_by_bin, truck_assignments, unfitted


def _fitness(
    placements_by_bin: Dict[int, List[Placement3D]],
    truck_assignments: Dict[int, str],
    trucks: List[Truck3D],
    unfitted: int,
    piece_info: Dict,
) -> float:
    """
    GA skoru — YÜKSEK = daha iyi. Ortak amaç fonksiyonunu (core_3d.packing_objective,
    düşük=iyi) kullanır ve işaretini çevirir. Böylece GA, Tabu/SA/Island/MC ile
    AYNI hedefi optimize eder (CoG dahil).
    """
    from core_3d import packing_objective
    bins_list = [placements_by_bin.get(i, [])
                 for i in range(max(placements_by_bin.keys()) + 1)
                 ] if placements_by_bin else []
    fitness, _util = packing_objective(
        bins_list, truck_assignments, trucks, piece_info,
        unplaced=unfitted, overflow_bins=0)
    return -fitness   # düşük fitness → yüksek skor


# ─── PARALEL DEĞERLENDİRME (opsiyonel) ──────────────────────────────────────
# Birey değerlendirmesi (decode = EP paketleme) DETERMİNİSTİKTİR ve bireyler
# arası bağımsızdır → süreç havuzunda güvenle paralelleştirilebilir; sonuçlar
# sıralı koşuyla birebir aynıdır. Windows 'spawn' için worker fonksiyonları
# modül seviyesindedir; ağır veriler (parçalar/araçlar) havuz başlatılırken
# BİR KEZ aktarılır.

_GA_WORKER_CTX: dict = {}

def _ga_worker_init(pieces_expanded, trucks, engine):
    _GA_WORKER_CTX["pieces"] = pieces_expanded
    _GA_WORKER_CTX["trucks"] = trucks
    _GA_WORKER_CTX["engine"] = engine
    _GA_WORKER_CTX["piece_info"] = {p.id: p for p in pieces_expanded}

def _ga_worker_eval(individual):
    return _evaluate_individual(
        individual, _GA_WORKER_CTX["pieces"], _GA_WORKER_CTX["trucks"],
        _GA_WORKER_CTX["piece_info"], engine=_GA_WORKER_CTX["engine"])


def _plan_to_individual(plan, pieces_expanded) -> Optional[Individual]:
    """
    CuttingPlan3D → index permütasyonu (FFD tohumu için).

    initial_solution parametresi bugüne dek KULLANILMIYORDU; artık plan,
    popülasyona bir birey olarak enjekte edilir → GA iyi bir noktadan
    başlar, aynı kaliteye daha az nesille ulaşır.
    """
    if plan is None or not getattr(plan, "bins", None):
        return None
    idx_by_piece: Dict[str, List[int]] = {}
    for i, p in enumerate(pieces_expanded):
        idx_by_piece.setdefault(p.id, []).append(i)
    order: List[int] = []
    used = set()
    for bin_placements in plan.bins:
        for pl in bin_placements:
            for i in idx_by_piece.get(pl.piece_id, []):
                if i not in used:
                    order.append(i)
                    used.add(i)
                    break
    for i in range(len(pieces_expanded)):      # plana girmeyenler sona
        if i not in used:
            order.append(i)
    return order if len(order) == len(pieces_expanded) else None


def _evaluate_individual(individual, pieces_expanded, trucks, piece_info, engine="EP"):
    placements_by_bin, truck_assignments, unfitted_list = _pack_individual(
        individual, pieces_expanded, trucks, piece_info, engine=engine)
    score = _fitness(placements_by_bin, truck_assignments, trucks,
                     len(unfitted_list), piece_info)
    plan_data = {
        'placements_by_bin': placements_by_bin,
        'truck_assignments': truck_assignments,
        'unfitted': len(unfitted_list),
        'unfitted_list': unfitted_list,
    }
    return score, plan_data


# ─── OPERATÖRLER (index bazlı, duplicate-safe) ───────────────────────────────

def _create_initial_population(pieces_expanded: List[Piece3D],
                                size: int) -> List[Individual]:
    """Index permütasyonları üreten çeşitlendirilmiş popülasyon."""
    n = len(pieces_expanded)
    base_indices = list(range(n))
    population: List[Individual] = []

    # 1. Hacim büyükten küçüğe
    by_vol = sorted(base_indices,
                    key=lambda i: -(pieces_expanded[i].width *
                                    pieces_expanded[i].length *
                                    pieces_expanded[i].height))
    population.append(by_vol)

    # 2. Ağırlık büyükten küçüğe
    if size > 1:
        by_wt = sorted(base_indices,
                       key=lambda i: -pieces_expanded[i].weight)
        population.append(by_wt)

    # 3. Kırılgan sona
    if size > 2:
        by_frag = sorted(base_indices,
                         key=lambda i: (
                             1 if pieces_expanded[i].is_fragile else 0,
                             -(pieces_expanded[i].width *
                               pieces_expanded[i].length *
                               pieces_expanded[i].height)
                         ))
        population.append(by_frag)

    # 4. Priority (priority_utils ile tutarli siralama)
    if size > 3:
        by_prio = sorted(base_indices,
                         key=lambda i: priority_sort_key(pieces_expanded[i]))
        population.append(by_prio)

    # Random shuffles
    while len(population) < size:
        shuf = list(base_indices)
        random.shuffle(shuf)
        population.append(shuf)

    return population[:size]


def _tournament_selection(scored, k=3):
    candidates = random.sample(scored, min(k, len(scored)))
    return max(candidates, key=lambda x: x[0])[1]


def _order_crossover(p1: Individual, p2: Individual) -> Tuple[Individual, Individual]:
    """
    OX1 — index permütasyonu için doğru implementasyon.
    Her index pieces_expanded'da unique konum → set işlemleri güvenli.
    """
    n = len(p1)
    if n < 2:
        return list(p1), list(p2)
    pt1, pt2 = sorted(random.sample(range(n), 2))

    def ox_child(a: Individual, b: Individual) -> Individual:
        seg = a[pt1:pt2]
        seg_set = set(seg)   # int'ler — duplicate yok
        rest = [x for x in b if x not in seg_set]
        child = rest[:pt1] + seg + rest[pt1:]
        return child[:n]

    return ox_child(p1, p2), ox_child(p2, p1)


def _mutate(individual: Individual) -> Individual:
    """Swap mutation."""
    n = len(individual)
    if n < 2:
        return individual
    ind = list(individual)
    i, j = random.sample(range(n), 2)
    ind[i], ind[j] = ind[j], ind[i]
    return ind


# ─── ANA OPTİMİZASYON ────────────────────────────────────────────────────────

def genetic_3d_optimization(
    pieces: List[Piece3D],
    trucks: List[Truck3D],
    population_size: int = 30,
    generations: int = 50,
    crossover_rate: float = 0.8,
    mutation_rate: float = 0.2,
    elitism: bool = True,
    progress_callback=None,
    initial_solution=None,
    max_time: float = 0.0,   # 0 = sınırsız (yalnız jenerasyon); >0 = zaman bütçesi (sn)
    seed: Optional[int] = None,   # Sabit seed → tekrarlanabilir sonuç
    n_workers: Optional[int] = None,  # None→env LOADPLAN_GA_WORKERS; 0=paralel kapalı
    # API uyumu — artık etkisiz
    use_adaptive_operators: bool = False,
    use_diversity_boost: bool = False,
    use_ox2: bool = False,
    diversity_threshold: float = 0.15,
) -> CuttingPlan3D:
    """
    Index-based order GA — duplicate parça örneklerini doğru ele alır.

    max_time > 0 verilirse, jenerasyon döngüsü bu süre dolduğunda erken biter
    (adil karşılaştırma için zaman-tabanlı sonlanma).
    seed verilirse rastgelelik sabitlenir → tekrarlanabilir karşılaştırma.
    n_workers > 0 → birey değerlendirmeleri süreç havuzunda paralel
    (deterministik decode → sonuç sıralı koşuyla aynı).
    """
    if seed is not None:
        random.seed(seed)
    start_time = time.time()
    piece_info = {p.id: p for p in pieces}

    if n_workers is None:
        try:
            n_workers = int(os.getenv("LOADPLAN_GA_WORKERS", "0"))
        except ValueError:
            n_workers = 0

    # Quantity expansion — index permütasyonu için temel liste
    pieces_expanded: List[Piece3D] = []
    for piece in pieces:
        pieces_expanded.extend([piece] * piece.quantity)
    total_pieces = len(pieces_expanded)

    if total_pieces == 0 or not trucks:
        return CuttingPlan3D([], 0, 0, 0, "GA", {})

    print(f"🧬 GA: {total_pieces} palet, pop={population_size}, "
          f"gen={generations}, workers={n_workers}")

    population = _create_initial_population(pieces_expanded, population_size)

    # FFD/başlangıç çözümünü popülasyona tohumla (parametre artık gerçek işlev
    # görüyor — eskiden kabul edilip yok sayılıyordu)
    if initial_solution is not None:
        _seed_ind = _plan_to_individual(initial_solution, pieces_expanded)
        if _seed_ind is not None and population:
            population[0] = _seed_ind
            print("  🌱 initial_solution popülasyona tohumlandı")

    best_score = float('-inf')
    best_plan_data = None
    fitness_cache: Dict[Tuple[int, ...], Tuple[float, dict]] = {}

    # ── Opsiyonel süreç havuzu ──────────────────────────────────────────
    _executor = None
    if n_workers and n_workers > 0 and total_pieces >= 8:
        try:
            from concurrent.futures import ProcessPoolExecutor
            _executor = ProcessPoolExecutor(
                max_workers=n_workers,
                initializer=_ga_worker_init,
                initargs=(pieces_expanded, trucks, "EP"))
        except Exception as _pe:
            print(f"  ⚠️ Paralel havuz açılamadı ({_pe}) — sıralı devam")
            _executor = None

    try:
        for gen in range(generations):
            # Zaman bütçesi kontrolü — adil karşılaştırma için erken sonlanma
            if max_time > 0 and (time.time() - start_time) >= max_time:
                print(f"  ⏱️ GA zaman bütçesi doldu (gen {gen}/{generations})")
                break

            # Önbellekte olmayan bireyleri (varsa) paralel değerlendir;
            # sonuçlar cache'e yazılır → aşağıdaki sıralı akış ve en-iyi
            # takibi DEĞİŞMEDEN aynı sırayla çalışır (sonuç birebir aynı).
            if _executor is not None:
                pending = []
                seen_pending = set()
                for ind in population:
                    key = tuple(ind)
                    if key not in fitness_cache and key not in seen_pending:
                        pending.append((key, ind))
                        seen_pending.add(key)
                if len(pending) >= 2:
                    try:
                        for (key, _ind), res in zip(
                                pending,
                                _executor.map(_ga_worker_eval,
                                              [i for _, i in pending])):
                            fitness_cache[key] = res
                    except Exception as _we:
                        print(f"  ⚠️ Paralel değerlendirme hatası ({_we}) — "
                              "sıralıya dönülüyor")
                        _executor.shutdown(wait=False, cancel_futures=True)
                        _executor = None

            scored = []
            _time_up = False
            for ind in population:
                # İNCE TANELİ süre kontrolü: yalnız nesil sınırında kontrol,
                # kalabalık popülasyonda bütçeyi nesil-boyu aşıyordu (BO
                # deneme tavanları için kritik). En az bir çözüm garantisi:
                # best_plan_data yokken kesilmez.
                if (max_time > 0 and best_plan_data is not None
                        and (time.time() - start_time) >= max_time):
                    _time_up = True
                    break
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

            if _time_up:
                print(f"  ⏱️ GA zaman bütçesi doldu (gen {gen} içinde, "
                      f"{len(scored)}/{len(population)} birey)")
                break

            if progress_callback:
                progress_callback(gen + 1, generations, best_score)

            if (gen + 1) % 10 == 0:
                unfit = best_plan_data.get('unfitted', '?') if best_plan_data else '?'
                print(f"  Gen {gen+1}/{generations} | Skor: {best_score:.1f} | unfit: {unfit}")

            scored.sort(key=lambda x: x[0], reverse=True)

            new_pop: List[Individual] = []
            if elitism and scored:
                new_pop.append(scored[0][1])
                if len(scored) > 1:
                    new_pop.append(scored[1][1])

            while len(new_pop) < population_size:
                p1 = _tournament_selection(scored, 3)
                p2 = _tournament_selection(scored, 3)
                if random.random() < crossover_rate:
                    c1, c2 = _order_crossover(p1, p2)
                else:
                    c1, c2 = list(p1), list(p2)
                if random.random() < mutation_rate:
                    c1 = _mutate(c1)
                if random.random() < mutation_rate:
                    c2 = _mutate(c2)
                new_pop.append(c1)
                if len(new_pop) < population_size:
                    new_pop.append(c2)
            population = new_pop
    finally:
        if _executor is not None:
            _executor.shutdown(wait=False, cancel_futures=True)

    execution_time = time.time() - start_time

    if best_plan_data is None:
        print("❌ GA: çözüm bulunamadı")
        return CuttingPlan3D([], 0, 0, 0, "GA", {})

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

    print(f"\n📊 GA SONUÇ:")
    print(f"  ✅ Yerleştirilen: {sum(len(b) for b in bins_list)}/{total_pieces}")
    print(f"  🚛 Kamyonet    : {num_trucks}")
    print(f"  📊 Kullanım    : %{utilization:.1f}")
    print(f"  ⏱️  Süre        : {execution_time:.2f}s")

    _placed = sum(len(b) for b in bins_list)
    assert _placed + unfitted_count == total_pieces, (
        f"GA: placed({_placed}) + unfitted({unfitted_count}) != total({total_pieces})"
    )

    return CuttingPlan3D(
        bins=bins_list,
        total_waste=total_volume - used_volume,
        utilization=utilization,
        execution_time=execution_time,
        algorithm=f"GA (pop={population_size}, gen={generations})",
        truck_assignments=truck_assignments,
        unfitted_pieces=best_plan_data.get('unfitted_list', []),
    )
