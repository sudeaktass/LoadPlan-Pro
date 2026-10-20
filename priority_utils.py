# -*- coding: utf-8 -*-
"""
Priority Utilities — Oncelik Bolge Yonetimi
============================================
Tum algoritmalar icin paylasilan oncelik yardimci fonksiyonlari.

Kural:
  priority=None → Normal urun, her yere gidebilir
  priority=1    → Kapiya en yakin bolge (son %30)  — son yuklenir
  priority=2    → Orta bolge (ort %30)
  priority=N    → Aracilikla eslesmis bolge

LIFO prensibi: son yuklenen ilk cikar → kapiya yakin = en son yuklenen.
"""

from __future__ import annotations
from typing import List, Tuple, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from core_3d import Piece3D, Placement3D, Truck3D


# ─────────────────────────────────────────────────────────────────────────────
# Bolge orani sabitleri
# ─────────────────────────────────────────────────────────────────────────────
ZONE1_START = 0.70   # Son %30 → Oncelik-1 bolgesi (kapiya en yakin)
ZONE2_START = 0.40   # Orta %30 → Oncelik-2 bolgesi
ZONE0_END   = 1.00   # Normal urunler her yere gidebilir

# Oncelik ihlal cezasi (iteratif algoritmalar icin)
PRIORITY_PENALTY = 1_000_000.0


# ─────────────────────────────────────────────────────────────────────────────
# Siralama anahtari
# ─────────────────────────────────────────────────────────────────────────────

def priority_sort_key(piece) -> tuple:
    """
    Tum algoritmalarda kullanilacak tutarli siralama anahtari.

    Siralama amaci (LIFO prensibine gore):
      1. priority=None  → en once yerlestir (depoya en uzak, on kisim)
      2. priority=buyuk → orta
      3. priority=1     → en son yerlestir (kapiya en yakin)

    Ayni oncelikte: MAX boyuta gore (buyukten kucuge), sonra hacime gore.

    Neden max boyut once?
      Profil gibi uzun/dar parcalar (L/T/I profil, boru) kucuk hacme sahip
      oldugu icin salt hacim sirasinda en sona kalir; o sirada kamyon
      uzunlugu diger kutularla dolmus olur ve 600 cm'lik kesintisiz alan
      bulunamaz. Max boyuta gore siralama bu parcalari one alarak
      uzunluk eksenini ilk onlar istesin.
    """
    p = piece
    prio    = p.priority if p.priority is not None else None
    volume  = p.width * p.length * p.height
    max_dim = max(p.width, p.length, p.height)

    if prio is None:
        return (0, -max_dim, -volume)   # En once; max boyut desc, sonra hacim desc
    else:
        return (1, -prio, -volume)      # Kucuk priority numarasi → daha GERI


def sort_piece_list(pieces: list) -> list:
    """Parca listesini priority_sort_key'e gore siralar (kopya dondurur)."""
    return sorted(pieces, key=priority_sort_key)


def sort_piece_list_inplace(pieces: list) -> None:
    """Parca listesini yerinde siralar."""
    pieces.sort(key=priority_sort_key)


# ─────────────────────────────────────────────────────────────────────────────
# Oncelik bolgesi hesaplama
# ─────────────────────────────────────────────────────────────────────────────

def get_priority_zone(truck_length: int, priority: Optional[int]) -> Tuple[int, int]:
    """
    Oncelik degerine gore arac uzunlugu (Y ekseni) icindeki
    gecerli [y_min, y_max) araligini dondurur.

    priority=None → (0, truck_length)    tam serbest
    priority=1    → (0.70*L, L)          kapiya en yakin
    priority=2    → (0.40*L, 0.70*L)     orta bolge
    priority>=3   → (0, 0.40*L)          on kisim
    """
    L = truck_length
    if priority is None or priority == 0:
        return (0, L)
    elif priority == 1:
        return (int(L * ZONE1_START), L)
    elif priority == 2:
        return (int(L * ZONE2_START), int(L * ZONE1_START))
    else:
        return (0, int(L * ZONE2_START))


def placement_in_zone(placement, piece, truck_length: int) -> bool:
    """
    Yerlesimin oncelik bolgesinde olup olmadigini kontrol eder.
    priority=None ise her zaman True.
    """
    prio = getattr(piece, 'priority', None)
    if prio is None or prio == 0:
        return True

    y_min, y_max = get_priority_zone(truck_length, prio)
    item_center_y = placement.y + placement.length / 2
    return y_min <= item_center_y <= y_max


# ─────────────────────────────────────────────────────────────────────────────
# Oncelik ihlal cezasi (iteratif algoritmalar icin)
# ─────────────────────────────────────────────────────────────────────────────

def priority_violation_penalty(
    bins_list: list,
    piece_info: dict,
    trucks: list,
    truck_assignments: dict,
) -> float:
    """
    Cozumdeki oncelik ihlallerinin toplam cezasini hesaplar.
    Her ihlal PRIORITY_PENALTY kadar ceza uretir.

    iteratif algoritmalarin evaluate_solution() fonksiyonuna eklenmeli:
        fitness += priority_violation_penalty(bins, piece_info, trucks, ta)
    """
    total_penalty = 0.0
    for bin_id, placements in enumerate(bins_list):
        if not placements:
            continue
        truck_id = truck_assignments.get(bin_id)
        truck = next((t for t in trucks if t.id == truck_id), None)
        if truck is None:
            continue
        L = truck.length
        for pl in placements:
            piece = piece_info.get(pl.piece_id)
            if piece is None:
                continue
            prio = getattr(piece, 'priority', None)
            if prio is None or prio == 0:
                continue
            y_min, y_max = get_priority_zone(L, prio)
            item_center_y = pl.y + pl.length / 2
            if not (y_min <= item_center_y <= y_max):
                total_penalty += PRIORITY_PENALTY
    return total_penalty


# ─────────────────────────────────────────────────────────────────────────────
# Cozum validasyonu (run() sonunda cagirilir)
# ─────────────────────────────────────────────────────────────────────────────

def collect_priority_violations(
    bins_list: list,
    piece_info: dict,
    trucks: list,
    truck_assignments: dict,
) -> list:
    """
    Cozumdeki oncelik ihlallerini yapisal liste olarak dondurur.
    UI'da (show_kpis) uyari paneli olarak gosterilir.

    Returns: [{"bin": int, "piece_id": str, "priority": int,
               "y_center": float, "expected": (y_min, y_max)}]
    """
    violations = []
    for bin_id, placements in enumerate(bins_list):
        if not placements:
            continue
        truck_id = truck_assignments.get(bin_id) if truck_assignments else None
        truck = next((t for t in trucks if t.id == truck_id), None)
        if truck is None:
            continue
        L = truck.length
        for pl in placements:
            piece = piece_info.get(pl.piece_id)
            if piece is None:
                continue
            prio = getattr(piece, 'priority', None)
            if prio is None or prio == 0:
                continue
            y_min, y_max = get_priority_zone(L, prio)
            item_center_y = pl.y + pl.length / 2
            if not (y_min <= item_center_y <= y_max):
                violations.append({
                    "bin": bin_id, "piece_id": pl.piece_id, "priority": prio,
                    "y_center": item_center_y, "expected": (y_min, y_max),
                })
    return violations


def validate_priority(
    bins_list: list,
    piece_info: dict,
    trucks: list,
    truck_assignments: dict,
    algo_name: str = "Algoritma",
) -> int:
    """
    Cozumdeki oncelik ihlallerini konsola raporlar.
    Ihlal sayisini dondurur (0 = temiz).
    """
    violations = collect_priority_violations(
        bins_list, piece_info, trucks, truck_assignments)
    if violations:
        print(f"[!] {algo_name}: {len(violations)} oncelik ihlali:")
        for v in violations:
            print(f"  - '{v['piece_id']}' (oncelik={v['priority']}) "
                  f"yanlis bolgede: y_center={v['y_center']:.0f} "
                  f"| beklenen [{v['expected'][0]}, {v['expected'][1]}]")
    else:
        print(f"[OK] {algo_name}: oncelik kontrolu temiz")
    return len(violations)
