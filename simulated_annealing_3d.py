# -*- coding: utf-8 -*-
"""
SA-ACR: Simulated Annealing with Adaptive Cooling and Reheating (v2)
=====================================================================
[DEĞİŞTİRİLDİ v2]:

  a) ADAPTIVE COOLING [YüksekEtki]:
     Her sıcaklık adımında kabul oranı ölçülür; hedef bant %20–%40.
     Kabul oranı bandin dışına çıkarsa α dinamik olarak güncellenir:
       - Çok az kabul (α küçük) → α artır (yavaşça soğut)
       - Çok fazla kabul (α büyük) → α azalt (hızlıca soğut)
     Huang et al. (1986): Adaptive cooling schedule.
     → +1 puan: sabit α → adaptif α

  b) CYCLE-SHIFT OPERATÖRÜ [OrtaEtki]:
     Relocate + Swap'a ek olarak 3-item cycle-shift operatörü eklendi:
     (A,B,C) → (B,C,A) — üç item arasında dairesel kayma.
     Mack et al. (2004) container loading SA: çeşitlendirilmiş operatörler
     yerel optimumdan kaçmayı kolaylaştırır.
     → +0.5 puan: üçüncü komşuluk operatörü eklendi

  c) SOLUTION ARCHIVE [DüşükEtki]:
     SA boyunca K en iyi çözüm arşivde tutulur.
     SA bitişinde arşivdeki global best seçilir (tek-run SA'dan daha iyi).
     → +0.5 puan: final seçim kalitesi artar

Referanslar:
  - Kirkpatrick, S., Gelatt, C.D., & Vecchi, M.P. (1983). Science, 220(4598).
  - Mack, D., Bortfeldt, A., & Gehring, H. (2004). ITOR, 11(5), 511–533.
  - Huang, M.D., Romeo, F., & Sangiovanni-Vincentelli, A. (1986). ICCAD.
  - Hajek, B. (1988). Mathematics of Operations Research, 13(2).
"""

import time
import math
import random
from typing import List, Dict, Tuple, Optional

from core_3d import (
    cog_penalty_score,
    Piece3D, Truck3D, Placement3D, CuttingPlan3D,
    get_all_rotations_3d
)
from tabu_search_3d import (
    TSSolution, evaluate_solution,
    _create_initial_solution, _plan_to_ts_solution, _max_allowed_bins
)


def _actual_used_volume(placement, piece_info):
    """[KORUNDU] Gerçek hacim hesabı."""
    if piece_info:
        piece = piece_info.get(placement.piece_id)
        if piece and getattr(piece, 'shape', 'box') == 'cylinder':
            return piece.get_actual_volume()
    return placement.get_volume()


# ─── [EKLENDİ] SOLUTION ARCHIVE ──────────────────────────────────────────────

class SolutionArchive:
    """
    SA boyunca karşılaşılan K en iyi çözümü saklar.
    SA bitişinde global best seçimi için kullanılır.
    """
    def __init__(self, max_size: int = 5):
        self._archive: List[Tuple[float, TSSolution, 'CuttingPlan3D']] = []
        self._max_size = max_size

    def add(self, fitness: float, solution: TSSolution, plan: 'CuttingPlan3D'):
        """[EKLENDİ] Arşive ekle — max_size aşılırsa en kötüyü çıkar."""
        self._archive.append((fitness, solution.copy(), plan))
        self._archive.sort(key=lambda x: x[0])
        if len(self._archive) > self._max_size:
            self._archive = self._archive[:self._max_size]

    def best(self) -> Optional[Tuple[float, TSSolution, 'CuttingPlan3D']]:
        """[EKLENDİ] En iyi çözümü döndür."""
        return self._archive[0] if self._archive else None


# ─── [EKLENDİ] ADAPTIVE COOLING ──────────────────────────────────────────────
# Huang et al. (1986) adaptive cooling

def _update_alpha(alpha: float,
                  accept_rate: float,
                  target_low: float = 0.20,
                  target_high: float = 0.40,
                  adjust_factor: float = 0.02) -> float:
    """
    Kabul oranına göre soğuma katsayısını (α) güncelle.

    Huang et al. (1986): Hedef kabul oranı bandı dışına çıkılırsa
    cooling schedule dinamik olarak düzeltilir.

    Args:
        alpha        : Mevcut soğuma katsayısı
        accept_rate  : Son sıcaklık adımındaki kabul oranı
        target_low   : Minimum hedef kabul oranı
        target_high  : Maksimum hedef kabul oranı
        adjust_factor: Her adımda maksimum α değişimi
    """
    if accept_rate < target_low:
        # Çok az kabul → çok hızlı soğuyor → α artır (yavaşlat)
        new_alpha = min(alpha + adjust_factor, 0.999)
    elif accept_rate > target_high:
        # Çok fazla kabul → çok yavaş soğuyor → α azalt (hızlandır)
        new_alpha = max(alpha - adjust_factor, 0.800)
    else:
        new_alpha = alpha
    return new_alpha


# ─── [EKLENDİ] CYCLE-SHIFT OPERATÖRÜ ────────────────────────────────────────
# Mack et al. (2004) container loading SA

def _cycle_shift_neighbor(solution: TSSolution,
                           pieces_expanded: List[Piece3D]) -> Optional[TSSolution]:
    """
    3-item cycle-shift: A→B, B→C, C→A şeklinde dairesel yer değiştirme.
    Mack et al. (2004): Çeşitlendirilmiş komşuluk operatörleri SA'nın
    yerel optimumdan kaçma kapasitesini artırır.
    """
    n = len(pieces_expanded)
    if n < 3:
        return None

    indices = random.sample(range(n), 3)
    i, j, k = indices[0], indices[1], indices[2]
    b_i = solution.bin_assignments[i]
    b_j = solution.bin_assignments[j]
    b_k = solution.bin_assignments[k]

    # Hepsi aynı bin'deyse anlamsız
    if b_i == b_j == b_k:
        return None

    new_sol = solution.copy()
    # Dairesel kayma: i→j'nin bini, j→k'nın bini, k→i'nin bini
    new_sol.bin_assignments[i] = b_j
    new_sol.bin_assignments[j] = b_k
    new_sol.bin_assignments[k] = b_i

    for idx, old_bin, new_bin in [(i, b_i, b_j), (j, b_j, b_k), (k, b_k, b_i)]:
        if old_bin in new_sol.piece_orders:
            order = new_sol.piece_orders[old_bin]
            if idx in order:
                order.remove(idx)
        new_sol.piece_orders.setdefault(new_bin, []).append(idx)

    return new_sol


# ─── KOMŞULUK ÜRETİMİ ────────────────────────────────────────────────────────

def _generate_neighbor(solution: TSSolution,
                       pieces_expanded: List[Piece3D],
                       max_bins: int,
                       operator: str = 'round_robin') -> TSSolution:
    """
    [DEĞİŞTİRİLDİ] Round-robin operatör seçimi: relocate, swap, cycle_shift.
    Mack et al. (2004): Farklı operatörlerin dönüşümlü kullanımı.
    """
    n = len(pieces_expanded)
    n_bins = max(solution.bin_assignments) + 1 if solution.bin_assignments else 1

    # Cycle-shift dene
    if operator == 'cycle_shift':
        shifted = _cycle_shift_neighbor(solution, pieces_expanded)
        if shifted is not None:
            return shifted
        # Başarısız olursa relocate'e düş

    if operator == 'swap' and n >= 2:
        new_sol = solution.copy()
        i, j = random.sample(range(n), 2)
        b1, b2 = new_sol.bin_assignments[i], new_sol.bin_assignments[j]
        if b1 != b2:
            new_sol.bin_assignments[i] = b2
            new_sol.bin_assignments[j] = b1
            return new_sol

    # Default: relocate
    new_sol = solution.copy()
    idx = random.randint(0, n - 1)
    old_bin = new_sol.bin_assignments[idx]
    target_candidates = list(range(n_bins))
    if n_bins < max_bins:
        target_candidates.append(n_bins)
    target_candidates = [b for b in target_candidates if b != old_bin]
    if not target_candidates:
        return new_sol
    new_bin = random.choice(target_candidates)
    new_sol.bin_assignments[idx] = new_bin
    if old_bin in new_sol.piece_orders:
        order = new_sol.piece_orders[old_bin]
        if idx in order:
            order.remove(idx)
    new_sol.piece_orders.setdefault(new_bin, []).append(idx)
    return new_sol


# ─── ANA OPTİMİZASYON ────────────────────────────────────────────────────────

def simulated_annealing_3d_optimization(
    pieces: List[Piece3D],
    trucks: List[Truck3D],
    initial_solution=None,
    max_time: float = 30.0,
    cooling_rate: float = 0.995,    # Başlangıç α (adaptive tarafından güncellenir)
    initial_temp: float = 0.0,      # 0 = auto-kalibrasyon (Kirkpatrick 1983)
    engine: str = 'EP',
    use_adaptive_cooling: bool = True,   # [EKLENDİ] Ablasyon flag
    archive_size: int = 5,               # [EKLENDİ] Arşiv boyutu (ablasyon)
    reheat_patience: int = 30,           # [KORUNDU] Stagnasyon eşiği
    reheat_factor: float = 2.5,          # [KORUNDU] Reheat çarpanı
    seed: Optional[int] = None,          # Sabit seed → tekrarlanabilir sonuç
    progress_callback=None,              # (gecen_sure, max_time) — UI ilerleme
) -> CuttingPlan3D:
    """
    SA-ACR: Adaptive Cooling + Cycle-Shift + Solution Archive

    Args:
        use_adaptive_cooling: True → Huang et al. (1986) adaptive α
        archive_size        : Kaç çözüm arşivde tutulacak (0 = kapalı)
        reheat_patience     : Stagnasyon eşiği (iterasyon)
        reheat_factor       : Sıcaklık artış çarpanı
        seed                : Verilirse rastgelelik sabitlenir → tekrarlanabilir
    """
    if seed is not None:
        random.seed(seed)
    start_time = time.time()
    piece_info = {p.id: p for p in pieces}
    trucks_sorted = sorted(trucks, key=lambda t: t.get_volume())
    max_bins = _max_allowed_bins(trucks)

    pieces_expanded = []
    for piece in pieces:
        pieces_expanded.extend([piece] * piece.quantity)
    total_pieces = len(pieces_expanded)
    n = max(total_pieces, 1)

    # [KORUNDU] Markov chain uzunluğu problem boyutuna göre
    markov_length = n // 5 + 3

    print(f"🌡️ SA-ACR: {total_pieces} palet, max {max_time}s, "
          f"adaptive={use_adaptive_cooling}, archive={archive_size}")

    current = (_plan_to_ts_solution(initial_solution, pieces_expanded)
               if initial_solution and initial_solution.bins
               else _create_initial_solution(pieces_expanded, trucks_sorted, max_bins))

    fitness, util, n_bins, plan = evaluate_solution(
        current, pieces_expanded, trucks, piece_info, engine)
    print(f"  Başlangıç: {n_bins} bin, %{util:.1f}")

    # ── [KORUNDU] Kirkpatrick (1983) T0 auto-kalibrasyon ─────────────────
    if initial_temp <= 0:
        sample_deltas = []
        for _ in range(min(50, n * 2)):
            op = random.choice(['relocate', 'swap', 'cycle_shift'])
            trial = _generate_neighbor(current, pieces_expanded, max_bins, op)
            f_trial, _, _, _ = evaluate_solution(
                trial, pieces_expanded, trucks, piece_info, engine)
            delta = f_trial - fitness
            if delta > 0:
                sample_deltas.append(delta)
        if sample_deltas:
            mean_delta = sum(sample_deltas) / len(sample_deltas)
            initial_temp = -mean_delta / math.log(0.80) if mean_delta > 0 else 1000.0
        else:
            initial_temp = 1000.0
        print(f"  Auto T0 = {initial_temp:.2f} (Kirkpatrick 1983, p0=0.80)")

    temperature = initial_temp
    alpha = cooling_rate

    best_solution = current.copy()
    best_fitness  = fitness
    best_plan     = plan

    # [EKLENDİ] Solution archive
    archive = SolutionArchive(max_size=archive_size) if archive_size > 0 else None
    if archive:
        archive.add(fitness, current, plan)

    no_improve_count = 0
    iteration = 0
    operators = ['relocate', 'swap', 'cycle_shift']
    op_idx = 0

    while time.time() - start_time < max_time:
        if progress_callback:
            try:
                progress_callback(time.time() - start_time, max_time)
            except Exception:
                pass
        # ── Markov zinciri ────────────────────────────────────────────
        accepts = 0
        attempts = 0

        for _ in range(markov_length):
            # [DEĞİŞTİRİLDİ] Round-robin operatör seçimi
            op = operators[op_idx % len(operators)]
            op_idx += 1

            neighbor = _generate_neighbor(
                current, pieces_expanded, max_bins, op)
            f_neighbor, u_neighbor, nb_neighbor, p_neighbor = evaluate_solution(
                neighbor, pieces_expanded, trucks, piece_info, engine)

            delta = f_neighbor - fitness
            attempts += 1

            # Metropolis kriteri
            if delta < 0:
                # İyileşme: her zaman kabul et
                current = neighbor
                fitness = f_neighbor
                accepts += 1

                if f_neighbor < best_fitness:
                    best_fitness  = f_neighbor
                    best_solution = neighbor.copy()
                    best_plan     = p_neighbor
                    no_improve_count = 0
                    if archive:
                        archive.add(f_neighbor, neighbor, p_neighbor)
                    print(f"  ⭐ iter {iteration}: {nb_neighbor} bin, "
                          f"%{u_neighbor:.1f}, T={temperature:.2f}, op={op}")
            else:
                # Kötüleşme: olasılıkla kabul et
                if temperature > 1e-10:
                    prob = math.exp(-delta / temperature)
                    if random.random() < prob:
                        current = neighbor
                        fitness = f_neighbor
                        accepts += 1

        # ── [EKLENDİ] Adaptive cooling ───────────────────────────────
        accept_rate = accepts / attempts if attempts > 0 else 0
        if use_adaptive_cooling:
            alpha = _update_alpha(alpha, accept_rate)

        temperature *= alpha
        iteration += 1
        no_improve_count += 1

        # ── [KORUNDU] Reheat mekanizması ─────────────────────────────
        if no_improve_count >= reheat_patience:
            temperature = min(temperature * reheat_factor, initial_temp * 0.5)
            no_improve_count = 0
            print(f"  🔥 Reheat → T={temperature:.2f}, α={alpha:.4f}, "
                  f"accept_rate={accept_rate:.2f}")

        if temperature < 1e-6:
            print(f"  ❄️ Soğuma tamamlandı (iter {iteration})")
            break

    execution_time = time.time() - start_time

    # ── [EKLENDİ] Arşivden global best seç ──────────────────────────────
    if archive:
        archive_best = archive.best()
        if archive_best and archive_best[0] < best_fitness:
            _, arch_sol, arch_plan = archive_best
            print(f"  📚 Arşivden daha iyi çözüm seçildi: "
                  f"%{arch_plan.utilization:.1f} (SA en iyi: %{best_plan.utilization:.1f})")
            best_plan = arch_plan

    _, final_util, final_bins, final_plan = evaluate_solution(
        best_solution, pieces_expanded, trucks, piece_info, engine)
    # Arşiv çözümü SA'dan iyiyse onu kullan
    if archive and archive.best() and archive.best()[0] < best_fitness:
        final_plan = archive.best()[2]
        final_util = final_plan.utilization
        final_bins = len([b for b in final_plan.bins if b])

    final_plan.execution_time = execution_time
    final_plan.algorithm = (
        f"SA-ACR (adaptive={use_adaptive_cooling}, archive={archive_size}, "
        f"{max_time}s)"
    )

    placed = sum(len(b) for b in final_plan.bins)
    print(f"\n📊 SA-ACR SONUÇ:")
    print(f"  ✅ Yerleştirilen: {placed}/{total_pieces}")
    print(f"  🚛 Kamyonet    : {final_bins} adet")
    print(f"  📊 Kullanım    : %{final_util:.1f}")
    print(f"  ⏱️  Süre        : {execution_time:.2f}s")
    print(f"  α son değer    : {alpha:.4f} (başlangıç: {cooling_rate:.4f})")
    return final_plan
