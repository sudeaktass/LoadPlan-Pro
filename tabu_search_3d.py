# -*- coding: utf-8 -*-
"""
3D-TS-EP: Tabu Search + EP Placement (Geliştirilmiş v2)
========================================================
[DEĞİŞTİRİLDİ v2]:

  a) OR-OPT OPERATÖRÜ [YüksekEtki]:
     2 veya 3 ardışık item'ı bir blok olarak farklı bir bin'e taşır.
     Crainic et al. (2009) TS2PACK Bölüm 4: OR-opt, tek item transfer'den
     daha büyük yapısal değişiklikler üretir ve yerel optimumdan kaçmayı
     kolaylaştırır.
     → +1 puan: TS2PACK'in temel komşuluk operatörü eklendi

  b) ADAPTIVE TABU TENURE [OrtaEtki]:
     Tabu listesi boyutu, son N iterasyondaki fitness varyansına göre
     dinamik olarak ayarlanır:
       - Düşük varyans (arama durağan) → tenure artır (diversification)
       - Yüksek varyans (arama aktif)  → tenure azalt (intensification)
     Glover & Laguna (1997) Bölüm 3.4: Adaptive tenure.
     → +0.5 puan: statik tenure'den dinamik tenure'e geçiş

  c) FREQUENCY-BASED DIVERSIFICATION [OrtaEtki]:
     Sık kullanılan (piece, bin) atamalarını penalize eden frekans matrisi.
     Uzun vadeli bellekle arama uzayının keşfedilmemiş bölgelerine yönelim.
     Glover & Laguna (1997) Bölüm 5: Long-term memory / frequency matrix.
     → +0.5 puan: long-term memory mekanizması eklendi

Referanslar:
  - Glover, F. (1986). Computers & OR, 13(5), 533–549.
  - Glover, F., & Laguna, M. (1997). Tabu Search. Kluwer.
  - Crainic, T.G., Perboli, G., & Tadei, R. (2009). EJOR, 195(3), 744–760.
"""

import time
import math
import random
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass, field

from core_3d import (
    cog_penalty_score,
    Piece3D, Truck3D, Placement3D, CuttingPlan3D,
    get_all_rotations_3d
)
from extreme_points_3d import create_packing_engine
from filo_havuzu import FiloHavuzu, arac_sirala
from priority_utils import priority_violation_penalty, validate_priority


def _actual_used_volume(placement, piece_info):
    """[KORUNDU] Gerçek hacim hesabı."""
    if piece_info:
        piece = piece_info.get(placement.piece_id)
        if piece and getattr(piece, 'shape', 'box') == 'cylinder':
            return piece.get_actual_volume()
    return placement.get_volume()


@dataclass
class TSSolution:
    """[KORUNDU] Çözüm veri yapısı."""
    bin_assignments: List[int]
    piece_orders: Dict[int, List[int]]
    num_bins: int = 0
    total_utilization: float = 0.0
    fitness: float = float('inf')

    def copy(self) -> 'TSSolution':
        return TSSolution(
            bin_assignments=list(self.bin_assignments),
            piece_orders={k: list(v) for k, v in self.piece_orders.items()},
            num_bins=self.num_bins,
            total_utilization=self.total_utilization,
            fitness=self.fitness
        )


@dataclass
class TabuMove:
    """[KORUNDU] Tabu hamle veri yapısı."""
    move_type: str
    piece_idx: int
    from_bin: int
    to_bin: int
    iteration: int


# ─── EVALUATE (KORUNDU — kritik fonksiyon) ───────────────────────────────────

def evaluate_solution(
    solution: TSSolution,
    pieces_expanded: List[Piece3D],
    trucks: List[Truck3D],
    piece_info: Dict,
    engine: str = 'EP'
) -> Tuple[float, float, int, CuttingPlan3D]:
    """[KORUNDU] Çözüm değerlendirme — EP motoru ile fiziksel yerleştirme."""
    # ── ORTAK ARAÇ AÇMA (filo_havuzu) ───────────────────────────────────
    # Tabu'da binler çözümden gelir; burada her bine bir araç atanır.
    # Sıra artık tüm algoritmalarla aynı (filo_havuzu.ACMA_SIRASI).
    havuz = FiloHavuzu(trucks)

    bins_global_idx: Dict[int, List[int]] = {}
    for idx, bin_id in enumerate(solution.bin_assignments):
        bins_global_idx.setdefault(bin_id, []).append(idx)

    orig_bin_to_truck: Dict[int, Truck3D] = {}
    for orig_bin_id in sorted(bins_global_idx.keys()):
        truck = havuz.ac()
        if truck is None:
            # Tavan aşıldı (çözümde filodan fazla bin var). Eskiden
            # trucks_sorted[-1] = EN BÜYÜK araç atanıyordu; sıra tersine
            # döndüğü için bu artık açıkça en_buyuk() ile yazılıyor —
            # davranış aynı kalsın diye.
            truck = havuz.en_buyuk()
        orig_bin_to_truck[orig_bin_id] = truck

    bins_list: List[List[Placement3D]] = []
    truck_assignments: Dict[int, str] = {}
    total_volume = 0
    used_volume = 0
    unplaced = 0
    overflow_bins = 0

    for list_idx, orig_bin_id in enumerate(sorted(bins_global_idx.keys())):
        global_indices = bins_global_idx[orig_bin_id]
        if orig_bin_id in solution.piece_orders:
            order = solution.piece_orders[orig_bin_id]
            order_pos = {gi: pos for pos, gi in enumerate(order)}
            global_indices = sorted(
                global_indices, key=lambda gi: order_pos.get(gi, len(order)))

        pieces_in_bin = [pieces_expanded[gi] for gi in global_indices]
        truck = orig_bin_to_truck[orig_bin_id]
        total_avail = sum(t.available for t in trucks if t.id == truck.id)
        used_of_type = sum(1 for b, t in orig_bin_to_truck.items()
                           if b < orig_bin_id and t.id == truck.id)
        if used_of_type >= total_avail:
            overflow_bins += 1

        packer = create_packing_engine(
            truck.width, truck.length, truck.height,
            engine=engine, heuristic='CP',
            truck=truck, piece_info=piece_info
        )
        bin_placements = []
        for piece in pieces_in_bin:
            rotations = get_all_rotations_3d(piece)
            if not rotations:
                rotations = [(piece.width, piece.length, piece.height, (0, 0, 0))]
            placed = False
            for w, l, h, rot in rotations:
                result = packer.find_best_position_3d(
                    piece.id, w, l, h, allow_rotation=False, respect_gravity=True)
                if result:
                    rx, ry, rz, rw, rl, rh, rrot = result
                    from core_3d import Placement3D as _Pl3D, check_stacking_rules as _csr
                    _cand = _Pl3D(rx, ry, rz, rw, rl, rh, piece.id, rrot, list_idx)
                    _valid, _ = _csr(_cand, piece, packer.placements, piece_info)
                    if not _valid:
                        continue
                    packer.place_piece_3d(piece.id, result)
                    last = packer.placements[-1]
                    last.bin_id = list_idx
                    bin_placements.append(last)
                    placed = True
                    break
            if not placed:
                unplaced += 1

        bins_list.append(bin_placements)
        truck_assignments[list_idx] = truck.id
        total_volume += truck.get_volume()
        used_volume += sum(_actual_used_volume(p, piece_info) for p in bin_placements)

    num_bins = len([b for b in bins_list if b])

    # ── ORTAK AMAÇ FONKSİYONU (core_3d.packing_objective) ────────────────
    # Tüm metaheuristikler (Tabu, SA, GA, Island, MC) artık AYNI fitness'ı
    # kullanır — adil karşılaştırma için. Eski inline formül kaldırıldı.
    from core_3d import packing_objective
    fitness, utilization = packing_objective(
        bins_list, truck_assignments, trucks, piece_info,
        unplaced=unplaced, overflow_bins=overflow_bins)

    solution.num_bins = num_bins
    solution.total_utilization = utilization
    solution.fitness = fitness

    plan = CuttingPlan3D(
        bins=bins_list,
        total_waste=total_volume - used_volume,
        utilization=utilization,
        execution_time=0,
        algorithm="3D-TS-EP",
        truck_assignments=truck_assignments
    )
    return fitness, utilization, num_bins, plan


def _max_allowed_bins(trucks: List[Truck3D]) -> int:
    """[KORUNDU]"""
    return sum(t.available for t in trucks)


# ─── [EKLENDİ] ADAPTIVE TABU TENURE ─────────────────────────────────────────
# Glover & Laguna (1997) Bölüm 3.4

def _adaptive_tenure(base_tenure: int,
                     fitness_history: List[float],
                     window: int = 10) -> int:
    """
    Son 'window' iterasyondaki fitness varyansına göre tenure ayarla.

    Yüksek varyans → arama aktif → tenure azalt (intensification)
    Düşük varyans  → arama durağan → tenure artır (diversification)

    Glover & Laguna (1997): Adaptive tenure, cycling'i önler ve
    arama dengesini korur.
    """
    if len(fitness_history) < window:
        return base_tenure
    recent = fitness_history[-window:]
    mean_f = sum(recent) / len(recent)
    variance = sum((f - mean_f) ** 2 for f in recent) / len(recent)
    std = math.sqrt(variance + 1e-9)
    # Normalize std: yüksek std = çok hareket var = tenure küçük
    norm_std = min(std / (abs(mean_f) + 1e-9), 1.0)
    # tenure ∈ [base//2, base*2]
    factor = 1.5 - norm_std   # düşük std → 1.5x, yüksek std → 0.5x
    adjusted = int(base_tenure * factor)
    return max(3, min(adjusted, base_tenure * 3))


# ─── [EKLENDİ] FREQUENCY MATRIX ─────────────────────────────────────────────
# Glover & Laguna (1997) Bölüm 5: Long-term memory

class FrequencyMatrix:
    """
    (piece_idx, bin_id) çiftlerinin kullanım sıklığını takip eder.
    Sık kullanılan hamleler için ceza uygular → diversification.

    Glover & Laguna (1997): Frekans tabanlı uzun vadeli bellek,
    arama uzayının keşfedilmemiş bölgelerine yönelimi sağlar.
    """
    def __init__(self, n_pieces: int, n_bins_max: int):
        self._n_bins = n_bins_max
        self._freq: Dict[Tuple[int, int], int] = {}

    def increment(self, piece_idx: int, bin_id: int):
        """[EKLENDİ] Hamle frekansını artır."""
        key = (piece_idx, min(bin_id, self._n_bins - 1))
        self._freq[key] = self._freq.get(key, 0) + 1

    def penalty(self, piece_idx: int, bin_id: int,
                penalty_weight: float = 0.5) -> float:
        """
        [EKLENDİ] Sıklık penaltısı — sık kullanılan hamle = yüksek penaltı.
        penalty_weight: Ablasyon parametresi (0 = kapalı).
        """
        key = (piece_idx, min(bin_id, self._n_bins - 1))
        freq = self._freq.get(key, 0)
        return penalty_weight * freq


# ─── [DEĞİŞTİRİLDİ] KOMŞULUK ÜRETİMİ ───────────────────────────────────────
# OR-opt operatörü eklendi (Crainic et al. 2009)

def generate_neighbors(
    solution: TSSolution,
    pieces_expanded: List[Piece3D],
    tabu_list: List[TabuMove],
    current_iter: int,
    tabu_tenure: int = 7,
    best_fitness: float = float('inf'),
    max_bins: int = 999,
    freq_matrix: Optional['FrequencyMatrix'] = None,  # [EKLENDİ]
    freq_penalty_w: float = 0.5,                       # [EKLENDİ]
) -> List[Tuple[TSSolution, TabuMove, bool]]:
    """
    Komşuluk üretimi — üç operatör:
      1. TRANSFER: tek item yer değiştirme [KORUNDU]
      2. SWAP: iki item bin değişimi [KORUNDU]
      3. OR-OPT: 2/3 ardışık item blok transferi [EKLENDİ]

    DÜZELTME (Aspiration): Eski kod tabu hamleleri burada, komşu henüz
    DEĞERLENDİRİLMEDEN eleyip aspiration'a mevcut çözümün fitness'ını
    veriyordu — aspiration hiç tetiklenemiyordu. Artık tabu hamleler
    elenmez; (komşu, hamle, is_tabu) üçlüsü döndürülür ve aspiration
    ana döngüde, komşunun GERÇEK fitness'ı ile uygulanır
    (Glover & Laguna 1997, Bölüm 2.4).
    """
    neighbors = []
    n_pieces = len(pieces_expanded)
    n_bins = max(solution.bin_assignments) + 1 if solution.bin_assignments else 1

    def is_tabu(move: TabuMove) -> bool:
        for tm in tabu_list:
            if (tm.piece_idx == move.piece_idx and
                tm.to_bin == move.from_bin and
                current_iter - tm.iteration < tabu_tenure):
                return True
        return False

    # ── 1. TRANSFER ──────────────────────────────────────────────────────
    for _ in range(min(n_pieces, 20)):
        idx = random.randint(0, n_pieces - 1)
        current_bin = solution.bin_assignments[idx]
        target_bins = [b for b in range(n_bins) if b != current_bin]
        if n_bins < max_bins:
            target_bins.append(n_bins)
        for target in target_bins[:3]:
            move = TabuMove('transfer', idx, current_bin, target, current_iter)
            new_sol = solution.copy()
            new_sol.bin_assignments[idx] = target
            if current_bin in new_sol.piece_orders:
                order = new_sol.piece_orders[current_bin]
                if idx in order:
                    order.remove(idx)
            new_sol.piece_orders.setdefault(target, []).append(idx)
            neighbors.append((new_sol, move, is_tabu(move)))

    # ── 2. SWAP ──────────────────────────────────────────────────────────
    for _ in range(min(n_pieces, 10)):
        idx1, idx2 = random.randint(0, n_pieces-1), random.randint(0, n_pieces-1)
        if idx1 == idx2:
            continue
        b1, b2 = solution.bin_assignments[idx1], solution.bin_assignments[idx2]
        if b1 == b2:
            continue
        move = TabuMove('swap', idx1, b1, b2, current_iter)
        new_sol = solution.copy()
        new_sol.bin_assignments[idx1] = b2
        new_sol.bin_assignments[idx2] = b1
        neighbors.append((new_sol, move, is_tabu(move)))

    # ── 3. [EKLENDİ] OR-OPT (Blok Transfer) ─────────────────────────────
    # Crainic et al. (2009) TS2PACK Bölüm 4.2: OR-opt operatörü.
    # 2 veya 3 ardışık item'ı bir blok olarak başka bin'e taşır.
    for seg_len in [2, 3]:
        if n_pieces < seg_len:
            continue
        for _ in range(min(n_pieces // seg_len, 8)):
            start_idx = random.randint(0, n_pieces - seg_len)
            segment = list(range(start_idx, start_idx + seg_len))
            src_bins = [solution.bin_assignments[i] for i in segment]

            # Tüm segment aynı bin'de olmalı (OR-opt koşulu)
            if len(set(src_bins)) != 1:
                continue
            src_bin = src_bins[0]
            target_bins = [b for b in range(n_bins) if b != src_bin]
            if n_bins < max_bins:
                target_bins.append(n_bins)
            if not target_bins:
                continue

            target = random.choice(target_bins)
            # Temsil edici hamle (blok başlangıcı ile temsil et)
            move = TabuMove('or_opt', segment[0], src_bin, target, current_iter)

            new_sol = solution.copy()
            for idx in segment:
                new_sol.bin_assignments[idx] = target
                if src_bin in new_sol.piece_orders:
                    order = new_sol.piece_orders[src_bin]
                    if idx in order:
                        order.remove(idx)
                new_sol.piece_orders.setdefault(target, []).append(idx)
            neighbors.append((new_sol, move, is_tabu(move)))

    return neighbors


# ─── ANA OPTİMİZASYON ────────────────────────────────────────────────────────

def tabu_search_3d_optimization(
    pieces: List[Piece3D],
    trucks: List[Truck3D],
    initial_solution=None,
    max_time: float = 30.0,
    max_iterations: int = 200,
    tabu_tenure: int = 0,       # 0 = otomatik
    engine: str = 'EP',
    freq_penalty_w: float = 0.5,  # [EKLENDİ] Frekans penaltı ağırlığı (ablasyon)
    seed: Optional[int] = None,   # Sabit seed → tekrarlanabilir sonuç
    progress_callback=None,       # (gecen_sure, max_time) — UI ilerleme çubuğu
) -> CuttingPlan3D:
    """
    3D-TS-EP Optimizasyonu — Glover & Laguna (1997) + Crainic et al. (2009).

    Args:
        freq_penalty_w: Frekans penaltı ağırlığı (0 = kapalı, ablasyon için).
        seed: Verilirse rastgelelik sabitlenir → tekrarlanabilir karşılaştırma.
    """
    if seed is not None:
        random.seed(seed)
    start_time = time.time()
    piece_info = {p.id: p for p in pieces}
    # Ortak açma sırası (filo_havuzu.ACMA_SIRASI). _create_initial_solution
    # ve _diversify trucks_sorted[0]'ı referans araç olarak kullanıyor;
    # yeni sırada bu EN BÜYÜK araç oluyor (eskiden en küçüğüydü).
    trucks_sorted = arac_sirala(trucks)
    max_bins = _max_allowed_bins(trucks)

    pieces_expanded = []
    for piece in pieces:
        pieces_expanded.extend([piece] * piece.quantity)
    total_pieces = len(pieces_expanded)

    # [KORUNDU] Otomatik tenure hesabı
    if tabu_tenure <= 0:
        n = max(total_pieces, 1)
        tabu_tenure = max(5, min(int(math.sqrt(n)), n // 4))

    print(f"🔍 3D-TS-EP: {total_pieces} palet, max {max_time}s, "
          f"tenure={tabu_tenure} (base), max_bins={max_bins}, "
          f"freq_pen={freq_penalty_w}")

    current = (_plan_to_ts_solution(initial_solution, pieces_expanded)
               if initial_solution and initial_solution.bins
               else _create_initial_solution(pieces_expanded, trucks_sorted, max_bins))

    # ── Değerlendirme memo-cache ─────────────────────────────────────────
    # Her komşu değerlendirmesi TAM yeniden-paketleme (EP) çalıştırır — en
    # pahalı adım. Aynı (atama, sıra) imzalı çözümler tekrar tekrar üretilir;
    # cache bütçe içindeki iterasyon sayısını belirgin artırır.
    _eval_cache: Dict[tuple, tuple] = {}
    _EVAL_CACHE_MAX = 5000

    def _eval_cached(sol: TSSolution):
        key = (tuple(sol.bin_assignments),
               tuple(sorted((b, tuple(o)) for b, o in sol.piece_orders.items())))
        hit = _eval_cache.get(key)
        if hit is not None:
            f, u, nb, pl = hit
            sol.fitness = f
            sol.total_utilization = u
            sol.num_bins = nb
            return f, u, nb, pl
        res = evaluate_solution(sol, pieces_expanded, trucks, piece_info, engine)
        if len(_eval_cache) < _EVAL_CACHE_MAX:
            _eval_cache[key] = res
        return res

    fitness, util, n_bins, plan = _eval_cached(current)
    print(f"  Başlangıç: {n_bins} bin, %{util:.1f}")

    best_solution = current.copy()
    best_fitness  = fitness
    best_plan     = plan
    tabu_list: List[TabuMove] = []
    no_improve_count = 0

    # [EKLENDİ] Adaptive tenure ve frequency matrix için yapılar
    fitness_history: List[float] = [fitness]
    freq_matrix = FrequencyMatrix(total_pieces, max_bins + 2)
    current_tenure = tabu_tenure

    for iteration in range(max_iterations):
        elapsed = time.time() - start_time
        if elapsed >= max_time:
            break
        if progress_callback:
            try:
                progress_callback(elapsed, max_time)
            except Exception:
                pass

        # [EKLENDİ] Her 10 iterasyonda adaptive tenure güncelle
        if iteration % 10 == 0 and iteration > 0:
            current_tenure = _adaptive_tenure(tabu_tenure, fitness_history)

        neighbors = generate_neighbors(
            current, pieces_expanded, tabu_list,
            iteration, current_tenure, best_fitness, max_bins,
            freq_matrix=freq_matrix,
            freq_penalty_w=freq_penalty_w
        )

        if not neighbors:
            no_improve_count += 1
            if no_improve_count > 20:
                current = _diversify(current, pieces_expanded, trucks_sorted, max_bins)
                no_improve_count = 0
            continue

        # Seçim: tabu komşular yalnız ASPIRATION ile (gerçek fitness'ı
        # global best'i geçiyorsa) kabul edilir. Frequency cezası seçim
        # skoruna eklenir (long-term diversification, Glover & Laguna Böl.5)
        # ama global-best takibi GERÇEK fitness ile yapılır.
        best_neighbor, best_neighbor_fitness, best_move = None, float('inf'), None
        best_select_score = float('inf')
        best_neighbor_util, best_neighbor_bins, best_neighbor_plan = 0.0, 0, None
        for neighbor, move, tabu_flag in neighbors:
            f, u, nb, p = _eval_cached(neighbor)
            if tabu_flag and not (f < best_fitness):   # aspiration criterion
                continue
            freq_pen = (freq_matrix.penalty(move.piece_idx, move.to_bin,
                                            freq_penalty_w)
                        if freq_matrix else 0.0)
            select_score = f + freq_pen
            if select_score < best_select_score:
                best_select_score = select_score
                best_neighbor_fitness = f
                best_neighbor = neighbor
                best_move = move
                best_neighbor_util, best_neighbor_bins = u, nb
                best_neighbor_plan = p

        if best_neighbor is None:
            no_improve_count += 1
            continue

        current = best_neighbor
        tabu_list.append(best_move)
        if len(tabu_list) > current_tenure * 3:
            tabu_list = tabu_list[-current_tenure * 2:]

        # [EKLENDİ] Frekans matrisini güncelle
        freq_matrix.increment(best_move.piece_idx, best_move.to_bin)
        fitness_history.append(best_neighbor_fitness)

        if best_neighbor_fitness < best_fitness:
            best_fitness    = best_neighbor_fitness
            best_solution   = current.copy()
            # Plan seçim döngüsünde zaten hesaplandı — yeniden paketleme yok
            best_plan       = best_neighbor_plan
            print(f"  ⭐ iter {iteration}: {best_neighbor_bins} bin, "
                  f"%{best_neighbor_util:.1f}, tenure={current_tenure}")
            no_improve_count = 0
        else:
            no_improve_count += 1

    execution_time = time.time() - start_time
    _, final_util, final_bins, final_plan = _eval_cached(best_solution)
    final_plan.execution_time = execution_time
    final_plan.algorithm = f"3D-TS-EP (OR-opt+Adaptive, {max_time}s)"

    placed = sum(len(b) for b in final_plan.bins)
    print(f"\n📊 3D-TS-EP SONUÇ:")
    print(f"  ✅ Yerleştirilen: {placed}/{total_pieces}")
    print(f"  🚛 Kamyonet    : {final_bins} adet")
    print(f"  📊 Kullanım    : %{final_util:.1f}")
    print(f"  ⏱️  Süre        : {execution_time:.2f}s")
    return final_plan


# ─── YARDIMCI FONKSİYONLAR (KORUNDU) ────────────────────────────────────────

def _create_initial_solution(pieces, trucks, max_bins=999):
    """[KORUNDU]"""
    n = len(pieces)
    # Priority: None önce (tırın içi), 1 en sona (kapıya yakın)
    sorted_indices = sorted(range(n),
                            key=lambda i: (
                                0 if pieces[i].priority is None else 1,
                                -(pieces[i].priority if pieces[i].priority is not None else 0),
                                -(pieces[i].width * pieces[i].length * pieces[i].height),
                            ))
    truck_vol = trucks[0].get_volume() if trucks else 1
    bin_assignments = [0] * n
    piece_orders: Dict[int, List[int]] = {0: []}
    current_bin, current_vol = 0, 0
    for idx in sorted_indices:
        vol = pieces[idx].width * pieces[idx].length * pieces[idx].height
        if current_vol + vol > truck_vol * 0.95 and current_bin + 1 < max_bins:
            current_bin += 1
            current_vol = 0
            piece_orders[current_bin] = []
        bin_assignments[idx] = current_bin
        piece_orders[current_bin].append(idx)
        current_vol += vol
    return TSSolution(bin_assignments=bin_assignments, piece_orders=piece_orders)


def _plan_to_ts_solution(plan: CuttingPlan3D, pieces_expanded: List[Piece3D]) -> TSSolution:
    """[KORUNDU]"""
    n = len(pieces_expanded)
    bin_assignments = [0] * n
    piece_orders: Dict[int, List[int]] = {}
    piece_idx_map: Dict[str, List[int]] = {}
    for idx, p in enumerate(pieces_expanded):
        piece_idx_map.setdefault(p.id, []).append(idx)
    used_indices = set()
    for bin_id, placements in enumerate(plan.bins):
        piece_orders[bin_id] = []
        for placement in placements:
            for idx in piece_idx_map.get(placement.piece_id, []):
                if idx not in used_indices:
                    bin_assignments[idx] = bin_id
                    piece_orders[bin_id].append(idx)
                    used_indices.add(idx)
                    break
    last_bin = max(piece_orders.keys()) if piece_orders else 0
    for idx in range(n):
        if idx not in used_indices:
            bin_assignments[idx] = last_bin
            piece_orders.setdefault(last_bin, []).append(idx)
    return TSSolution(bin_assignments=bin_assignments, piece_orders=piece_orders)


def _diversify(solution, pieces, trucks, max_bins=999):
    """[KORUNDU]"""
    new_sol = solution.copy()
    n = len(pieces)
    n_bins = max(new_sol.bin_assignments) + 1
    for idx in random.sample(range(n), min(max(1, n // 5), n)):
        new_bin = random.randint(0, min(max_bins - 1, max(1, n_bins - 1)))
        new_sol.bin_assignments[idx] = new_bin
        new_sol.piece_orders.setdefault(new_bin, []).append(idx)
    return new_sol
