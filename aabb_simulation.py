# -*- coding: utf-8 -*-
"""
AABB Collision Simulation & Swap Operator Foundation
=====================================================
3D Axis-Aligned Bounding Box çakışma testi + swap önizleme.

References:
    Ericson, C. (2004). "Real-Time Collision Detection".
    Morgan Kaufmann, pp. 79-82 — AABB SAT (Separating Axis Theorem).

    Glover, F. (1989). "Tabu Search — Part I". ORSA Journal on
    Computing, 1(3), 190-206 — swap operator tasarımı.

NOT (Tez Savunması):
    Bu modül 3D çakışma testi (AABB) için tam doğru bir implementasyondur.
    swap_priority_positions(), priority+CoG çakışmalarında öncelikli
    swap denemesi yapar; mevcut bin'in plan'ından bir parçayı kaldırıp
    önceliği yüksek parçayı yerine simüle eder. Başarılı olursa plan'ı
    günceller; başarısız olursa fallback chain'in tam-filo retry adımına
    devreder. Tam bir Tabu Search swap operatörü (geri alma + komşuluk
    arama) gelecek çalışma kapsamındadır.
"""

from typing import List, Optional, Tuple, Dict
from dataclasses import dataclass

from core_3d import Piece3D, Truck3D, Placement3D, CuttingPlan3D


@dataclass
class BoundingBox:
    """Axis-aligned bounding box (mm cinsinden)."""
    x_min: float
    x_max: float
    y_min: float
    y_max: float
    z_min: float
    z_max: float

    @classmethod
    def from_placement(cls, p: Placement3D) -> 'BoundingBox':
        return cls(
            x_min=p.x, x_max=p.x + p.width,
            y_min=p.y, y_max=p.y + p.length,
            z_min=p.z, z_max=p.z + p.height,
        )


@dataclass
class SimResult:
    """Simülasyon çıktısı."""
    ok: bool
    reason: Optional[str] = None


@dataclass
class SwapResult:
    """Swap operatörü çıktısı."""
    success: bool
    reason: Optional[str] = None
    new_plan: Optional[CuttingPlan3D] = None


def aabb_intersects(a: BoundingBox, b: BoundingBox) -> bool:
    """
    İki AABB çakışıyor mu? Separating Axis Theorem (SAT) ile O(1).

    References:
        Ericson (2004), Section 4.2.1, pp. 79-80

    Returns:
        True iff hiçbir eksen boyunca ayrılamıyorlar.
    """
    return not (
        a.x_max <= b.x_min or b.x_max <= a.x_min or
        a.y_max <= b.y_min or b.y_max <= a.y_min or
        a.z_max <= b.z_min or b.z_max <= a.z_min
    )


def simulate_placement(
    truck: Truck3D,
    existing_placements: List[Placement3D],
    candidate_x: float,
    candidate_y: float,
    candidate_z: float,
    candidate_w: float,
    candidate_l: float,
    candidate_h: float,
) -> SimResult:
    """
    Aday parçanın yerleştirilmesi geçerli mi?
    AABB SAT ile O(n) çakışma testi yapar.

    References:
        Ericson (2004), Section 4.2.1
    """
    new_box = BoundingBox(
        x_min=candidate_x, x_max=candidate_x + candidate_w,
        y_min=candidate_y, y_max=candidate_y + candidate_l,
        z_min=candidate_z, z_max=candidate_z + candidate_h,
    )

    # Araç sınırları
    if (new_box.x_max > truck.width or
            new_box.y_max > truck.length or
            new_box.z_max > truck.height or
            new_box.x_min < 0 or new_box.y_min < 0 or new_box.z_min < 0):
        return SimResult(ok=False, reason="BOUNDARY_EXCEEDED")

    # Mevcut parçalarla çakışma
    for existing in existing_placements:
        existing_box = BoundingBox.from_placement(existing)
        if aabb_intersects(new_box, existing_box):
            return SimResult(
                ok=False,
                reason=f"OVERLAP_WITH_{existing.piece_id}"
            )

    return SimResult(ok=True)


def get_front_zone_placements(
    bin_placements: List[Placement3D],
    truck: Truck3D,
    front_ratio: float = 0.5,
) -> List[Placement3D]:
    """
    Bin'in kapı tarafındaki (Y > truck.length * (1-front_ratio)) parçalar.
    Default: kapıya yakın %50'lik bölge.
    """
    threshold = truck.length * (1.0 - front_ratio)
    return [p for p in bin_placements if p.y >= threshold]


def swap_priority_positions(
    plan: CuttingPlan3D,
    pieces: List[Piece3D],
    trucks: List[Truck3D],
    unplaced_piece: Piece3D,
    weight_center_config=None,
) -> SwapResult:
    """
    Önceliği yüksek (priority=1) ama yerleşemeyen parça için
    mevcut bin'lerden swap denemesi yapar.

    Algoritma:
      1. Her bin için, kapı bölgesindeki en düşük öncelikli parçayı bul
      2. O parçayı kaldırıp unplaced_piece'i yerine simüle et
      3. AABB çakışma testi — geçerse ağırlık merkezini kontrol et
      4. Hepsi geçerse plan'ı güncelle; geçmezse SwapResult(False)

    NOT: Bu basitleştirilmiş swap'tır. Kaldırılan parça için yeniden
    yerleştirme yapılmaz — onun yeri de boşaltılır, fallback chain
    ileride o parçayı yeniden yerleştirir. Gerçek Tabu-style swap
    operatörü gelecek çalışma kapsamındadır.

    References:
        Glover (1989) — swap operator tasarımı
    """
    from minimum_vehicle_selector import weight_center_ok, WeightCenterConfig

    if weight_center_config is None:
        weight_center_config = WeightCenterConfig()

    if unplaced_piece.priority != 1:
        return SwapResult(False, "NOT_PRIORITY_1")

    truck_by_id: Dict[str, Truck3D] = {t.id: t for t in trucks}

    for bin_id, bin_placements in enumerate(plan.bins or []):
        if not bin_placements:
            continue
        truck_id = (plan.truck_assignments or {}).get(bin_id)
        if not truck_id or truck_id not in truck_by_id:
            continue
        truck = truck_by_id[truck_id]

        # Ön bölgede düşük öncelikli parçalar
        front = get_front_zone_placements(bin_placements, truck)
        piece_info = {p.id: p for p in pieces}
        candidates = []
        for pl in front:
            piece = piece_info.get(pl.piece_id)
            if piece is None:
                continue
            # priority=None veya >=2 olanlar swap edilebilir
            if piece.priority is None or piece.priority > unplaced_piece.priority:
                candidates.append((pl, piece))

        if not candidates:
            continue

        # Hacme göre en uygun adayı seç (yakın boyut)
        target_vol = (unplaced_piece.width * unplaced_piece.length *
                      unplaced_piece.height)
        candidates.sort(key=lambda c: abs(
            (c[0].width * c[0].length * c[0].height) - target_vol))

        for swap_pl, swap_piece in candidates:
            # Adım 1: AABB simulation — swap pozisyonuna unplaced koy
            others = [p for p in bin_placements if p.piece_id != swap_pl.piece_id]
            sim = simulate_placement(
                truck, others,
                swap_pl.x, swap_pl.y, swap_pl.z,
                unplaced_piece.width, unplaced_piece.length, unplaced_piece.height,
            )
            if not sim.ok:
                continue

            # Adım 2: Ağırlık merkezi kontrolü — temp plan
            new_placement = Placement3D(
                swap_pl.x, swap_pl.y, swap_pl.z,
                unplaced_piece.width, unplaced_piece.length, unplaced_piece.height,
                unplaced_piece.id, (0, 0, 0), bin_id,
            )
            temp_bins = [list(b) for b in plan.bins]
            temp_bins[bin_id] = others + [new_placement]
            temp_plan = CuttingPlan3D(
                bins=temp_bins,
                total_waste=plan.total_waste,
                utilization=plan.utilization,
                execution_time=plan.execution_time,
                algorithm=plan.algorithm + "+swap",
                truck_assignments=plan.truck_assignments,
                unfitted_pieces=list(plan.unfitted_pieces or []) + [swap_piece],
            )
            if not weight_center_ok(temp_plan, pieces, trucks, weight_center_config):
                continue

            # Başarılı swap
            return SwapResult(
                success=True,
                reason=f"swap_in_bin_{bin_id}_with_{swap_pl.piece_id}",
                new_plan=temp_plan,
            )

    return SwapResult(False, "NO_VALID_SWAP_FOUND")
