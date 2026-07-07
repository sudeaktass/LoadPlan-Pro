# -*- coding: utf-8 -*-
"""
Minimum Vehicle Selector — Tüm Ürünleri Kapsayan Minimum Araç Seçimi
======================================================================
Yeni kural: "minimum araç" artık "tüm ürünleri kapsayan minimum araç"
demektir. Filo kapasitesi yetersizse algoritma başlamadan ValueError
fırlatılır — hiçbir algoritma eksik çözüm dönemez.

Ayrıca: validate_all_placed() — her algoritmanın sonunda çağrılır.
Bir tek ürün bile eksikse ConstraintViolation atılır.
"""

from typing import List, Optional, Tuple
from dataclasses import dataclass
import copy

from core_3d import Piece3D, Truck3D, CuttingPlan3D
from priority_utils import sort_piece_list_inplace


class ConstraintViolation(Exception):
    """Bir veya daha fazla ürün yerleştirilemediğinde fırlatılır."""
    pass


class NoVehicleAvailable(Exception):
    """Yerleştirme için uygun araç bulunamadığında fırlatılır."""
    pass


class WeightCenterViolation(Exception):
    """Ağırlık merkezi sınır dışına çıktığında fırlatılır."""
    pass


class PriorityConflict(Exception):
    """Öncelik kısıtı sağlanamadığında fırlatılır."""
    pass


class ImpossibleToSolve(Exception):
    """Tüm fallback adımları tükendiğinde fırlatılır."""
    pass


@dataclass
class WeightCenterConfig:
    """
    Ağırlık merkezi sınırları.

    References:
        Ruan, Q. et al. (2013). "A Hybrid Approach for the Vehicle
        Routing Problem with 3D Loading Constraints",
        Computers & OR, 40(8), 2249-2258.

    Standart literatür değerleri:
        Uzunluk ekseni (Y): [0.40, 0.60] — orta %20
        Genişlik ekseni (X): [0.45, 0.55] — orta %10
    """
    min_x_ratio: float = 0.40
    max_x_ratio: float = 0.60
    min_y_ratio: float = 0.45
    max_y_ratio: float = 0.55
    tolerance: float = 0.05


@dataclass
class VehicleSelectionResult:
    """Faz 1 çıktısı."""
    selected_trucks: List[Truck3D]
    total_demand_vol: float
    total_demand_wt: float
    covered_vol: float
    covered_wt: float
    n_truck_slots: int
    log_lines: List[str]


def minimum_vehicle_selector(
    pieces: List[Piece3D],
    trucks: List[Truck3D],
    safety_margin: float = 1.10,
) -> VehicleSelectionResult:
    """
    Tüm siparişlerin MUTLAKA yerleşeceği minimum araç setini seçer.

    YENİ MANTIK (geometrik simülasyon):
        - Teorik hacim toplamına bakmaz
        - Her slot sayısı için GERÇEK 3D FFD simülasyonu çalıştırır
        - Tüm parçalar yerleşene kadar slot eklemeye devam eder
        - 1 araç seçip parça dışarıda kalması imkânsız

    Strateji:
        1. Filo toplam kapasitesi ön kontrolü (ValueError early-exit)
        2. Slot'ları büyükten küçüğe sırala
        3. k = 1, 2, 3, ... için FFD simülasyon dene
        4. all_placed=True olan ilk k → o setle dön
        5. Tüm filo yetmiyorsa ImpossibleToSolve

    Raises:
        ValueError      : Filo toplam kapasitesi YETERSİZ (teorik ön kontrol)
        ImpossibleToSolve: Tüm filo yeterli teorik kapasite ama geometrik
                          olarak yerleşim imkânsız
    """
    log_lines: List[str] = []

    # ── 0. Boş input kontrolü ────────────────────────────────────────────
    if not pieces:
        raise ValueError("❌ Sipariş listesi boş.")
    if not trucks:
        raise ValueError("❌ Araç listesi boş.")

    # ── 1. Toplam talep ──────────────────────────────────────────────────
    total_demand_vol = sum(
        p.get_bounding_volume() * p.quantity for p in pieces
    )
    total_demand_wt = sum(p.weight * p.quantity for p in pieces)
    n_pieces = sum(p.quantity for p in pieces)

    eff_demand_vol = total_demand_vol * safety_margin
    eff_demand_wt = total_demand_wt * safety_margin

    log_lines.append(
        f"📦 Toplam talep: {n_pieces} parça | "
        f"{total_demand_vol/1e9:.2f} m³ | {total_demand_wt:.0f} kg"
    )
    log_lines.append(
        f"🛡️  Emniyet payı: ×{safety_margin:.2f} → "
        f"hedef {eff_demand_vol/1e9:.2f} m³"
    )

    # ── 2. Erken kontrol: filo toplam kapasitesi yeterli mi? ────────────
    fleet_volume = sum(t.get_volume() * t.available for t in trucks)
    fleet_weight = sum(t.capacity * t.available for t in trucks)

    if total_demand_vol > fleet_volume or total_demand_wt > fleet_weight:
        raise ValueError(
            f"❌ Filo toplam kapasitesi yetersiz!\n"
            f"Gereken hacim: {total_demand_vol/1e9:.2f} m³, "
            f"filo hacmi: {fleet_volume/1e9:.2f} m³\n"
            f"Gereken ağırlık: {total_demand_wt:.0f} kg, "
            f"filo kapasitesi: {fleet_weight:.0f} kg"
        )

    # ── 3. Slot listesi: her available adet ayrı slot ───────────────────
    truck_slots: List[Truck3D] = []
    for truck in trucks:
        for _ in range(truck.available):
            slot = copy.copy(truck)
            slot.available = 1
            truck_slots.append(slot)

    # Büyükten küçüğe (kapasite öncelikli)
    truck_slots.sort(
        key=lambda t: (t.get_volume(), t.capacity),
        reverse=True,
    )

    total_pieces_count = sum(p.quantity for p in pieces)
    log_lines.append(
        f"🔄 Geometrik simülasyon başlıyor (1..{len(truck_slots)} slot)..."
    )

    # ── 4. Geometrik FFD simülasyonu ile minimum k bul ──────────────────
    chosen_set: Optional[List[Truck3D]] = None
    chosen_k = 0

    for k in range(1, len(truck_slots) + 1):
        candidate_set = truck_slots[:k]
        types_summary = ", ".join(
            f"{t.id}" for t in candidate_set
        )

        # Her slot için available=1 → konsolide etmeden FFD'ye geçir
        sim_placed, sim_total = _simulate_ffd(pieces, candidate_set)

        if sim_placed == sim_total:
            log_lines.append(
                f"🔄 {k} slot deneniyor [{types_summary}]: "
                f"{sim_placed}/{sim_total} ürün yerleşti ✅"
            )
            chosen_set = candidate_set
            chosen_k = k
            break
        else:
            log_lines.append(
                f"🔄 {k} slot deneniyor [{types_summary}]: "
                f"{sim_placed}/{sim_total} ürün yerleşti ❌ "
                f"({sim_total - sim_placed} sığmadı)"
            )

    if chosen_set is None:
        # Tüm filo yine yeterli değil — geometrik olarak imkânsız
        log_lines.append(
            "❌ Tüm filo kullanılsa dahi tüm ürünler yerleştirilemiyor"
        )
        raise ImpossibleToSolve(
            "❌ Tüm filo kullanılsa dahi tüm ürünler yerleştirilemiyor.\n"
            "Geometrik kısıtlar (boyut, ağırlık merkezi, istiflenme) "
            "nedeniyle çözüm bulunamadı. Filoyu büyütün veya parça "
            "boyutlarını gözden geçirin."
        )

    # ── 5. Aynı id'li slotları konsolide et ─────────────────────────────
    consolidated_map = {}
    for slot in chosen_set:
        if slot.id in consolidated_map:
            consolidated_map[slot.id].available += 1
        else:
            consolidated_map[slot.id] = copy.copy(slot)
            consolidated_map[slot.id].available = 1
    consolidated = list(consolidated_map.values())

    covered_vol = sum(t.get_volume() for t in chosen_set)
    covered_wt = sum(t.capacity for t in chosen_set)

    types_summary = ", ".join(
        f"{t.id}×{t.available}" for t in consolidated
    )
    log_lines.append(
        f"✅ Minimum slot sayısı: {chosen_k} ({types_summary})"
    )
    log_lines.append(
        f"📊 Toplam kapasite: {covered_vol/1e9:.2f} m³ | {covered_wt:.0f} kg"
    )

    return VehicleSelectionResult(
        selected_trucks=consolidated,
        total_demand_vol=total_demand_vol,
        total_demand_wt=total_demand_wt,
        covered_vol=covered_vol,
        covered_wt=covered_wt,
        n_truck_slots=chosen_k,
        log_lines=log_lines,
    )


def _simulate_ffd(
    pieces: List[Piece3D],
    truck_slots: List[Truck3D],
) -> tuple:
    """
    GERÇEK 3D FFD simülasyonu — kapasite + yerleşim + istiflenme.

    Her slot için ayrı EP packer instance'ı kurar; FFD pattern (volume sort
    + first fit) ile parçaları yerleştirir. Geometrik kontroller:
      - AABB çakışma (extreme_points içinde)
      - Gravity support (extreme_points içinde)
      - Stacking rules (check_stacking_rules)
      - Ağırlık kapasitesi (truck.capacity)

    Returns:
        (placed_count, total_count)
    """
    from core_3d import Placement3D, get_all_rotations_3d, check_stacking_rules
    from extreme_points_3d import create_packing_engine

    piece_info = {p.id: p for p in pieces}

    # quantity expansion
    piece_list: List[Piece3D] = []
    for p in pieces:
        piece_list.extend([p] * p.quantity)
    total = len(piece_list)

    # Öncelik sıralaması — priority_utils ile tüm algoritmalarla tutarlı
    sort_piece_list_inplace(piece_list)

    # Her slot için bir packer kur
    packers = []
    for slot in truck_slots:
        try:
            pk = create_packing_engine(
                slot.width, slot.length, slot.height,
                engine="EP", heuristic="CP",
                truck=slot, piece_info=piece_info,
            )
            packers.append({'truck': slot, 'packer': pk, 'placements': []})
        except Exception:
            return 0, total

    placed = 0
    for piece in piece_list:
        ok = False
        rotations = get_all_rotations_3d(piece)
        if not rotations:
            rotations = [(piece.width, piece.length, piece.height, (0, 0, 0))]

        for bin_idx, slot_data in enumerate(packers):
            packer = slot_data['packer']
            truck = slot_data['truck']

            # Ağırlık kontrolü
            current_w = sum(
                piece_info[pl.piece_id].weight for pl in packer.placements
                if pl.piece_id in piece_info
            )
            if current_w + piece.weight > truck.capacity:
                continue

            placed_in_bin = False
            for w, l, h, _rot in rotations:
                result = packer.find_best_position_3d(
                    piece.id, w, l, h,
                    allow_rotation=False, respect_gravity=True
                )
                if not result:
                    continue
                rx, ry, rz, rw, rl, rh, rrot = result
                cand = Placement3D(rx, ry, rz, rw, rl, rh, piece.id, rrot, bin_idx)
                valid, _ = check_stacking_rules(
                    cand, piece, packer.placements, piece_info
                )
                if not valid:
                    continue
                packer.place_piece_3d(piece.id, result)
                placed_in_bin = True
                break

            if placed_in_bin:
                placed += 1
                ok = True
                break

        if not ok:
            # Bu parça hiçbir slota sığmadı — devam et, sayım yapalım
            pass

    return placed, total


# ─── KISIT DOĞRULAMASI ─────────────────────────────────────────────────────

def validate_all_placed(
    pieces: List[Piece3D],
    plan: CuttingPlan3D,
) -> bool:
    """
    Tüm ürünler yerleşmiş mi kontrol et. İhlal varsa ConstraintViolation.

    Bir Piece3D'nin 'quantity' adet kopyası vardır — her kopya plan içinde
    aynı piece_id ile temsil edilir. Sayım: piece_id başına yerleşen kopya.

    Raises:
        ConstraintViolation: Bir veya daha fazla ürün yerleşmediyse.
    """
    # Hedef: piece_id → beklenen adet
    expected: dict = {}
    for p in pieces:
        expected[p.id] = expected.get(p.id, 0) + p.quantity

    # Plan'da gerçekten yerleşen: piece_id → fiili adet
    actual: dict = {}
    for bin_placements in (plan.bins or []):
        for placement in bin_placements:
            pid = placement.piece_id
            actual[pid] = actual.get(pid, 0) + 1

    # Eksikleri tespit et
    missing: dict = {}
    for pid, need in expected.items():
        got = actual.get(pid, 0)
        if got < need:
            missing[pid] = need - got

    if missing:
        total_missing = sum(missing.values())
        details = ", ".join(f"{pid}×{count}" for pid, count in missing.items())
        raise ConstraintViolation(
            f"❌ Kısıt ihlali: {total_missing} ürün yerleştirilmedi → {details}"
        )
    return True


def format_validation_summary(pieces: List[Piece3D], plan: CuttingPlan3D) -> str:
    """UI logu için özet."""
    total = sum(p.quantity for p in pieces)
    placed = sum(len(b) for b in (plan.bins or []))
    return f"{placed}/{total} ürün yerleştirildi"


def weight_center_ok(
    plan: CuttingPlan3D,
    pieces: List[Piece3D],
    trucks: List[Truck3D],
    config: WeightCenterConfig = None,
) -> bool:
    """
    Plan'ın tüm bin'lerinin ağırlık merkezi sınır içinde mi?

    References:
        Ruan et al. (2013), Equation (3)-(5), pp. 2251

    Args:
        plan   : Algoritma çıktısı
        pieces : Sipariş listesi (piece_info için)
        trucks : Araç listesi
        config : WeightCenterConfig (None = default değerler)

    Returns:
        True  → Tüm bin'ler geçerli
        False → En az bir bin'de CoG sınır dışı
    """
    if config is None:
        config = WeightCenterConfig()

    piece_info = {p.id: p for p in pieces}
    trucks_by_id = {t.id: t for t in trucks}

    for bin_id, placements in enumerate(plan.bins or []):
        if not placements:
            continue
        truck_id = (plan.truck_assignments or {}).get(bin_id)
        if truck_id is None or truck_id not in trucks_by_id:
            continue
        truck = trucks_by_id[truck_id]

        # Ağırlıklı CoG hesabı
        total_w = 0.0
        weighted_x = 0.0
        weighted_y = 0.0
        for pl in placements:
            if pl.piece_id not in piece_info:
                continue
            w = piece_info[pl.piece_id].weight
            cx = pl.x + pl.width / 2.0
            cy = pl.y + pl.length / 2.0
            total_w += w
            weighted_x += w * cx
            weighted_y += w * cy

        if total_w <= 1e-6:
            continue

        cog_x = weighted_x / total_w
        cog_y = weighted_y / total_w

        # Normalize
        norm_x = cog_x / truck.width if truck.width > 0 else 0.5
        norm_y = cog_y / truck.length if truck.length > 0 else 0.5

        x_ok = (config.min_x_ratio - config.tolerance
                <= norm_x <=
                config.max_x_ratio + config.tolerance)
        y_ok = (config.min_y_ratio - config.tolerance
                <= norm_y <=
                config.max_y_ratio + config.tolerance)

        if not (x_ok and y_ok):
            return False

    return True


def diagnose_unplaced(
    pieces: List[Piece3D],
    plan: CuttingPlan3D,
) -> dict:
    """
    Yerleşmeyen parçaların tanısını döndürür.

    Returns:
        {
            "missing_count": int,
            "missing_by_id": {piece_id: count, ...},
            "priority_critical": [piece_id, ...],  # priority=1 olan eksikler
        }
    """
    expected: dict = {}
    for p in pieces:
        expected[p.id] = expected.get(p.id, 0) + p.quantity

    actual: dict = {}
    for bin_placements in (plan.bins or []):
        for placement in bin_placements:
            actual[placement.piece_id] = actual.get(placement.piece_id, 0) + 1

    piece_by_id = {p.id: p for p in pieces}
    missing_by_id: dict = {}
    priority_critical: List[str] = []
    for pid, need in expected.items():
        got = actual.get(pid, 0)
        diff = need - got
        if diff > 0:
            missing_by_id[pid] = diff
            piece = piece_by_id.get(pid)
            if piece and piece.priority == 1:
                priority_critical.append(pid)

    return {
        "missing_count": sum(missing_by_id.values()),
        "missing_by_id": missing_by_id,
        "priority_critical": priority_critical,
    }
