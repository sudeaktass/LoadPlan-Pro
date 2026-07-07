# -*- coding: utf-8 -*-
"""
Fallback Strategy — Öncelik & Ağırlık Merkezi Çakışması Çözümü
================================================================
Temel kural: ağırlık merkezi gevşetilmez, öncelik görmezden gelinmez.
Çözüm her zaman ek araç ekleme yönünde.

Fallback zinciri:
  Adım 1 — Silindir ise bounding-box ile tekrar dene
  Adım 2 — Ön bölgede swap dene (motor desteklemiyorsa skip)
  Adım 3 — Yeni araç ata (tam filo ile algoritmayı tekrar çalıştır)
  Adım 4 — Filo limiti aşıldı: detaylı rapor + ConstraintViolation
"""

from typing import List, Dict, Callable, Tuple
from dataclasses import dataclass, field

from core_3d import Piece3D, Truck3D, CuttingPlan3D
from minimum_vehicle_selector import ConstraintViolation


@dataclass
class FallbackReport:
    """Fallback zincirinin çıktısı — UI'ya verilen rapor."""
    success: bool
    plan: 'CuttingPlan3D'
    steps_tried: List[str] = field(default_factory=list)
    log_lines: List[str] = field(default_factory=list)
    unplaced_initial: int = 0
    unplaced_final: int = 0
    added_vehicles: int = 0


def get_unplaced_pieces(pieces: List[Piece3D],
                        plan: 'CuttingPlan3D') -> List[Piece3D]:
    """Plan'da yerleşmeyen Piece3D örneklerini döndürür (quantity dahil)."""
    expected: Dict[str, int] = {}
    for p in pieces:
        expected[p.id] = expected.get(p.id, 0) + p.quantity
    actual: Dict[str, int] = {}
    for bin_placements in (plan.bins or []):
        for placement in bin_placements:
            actual[placement.piece_id] = actual.get(placement.piece_id, 0) + 1

    piece_by_id = {p.id: p for p in pieces}
    unplaced: List[Piece3D] = []
    for pid, need in expected.items():
        got = actual.get(pid, 0)
        missing = need - got
        if missing > 0:
            unplaced.extend([piece_by_id[pid]] * missing)
    return unplaced


def _piece_summary(pieces: List[Piece3D]) -> str:
    """Birkaç eksik parça için kompakt özet."""
    counts: Dict[str, int] = {}
    for p in pieces:
        counts[p.id] = counts.get(p.id, 0) + 1
    return ", ".join(f"{pid}×{c}" for pid, c in counts.items())


# ─── ADIM 1: SİLİNDİR → BOUNDING-BOX ────────────────────────────────────────

def _has_cylinders(unplaced: List[Piece3D]) -> bool:
    return any(getattr(p, 'shape', 'box') == 'cylinder' for p in unplaced)


# ─── ADIM 3: YENİ ARAÇ EKLE (Tam Filo Retry) ────────────────────────────────

def _try_full_fleet_retry(
    key: str,
    pieces: List[Piece3D],
    full_trucks: List[Truck3D],
    run_algo_fn: Callable,
    **kw,
) -> 'CuttingPlan3D':
    """
    Algoritmayı Faz 1'i bypass ederek tam filo ile tekrar çalıştırır.
    Bu, "yeni araç ekleme" mantığının pratik karşılığıdır: minimum filo
    yerine kullanıcının tanımladığı tüm araç havuzu kullanılır.
    """
    return run_algo_fn(key, pieces, full_trucks, _bypass_phase1=True, **kw)


# ─── ANA FALLBACK ZİNCİRİ ──────────────────────────────────────────────────

def apply_fallback_chain(
    key: str,
    pieces: List[Piece3D],
    full_trucks: List[Truck3D],
    initial_plan: 'CuttingPlan3D',
    run_algo_fn: Callable,
    **kw,
) -> FallbackReport:
    """
    Eksik ürün varsa fallback adımlarını sırayla dene.

    Args:
        key            : Algoritma key'i ("greedy_ep", "genetic", vb.)
        pieces         : Sipariş listesi
        full_trucks    : Kullanıcının tanımladığı TÜM araç havuzu
        initial_plan   : İlk denemenin (min araç ile) çıktısı
        run_algo_fn    : run_algo fonksiyonu (Faz 1 bypass desteği olmalı)
        **kw           : Algoritma parametreleri

    Returns:
        FallbackReport — plan + log + adımlar
    """
    report = FallbackReport(
        success=False,
        plan=initial_plan,
        unplaced_initial=len(get_unplaced_pieces(pieces, initial_plan)),
    )

    unplaced = get_unplaced_pieces(pieces, initial_plan)
    if not unplaced:
        # Zaten her şey yerleşmiş — fallback'e gerek yok
        report.success = True
        report.unplaced_final = 0
        return report

    report.log_lines.append(
        f"⚠️ Eksik ürünler: {_piece_summary(unplaced)} ({len(unplaced)} adet)"
    )

    # ── ADIM 1: Silindir → bounding-box ──────────────────────────────────
    if _has_cylinders(unplaced):
        report.steps_tried.append("cylinder_bbox")
        report.log_lines.append(
            "🔄 Adım 1: Silindir bounding-box ile değerlendiriliyor"
        )
        # EP motoru zaten silindirleri bbox olarak ele alıyor — bu adım
        # mevcut sistemde otomatik gerçekleşiyor. Burada log mesajı veriyoruz.
        report.log_lines.append("   ℹ️  EP motoru zaten bbox modunda; pratik etki yok")

    # ── ADIM 2: Öncelik swap ─────────────────────────────────────────────
    # 3B simülasyon motoru bu adımı doğrudan desteklemiyor; algoritmalar
    # zaten fitness fonksiyonlarında priority cezasını uyguluyor.
    has_priority_conflict = any(p.priority == 1 for p in unplaced)
    if has_priority_conflict:
        report.steps_tried.append("priority_swap")
        report.log_lines.append(
            "🔄 Adım 2: Öncelik swap simülasyonu"
        )
        report.log_lines.append(
            "   ℹ️  Algoritma içindeki priority cezası zaten uygulandı; "
            "ek araç stratejisine geçiliyor"
        )

    # ── ADIM 3: Yeni araç ata (tam filo retry) ───────────────────────────
    report.steps_tried.append("full_fleet_retry")
    report.log_lines.append(
        "🚛 Adım 3: Tam filo ile algoritmayı tekrar çalıştırıyor"
    )

    try:
        retry_plan = _try_full_fleet_retry(
            key, pieces, full_trucks, run_algo_fn, **kw
        )
        retry_unplaced = get_unplaced_pieces(pieces, retry_plan)
        report.plan = retry_plan

        # İlk plan'daki kullanılan araç sayısı vs tekrar denemenin sayısı
        initial_used = len([b for b in (initial_plan.bins or []) if b])
        retry_used = len([b for b in (retry_plan.bins or []) if b])
        report.added_vehicles = max(0, retry_used - initial_used)

        if not retry_unplaced:
            report.success = True
            report.unplaced_final = 0
            report.log_lines.append(
                f"✅ Tam filo retry başarılı: {retry_used} araç kullanıldı "
                f"(+{report.added_vehicles} ek araç)"
            )
            return report
        else:
            report.unplaced_final = len(retry_unplaced)
            report.log_lines.append(
                f"⚠️ Tam filo retry sonrası hâlâ {len(retry_unplaced)} ürün eksik"
            )
    except Exception as e:
        report.log_lines.append(f"⚠️ Tam filo retry hatası: {e}")
        report.unplaced_final = len(unplaced)

    # ── ADIM 4: Filo limiti aşıldı — detaylı rapor ──────────────────────
    report.steps_tried.append("raise_with_report")
    final_unplaced = get_unplaced_pieces(pieces, report.plan)
    detail = _piece_summary(final_unplaced)

    raise ConstraintViolation(
        f"❌ Çözüm bulunamadı. {len(final_unplaced)} ürün yerleştirilemedi: {detail}\n\n"
        f"DENENEN ÇÖZÜMLER:\n"
        f"  • Bounding-box yerleştirme: {'denendi' if 'cylinder_bbox' in report.steps_tried else 'gereksiz'}\n"
        f"  • Öncelik swap: {'denendi (motor desteklemiyor)' if 'priority_swap' in report.steps_tried else 'gereksiz'}\n"
        f"  • Tam filo ile tekrar: denendi (hâlâ {len(final_unplaced)} eksik)\n\n"
        f"KULLANICIDAN BEKLENEN KARAR:\n"
        f"  [1] Filoya yeni araç ekle\n"
        f"  [2] Bu ürün(ler)i bu seferden çıkar\n"
        f"  [3] Ürün önceliklerini gözden geçir"
    )


# ─── RESCUE PLACEMENT — Algoritma eksik bıraktığında parça-bazlı kurtarma ───

def rescue_placement(
    pieces: List[Piece3D],
    plan: 'CuttingPlan3D',
    full_trucks: List[Truck3D],
    piece_info: dict = None,
) -> 'CuttingPlan3D':
    """
    Algoritma sonrası eksik kalan parçaları tek tek kurtarmaya çalışır.

    Akış:
        1. plan'ın mevcut bin'lerinde her eksik parça için yer ara
        2. Sığmazsa yeni bir araç (full_trucks'tan henüz kullanılmamış)
           aç ve oraya yerleştir
        3. Hiçbir yere sığmazsa ImpossibleToSolve

    Bu, apply_fallback_chain'in tam-filo retry'ından sonra son şanstır.
    """
    from minimum_vehicle_selector import ImpossibleToSolve
    from core_3d import Placement3D, get_all_rotations_3d, check_stacking_rules
    from extreme_points_3d import create_packing_engine

    if piece_info is None:
        piece_info = {p.id: p for p in pieces}

    # Mevcut bin'lerin packer'larını rekonstrüksiyon ile yeniden kur
    bins_list = [list(b) for b in (plan.bins or [])]
    truck_assignments = dict(plan.truck_assignments or {})
    trucks_by_id = {t.id: t for t in full_trucks}
    packers = {}
    for bin_id, bin_placements in enumerate(bins_list):
        truck_id = truck_assignments.get(bin_id)
        if not truck_id or truck_id not in trucks_by_id:
            continue
        truck = trucks_by_id[truck_id]
        pk = create_packing_engine(
            truck.width, truck.length, truck.height,
            engine="EP", heuristic="CP",
            truck=truck, piece_info=piece_info,
        )
        # Mevcut yerleşimleri packer'a aktar
        for placement in bin_placements:
            try:
                pk.place_piece_3d(placement.piece_id, (
                    placement.x, placement.y, placement.z,
                    placement.width, placement.length, placement.height,
                    placement.rotation,
                ))
            except Exception:
                pass
        packers[bin_id] = {'truck': truck, 'packer': pk}

    # Eksik parça sayımı
    unplaced = get_unplaced_pieces(pieces, plan)
    if not unplaced:
        return plan

    # Hangi truck id'leri zaten kullanılıyor (slot sayısı dahil)
    used_truck_count: dict = {}
    for tid in truck_assignments.values():
        used_truck_count[tid] = used_truck_count.get(tid, 0) + 1

    rescued: List[Placement3D] = []

    def _try_place(bin_id: int, piece: Piece3D) -> bool:
        packer = packers[bin_id]['packer']
        truck = packers[bin_id]['truck']
        # Ağırlık kontrolü
        current_w = sum(
            piece_info[pl.piece_id].weight for pl in packer.placements
            if pl.piece_id in piece_info
        )
        if current_w + piece.weight > truck.capacity:
            return False

        rotations = get_all_rotations_3d(piece)
        if not rotations:
            rotations = [(piece.width, piece.length, piece.height, (0, 0, 0))]
        for w, l, h, _rot in rotations:
            result = packer.find_best_position_3d(
                piece.id, w, l, h,
                allow_rotation=False, respect_gravity=True
            )
            if not result:
                continue
            rx, ry, rz, rw, rl, rh, rrot = result
            cand = Placement3D(rx, ry, rz, rw, rl, rh, piece.id, rrot, bin_id)
            valid, _ = check_stacking_rules(
                cand, piece, packer.placements, piece_info
            )
            if not valid:
                continue
            packer.place_piece_3d(piece.id, result)
            last = packer.placements[-1]
            last.bin_id = bin_id
            bins_list[bin_id].append(last)
            rescued.append(last)
            return True
        return False

    def _open_new_bin(piece: Piece3D) -> bool:
        # Henüz tam kullanılmamış bir truck tipi bul
        for truck in sorted(full_trucks,
                            key=lambda t: t.get_volume()):
            already = used_truck_count.get(truck.id, 0)
            if already >= truck.available:
                continue
            # Bu parça için kapasite yeterli mi?
            if (piece.weight > truck.capacity or
                    piece.get_bounding_volume() > truck.get_volume()):
                continue
            # Yeni bin aç
            new_bin_id = len(bins_list)
            bins_list.append([])
            truck_assignments[new_bin_id] = truck.id
            used_truck_count[truck.id] = already + 1
            pk = create_packing_engine(
                truck.width, truck.length, truck.height,
                engine="EP", heuristic="CP",
                truck=truck, piece_info=piece_info,
            )
            packers[new_bin_id] = {'truck': truck, 'packer': pk}
            return _try_place(new_bin_id, piece)
        return False

    for piece in unplaced:
        ok = False
        # 1) Mevcut bin'leri dene
        for bin_id in list(packers.keys()):
            if _try_place(bin_id, piece):
                ok = True
                break
        # 2) Yeni bin aç
        if not ok:
            ok = _open_new_bin(piece)
        if not ok:
            raise ImpossibleToSolve(
                f"❌ '{piece.id}' hiçbir araca sığmıyor (kurtarma modu da başarısız)."
            )

    # Yeni plan üret
    from core_3d import CuttingPlan3D
    used_vol = sum(
        sum(pl.get_volume() for pl in b) for b in bins_list
    )
    total_vol = sum(
        trucks_by_id[truck_assignments[i]].get_volume()
        for i in range(len(bins_list)) if i in truck_assignments
    )
    utilization = (used_vol / total_vol * 100) if total_vol > 0 else 0
    return CuttingPlan3D(
        bins=bins_list,
        total_waste=max(0, total_vol - used_vol),
        utilization=utilization,
        execution_time=plan.execution_time,
        algorithm=(plan.algorithm or "") + "+rescue",
        truck_assignments=truck_assignments,
        unfitted_pieces=[],
    )


# ─── DETAYLI YERLEŞTİRME TEŞHİSİ ────────────────────────────────────────────

def diagnose_placement_failure(
    piece: 'Piece3D',
    plan: 'CuttingPlan3D',
    trucks: List['Truck3D'],
    piece_info: dict = None,
) -> dict:
    """
    Bir parçanın neden yerleşemediğini katman katman tespit et.

    Returns:
        {
            "piece_id": str,
            "checks": [
                {"bin_id": int, "truck_id": str, "layer": "CAPACITY"|"WEIGHT"|
                                                          "GEOMETRY"|"COG"|"OK",
                 "message": str},
                ...
            ],
            "summary": str,  # Tek satır özet
        }
    """
    from core_3d import get_all_rotations_3d
    from extreme_points_3d import create_packing_engine

    if piece_info is None:
        piece_info = {}

    trucks_by_id = {t.id: t for t in trucks}
    checks = []

    for bin_id, bin_placements in enumerate(plan.bins or []):
        truck_id = (plan.truck_assignments or {}).get(bin_id)
        if not truck_id or truck_id not in trucks_by_id:
            continue
        truck = trucks_by_id[truck_id]

        # Katman 1: Hacim kapasitesi
        used_w = sum(piece_info[pl.piece_id].weight
                     for pl in bin_placements if pl.piece_id in piece_info)
        if piece.weight > truck.capacity - used_w:
            checks.append({
                "bin_id": bin_id, "truck_id": truck_id,
                "layer": "WEIGHT",
                "message": f"Ağırlık: {piece.weight} kg > kalan {truck.capacity - used_w} kg",
            })
            continue

        # Katman 2: Geometri — EP motorundan dene
        try:
            pk = create_packing_engine(
                truck.width, truck.length, truck.height,
                engine="EP", heuristic="CP",
                truck=truck, piece_info=piece_info,
            )
            # Mevcut yerleşimleri rekonstrüksiyon
            for pl in bin_placements:
                try:
                    pk.place_piece_3d(pl.piece_id, (
                        pl.x, pl.y, pl.z, pl.width, pl.length, pl.height, pl.rotation,
                    ))
                except Exception:
                    pass

            # Tüm rotasyonlarda dene
            rotations = get_all_rotations_3d(piece)
            if not rotations:
                rotations = [(piece.width, piece.length, piece.height, (0, 0, 0))]
            found = False
            for w, l, h, _rot in rotations:
                result = pk.find_best_position_3d(
                    piece.id, w, l, h,
                    allow_rotation=False, respect_gravity=True
                )
                if result:
                    found = True
                    break

            if not found:
                checks.append({
                    "bin_id": bin_id, "truck_id": truck_id,
                    "layer": "GEOMETRY",
                    "message": f"Hiçbir rotasyonda EP boş alan bulamadı",
                })
            else:
                checks.append({
                    "bin_id": bin_id, "truck_id": truck_id,
                    "layer": "OK",
                    "message": f"Yerleşebilir görünüyor (algoritma neden denemedi?)",
                })
        except Exception as e:
            checks.append({
                "bin_id": bin_id, "truck_id": truck_id,
                "layer": "ERROR",
                "message": f"EP rekonstrüksiyon hatası: {e}",
            })

    # Özet
    if not checks:
        summary = f"'{piece.id}': Hiç bin denenmedi (filo boş?)"
    elif any(c["layer"] == "OK" for c in checks):
        summary = f"'{piece.id}': Aslında yer var ama algoritma kaçırmış"
    else:
        layers = [c["layer"] for c in checks]
        layer_counts = {l: layers.count(l) for l in set(layers)}
        summary = (f"'{piece.id}': "
                   + ", ".join(f"{l}={c}" for l, c in layer_counts.items()))

    return {
        "piece_id": piece.id,
        "checks": checks,
        "summary": summary,
    }


def cleanup_empty_bins(plan: 'CuttingPlan3D') -> 'CuttingPlan3D':
    """
    Sonuç plan'ında parça içermeyen bin'leri (boş araçlar) kaldırır.
    truck_assignments ve bins listelerini yeniden indexler.
    """
    from core_3d import CuttingPlan3D

    if not plan.bins:
        return plan

    # Dolu bin'leri yeni index'lere eşle
    new_bins = []
    new_assignments = {}
    old_to_new: dict = {}
    for old_idx, bin_placements in enumerate(plan.bins):
        if bin_placements:
            new_idx = len(new_bins)
            new_bins.append(list(bin_placements))
            if plan.truck_assignments and old_idx in plan.truck_assignments:
                new_assignments[new_idx] = plan.truck_assignments[old_idx]
            old_to_new[old_idx] = new_idx
            # Placement'lardaki bin_id'leri güncelle
            for pl in bin_placements:
                pl.bin_id = new_idx

    return CuttingPlan3D(
        bins=new_bins,
        total_waste=plan.total_waste,
        utilization=plan.utilization,
        execution_time=plan.execution_time,
        algorithm=plan.algorithm,
        truck_assignments=new_assignments,
        unfitted_pieces=plan.unfitted_pieces,
    )
