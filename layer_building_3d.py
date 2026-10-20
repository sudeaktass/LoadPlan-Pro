# -*- coding: utf-8 -*-
"""
Layer Building 3D — Wall-Building Heuristic (Optimised v2)
===========================================================
George & Robinson (1980) duvar-inşa sezgiseli.

v2'deki iyileştirmeler:
  - MIN_LAYER_FILL_RATIO  = 0.75  → katman %75 dolmadan kapanmaz
  - MIN_VEHICLE_FILL_RATIO = 0.80 → araç %80 dolmadan yenisi açılmaz
  - Katman derinliği dinamik (ürüne göre en küçük yeterli değer)
  - Katman boşlukları küçük ürünlerle doldurulur (gap packing)
  - SMALL_ITEM_THRESHOLD = 0.05 m³ = 50 000 cm³ eşiği

Sonunda assert: yerleştirilen + yerleşmeyen == toplam.
"""

import time
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field

from core_3d import (
    Piece3D, Truck3D, Placement3D, CuttingPlan3D,
    get_all_rotations_3d, check_collision_with_list,
    check_support_3d, check_stacking_rules,
    DEFAULT_SUPPORT_RATIO, piece_used_volume as _actual_used_volume
)
from priority_utils import sort_piece_list_inplace, validate_priority, get_priority_zone

# ─────────────────────────────────────────────────────────────────────────────
# Parametreler
# ─────────────────────────────────────────────────────────────────────────────
MIN_LAYER_FILL_RATIO   = 0.75   # Katman min %75 dolmadan kapanmaz
MIN_VEHICLE_FILL_RATIO = 0.80   # Araç min %80 dolmadan yenisi açılmaz
MAX_GAP_CM             = 0      # Ürünler arası boşluk — sıfır (tam yapışık)
SMALL_ITEM_THRESHOLD   = 50_000 # cm³ — bu altı "küçük ürün"


# _actual_used_volume artık core_3d.piece_used_volume'dan import ediliyor
# (yukarıdaki import satırına bakınız). Buradaki yerel kopya kaldırıldı —
# davranış birebir aynı, tek fark tanımın tek yerde durması.


@dataclass
class Layer:
    y_start: int
    depth: int
    placements: List[Placement3D] = field(default_factory=list)
    layer_index: int = 0


@dataclass
class LayerResult:
    layers: List[Layer]
    bin_id: int
    truck_id: str
    utilization: float

    def get_operator_instructions(self) -> str:
        lines = [f"Kamyon: {self.truck_id} (Doluluk: %{self.utilization:.1f})"]
        lines.append("=" * 50)
        for layer in self.layers:
            lines.append(
                f"\nDUVAR {layer.layer_index + 1} "
                f"(Y: {layer.y_start}-{layer.y_start + layer.depth} cm, "
                f"Kalinlik: {layer.depth} cm)"
            )
            lines.append("-" * 40)
            for p in layer.placements:
                lines.append(
                    f"  - Palet {p.piece_id}: "
                    f"pozisyon ({p.x}, {p.y}, {p.z}) "
                    f"boyut {p.width}x{p.length}x{p.height}"
                )
            lines.append(f"  Toplam: {len(layer.placements)} palet")
        return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Katman içi 2D yerleştirici
# ─────────────────────────────────────────────────────────────────────────────

class WallPacker2D:
    """Bottom-Left 2D packing — katman içi."""

    def __init__(self, wall_width, wall_height, wall_depth, y_start,
                 truck=None, piece_info=None, truck_placements=None):
        self.wall_width   = wall_width
        self.wall_height  = wall_height
        self.wall_depth   = wall_depth
        self.y_start      = y_start
        self.truck        = truck
        self.piece_info   = piece_info or {}
        self.placements: List[Placement3D] = []
        self.truck_placements = (truck_placements
                                 if truck_placements is not None else [])
        self.candidate_points: List[Tuple[int, int]] = [(0, 0)]

    def try_place(self, piece: Piece3D, bin_id: int = 0) -> Optional[Placement3D]:
        rotations = get_all_rotations_3d(piece)
        if not rotations:
            rotations = [(piece.width, piece.length, piece.height, (0, 0, 0))]

        best_score     = float('inf')
        best_placement = None

        for w, l, h, rot in rotations:
            if piece.shape == 'cylinder':
                l = w
            if l > self.wall_depth:
                continue
            for cx, cz in self.candidate_points:
                if cx + w > self.wall_width or cz + h > self.wall_height:
                    continue
                candidate = Placement3D(cx, self.y_start, cz, w, l, h,
                                        piece.id, rot, bin_id)
                if check_collision_with_list(candidate, self.placements,
                                             piece_info=self.piece_info):
                    continue
                if cz > 0:
                    if not check_support_3d(candidate, self.placements,
                                            min_support_ratio=DEFAULT_SUPPORT_RATIO,
                                            piece_info=self.piece_info):
                        continue
                    if piece.id in self.piece_info:
                        valid, _ = check_stacking_rules(
                            candidate, piece, self.placements, self.piece_info)
                        if not valid:
                            continue
                if self.truck and piece.id in self.piece_info:
                    all_loaded = list(self.truck_placements) + list(self.placements)
                    current_weight = sum(
                        self.piece_info[p.piece_id].weight for p in all_loaded
                        if p.piece_id in self.piece_info)
                    if current_weight + piece.weight > self.truck.capacity:
                        return None
                score = cz * 10000 + cx * 10
                if score < best_score:
                    best_score     = score
                    best_placement = candidate

        if best_placement:
            self.placements.append(best_placement)
            self._update_candidates(best_placement)

        return best_placement

    def _update_candidates(self, placed: Placement3D):
        new_pts = [
            (placed.x + placed.width, placed.z),
            (placed.x, placed.z + placed.height),
        ]
        for pt in new_pts:
            if (pt[0] <= self.wall_width and pt[1] <= self.wall_height
                    and pt not in self.candidate_points):
                self.candidate_points.append(pt)
        self.candidate_points.sort(key=lambda p: p[1] * 10000 + p[0])


# ─────────────────────────────────────────────────────────────────────────────
# Katman derinliği seçimi
# ─────────────────────────────────────────────────────────────────────────────

def _choose_layer_depth(pieces: List[Piece3D], remaining_length: int,
                        strategy: str = "adaptive") -> int:
    """
    Katman derinliğini (Y ekseni) seç.

    strategy (UI "Strateji" seçicisiyle birebir — eskiden seçici kozmetikti,
    değer fonksiyona hiç ulaşmıyordu):
      "adaptive" → adayların MİNİMUM min-Y'si: aynı katmana yalnızca aynı
                   (veya daha küçük) derinlikte ürünler girer, katman-içi
                   boşluk sıfıra yakın (önceki tek davranış).
      "median"   → adayların medyan min-Y'si: orta kalınlık, karışık
                   boyutlarda katman sayısı/doluluk dengesi.
      "max"      → adayların MAKSİMUM min-Y'si: derin katman, az katman
                   sayısı; homojen-iri yüklerde hızlı dolum.
    """
    if not pieces:
        return remaining_length

    candidates = []
    for piece in pieces[:15]:
        rots = get_all_rotations_3d(piece)
        if not rots:
            rots = [(piece.width, piece.length, piece.height, (0, 0, 0))]
        min_y = min(rot[1] for rot in rots)
        if 0 < min_y <= remaining_length:
            candidates.append(min_y)

    if not candidates:
        return remaining_length

    if strategy == "max":
        return max(candidates)
    if strategy == "median":
        candidates.sort()
        return candidates[len(candidates) // 2]
    return min(candidates)          # "adaptive" (varsayılan)


# ─────────────────────────────────────────────────────────────────────────────
# Katman doluluk oranı
# ─────────────────────────────────────────────────────────────────────────────

def _layer_fill_ratio(placements: List[Placement3D],
                      piece_info: Dict,
                      layer_depth: int,
                      truck_width: int,
                      truck_height: int) -> float:
    layer_vol = layer_depth * truck_width * truck_height
    if layer_vol <= 0:
        return 0.0
    used = sum(_actual_used_volume(p, piece_info) for p in placements)
    return used / layer_vol


def _vehicle_fill_ratio(placements: List[Placement3D],
                        piece_info: Dict,
                        truck: Truck3D) -> float:
    truck_vol = truck.get_volume()
    if truck_vol <= 0:
        return 0.0
    used = sum(_actual_used_volume(p, piece_info) for p in placements)
    return used / truck_vol


# ─────────────────────────────────────────────────────────────────────────────
# Ana fonksiyon
# ─────────────────────────────────────────────────────────────────────────────

def layer_building_3d_optimization(
    pieces: List[Piece3D],
    trucks: List[Truck3D],
    use_guillotine: bool = False,
    depth_extend_max_ratio: float = 0.0,
    use_lookahead: bool = False,
    depth_strategy: str = "adaptive",   # 'adaptive' | 'median' | 'max' (UI Strateji)
) -> CuttingPlan3D:
    """
    Wall-Building heuristic — optimised v2.

    Temel farklar v1'e göre:
    • Katman derinliği dinamik ve depth_strategy ile seçilebilir
    • Katman %75 dolmadan kapanmaz; boşluklar küçük ürünlerle doldurulur
    • Araç %80 dolmadan yeni araç açılmaz
    • Büyük→küçük ürün sıralaması her katmanda yenilenir
    """
    start_time = time.time()
    piece_info  = {p.id: p for p in pieces}

    # Büyük araçları önce dene (daha az araç kullan)
    trucks_sorted = sorted(trucks, key=lambda t: t.get_volume(), reverse=True)

    # quantity'yi aç
    piece_list: List[Piece3D] = []
    for piece in pieces:
        piece_list.extend([piece] * piece.quantity)
    total_pieces = len(piece_list)

    # Öncelik: priority_utils ile tutarlı sıralama
    sort_piece_list_inplace(piece_list)

    # Küçük / büyük ayrımı (gap filling için)
    small_threshold = SMALL_ITEM_THRESHOLD

    print(f"[LB] Layer Building v2: {total_pieces} palet, "
          f"min katman doluluk %{MIN_LAYER_FILL_RATIO*100:.0f}, "
          f"min arac doluluk %{MIN_VEHICLE_FILL_RATIO*100:.0f}")

    all_layer_results: List[LayerResult] = []
    bins_list:         List[List[Placement3D]] = []
    truck_assignments: Dict[int, str] = {}
    truck_used_count:  Dict[str, int]  = {t.id: 0 for t in trucks}
    placed_count  = 0
    remaining_pieces = list(piece_list)

    for truck in trucks_sorted:
        if not remaining_pieces:
            break

        while truck_used_count[truck.id] < truck.available and remaining_pieces:
            truck_used_count[truck.id] += 1
            bin_id = len(bins_list)

            truck_w = truck.width
            truck_h = truck.height
            truck_l = truck.length

            layers_this_truck: List[Layer]       = []
            truck_placements:  List[Placement3D] = []
            y_cursor = 0

            # Bu araç için deneyeceğimiz parçalar
            items_to_place     = list(remaining_pieces)
            remaining_in_truck: List[Piece3D] = []

            # ── Katman döngüsü ────────────────────────────────────────
            while items_to_place and y_cursor < truck_l:
                remaining_length = truck_l - y_cursor

                # Dinamik katman derinliği
                # Zone-ertelenmiş öncelik parçaları derinlik hesabını bozmasın
                depth_candidates = [
                    p for p in items_to_place
                    if not (p.priority is not None and p.priority > 0
                            and y_cursor < get_priority_zone(truck_l, p.priority)[0])
                ] or items_to_place  # fallback: hepsi ertelendiyse orijinal listeyi kullan
                layer_depth = _choose_layer_depth(depth_candidates,
                                                   remaining_length,
                                                   strategy=depth_strategy)
                if layer_depth <= 0 or layer_depth > remaining_length:
                    remaining_in_truck.extend(items_to_place)
                    items_to_place = []
                    break

                layer = Layer(y_start=y_cursor, depth=layer_depth,
                              layer_index=len(layers_this_truck))

                # ── Faz 1: Büyük→küçük sıralı 2D packing ────────────
                packer2d = WallPacker2D(
                    truck_w, truck_h, layer_depth, y_cursor,
                    truck=truck, piece_info=piece_info,
                    truck_placements=truck_placements
                )
                new_remaining: List[Piece3D] = []

                # Her katman başında büyükten küçüğe yeniden sırala
                items_sorted = sorted(
                    items_to_place,
                    key=lambda p: -(p.width * p.length * p.height)
                )

                for piece in items_sorted:
                    # Zone guard: priority items wait until y_cursor reaches their zone
                    if piece.priority is not None and piece.priority > 0:
                        y_min, _ = get_priority_zone(truck_l, piece.priority)
                        if y_cursor < y_min:
                            new_remaining.append(piece)
                            continue
                    rots = get_all_rotations_3d(piece)
                    can_fit = any(rot[1] <= layer_depth
                                  for rot in (rots or []))
                    if not can_fit:
                        new_remaining.append(piece)
                        continue
                    result = packer2d.try_place(piece, bin_id)
                    if result:
                        result.bin_id = bin_id
                        truck_placements.append(result)
                        placed_count += 1
                    else:
                        new_remaining.append(piece)

                # Boş katman → tüm parçalar ertelendi mi yoksa gerçekten sığmıyor mu?
                if not packer2d.placements:
                    # Tüm kalan parçalar öncelik zone bekliyorsa y_cursor'u ileri al
                    deferred_only = all(
                        (p.priority is not None and p.priority > 0
                         and y_cursor < get_priority_zone(truck_l, p.priority)[0])
                        for p in items_to_place
                    )
                    if deferred_only and items_to_place:
                        min_zone_y = min(
                            get_priority_zone(truck_l, p.priority)[0]
                            for p in items_to_place
                        )
                        y_cursor = min_zone_y
                        continue  # Bir sonraki katmana geç (y artık zone içinde)
                    remaining_in_truck.extend(items_to_place)
                    items_to_place = []
                    break

                # ── Faz 2: Gap filling — küçük parçaları boşluklara sok
                fill_after_primary = _layer_fill_ratio(
                    packer2d.placements, piece_info,
                    layer_depth, truck_w, truck_h
                )

                if fill_after_primary < MIN_LAYER_FILL_RATIO:
                    # Küçük parçalardan başla; already-remaining'dan seç
                    gap_candidates = sorted(
                        [p for p in new_remaining
                         if p.width * p.length * p.height <= small_threshold],
                        key=lambda p: -(p.width * p.length * p.height)
                    )
                    still_remaining_after_gap: List[Piece3D] = []
                    for piece in gap_candidates:
                        # Zone guard: öncelik parçaları zone dışında gap filling'e katılmaz
                        if piece.priority is not None and piece.priority > 0:
                            y_min, _ = get_priority_zone(truck_l, piece.priority)
                            if y_cursor < y_min:
                                still_remaining_after_gap.append(piece)
                                continue
                        rots = get_all_rotations_3d(piece)
                        can_fit = any(rot[1] <= layer_depth
                                      for rot in (rots or []))
                        if not can_fit:
                            still_remaining_after_gap.append(piece)
                            continue
                        result = packer2d.try_place(piece, bin_id)
                        if result:
                            result.bin_id = bin_id
                            truck_placements.append(result)
                            placed_count += 1
                            new_remaining.remove(piece)
                        else:
                            still_remaining_after_gap.append(piece)

                    fill_after_gap = _layer_fill_ratio(
                        packer2d.placements, piece_info,
                        layer_depth, truck_w, truck_h
                    )
                    print(f"   [gap] Gap filling: "
                          f"%{fill_after_primary*100:.1f} -> "
                          f"%{fill_after_gap*100:.1f}")

                layer.placements = list(packer2d.placements)
                layers_this_truck.append(layer)

                # Sıkı geçiş: katman gerçek derinliği (max kullanılan Y)
                if layer.placements:
                    actual_depth = max(
                        p.length for p in layer.placements
                    )
                    # Boşluk bırakmadan ilerle; ama en az layer_depth kadar git
                    # (sığamayan parçalar için o derinliği rezerve etmişiz)
                    y_cursor += max(actual_depth, 1)
                else:
                    y_cursor += layer_depth

                items_to_place = new_remaining

            # ── Bin kapat ─────────────────────────────────────────────
            bin_placements: List[Placement3D] = []
            for lyr in layers_this_truck:
                bin_placements.extend(lyr.placements)

            if not bin_placements:
                # Hiç parça yerleştirilemedi — bu kamyon yaklaşımını geri al
                truck_used_count[truck.id] -= 1
                remaining_pieces = remaining_in_truck + list(items_to_place)
                break

            # Araç doluluk kontrolü
            vehicle_fill = _vehicle_fill_ratio(
                bin_placements, piece_info, truck
            )
            if vehicle_fill < MIN_VEHICLE_FILL_RATIO:
                print(f"   [!] {truck.id} bin-{bin_id}: "
                      f"%{vehicle_fill*100:.1f} dolu "
                      f"(hedef min %{MIN_VEHICLE_FILL_RATIO*100:.0f}) "
                      f"-- kucuk urunler ekleniyor")
                # Kalan parçalardan küçükleri bu araca ekle
                extra_small = sorted(
                    [p for p in remaining_in_truck + list(items_to_place)
                     if p.width * p.length * p.height <= small_threshold],
                    key=lambda p: -(p.width * p.length * p.height)
                )
                added_extra = set()
                for piece in extra_small:
                    # Son katmana ya da yeni bir küçük katmana ekle
                    if layers_this_truck:
                        last_layer = layers_this_truck[-1]
                        # Aynı packer2d'ye ekleme yapamayız, yeni bir tane aç
                        packer_extra = WallPacker2D(
                            truck_w, truck_h,
                            last_layer.depth, last_layer.y_start,
                            truck=truck, piece_info=piece_info,
                            truck_placements=truck_placements
                        )
                        # Mevcut placements'ı yükle
                        packer_extra.placements = list(last_layer.placements)
                        packer_extra.candidate_points = [(0, 0)]
                        for placed in last_layer.placements:
                            packer_extra._update_candidates(placed)
                        result = packer_extra.try_place(piece, bin_id)
                        if result:
                            result.bin_id = bin_id
                            last_layer.placements.append(result)
                            bin_placements.append(result)
                            truck_placements.append(result)
                            placed_count += 1
                            added_extra.add(id(piece))
                # Eklenenler remaining listesinden çıkar
                remaining_in_truck = [
                    p for p in remaining_in_truck
                    if id(p) not in added_extra
                ]
                items_to_place = [
                    p for p in items_to_place
                    if id(p) not in added_extra
                ]

            bins_list.append(bin_placements)
            truck_assignments[bin_id] = truck.id

            bin_vol = truck.get_volume()
            used    = sum(_actual_used_volume(p, piece_info)
                          for p in bin_placements)
            util    = (used / bin_vol * 100) if bin_vol > 0 else 0
            all_layer_results.append(
                LayerResult(layers_this_truck, bin_id, truck.id, util))

            print(f"  [bin] Bin {bin_id} ({truck.id}): "
                  f"{len(layers_this_truck)} katman, "
                  f"{len(bin_placements)} palet, %{util:.1f}")

            remaining_pieces = remaining_in_truck + list(items_to_place)
            if not remaining_pieces:
                break

    # ─── Sonuç ──────────────────────────────────────────────────
    total_volume = 0
    used_volume  = 0
    for bin_id, placements in enumerate(bins_list):
        if bin_id in truck_assignments:
            t = next((t for t in trucks
                      if t.id == truck_assignments[bin_id]), None)
            if t:
                total_volume += t.get_volume()
        used_volume += sum(_actual_used_volume(p, piece_info)
                           for p in placements)

    total_waste    = total_volume - used_volume
    utilization    = (used_volume / total_volume * 100) if total_volume > 0 else 0
    execution_time = time.time() - start_time
    num_used       = len([b for b in bins_list if b])

    fills = []
    for bid, bps in enumerate(bins_list):
        if bps and bid in truck_assignments:
            t = next((t for t in trucks
                      if t.id == truck_assignments[bid]), None)
            if t and t.get_volume() > 0:
                fills.append(
                    sum(_actual_used_volume(p, piece_info) for p in bps)
                    / t.get_volume() * 100
                )

    print(f"\n{'='*42}")
    print(f"LAYER BUILDING v2 SONUC")
    print(f"{'='*42}")
    print(f"  Yerlestirilen   : {placed_count}/{total_pieces}")
    print(f"  Kullanilan arac : {num_used}")
    print(f"  Ort. doluluk    : %{utilization:.1f}")
    if fills:
        print(f"  Min doluluk     : %{min(fills):.1f}")
        print(f"  Max doluluk     : %{max(fills):.1f}")
    print(f"  Sure            : {execution_time:.3f}s")
    print(f"{'='*42}\n")

    # ASSERT
    _placed = sum(len(b) for b in bins_list)
    assert _placed == placed_count, (
        f"Layer: bins_total({_placed}) != placed_count({placed_count})"
    )
    assert _placed + len(remaining_pieces) == total_pieces, (
        f"Layer: placed({_placed}) + unfitted({len(remaining_pieces)}) "
        f"!= total({total_pieces})"
    )

    # Öncelik validasyonu
    validate_priority(bins_list, piece_info, trucks,
                      truck_assignments, "Layer Building v2")

    plan = CuttingPlan3D(
        bins=bins_list,
        total_waste=total_waste,
        utilization=utilization,
        execution_time=execution_time,
        algorithm="Layer Building v2",
        truck_assignments=truck_assignments,
        unfitted_pieces=remaining_pieces,
    )
    plan._layer_results = all_layer_results
    return plan
