# -*- coding: utf-8 -*-
"""
Bounds 3D — Alt/Üst Sınır Hesapları (Optimality Bounds)
========================================================
3D bin packing NP-zor olduğundan büyük örneklerde mutlak optimum garanti
edilemez. Ancak GEÇERLİ ALT SINIRLAR (lower bounds) hesaplanabilir: bu
sınırlardan daha iyi bir çözüm GEOMETRİK/FİZİKSEL OLARAK İMKANSIZDIR.

Bu modül, sezgisel çözümün optimuma ne kadar yakın olduğunu ÖLÇMEYİ sağlar:
  • Araç sayısı alt sınırı  → "en az kaç araç şart"
  • Doluluk üst sınırı      → "teorik maksimum doluluk"
  • Optimality gap          → "çözüm optimumdan en fazla %X uzakta"

Referanslar:
  - Martello, S., Pisinger, D., & Vigo, D. (2000). The Three-Dimensional
    Bin Packing Problem. Operations Research, 48(2), 256–267.
    (L0 hacim alt sınırı — bölüm 2.1)
  - Boschetti, M.A. (2004). New lower bounds for the 3D-BPP. Discrete
    Applied Mathematics.
"""

from __future__ import annotations
from typing import List, Dict
from dataclasses import dataclass


@dataclass
class FleetBounds:
    """Filo (araç seçimi) için sınır raporu."""
    lb_trucks:        int     # Araç sayısı alt sınırı (max(hacim, ağırlık))
    lb_by_volume:     int     # Hacim kaynaklı alt sınır
    lb_by_weight:     int     # Ağırlık kaynaklı alt sınır
    total_item_vol:   float   # Toplam parça hacmi (cm³)
    total_item_weight:float   # Toplam parça ağırlığı (kg)
    max_util_at_lb:   float   # LB araçla teorik maksimum doluluk (%)
    unfit_pieces:     List[str]  # Hiçbir araca sığmayan parça id'leri
    feasible:         bool    # Tüm parçalar en az bir araca sığıyor mu? (boyut)
    capacity_feasible:bool    # Eldeki filonun toplam hacmi/kapasitesi yetiyor mu?


def _piece_fits_truck(piece, truck) -> bool:
    """Parça (rotasyon dahil) bu aracın boyutlarına sığar mı?"""
    dims  = sorted([piece.width, piece.length, piece.height])
    tdims = sorted([truck.width, truck.length, truck.height])
    return all(dims[i] <= tdims[i] for i in range(3))


def _actual_piece_volume(piece) -> float:
    """Silindir için gerçek hacim (π·r²·h), kutu için bounding-box."""
    if getattr(piece, 'shape', 'box') == 'cylinder':
        try:
            return piece.get_actual_volume()
        except Exception:
            pass
    return piece.width * piece.length * piece.height


def _min_trucks_to_cover(amount: float, capacities: List[float]) -> int:
    """
    Verilen 'amount' (hacim veya ağırlık) miktarını kapsamak için gereken
    MİNİMUM araç sayısı. En büyük kapasiteli araçlar önce kullanılır →
    bu, geçerli bir ALT SINIRDIR (daha az araçla bu miktar taşınamaz).

    ÖNEMLİ: Alt sınır, eldeki araç adedi (availability) ile SINIRLANMAZ —
    o parçaların kendi özelliğidir. Eldeki araçlar tükenirse, kalan miktar
    en büyük araç kapasitesiyle (hipotetik) kapatılarak ceil alınır.
    Yetersizlik ayrı bir 'feasible' bayrağıyla raporlanır.

    capacities: kullanılabilir araç kapasiteleri (availability açılmış).
    """
    import math
    if amount <= 0:
        return 0
    caps = sorted(capacities, reverse=True)
    if not caps:
        return 0
    acc = 0.0
    n = 0
    for c in caps:
        if acc >= amount - 1e-9:
            break
        acc += c
        n += 1
    # Eldeki araçlar yetmedi → kalanı en büyük araçla (hipotetik) kapat
    if acc < amount - 1e-9:
        remaining = amount - acc
        n += int(math.ceil(remaining / caps[0]))
    return n


def compute_fleet_bounds(pieces: List, trucks: List) -> FleetBounds:
    """
    Filo için alt sınır raporu hesapla.

    Args:
        pieces: Piece3D listesi (quantity alanlı)
        trucks: Truck3D listesi (available alanlı)

    Returns:
        FleetBounds
    """
    # ── Parça toplamları (quantity dahil) ────────────────────────────────
    total_item_vol = sum(_actual_piece_volume(p) * p.quantity for p in pieces)
    total_item_weight = sum(p.weight * p.quantity for p in pieces)

    # ── Sığmazlık kontrolü: her parça en az bir araca sığmalı ────────────
    unfit = []
    for p in pieces:
        if not any(_piece_fits_truck(p, t) for t in trucks):
            unfit.append(str(p.id))

    # ── Availability açılmış kapasite listeleri ──────────────────────────
    vol_caps:    List[float] = []
    weight_caps: List[float] = []
    for t in trucks:
        for _ in range(max(0, int(t.available))):
            vol_caps.append(t.get_volume())
            weight_caps.append(t.capacity)

    # ── İki bağımsız alt sınır → maksimumu al ────────────────────────────
    lb_vol = _min_trucks_to_cover(total_item_vol, vol_caps)
    lb_wt  = _min_trucks_to_cover(total_item_weight, weight_caps)
    lb = max(lb_vol, lb_wt, 1 if (pieces and not unfit) else 0)

    # ── Kapasite yeterliliği: eldeki filo toplamı parçaları taşıyabilir mi?
    total_avail_vol    = sum(vol_caps)
    total_avail_weight = sum(weight_caps)
    capacity_ok = (total_avail_vol >= total_item_vol - 1e-9 and
                   total_avail_weight >= total_item_weight - 1e-9)

    # ── LB araçla teorik maksimum doluluk ────────────────────────────────
    # En büyük lb araç seçilirse → en küçük toplam hacim → en yüksek doluluk
    top_vols = sorted(vol_caps, reverse=True)[:lb]
    lb_fleet_vol = sum(top_vols) if top_vols else 0.0
    max_util = (total_item_vol / lb_fleet_vol * 100.0) if lb_fleet_vol > 0 else 0.0
    max_util = min(max_util, 100.0)

    return FleetBounds(
        lb_trucks=lb,
        lb_by_volume=lb_vol,
        lb_by_weight=lb_wt,
        total_item_vol=total_item_vol,
        total_item_weight=total_item_weight,
        max_util_at_lb=max_util,
        unfit_pieces=unfit,
        feasible=(len(unfit) == 0),
        capacity_feasible=capacity_ok,
    )


def optimality_report(num_trucks_used: int,
                      utilization: float,
                      bounds: FleetBounds) -> Dict[str, object]:
    """
    Sezgisel çözümü alt sınıra karşı değerlendir.

    Returns dict:
        proven_optimal_trucks : bool — araç sayısı kanıtlanmış optimum mu?
        truck_gap             : int  — kullanılan - alt sınır (0 = optimum)
        util_gap_pts          : float — teorik maks. doluluk - gerçek (puan)
        verdict               : str  — kullanıcıya gösterilecek özet
    """
    truck_gap = max(0, num_trucks_used - bounds.lb_trucks)
    proven = (num_trucks_used == bounds.lb_trucks and bounds.feasible
              and bounds.lb_trucks > 0)
    util_gap = max(0.0, bounds.max_util_at_lb - utilization)

    if not bounds.feasible:
        verdict = (f"⚠️ {len(bounds.unfit_pieces)} parça hiçbir araca sığmıyor "
                   f"— önce daha büyük araç ekleyin.")
    elif not bounds.capacity_feasible:
        verdict = (f"⚠️ Eldeki filonun toplam hacmi/kapasitesi yetersiz — "
                   f"en az {bounds.lb_trucks} araç gerekir, daha fazla araç ekleyin.")
    elif proven:
        verdict = (f"✅ KANITLANMIŞ OPTİMUM (araç sayısı): {num_trucks_used} araç, "
                   f"teorik alt sınıra eşit. Daha az araçla çözüm İMKANSIZ.")
    else:
        verdict = (f"≈ Araç sayısı: {num_trucks_used} (alt sınır: {bounds.lb_trucks}). "
                   f"En iyi durumda {truck_gap} araç daha az olabilir — "
                   f"ancak alt sınır geometrik olarak ulaşılamayabilir.")

    return {
        "proven_optimal_trucks": proven,
        "truck_gap": truck_gap,
        "util_gap_pts": util_gap,
        "verdict": verdict,
    }
