# -*- coding: utf-8 -*-
"""
Greedy 3D Algorithm — EP destekli hızlı yerleştirme

Akademik Referanslar:
  - Lodi, Martello & Vigo (2002): Basit heuristikler
  - Crainic vd. (2008): Extreme Points motoru

Strateji:
  1. En küçük kamyonetten başla (minimum maliyet)
  2. Paletleri hacme göre büyükten küçüğe sırala
  3. Sığmazsa bir sonraki kamyona geç
  4. Hızlı/acil yükler için ideal — "Hızlı Mod"
"""

import time
from typing import List

from core_3d import (gravity_settle_placements, check_stacking_rules,
    Piece3D, Truck3D, CuttingPlan3D,
    get_all_rotations_3d
)
from extreme_points_3d import create_packing_engine


def greedy_3d_optimization(
    pieces: List[Piece3D],
    trucks: List[Truck3D],
    heuristic: str = "CP",
    engine: str = "EP"
) -> CuttingPlan3D:
    """
    Greedy 3D — Hızlı yerleştirme, minimum kamyon kullanımı

    Args:
        pieces: Palet listesi
        trucks: Kamyonet listesi
        heuristic: 'CP' veya 'BLF'
        engine: 'EP' veya 'MR'

    Returns:
        CuttingPlan3D
    """
    start_time = time.time()

    piece_info = {p.id: p for p in pieces}
    trucks_sorted = sorted(trucks, key=lambda t: t.get_volume())

    # Palet listesi
    piece_list = []
    for piece in pieces:
        piece_list.extend([piece] * piece.quantity)
    total_pieces = len(piece_list)

    # Büyükten küçüğe sırala
    piece_list.sort(key=lambda p: -(p.width * p.length * p.height))

    print(f"🚀 Greedy 3D ({engine}): {total_pieces} palet")

    bins_list = []
    truck_assignments = {}
    unfitted = []
    placed_count = 0
    truck_used_count = {t.id: 0 for t in trucks}

    # Kamyonları sırayla kullan
    for truck in trucks_sorted:
        while truck_used_count[truck.id] < truck.available:
            if not piece_list:
                break

            bin_id = len(bins_list)
            truck_used_count[truck.id] += 1

            packer = create_packing_engine(
                truck.width, truck.length, truck.height,
                engine=engine, heuristic=heuristic,
                truck=truck, piece_info=piece_info
            )

            bin_placements = []
            remaining = []

            for piece in piece_list:
                rotations = get_all_rotations_3d(piece)
                if not rotations:
                    rotations = [(piece.width, piece.length, piece.height, (0, 0, 0))]

                # FIX-Y3: first-fit → best-fit rotation.
                # Eski kod ilk uygun rotasyonu bulunca break yapıyordu.
                # Yeni kod tüm rotasyonları değerlendirir ve EP motorunun
                # score fonksiyonuna göre en iyi yerleşimi seçer.
                # Özellikle dar-uzun parçaların yatay/dikey seçiminde
                # doluluk farkı gözlemlendi.
                placed      = False
                best_result = None
                best_score  = float('inf')

                from core_3d import Placement3D as _Pl3D

                for w, l, h, rot in rotations:
                    result = packer.find_best_position_3d(
                        piece.id, w, l, h,
                        allow_rotation=False,
                        respect_gravity=True
                    )
                    if not result:
                        continue
                    # İstiflenme kuralı kontrolü
                    rx, ry, rz, rw, rl, rh, rrot = result
                    _cand = _Pl3D(rx, ry, rz, rw, rl, rh, piece.id, rrot, bin_id)
                    _valid, _ = check_stacking_rules(
                        _cand, piece, packer.placements, piece_info)
                    if not _valid:
                        continue
                    # EP motoru score fonksiyonuyla kıyasla
                    rot_score = packer._score_placement(rx, ry, rz, rw, rl, rh, piece.id)
                    if rot_score < best_score:
                        best_score  = rot_score
                        best_result = result

                if best_result is not None:
                    packer.place_piece_3d(piece.id, best_result)
                    last = packer.placements[-1]
                    last.bin_id = bin_id
                    bin_placements.append(last)
                    placed_count += 1
                    placed = True

                if not placed:
                    remaining.append(piece)

            # ── Boş bin koruması: hiçbir parça yerleşmediyse bu truck tipi
            # için denemeyi durdur — sonsuz boş-bin döngüsünü önler ────────
            if not bin_placements:
                truck_used_count[truck.id] -= 1  # slot'u geri ver
                print(f"  ⚠️ {truck.id}: Hiçbir parça yerleşmedi — truck tipi atlanıyor")
                break  # Bu truck tipiyle devam etme

            piece_list = remaining
            bin_placements = gravity_settle_placements(bin_placements, piece_info=piece_info)
            bins_list.append(bin_placements)
            truck_assignments[bin_id] = truck.id
            print(f"  🚚 Bin {bin_id} ({truck.id}): {len(bin_placements)} palet")

            if not remaining:
                break

    unfitted = piece_list

    # Sonuç hesapla
    total_volume = 0
    used_volume = 0
    for bin_id, placements in enumerate(bins_list):
        if bin_id in truck_assignments:
            for t in trucks:
                if t.id == truck_assignments[bin_id]:
                    total_volume += t.get_volume()
                    break
        used_volume += sum(p.get_volume() for p in placements)

    total_waste = total_volume - used_volume
    utilization = (used_volume / total_volume * 100) if total_volume > 0 else 0
    execution_time = time.time() - start_time

    num_used = len([b for b in bins_list if len(b) > 0])

    print(f"\n📊 Greedy ({engine}) SONUÇ:")
    print(f"  ✅ Yerleştirilen: {placed_count}/{total_pieces}")
    print(f"  🚛 Kamyonet    : {num_used} adet")
    print(f"  📊 Kullanım    : %{utilization:.1f}")
    print(f"  ⏱️  Süre        : {execution_time:.3f}s")

    return CuttingPlan3D(
        bins=bins_list,
        total_waste=total_waste,
        utilization=utilization,
        execution_time=execution_time,
        algorithm=f"Greedy 3D ({engine}+{heuristic})",
        truck_assignments=truck_assignments,
        unfitted_pieces=unfitted,
    )
