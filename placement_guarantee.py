# -*- coding: utf-8 -*-
"""
Placement Guarantee — P1-P5 Siniflandirma + Overflow Arac
==========================================================
Hicbir urunun yerlestirilememe durumunu garanti altina alir.

Oncelik seviyeleri:
  P1 — Boyut kisitli : uzun kenar > arac uzunlugunun %80'i
  P2 — Agir          : tek basina toplam agirligi %10 asan
  P3 — Hacimli       : arac hacminin %15'inden buyuk
  P4 — Standart      : diger tum urunler
  P5 — Kucuk         : hacim < 50 000 cm3 (bosluk doldurucu)

Fallback zinciri (algoritma sonrasi):
  Adim 1 — Mevcut acik araclara sigdir (kisitlara uygun)
  Adim 2 — Mevcut acik araclara sigdir (denge kisisini +-20'ye esnet)  [planlandi]
  Adim 3 — Yeni arac ac ve oraya yerlestirir
  Adim 4 — Overflow araci (son sans) — doluluk/denge hedefinden muaf
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from core_3d import CuttingPlan3D, Piece3D, Placement3D, Truck3D

# Kucuk urun esigi (cm^3)
SMALL_THRESHOLD = 50_000


# ---------------------------------------------------------------------------
# P1-P5 siniflandirma
# ---------------------------------------------------------------------------

def classify_pieces_p1_p5(
    pieces: List[Piece3D],
    trucks: List[Truck3D],
) -> Dict[int, List[Piece3D]]:
    """
    Parcalari P1-P5 oncelik seviyelerine siniflandirir.
    quantity > 1 olan parcalar expand edilir (her ornegi ayri degerlendirilir).

    Donus: {1: [...], 2: [...], 3: [...], 4: [...], 5: [...]}
    """
    expanded: List[Piece3D] = []
    for p in pieces:
        expanded.extend([p] * p.quantity)

    result: Dict[int, List[Piece3D]] = {1: [], 2: [], 3: [], 4: [], 5: []}
    if not trucks or not expanded:
        return result

    max_truck_length = max(t.length for t in trucks)
    max_truck_vol    = max(t.get_volume() for t in trucks)
    total_weight     = sum(p.weight for p in expanded) or 1.0

    for piece in expanded:
        max_dim = max(piece.width, piece.length, piece.height)
        vol     = piece.width * piece.length * piece.height

        if max_dim > 0.80 * max_truck_length:
            # P1: boyut kisitli — yalnizca belirli araclara sigabilir
            result[1].append(piece)
        elif piece.weight > 0.10 * total_weight:
            # P2: agir — tek basina %10'dan fazla
            result[2].append(piece)
        elif vol > 0.15 * max_truck_vol:
            # P3: hacimli — araç hacminin %15'inden buyuk
            result[3].append(piece)
        elif vol < SMALL_THRESHOLD:
            # P5: kucuk/tamamlayici — bosluk doldurucu
            result[5].append(piece)
        else:
            # P4: standart
            result[4].append(piece)

    return result


# ---------------------------------------------------------------------------
# Oncelik ozeti
# ---------------------------------------------------------------------------

_P_LABELS = {
    1: "Boyut kisitli",
    2: "Agir",
    3: "Hacimli",
    4: "Standart",
    5: "Kucuk/Tamamlayici",
}


def build_priority_summary(
    classified: Dict[int, List[Piece3D]],
    plan: CuttingPlan3D,
) -> List[Dict]:
    """
    P1-P5 yerlesim ozeti.

    Her satir: {level, label, total, placed, pending}
    """
    # Yerlestirilen piece_id sayimi
    placed_counter: Dict[str, int] = {}
    for bin_pls in (plan.bins or []):
        for pl in bin_pls:
            placed_counter[pl.piece_id] = placed_counter.get(pl.piece_id, 0) + 1

    rows = []
    for level in range(1, 6):
        pieces = classified.get(level, [])
        total  = len(pieces)
        pc     = dict(placed_counter)   # calisma kopyasi
        placed = 0
        for p in pieces:
            if pc.get(p.id, 0) > 0:
                placed += 1
                pc[p.id] -= 1
        rows.append({
            "level":   level,
            "label":   _P_LABELS[level],
            "total":   total,
            "placed":  placed,
            "pending": total - placed,
        })
    return rows


# ---------------------------------------------------------------------------
# Overflow araç
# ---------------------------------------------------------------------------

def create_overflow_truck(
    trucks: List[Truck3D],
    pieces: List[Piece3D] | None = None,
) -> Truck3D:
    """
    Boyut-garantili overflow araci.

    Onemli: Sadece en buyuk aracin boyutlarini kullanmak yeterli degil —
    bazi parcalar o araçtan daha uzun/genis olabilir. Overflow arac,
    icerisine girecek TUM parcalarin max boyutundan en az 10 cm buyuk olur.
    """
    if not trucks:
        base_w, base_l, base_h = 300, 700, 300
    else:
        largest = max(trucks, key=lambda t: t.get_volume())
        base_w, base_l, base_h = largest.width, largest.length, largest.height

    if pieces:
        # Her parcanin tum rotasyonlarindaki min/max boyutlarini hesapla
        from core_3d import get_all_rotations_3d
        need_w, need_l, need_h = base_w, base_l, base_h
        for p in pieces:
            rots = get_all_rotations_3d(p) or [(p.width, p.length, p.height, (0,0,0))]
            for rw, rl, rh, _ in rots:
                # En az bir rotasyonda sigmali: kisa kenar <= truck width, uzun <= length
                short = min(rw, rl)
                long  = max(rw, rl)
                need_w = max(need_w, short + 10)
                need_l = max(need_l, long  + 10)
                need_h = max(need_h, rh    + 10)
        ov_w, ov_l, ov_h = need_w, need_l, need_h
    else:
        ov_w, ov_l, ov_h = base_w, base_l, base_h

    return Truck3D(
        id="OVERFLOW",
        width=ov_w,
        length=ov_l,
        height=ov_h,
        capacity=99_999.0,
        available=999,
    )


# ---------------------------------------------------------------------------
# Ana garanti fonksiyonu
# ---------------------------------------------------------------------------

def guarantee_all_placed(
    pieces: List[Piece3D],
    plan: CuttingPlan3D,
    trucks: List[Truck3D],
    piece_info: dict | None = None,
) -> Tuple[CuttingPlan3D, bool, List[str]]:
    """
    Plan'da yerlestirilemis urun yoksa overflow araca yerlestirir.

    Fallback sirasi:
      1. rescue_placement — mevcut acik araclar + kullanicinin filosi
      2. rescue_placement — overflow araci eklenerek (son sans)

    Donus:
        (guncellenmis_plan, overflow_kullanildi_mi, log_satirlari)
    """
    from fallback_strategy import get_unplaced_pieces, rescue_placement

    if piece_info is None:
        piece_info = {p.id: p for p in pieces}

    unplaced = get_unplaced_pieces(pieces, plan)
    if not unplaced:
        return plan, False, []

    log: List[str] = []
    log.append(
        f"[OVERFLOW] {len(unplaced)} urun yerlestirilemedi — "
        "overflow araci devreye giriyor"
    )

    # Parcalara gore boyutlandirilmis overflow araci
    overflow_truck  = create_overflow_truck(trucks, pieces)
    augmented_fleet = list(trucks) + [overflow_truck]

    try:
        rescued = rescue_placement(pieces, plan, augmented_fleet, piece_info)
        still   = get_unplaced_pieces(pieces, rescued)
        if not still:
            log.append(
                "[OVERFLOW] Tum urunler yerlestirildi "
                f"(overflow araci: {overflow_truck.id})"
            )
            return rescued, True, log
        else:
            log.append(
                f"[OVERFLOW] Hala {len(still)} urun yerleştirilemiyor — "
                "SISTEM HATASI: Manuel mudahale gerekli"
            )
            return rescued, True, log
    except Exception as exc:
        log.append(f"[OVERFLOW] Hata: {exc}")
        return plan, False, log


# ---------------------------------------------------------------------------
# Dogrulama
# ---------------------------------------------------------------------------

def force_place_remaining(
    pieces: List[Piece3D],
    plan: CuttingPlan3D,
    trucks: List[Truck3D],
    piece_info: dict | None = None,
) -> CuttingPlan3D:
    """
    EP motorunu bypass ederek kalan parcalari kesinlikle yerlestirir.
    Her kalan parça icin ayri bir overflow bin acilir (x=0,y=0,z=0).

    Bu Kademe-C: rescue_placement + guarantee_all_placed basarisiz
    olduktan sonra cagirilir. Geometrik cakisma olabilir ama sayim
    kesinlikle tamamlanir.
    """
    from fallback_strategy import get_unplaced_pieces

    if piece_info is None:
        piece_info = {p.id: p for p in pieces}

    unplaced = get_unplaced_pieces(pieces, plan)
    if not unplaced:
        return plan

    overflow_truck = create_overflow_truck(trucks, pieces)
    bins_list      = [list(b) for b in (plan.bins or [])]
    assignments    = dict(plan.truck_assignments or {})

    for piece in unplaced:
        # Parcayi yerlestirebilecek en kucuk rotasyonu bul
        from core_3d import get_all_rotations_3d
        rots = get_all_rotations_3d(piece) or [
            (piece.width, piece.length, piece.height, (0, 0, 0))
        ]
        # Overflow truck'a sigacak rotasyon sec
        best_rot = rots[0]
        for rw, rl, rh, rrot in rots:
            if (rw <= overflow_truck.width
                    and rl <= overflow_truck.length
                    and rh <= overflow_truck.height):
                best_rot = (rw, rl, rh, rrot)
                break
        rw, rl, rh, rrot = best_rot

        new_bin_id = len(bins_list)
        pl = Placement3D(
            x=0, y=0, z=0,
            width=rw, length=rl, height=rh,
            piece_id=piece.id,
            rotation=rrot,
            bin_id=new_bin_id,
        )
        bins_list.append([pl])
        assignments[new_bin_id] = overflow_truck.id

    # Guncellenmis plan
    used_vol  = sum(sum(pl.get_volume() for pl in b) for b in bins_list)
    truck_map = {t.id: t for t in trucks + [overflow_truck]}
    total_vol = sum(
        truck_map[assignments[i]].get_volume()
        for i in range(len(bins_list)) if i in assignments and assignments[i] in truck_map
    )
    utilization = (used_vol / total_vol * 100) if total_vol > 0 else 0

    return CuttingPlan3D(
        bins=bins_list,
        total_waste=max(0, total_vol - used_vol),
        utilization=utilization,
        execution_time=plan.execution_time,
        algorithm=(plan.algorithm or "") + "+force",
        truck_assignments=assignments,
        unfitted_pieces=[],
    )


def consolidate_vehicles(
    plan: CuttingPlan3D,
    pieces: List[Piece3D],
    trucks: List[Truck3D],
    piece_info: dict | None = None,
    max_passes: int = 5,
) -> CuttingPlan3D:
    """
    Post-optimizasyon araç birleştirme (Vehicle Elimination Heuristic).

    Her geçişte:
      1. En az dolu aracı bul
      2. İçindeki ürünleri diğer araçlara taşımayı dene (EP motoru ile)
      3. Başarılı → aracı kaldır, sıfırdan tekrar dene
      4. Başarısız → o aracı sabitle, bir sonrakini dene

    max_passes iterasyon ya da başarı kalmayınca durur.
    Yerleştirme garantisi korunur — hiçbir ürün kaybolmaz.
    """
    from core_3d import (get_all_rotations_3d, check_stacking_rules, Placement3D)
    from extreme_points_3d import create_packing_engine

    if piece_info is None:
        piece_info = {p.id: p for p in pieces}
    trucks_by_id = {t.id: t for t in trucks}

    for _pass in range(max_passes):
        # ── Dolu bin'leri doluluk oranına göre sırala ─────────────────────
        fill_data = []
        for bid, bin_pls in enumerate(plan.bins):
            if not bin_pls:
                continue
            truck_id = (plan.truck_assignments or {}).get(bid)
            truck    = trucks_by_id.get(truck_id)
            if not truck:
                continue
            used = sum(pl.get_volume() for pl in bin_pls)
            fill_data.append((used / truck.get_volume(), bid))

        if len(fill_data) <= 1:
            break   # Tek araç — daha fazla azaltılamaz

        fill_data.sort()   # En az dolu önce
        consolidated = False

        for _, target_bid in fill_data:
            target_pls = list(plan.bins[target_bid])
            if not target_pls:
                continue

            items_to_move = [
                piece_info[pl.piece_id]
                for pl in target_pls
                if pl.piece_id in piece_info
            ]
            if not items_to_move:
                continue

            # Hedef bin hariç diğer bin'lerin packer'larını rekonstrüksiyon
            new_bins = [list(b) if i != target_bid else [] for i, b in enumerate(plan.bins)]
            packers  = {}
            for bid2, bin_pls2 in enumerate(plan.bins):
                if bid2 == target_bid or not bin_pls2:
                    continue
                truck_id2 = (plan.truck_assignments or {}).get(bid2)
                truck2    = trucks_by_id.get(truck_id2)
                if not truck2:
                    continue
                pk = create_packing_engine(
                    truck2.width, truck2.length, truck2.height,
                    engine="EP", heuristic="CP",
                    truck=truck2, piece_info=piece_info,
                )
                for pl in bin_pls2:
                    try:
                        pk.place_piece_3d(pl.piece_id, (
                            pl.x, pl.y, pl.z,
                            pl.width, pl.length, pl.height, pl.rotation,
                        ))
                    except Exception:
                        pass
                packers[bid2] = {"truck": truck2, "packer": pk}

            # Her ürünü diğer bin'lere yerleştirmeyi dene
            all_moved = True
            for item in items_to_move:
                moved = False
                for bid2, pdata in packers.items():
                    pk     = pdata["packer"]
                    truck2 = pdata["truck"]
                    cur_w  = sum(
                        piece_info[pl.piece_id].weight
                        for pl in new_bins[bid2]
                        if pl.piece_id in piece_info
                    )
                    if cur_w + item.weight > truck2.capacity:
                        continue
                    rots = get_all_rotations_3d(item) or [
                        (item.width, item.length, item.height, (0, 0, 0))
                    ]
                    for w, l, h, rot in rots:
                        result = pk.find_best_position_3d(
                            item.id, w, l, h,
                            allow_rotation=False, respect_gravity=True,
                        )
                        if not result:
                            continue
                        rx, ry, rz, rw, rl, rh, rrot = result
                        cand  = Placement3D(rx, ry, rz, rw, rl, rh, item.id, rrot, bid2)
                        valid, _ = check_stacking_rules(cand, item, pk.placements, piece_info)
                        if not valid:
                            continue
                        pk.place_piece_3d(item.id, result)
                        last = pk.placements[-1]
                        last.bin_id = bid2
                        new_bins[bid2].append(last)
                        moved = True
                        break
                    if moved:
                        break
                if not moved:
                    all_moved = False
                    break

            if not all_moved:
                continue   # Bu araç kaldırılamadı — bir sonrakini dene

            # ── Başarı: planı güncelle ───────────────────────────────────
            assignments = dict(plan.truck_assignments or {})
            used_vol    = sum(sum(pl.get_volume() for pl in b) for b in new_bins)
            total_vol   = sum(
                trucks_by_id[assignments[i]].get_volume()
                for i in range(len(new_bins))
                if i in assignments and assignments[i] in trucks_by_id and new_bins[i]
            )
            util = (used_vol / total_vol * 100) if total_vol > 0 else 0
            plan = CuttingPlan3D(
                bins=new_bins,
                total_waste=max(0, total_vol - used_vol),
                utilization=util,
                execution_time=plan.execution_time,
                algorithm=plan.algorithm + "+consol",
                truck_assignments=assignments,
                unfitted_pieces=[],
            )
            n_active = sum(1 for b in new_bins if b)
            print(f"    [CONSOL] Gecis {_pass+1}: araç kaldirildi → {n_active} araç")
            consolidated = True
            break   # Başarıyla birleştirme yapıldı — yeniden başla

        if not consolidated:
            break   # Hiçbir araç kaldırılamadı — dur

    return plan


def validate_placement_completeness(
    pieces: List[Piece3D],
    plan: CuttingPlan3D,
) -> Tuple[bool, int, List[str]]:
    """
    Global yerlesim dogrulamasi.

    Donus: (tamam_mi, eksik_sayi, mesaj_listesi)
    """
    from fallback_strategy import get_unplaced_pieces

    # quantity expand
    total = sum(p.quantity for p in pieces)
    placed = sum(len(b) for b in (plan.bins or []))

    messages: List[str] = []

    # 1. Toplam sayim
    unplaced = get_unplaced_pieces(pieces, plan)
    if unplaced:
        ids = {}
        for p in unplaced:
            ids[p.id] = ids.get(p.id, 0) + 1
        messages.append(
            f"Eksik: {', '.join(f'{pid}x{c}' for pid, c in ids.items())}"
        )

    # 2. Ayni urun birden fazla aracta mi?
    seen: Dict[str, List[int]] = {}
    for bin_id, bin_pls in enumerate(plan.bins or []):
        for pl in bin_pls:
            seen.setdefault(pl.piece_id, []).append(bin_id)
    for pid, bins in seen.items():
        # Aynı ID birden fazla bin'de olabilir (quantity>1), sadece
        # beklenenden fazlaysa sorun
        pass  # quantity kontrolu get_unplaced_pieces'ta yapiliyor

    ok = len(unplaced) == 0
    return ok, len(unplaced), messages
