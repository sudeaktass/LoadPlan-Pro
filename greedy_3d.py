# -*- coding: utf-8 -*-
"""
Greedy 3D — Online Best-Fit (Açgözlü / Çevrimiçi Taban Çizgisi)
===============================================================
Bu, açgözlü (greedy) paradigmanın katı biçimidir: her adımda YEREL-OPTIMAL
kararı verir. FFD'den TEK değişkende ayrışır (kontrollü ablasyon):

  FFD (=BFD): Çevrimdışı (offline). Parçaları AZALAN BOYUTA göre sıralar,
              sonra best-fit araç seçimiyle yerleştirir.
  Greedy (BF): Çevrimiçi (online). Boyuta göre ön-sıralama YAPMAZ; parçaları
              geliş sırasında işler ve her parçayı, en az boş hacim bırakan
              (= en dolu) uygun araca koyar — yani her adımda YEREL-OPTIMAL
              araç seçimi (Best-Fit). Geriye dönüş ve ileri-bakış yoktur.

İkisi yalnızca AZALAN SIRALAMA'da ayrışır (araç-seçim kuralı best-fit olarak
sabit tutulur). Böylece aradaki doluluk farkı, doğrudan azalan-sıralama
ön-işlemesinin katkısını ölçer. Bu, klasik BF ↔ BFD ayrımıdır
(Johnson, 1973; Coffman, Garey & Johnson, 1997).

Açgözlülük doğrulaması: (1) artımlı — tek tek parça; (2) yerel-optimal seçim
— en dolu uygun araç; (3) geri dönüşsüz — yerleşen parça sökülmez;
(4) ileri-bakışsız — sonraki parçalar simüle edilmez.

NOT: Öncelik (priority) bölgesi korunur; yalnızca BOYUT sıralaması kaldırılır.
Sonunda assert: yerleştirilen + yerleşmeyen == toplam.
"""

import time
from typing import List, Dict, Optional

from core_3d import (
    gravity_settle_placements, check_stacking_rules,
    Piece3D, Truck3D, CuttingPlan3D, Placement3D,
    get_all_rotations_3d
)
from extreme_points_3d import create_packing_engine
from priority_utils import validate_priority, get_priority_zone


def _piece_used_volume(placement, piece_info):
    if piece_info:
        piece = piece_info.get(placement.piece_id)
        if piece and piece.shape == "cylinder":
            return piece.get_actual_volume()
    return placement.get_volume()


def greedy_3d_optimization(
    pieces: List[Piece3D],
    trucks: List[Truck3D],
    heuristic: str = "CP",
    engine: str = "EP",
    w_cog: float = 0.0,          # API uyumu (artık etkisiz)
    use_lookahead: bool = False, # API uyumu (artık etkisiz)
) -> CuttingPlan3D:
    """
    Volume-Sorted FFD baseline.

    NOT: w_cog ve use_lookahead parametreleri API uyumu için tutuldu.
    Eski sürümde combined = ep_score + w_cog*cog*1000 + 0.1*la*1000
    formülü EP skor ölçeğini (-1..+0.7) bozuyordu — kaldırıldı.
    """
    start_time = time.time()
    piece_info = {p.id: p for p in pieces}
    trucks_sorted = sorted(trucks, key=lambda t: t.get_volume())

    piece_list = []
    for piece in pieces:
        piece_list.extend([piece] * piece.quantity)
    total_pieces = len(piece_list)

    # ── ÇEVRİMİÇİ (online) SIRALAMA — FFD'den temel fark burada ──────────
    # Boyuta göre AZALAN sıralama YAPILMAZ; parçalar geliş sırasında işlenir.
    # Yalnızca öncelik (priority) bölgesi korunur: priority=None önce (tırın
    # içi), priority>0 sonra (kapıya yakın). Aynı öncelik grubu içinde stable
    # sort sayesinde GELİŞ SIRASI korunur → çevrimiçi (online) davranış.
    def _greedy_priority_key(p):
        prio = getattr(p, 'priority', None)
        return (0 if prio is None else 1, -(prio if prio is not None else 0))
    piece_list.sort(key=_greedy_priority_key)   # stable → grup içi geliş sırası

    print(f"🚀 Greedy/Online Best-Fit ({engine}): {total_pieces} palet")

    open_bins: Dict[int, dict] = {}
    truck_assignments: Dict[int, str] = {}
    placements_by_bin: Dict[int, List[Placement3D]] = {}
    truck_used_count: Dict[str, int] = {t.id: 0 for t in trucks}
    unfitted: List[Piece3D] = []
    placed_count = 0

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
                print(f"  🚚 Yeni bin: {bid} → {truck.id}")
                return bid
        return None

    def _bin_used_volume(bin_id: int) -> float:
        """Bir aracın o anki dolu hacmi (best-fit ölçütü için)."""
        return sum(_piece_used_volume(p, piece_info)
                   for p in placements_by_bin[bin_id])

    def probe(bin_id: int, piece: Piece3D):
        """
        Parça bu araca KOMUT VERMEDEN (commit etmeden) sığar mı?
        Sığıyorsa aday yerleşim 7'lisini döndürür, yoksa None.
        find_best_position_3d saf sorgudur (motoru değiştirmez) → birden çok
        aracı yoklamak güvenlidir.
        """
        packer = open_bins[bin_id]['packer']
        rotations = get_all_rotations_3d(piece)
        if not rotations:
            rotations = [(piece.width, piece.length, piece.height, (0, 0, 0))]
        for w, l, h, rot in rotations:
            result = packer.find_best_position_3d(
                piece.id, w, l, h, allow_rotation=False, respect_gravity=True)
            if result:
                rx, ry, rz, rw, rl, rh, rrot = result
                cand = Placement3D(rx, ry, rz, rw, rl, rh, piece.id, rrot, bin_id)
                valid, _ = check_stacking_rules(
                    cand, piece, packer.placements, piece_info)
                if valid:
                    return result
        return None

    def commit(bin_id: int, piece: Piece3D, result) -> None:
        """Yoklanan aday yerleşimi kesinleştir."""
        packer = open_bins[bin_id]['packer']
        packer.place_piece_3d(piece.id, result)
        last = packer.placements[-1]
        last.bin_id = bin_id
        placements_by_bin[bin_id].append(last)

    # İlk bini aç
    if open_new_bin() is None:
        return CuttingPlan3D([], 0, 0, 0, "Greedy", {})

    # ── Ana döngü: BEST-FIT (açgözlü yerel-optimal araç seçimi) ──────────
    # Her parça için TÜM açık araçları yokla; sığanlar arasından EN DOLU
    # (en az boş hacim bırakan = best-fit) aracı seç ve oraya yerleştir.
    # Hiç uygun araç yoksa yeni araç aç.
    for piece in piece_list:
        best_bid, best_result, best_used = None, None, -1.0
        for bid in list(open_bins.keys()):
            res = probe(bid, piece)
            if res is not None:
                u = _bin_used_volume(bid)
                if u > best_used:        # en dolu uygun araç → best-fit
                    best_used, best_bid, best_result = u, bid, res
        if best_bid is not None:
            commit(best_bid, piece, best_result)
            placed_count += 1
        else:
            new_bin_id = open_new_bin()
            if new_bin_id is not None:
                res = probe(new_bin_id, piece)
                if res is not None:
                    commit(new_bin_id, piece, res)
                    placed_count += 1
                else:
                    unfitted.append(piece)
            else:
                unfitted.append(piece)

    # Sonuç
    total_volume = 0
    used_volume = 0
    for bin_id in list(placements_by_bin.keys()):
        truck = open_bins[bin_id]['truck']
        placements_by_bin[bin_id] = gravity_settle_placements(
            placements_by_bin[bin_id], piece_info=piece_info)
        total_volume += truck.get_volume()
        used_volume += sum(_piece_used_volume(p, piece_info)
                           for p in placements_by_bin[bin_id])

    max_bin = max(placements_by_bin.keys()) if placements_by_bin else 0
    bins_list = [placements_by_bin.get(i, []) for i in range(max_bin + 1)]
    execution_time = time.time() - start_time
    num_used = len([b for b in bins_list if b])
    utilization = (used_volume / total_volume * 100) if total_volume > 0 else 0
    total_waste = total_volume - used_volume

    print(f"\n📊 Greedy ({engine}) SONUÇ:")
    print(f"  ✅ Yerleştirilen: {placed_count}/{total_pieces}")
    print(f"  🚛 Kamyonet    : {num_used} adet")
    print(f"  📊 Kullanım    : %{utilization:.1f}")
    print(f"  ⏱️  Süre        : {execution_time:.3f}s")

    # ASSERT
    _total_placed = sum(len(b) for b in bins_list)
    assert _total_placed + len(unfitted) == total_pieces, (
        f"Greedy: placed({_total_placed}) + unfitted({len(unfitted)}) "
        f"!= total({total_pieces})"
    )
    assert placed_count == _total_placed, (
        f"Greedy: placed_count({placed_count}) != bins_total({_total_placed})"
    )

    validate_priority(bins_list, piece_info, trucks,
                      truck_assignments, f"Greedy ({engine}+{heuristic})")

    return CuttingPlan3D(
        bins=bins_list,
        total_waste=total_waste,
        utilization=utilization,
        execution_time=execution_time,
        algorithm=f"Greedy/Online Best-Fit ({engine})",
        truck_assignments=truck_assignments,
        unfitted_pieces=unfitted,
    )
