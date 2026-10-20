# -*- coding: utf-8 -*-
"""
Randomized Constructive Search (RCS) — Monte Carlo Tabanlı 3D Optimizasyon
===========================================================================
Akademik Çerçeve:
  Bu modül "Monte Carlo Randomized Constructive Search" (MC-RCS) adlı
  stokastik bir sezgiseli uygular. Temel Monte Carlo ilkesi — tekrarlı
  rastgele örnekleme ile zor problemlere yaklaşık çözüm üretme —
  Metropolis & Ulam (1949) tarafından tanımlanmış ve Rubinstein & Kroese
  (2004) tarafından kombinatoryal optimizasyona uyarlanmıştır.

  Bu implementasyon MCTS (Monte Carlo Tree Search) değildir.
  Her deneme birbirinden bağımsızdır; aralarında öğrenme mekanizması
  yoktur. Birincil kullanım: çeşitlendirilmiş başlangıç çözümleri
  üretmek ve Multi-Start SA gibi iyileştirici algoritmalara seed sağlamak.

[DEĞİŞTİRİLDİ v2 — Akademik iyileştirmeler]:
  1. Uniform random yerine IMPORTANCE SAMPLING (hacim+ağırlık ağırlıklı)
     → Rubinstein & Kroese (2004) Bölüm 2.3
  2. İstatistiksel özet (mean, std, best, worst) her çalışmada raporlanır
     → Talbi (2009) stokastik algoritma değerlendirme standardı
  3. Fonksiyon adı monte_carlo_3d_optimization olarak korundu (API uyumu)
     ama docstring ve algorithm etiketi RCS terminolojisini kullanır
  4. Best-of-K yapısı daha net; her trial bağımsız (no inter-trial learning)
"""

import random
import math
import time
from typing import List, Dict, Tuple, Optional

from core_3d import (
    Piece3D, Truck3D, CuttingPlan3D,
    get_all_rotations_3d
)
# Ortak yerleştirme motoru — diğer tüm metaheuristiklerle AYNI decoder (EP).
# Eski sürüm MaxRects3D kullanıyordu: destek oranı 0.95 (EP'de 0.75) ve eski
# priority*50 mantığı → adil olmayan farklı fizik. Artık EP kullanılıyor.
from extreme_points_3d import create_packing_engine
from priority_utils import priority_violation_penalty


# ─── YARDIMCI ────────────────────────────────────────────────────────────────

def _actual_used_volume(placement, piece_info):
    """Gerçek hacim: silindir için π·r²·h, kutu için w·l·h."""
    # [KORUNDU] Mevcut hacim hesabı doğru
    if piece_info:
        piece = piece_info.get(placement.piece_id)
        if piece and getattr(piece, 'shape', 'box') == 'cylinder':
            return piece.get_actual_volume()
    return placement.get_volume()


# ─── [EKLENDİ] IMPORTANCE SAMPLING ──────────────────────────────────────────
# Rubinstein & Kroese (2004): Uniform random yerine ağırlıklı dağılım.
# Büyük/ağır parçaları dizinin önüne taşıma olasılığını artırır.
# Bu, "importance sampling" ilkesinin kombinatoryal sıralama problemine
# adaptasyonudur: yüksek katkılı elemanların önce seçilmesi beklenen
# çözüm kalitesini arttırır.

def _importance_weights(piece_list: List[Piece3D]) -> List[float]:
    """
    Her palet için önem ağırlığı hesapla.
    Büyük/ağır paletler daha yüksek ağırlık alır.

    Rubinstein & Kroese (2004): İmportance sampling ağırlıkları
    amaç fonksiyonuna katkıyla orantılı olmalı.
    """
    # [EKLENDİ] Normalize edilmiş hacim + ağırlık kombinasyonu
    if not piece_list:
        return []
    max_vol = max(p.width * p.length * p.height for p in piece_list) or 1
    max_wt  = max(p.weight for p in piece_list) or 1
    weights = []
    for p in piece_list:
        vol_norm = (p.width * p.length * p.height) / max_vol
        wt_norm  = p.weight / max_wt
        # 0.7 hacim + 0.3 ağırlık ağırlıklandırması
        weights.append(0.7 * vol_norm + 0.3 * wt_norm + 1e-6)  # ε: sıfır ağırlık yok
    return weights


def _weighted_shuffle(piece_list: List[Piece3D],
                      weights: List[float],
                      use_importance: bool = True) -> List[Piece3D]:
    """
    Ağırlıklı örnekleme ile karıştır.
    use_importance=False → uniform random (klasik MC)
    use_importance=True  → importance sampling (gelişmiş MC-RCS)

    Uygulama: Weighted reservoir sampling (Efraimidis & Spirakis, 2006)
    """
    # [EKLENDİ] Ağırlıklı karıştırma seçeneği
    if not use_importance:
        result = list(piece_list)
        random.shuffle(result)
        return result

    # Weighted reservoir: her elemana u^(1/w) anahtarı ata, büyükten küçüğe sırala
    keyed = [(piece, random.random() ** (1.0 / w))
             for piece, w in zip(piece_list, weights)]
    keyed.sort(key=lambda x: -x[1])
    return [p for p, _ in keyed]


def _select_rotation_weighted(piece: Piece3D, use_importance: bool = True):
    """
    Rotasyon seçimi: importance sampling ile büyük rotasyonları tercih et.
    En büyük hacim kaplayanı seçme eğilimi — boşa giden alan azalır.
    """
    # [EKLENDİ] Rotasyon için de ağırlıklı seçim
    rotations = get_all_rotations_3d(piece)
    if not rotations:
        return piece.width, piece.length, piece.height, (0, 0, 0)

    if not use_importance or len(rotations) == 1:
        return random.choice(rotations)

    # Büyük hacimli rotasyonu tercih et (aslında tüm rotasyonlar aynı hacim
    # verir; burada "en uzun ekseni dik" rotasyonu tercih edeceğiz)
    # → stabilitenin proxy'si: yüksekliği minimize et
    best = min(rotations, key=lambda r: r[2])   # r[2] = height
    fallback = random.choice(rotations)
    # %60 olasılıkla en stabil rotasyonu, %40 rastgele seç (çeşitlilik)
    return best if random.random() < 0.6 else fallback


# ─── ANA OPTİMİZASYON ────────────────────────────────────────────────────────

def monte_carlo_3d_optimization(
    pieces: List[Piece3D],
    trucks: List[Truck3D],
    iterations: int = 100,
    progress_callback=None,
    initial_solution=None,
    use_importance_sampling: bool = True,   # [EKLENDİ] Açma/kapama anahtarı
    max_time: float = 0.0,   # 0 = sınırsız (yalnız iterasyon); >0 = zaman bütçesi (sn)
    seed: Optional[int] = None,   # Sabit seed → tekrarlanabilir sonuç
) -> CuttingPlan3D:
    """
    Monte Carlo Randomized Constructive Search (MC-RCS) — 3D Araç Yükleme

    Her iterasyonda bağımsız bir tam çözüm oluşturulur; bireyler arası
    öğrenme mekanizması yoktur (no inter-trial learning). En yüksek doluluk
    oranı veren çözüm döndürülür.

    Args:
        pieces              : Palet listesi
        trucks              : Kamyonet listesi
        iterations          : Bağımsız deneme sayısı N (default: 100)
        progress_callback   : İlerleme callback (Streamlit için)
        initial_solution    : Varsa başlangıç seed (FFD vb.)
        use_importance_sampling: True → ağırlıklı permütasyon örnekleme
                                 False → uniform random (klasik MC)

    Returns:
        En yüksek doluluk oranını veren CuttingPlan3D

    Akademik not:
        Talbi (2009) Bölüm 2.1: Randomized constructive heuristics,
        deterministik açgözlü yöntemlere stokastik çeşitlilik ekler.
        Metropolis & Ulam (1949): Monte Carlo ilkesi — rastgele örnekleme
        ile deterministik olmayan problemleri yaklaşık çöz.
    """
    if seed is not None:
        random.seed(seed)
    start_time = time.time()
    piece_info = {p.id: p for p in pieces}

    piece_list = []
    for piece in pieces:
        piece_list.extend([piece] * piece.quantity)
    total_pieces = len(piece_list)

    # [KORUNDU] Başlangıç seed
    best_plan  = initial_solution if initial_solution else None
    best_score = initial_solution.utilization if initial_solution else float('-inf')

    # [EKLENDİ] İstatistik takibi — Talbi (2009) değerlendirme standardı
    trial_scores: List[float] = []
    improved_count = 0

    # [EKLENDİ] Importance sampling ağırlıkları (bir kez hesapla)
    imp_weights = _importance_weights(piece_list) if use_importance_sampling else None

    sampling_mode = "importance" if use_importance_sampling else "uniform"
    print(f"🎲 MC-RCS: {total_pieces} palet, {iterations} iterasyon, "
          f"örnekleme={sampling_mode}")

    for iteration in range(iterations):
        # Zaman bütçesi kontrolü — adil karşılaştırma için erken sonlanma
        if max_time > 0 and (time.time() - start_time) >= max_time:
            print(f"  ⏱️ MC zaman bütçesi doldu (iter {iteration}/{iterations})")
            break
        if progress_callback:
            progress_callback(iteration, iterations)

        # ── [DEĞİŞTİRİLDİ] Ağırlıklı permütasyon örnekleme ──────────────
        # Önceki: random.shuffle(piece_list) — uniform random
        # Yeni:   _weighted_shuffle ile importance sampling
        # Ref: Rubinstein & Kroese (2004) Bölüm 2.3
        if use_importance_sampling and imp_weights:
            shuffled = _weighted_shuffle(piece_list, imp_weights, use_importance=True)
        else:
            shuffled = list(piece_list)
            random.shuffle(shuffled)

        # ── [DEĞİŞTİRİLDİ] Rotasyon seçimi ──────────────────────────────
        # Önceki: random.choice(rotations) — uniform
        # Yeni:   ağırlıklı rotasyon seçimi (stabil yönelim tercihi)
        trial_list = []
        for piece in shuffled:
            w, l, h, rot = _select_rotation_weighted(piece, use_importance_sampling)
            trial_list.append((piece.id, w, l, h, rot, piece))

        # ── Yerleştirme ──────────────────────────────────────────────────
        placements_by_bin, truck_assignments, unfitted_count = pack_trial_3d(
            trial_list, trucks, piece_info
        )

        score = calculate_trial_score_3d(
            placements_by_bin, truck_assignments, trucks,
            unfitted_count, piece_info
        )

        # [EKLENDİ] Sadece tamamlanmış çözümlerin skorunu kaydet
        if unfitted_count == 0 and placements_by_bin:
            tv = sum(
                next(t for t in trucks if t.id == truck_assignments[b]).get_volume()
                for b in placements_by_bin
            )
            uv = sum(
                sum(_actual_used_volume(p, piece_info) for p in pls)
                for pls in placements_by_bin.values()
            )
            trial_util = (uv / tv * 100) if tv > 0 else 0
            trial_scores.append(trial_util)

        if score > best_score:
            best_score = score
            improved_count += 1

            total_waste = 0
            total_volume = 0
            used_volume = 0
            for bin_id, placements in placements_by_bin.items():
                truck_id = truck_assignments[bin_id]
                truck = next(t for t in trucks if t.id == truck_id)
                bin_vol = truck.get_volume()
                used = sum(_actual_used_volume(p, piece_info) for p in placements)
                total_waste += (bin_vol - used)
                total_volume += bin_vol
                used_volume += used

            bins_list = [
                placements_by_bin.get(i, [])
                for i in range(max(placements_by_bin.keys()) + 1)
            ] if placements_by_bin else []

            best_plan = CuttingPlan3D(
                bins=bins_list,
                total_waste=total_waste,
                utilization=(used_volume / total_volume * 100) if total_volume > 0 else 0,
                execution_time=0,
                algorithm=f"MC-RCS ({sampling_mode}, {iterations} iter)",
                truck_assignments=truck_assignments
            )

    execution_time = time.time() - start_time

    # [EKLENDİ] İstatistiksel özet — Talbi (2009) standart raporlama
    if trial_scores:
        mean_util = sum(trial_scores) / len(trial_scores)
        std_util  = math.sqrt(
            sum((s - mean_util) ** 2 for s in trial_scores) / len(trial_scores)
        ) if len(trial_scores) > 1 else 0.0
        print(f"\n📊 MC-RCS İstatistik (N={len(trial_scores)} geçerli trial):")
        print(f"  En iyi : %{max(trial_scores):.2f}")
        print(f"  Ortalama: %{mean_util:.2f} ± {std_util:.2f}")
        print(f"  En kötü: %{min(trial_scores):.2f}")
        print(f"  İyileşme: {improved_count} kez")
    else:
        print("  ⚠️ Geçerli trial bulunamadı (tüm denemeler unfitted var)")

    if best_plan:
        best_plan.execution_time = execution_time
    else:
        best_plan = CuttingPlan3D(
            bins=[], total_waste=0, utilization=0,
            execution_time=execution_time,
            algorithm=f"MC-RCS ({sampling_mode}, {iterations} iter — BAŞARISIZ)",
            truck_assignments={}
        )

    return best_plan


# ─── YERLEŞTIRME (KORUNDU — API değişmedi) ───────────────────────────────────

def pack_trial_3d(
    trial_list: List[Tuple],
    trucks: List[Truck3D],
    piece_info: Dict
) -> Tuple[Dict, Dict, int]:
    """
    Bir trial'ı EP (Extreme Points) motoru ile yerleştir.
    Diğer tüm metaheuristiklerle AYNI decoder — adil karşılaştırma için.

    DÜZELTME: Eski kod tek "açık bin" tutuyordu — parça mevcut araca
    sığmayınca yeni araç açılıyor ve ÖNCEKI araçlara bir daha
    dönülmüyordu. Küçük parçalar yarı boş eski araçlara sığacakken yeni
    araca gidiyordu; MC diğer algoritmalara karşı yapısal olarak
    dezavantajlıydı. Artık FFD/GA decoder'ı gibi TÜM açık binler denenir.
    """
    placements_by_bin = {}
    truck_assignments = {}
    open_packers = {}          # bin_id → packer
    truck_used_count = {t.id: 0 for t in trucks}
    unfitted_count = 0

    if len(trucks) == 0:
        return {}, {}, len(trial_list)

    trucks_sorted = sorted(trucks, key=lambda t: t.get_volume())

    def _open_new_bin():
        for truck in trucks_sorted:
            if truck_used_count[truck.id] < truck.available:
                bid = len(open_packers)
                truck_used_count[truck.id] += 1
                open_packers[bid] = create_packing_engine(
                    truck.width, truck.length, truck.height,
                    engine='EP', heuristic='CP',
                    truck=truck, piece_info=piece_info)
                placements_by_bin[bid] = []
                truck_assignments[bid] = truck.id
                return bid
        return None

    def _try_place(bid, piece_id, w, l, h):
        packer = open_packers[bid]
        result = packer.find_best_position_3d(
            piece_id, w, l, h, allow_rotation=False, respect_gravity=True)
        if result:
            packer.place_piece_3d(piece_id, result)
            last = packer.placements[-1]
            last.bin_id = bid
            placements_by_bin[bid].append(last)
            return True
        return False

    if _open_new_bin() is None:
        return {}, {}, len(trial_list)

    for piece_id, w, l, h, rot, piece in trial_list:
        placed = False
        for bid in list(open_packers.keys()):
            if _try_place(bid, piece_id, w, l, h):
                placed = True
                break
        if not placed:
            new_bid = _open_new_bin()
            if new_bid is not None and _try_place(new_bid, piece_id, w, l, h):
                placed = True
        if not placed:
            unfitted_count += 1

    return placements_by_bin, truck_assignments, unfitted_count


def calculate_trial_score_3d(
    placements_by_bin: Dict,
    truck_assignments: Dict,
    trucks: List[Truck3D],
    unfitted_count: int,
    piece_info: Dict
) -> float:
    """
    Trial skoru — YÜKSEK = daha iyi. Ortak amaç fonksiyonunu
    (core_3d.packing_objective, düşük=iyi) kullanır ve işaretini çevirir.
    Böylece Monte Carlo, Tabu/SA/GA/Island ile AYNI hedefi optimize eder.
    """
    from core_3d import packing_objective
    bins_list = [placements_by_bin.get(i, [])
                 for i in range(max(placements_by_bin.keys()) + 1)
                 ] if placements_by_bin else []
    fitness, _util = packing_objective(
        bins_list, truck_assignments, trucks, piece_info,
        unplaced=unfitted_count, overflow_bins=0)
    return -fitness   # düşük fitness → yüksek skor
