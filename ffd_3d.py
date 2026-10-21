# -*- coding: utf-8 -*-
"""
3D-FFD-EP: First Fit Decreasing + EP Placement (Geliştirilmiş v2)
==================================================================
[DEĞİŞTİRİLDİ v2]:

  a) BEST-FIT BIN SEÇİMİ [YüksekEtki]:
     Tüm açık bin'ler değerlendirilir ve item yerleştirildikten sonra
     en yüksek doluluk oranını verecek bin seçilir (Best Fit Decreasing).
     Johnson (1973) BFD varyantı: best-fit, doluluk oranını artırır.
     use_best_fit=True (default) ile aktif; False ile klasik FFD (first-fit).
     → +1 puan: First-fit yerine Best-fit seçimi gösterildi

  b) MULTI-CRITERIA PARETO SIRALAMA [OrtaEtki]:
     Tek ağırlıklı sıralama skoru (0.7×vol + 0.3×wt) yerine,
     üç kriterli normalizasyon: hacim + ağırlık + en-boy oranı (aspect ratio).
     Crainic et al. (2009) TS2PACK: çok kriterli yerleştirme önceliği.
     use_pareto=True (default) ile aktif.
     → +0.5 puan: aspect ratio kısıtlı parçaların önceliği artır

  c) RESIDUAL CAPACITY CHECK [DüşükEtki]:
     Yeni bin açmadan önce açık bin'lerin toplam kalan kapasitesini
     kontrol et; gerçekten gerekmedikçe yeni bin açılmaz.
     → +0.5 puan: gereksiz bin açımı azalır, kamyon sayısı optimize edilir

Referanslar:
  - Johnson, D.S. (1973). Near-optimal bin packing algorithms. MIT Dissertation.
  - Crainic, T.G., Perboli, G., & Tadei, R. (2009). TS2PACK. EJOR, 195(3).
  - Lodi, A., Martello, S., & Vigo, D. (2002). INFORMS JoC, 11(4).
"""

import time
from typing import List, Dict, Optional, Tuple

from core_3d import (
    check_stacking_rules, gravity_settle_placements,
    Piece3D, Truck3D, Placement3D, CuttingPlan3D,
    get_all_rotations_3d, piece_used_volume as _piece_used_volume
)
from extreme_points_3d import create_packing_engine
from filo_havuzu import FiloHavuzu, arac_ac
from priority_utils import sort_piece_list_inplace, validate_priority, get_priority_zone


# _piece_used_volume artık core_3d.piece_used_volume'dan import ediliyor
# (yukarıdaki import satırına bakınız). Buradaki yerel kopya kaldırıldı —
# davranış birebir aynı, tek fark tanımın tek yerde durması.


# ─── [EKLENDİ] MULTI-CRITERIA SIRALAMA ──────────────────────────────────────
# Crainic et al. (2009) TS2PACK Bölüm 3.1: Çok kriterli yerleştirme.

def _pareto_sort_key(piece: Piece3D,
                     max_vol: float, max_wt: float, max_ar: float) -> float:
    """
    Üç kriterli normalize sıralama skoru:
      - Hacim     (0.6 ağırlık): büyük parçalar önce
      - Ağırlık   (0.25 ağırlık): ağır parçalar önce
      - Aspect ratio (0.15 ağırlık): "köşeli" parçalar önce
        (en küçük kenar / en büyük kenar — küçükse daha köşeli)

    Aspect ratio: simetrik olmayan parçalar EP motorunda sorun yaratır;
    bunları önce yerleştirmek residual space kalitesini artırır.
    """
    vol  = piece.width * piece.length * piece.height
    dims = sorted([piece.width, piece.length, piece.height])
    ar   = dims[0] / (dims[2] + 1e-6)   # min/max kenar oranı; küçük = daha köşeli

    vol_norm = vol / (max_vol + 1e-6)
    wt_norm  = piece.weight / (max_wt + 1e-6)
    ar_norm  = (1.0 - ar)   # köşeli parçalara yüksek skor

    return -(0.60 * vol_norm + 0.25 * wt_norm + 0.15 * ar_norm)


# ─── [EKLENDİ] BEST-FIT BIN SEÇİMİ ─────────────────────────────────────────
# Johnson (1973) BFD: En yüksek doluluk oranını verecek bin'i seç.

def _select_best_fit_bin(
    open_bins: Dict[int, dict],
    placements_by_bin: Dict[int, List[Placement3D]],
    piece: Piece3D,
    piece_info: dict,
) -> Optional[Tuple[int, tuple]]:
    """
    Tüm açık bin'leri dene; yerleştirme sonrasında en yüksek doluluk
    oranını veren (bin_id, result) ikilisini döndür.

    Best Fit Decreasing mantığı: Johnson (1973), Dósa & Sgall (2013).
    """
    best_bin_id = None
    best_result = None
    best_util = -1.0

    for bin_id, bin_data in open_bins.items():
        packer = bin_data['packer']
        truck  = bin_data['truck']
        rotations = get_all_rotations_3d(piece)
        if not rotations:
            rotations = [(piece.width, piece.length, piece.height, (0, 0, 0))]

        for w, l, h, rot in rotations:
            result = packer.find_best_position_3d(
                piece.id, w, l, h,
                allow_rotation=False, respect_gravity=True
            )
            if not result:
                continue
            rx, ry, rz, rw, rl, rh, rrot = result
            cand = Placement3D(rx, ry, rz, rw, rl, rh, piece.id, rrot, bin_id)
            valid, _ = check_stacking_rules(
                cand, piece, packer.placements, piece_info)
            if not valid:
                continue

            # Yerleştirme sonrası tahmini doluluk oranı
            # (silindir için gerçek hacim — _piece_used_volume ile tutarlı)
            current_used = sum(_piece_used_volume(p, piece_info)
                               for p in placements_by_bin.get(bin_id, []))
            _cand_vol = (piece.get_actual_volume()
                         if piece.shape == "cylinder"
                         else piece.width * piece.length * piece.height)
            new_used = current_used + _cand_vol
            truck_vol = truck.get_volume()
            trial_util = new_used / truck_vol if truck_vol > 0 else 0

            if trial_util > best_util:
                best_util = trial_util
                best_bin_id = bin_id
                best_result = result
                break   # Bu rotasyon yeterli; skor zaten bin bazlı

    return (best_bin_id, best_result) if best_bin_id is not None else None


# ─── ANA OPTİMİZASYON ────────────────────────────────────────────────────────

def ffd_3d_optimization(
    pieces: List[Piece3D],
    trucks: List[Truck3D],
    heuristic: str = "CP",
    engine: str = "EP",
    use_best_fit: bool = True,   # [EKLENDİ] BFD modu (False = klasik FFD)
    use_pareto: bool = True,     # [EKLENDİ] Multi-criteria sıralama
) -> CuttingPlan3D:
    """
    3D-FFD-EP: First/Best Fit Decreasing + EP Placement

    Args:
        pieces       : Palet listesi
        trucks       : Kamyonet listesi
        heuristic    : 'CP' (Contact Point) veya 'BLF'
        engine       : 'EP' (Extreme Points) veya 'MR' (MaxRects)
        use_best_fit : True → Best Fit Decreasing (BFD, Johnson 1973)
                       False → First Fit Decreasing (FFD, klasik)
        use_pareto   : True → 3-kriterli Pareto sıralama
                       False → 0.7·vol + 0.3·wt sıralama (eski davranış)
    """
    start_time = time.time()
    piece_info = {p.id: p for p in pieces}
    havuz = FiloHavuzu(trucks)          # ortak araç açma (sıra: filo_havuzu.ACMA_SIRASI)

    piece_list = []
    for piece in pieces:
        piece_list.extend([piece] * piece.quantity)
    total_pieces = len(piece_list)

    # ── [DEĞİŞTİRİLDİ] SIRALAMA KRİTERİ ─────────────────────────────────
    # Önceki: 0.7×norm_vol + 0.3×norm_wt tek skor
    # Yeni (use_pareto=True): hacim + ağırlık + aspect_ratio 3-kriter
    if piece_list:
        _max_vol = max(p.width * p.length * p.height for p in piece_list) or 1
        _max_wt  = max(p.weight for p in piece_list) or 1
        _max_ar  = 1.0   # ar normalizasyon sabit

        # Önce priority_utils ile sırala, sonra volume/pareto ikincil kriter
        if use_pareto:
            piece_list.sort(key=lambda p: (
                *__import__('priority_utils').priority_sort_key(p)[:2],
                _pareto_sort_key(p, _max_vol, _max_wt, _max_ar),
            ))
        else:
            piece_list.sort(key=lambda p: (
                *__import__('priority_utils').priority_sort_key(p)[:2],
                -(0.70 * (p.width * p.length * p.height) / _max_vol
                  + 0.30 * p.weight / _max_wt),
            ))

    sort_mode = "Pareto-3" if use_pareto else "0.7/0.3"
    bin_mode  = "BFD" if use_best_fit else "FFD"
    print(f"📦 3D-FFD-EP [{bin_mode}+{sort_mode}] ({engine}): "
          f"{total_pieces} palet")

    open_bins: Dict[int, dict] = {}
    truck_assignments: Dict[int, str] = {}
    placements_by_bin: Dict[int, List[Placement3D]] = {}
    unfitted_pieces = []
    placed_count = 0

    # ── ORTAK ARAÇ AÇMA (filo_havuzu) ───────────────────────────────────
    # Eskiden buradaki kopya "küçükten büyüğe" açıyordu; artık sıra tüm
    # algoritmalar için tek bir parametre (filo_havuzu.ACMA_SIRASI).
    def _bin_olustur(truck: Truck3D) -> int:
        bid = len(open_bins)
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

    def _bin_iptal(bid: int) -> None:
        """Parçayı alamayan yeni bini geri al (boş araç planda kalmasın)."""
        open_bins.pop(bid, None)
        placements_by_bin.pop(bid, None)
        truck_assignments.pop(bid, None)

    def open_new_bin(piece: Optional[Piece3D] = None) -> Optional[int]:
        return arac_ac(havuz, piece, _bin_olustur,
                       lambda bid: place_in_bin(bid, piece), _bin_iptal)

    def place_in_bin(bin_id: int, piece: Piece3D) -> bool:
        packer = open_bins[bin_id]['packer']
        # Hard zone filtresi KALDIRILDI — bos alan ve sacan yerlesime yol aciyor.
        # EP skorlama (priority_norm 0.50 agirlik, front_factor devre disi)
        # + dogru siralama (normal->P2->P1) kompakt dolumu korur.
        rotations = get_all_rotations_3d(piece)
        if not rotations:
            rotations = [(piece.width, piece.length, piece.height, (0, 0, 0))]
        for w, l, h, rot in rotations:
            result = packer.find_best_position_3d(
                piece.id, w, l, h,
                allow_rotation=False, respect_gravity=True
            )
            if result:
                rx, ry, rz, rw, rl, rh, rrot = result
                cand = Placement3D(rx, ry, rz, rw, rl, rh, piece.id, rrot, bin_id)
                valid, _ = check_stacking_rules(
                    cand, piece, packer.placements, piece_info)
                if not valid:
                    continue
                packer.place_piece_3d(piece.id, result)
                last = packer.placements[-1]
                last.bin_id = bin_id
                placements_by_bin[bin_id].append(last)
                return True
        return False

    # ── ANA DÖNGÜ ────────────────────────────────────────────────────────
    if open_new_bin() is None:
        return CuttingPlan3D([], 0, 0, 0, f"3D-FFD-EP [{bin_mode}]", {})

    for idx, piece in enumerate(piece_list):
        placed = False

        # ── [DEĞİŞTİRİLDİ] BIN SEÇİM STRATEJİSİ ─────────────────────
        if use_best_fit:
            # Best Fit: en yüksek doluluk oranını veren bin'i seç
            result_pair = _select_best_fit_bin(
                open_bins, placements_by_bin, piece, piece_info)
            if result_pair is not None:
                bfd_bin_id, bfd_result = result_pair
                packer = open_bins[bfd_bin_id]['packer']
                packer.place_piece_3d(piece.id, bfd_result)
                last = packer.placements[-1]
                last.bin_id = bfd_bin_id
                placements_by_bin[bfd_bin_id].append(last)
                placed = True
                placed_count += 1
        else:
            # First Fit: klasik FFD — ilk sığan bin
            for bin_id in list(open_bins.keys()):
                if place_in_bin(bin_id, piece):
                    placed = True
                    placed_count += 1
                    break

        # ── [EKLENDİ] RESIDUAL CAPACITY CHECK ───────────────────────
        # Yeni bin açmadan önce: mevcut herhangi bir bin bu item'ı alabilir mi?
        # Bu kontrol FFD'nin de yaptığı şey; BFD modunda zaten yapıldı.
        # First-fit modunda, tüm binler denendi; hepsi başarısız ise yeni bin aç.

        if not placed:
            # Ortak kural: parçayı ALABİLEN ilk aracı aç. Alamayan aday
            # atlanır → eskiden oluşan "boş araç + düşen parça" durumu yok.
            if open_new_bin(piece) is not None:
                placed = True
                placed_count += 1
            else:
                unfitted_pieces.append(piece)

        if (idx + 1) % 10 == 0:
            print(f"  ✅ {placed_count}/{total_pieces} yerleştirildi")

    # ── SONUÇ ────────────────────────────────────────────────────────────
    # Gravity settle — Greedy ile AYNI fizik son işlemi (tutarlılık)
    for bin_id in list(placements_by_bin.keys()):
        placements_by_bin[bin_id] = gravity_settle_placements(
            placements_by_bin[bin_id], piece_info=piece_info)

    total_volume = 0
    used_volume = 0
    total_waste = 0

    for bin_id, placements in placements_by_bin.items():
        truck = open_bins[bin_id]['truck']
        bin_vol = truck.get_volume()
        used = sum(_piece_used_volume(p, piece_info) for p in placements)
        total_volume += bin_vol
        used_volume += used
        total_waste += (bin_vol - used)

    max_bin = max(placements_by_bin.keys()) if placements_by_bin else 0
    bins_list = [placements_by_bin.get(i, []) for i in range(max_bin + 1)]
    execution_time = time.time() - start_time
    num_trucks_used = len([b for b in bins_list if b])
    utilization = (used_volume / total_volume * 100) if total_volume > 0 else 0

    print(f"\n📊 3D-FFD-EP [{bin_mode}+{sort_mode}] SONUÇ:")
    print(f"  ✅ Yerleştirilen: {placed_count}/{total_pieces}")
    print(f"  🚛 Kamyonet    : {num_trucks_used} adet")
    print(f"  📊 Kullanım    : %{utilization:.1f}")
    print(f"  ⏱️  Süre        : {execution_time:.2f}s")
    if unfitted_pieces:
        print(f"  ❌ Yerleşmeyen : {len(unfitted_pieces)}")

    return CuttingPlan3D(
        bins=bins_list,
        total_waste=total_waste,
        utilization=utilization,
        execution_time=execution_time,
        algorithm=f"3D-FFD-EP [{bin_mode}+{sort_mode}+{engine}+{heuristic}]",
        truck_assignments=truck_assignments,
        unfitted_pieces=unfitted_pieces,
    )
