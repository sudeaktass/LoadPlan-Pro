# -*- coding: utf-8 -*-
"""
3D Bin Packing — Core Module
Veri yapıları ve yardımcı fonksiyonlar
Silindirik yük desteği eklendi.

--- DÜZELTMELER (v2) ---

HATA-3 (Gravity Settle Tek Geçiş): Orijinal gravity_settle_placements
  fonksiyonu çakışma düzeltmesini tek geçişte yapıyordu. Bir parçayı
  yukarı taşımak, onun üzerindeki başka bir parçayla yeni bir çakışma
  yaratabilir. Tek geçiş bu zincir reaksiyonu yakalamıyordu.
  ÇÖZÜM: Düzeltme döngüsü, hiç değişiklik olmayıncaya kadar (yakınsama)
  tekrarlanıyor. Maksimum iterasyon sayısı N+1 ile sınırlandırılmış
  (N = parça sayısı); sonsuz döngü riski yok.
"""

import math
from dataclasses import dataclass
from typing import List, Tuple, Optional, Dict

# ============================================================================
# SABİTLER
# ============================================================================

DEFAULT_SUPPORT_RATIO      = 0.80   # Havadaki parça için minimum destekli taban oranı
GRAVITY_OVERLAP_THRESHOLD  = 0.10  # Düşük eşik: parçalar %10+ örtüşen engelden geçemez
FRAGILE_MAX_WEIGHT         = 50.0
WEIGHT_CENTER_TOLERANCE    = 0.10
SCORE_MISSING_PENALTY      = -1000
SCORE_TRUCK_PENALTY        = -50
SCORE_UTILIZATION_WEIGHT   = 0.8


# ============================================================================
# VERİ YAPILARI
# ============================================================================

@dataclass
class Piece3D:
    """3D Yük bilgileri — dikdörtgensel veya silindirik"""
    id: str
    width: int           # Kutu: genişlik  | Silindir: çap
    length: int          # Kutu: uzunluk   | Silindir: çap (= width)
    height: int          # Yükseklik (her iki şekil için aynı)
    quantity: int
    weight: float        = 0.0
    shape: str           = 'box'       # 'box' veya 'cylinder'
    allow_rotation_xy: bool = True
    allow_rotation_z: bool  = False
    priority: Optional[int] = None
    customer_id: Optional[str] = None
    is_fragile: bool     = False
    max_stack_weight: float = 1000.0
    is_stackable: bool   = True

    @property
    def radius(self) -> float:
        """Silindir yarıçapı (yalnızca shape='cylinder')"""
        return self.width / 2.0

    def get_bounding_volume(self) -> int:
        """Bounding-box hacmi (her iki şekil için aynı yerleştirme ızgarası)"""
        return self.width * self.length * self.height

    def get_actual_volume(self) -> float:
        """Gerçek hacim"""
        if self.shape == 'cylinder':
            return math.pi * (self.width / 2) ** 2 * self.height
        return float(self.width * self.length * self.height)


@dataclass
class Placement3D:
    """3D Yerleştirme bilgisi"""
    x: int
    y: int
    z: int
    width: int
    length: int
    height: int
    piece_id: str
    rotation: Tuple[int, int, int]
    bin_id: int = 0

    def get_volume(self) -> int:
        """Bounding-box hacmi (doluluk/fire hesabı için)"""
        return self.width * self.length * self.height

    def get_center(self) -> Tuple[float, float, float]:
        return (self.x + self.width  / 2,
                self.y + self.length / 2,
                self.z + self.height / 2)

    def get_cx(self) -> float:
        return self.x + self.width  / 2.0

    def get_cy(self) -> float:
        return self.y + self.length / 2.0


@dataclass
class Truck3D:
    """3D Kamyonet bilgileri"""
    id: str
    width: int
    length: int
    height: int
    capacity: float
    available: int

    def get_volume(self) -> int:
        return self.width * self.length * self.height


@dataclass
class Cuboid:
    """3D Boş alan"""
    x: int; y: int; z: int
    width: int; length: int; height: int

    def get_volume(self) -> int:
        return self.width * self.length * self.height


@dataclass
class CuttingPlan3D:
    """3D Paletleme planı"""
    bins: List[List[Placement3D]]
    total_waste: float
    utilization: float
    execution_time: float
    algorithm: str
    truck_assignments: Optional[Dict[int, str]] = None
    unfitted_pieces: Optional[List["Piece3D"]] = None   # Yerleştirilemeyen parçalar


# ============================================================================
# ROTASYON
# ============================================================================

def get_all_rotations_3d(piece: Piece3D) -> List[Tuple[int, int, int, Tuple]]:
    """
    Tüm olası rotasyonlar — silindir sadece Z ekseni döndürme.

    DÜZELTME (HATA-6 — Eksik Rotasyonlar):
    Orijinal kod kutu için 6 oryantasyondan yalnızca 4 tanesini üretiyordu;
    (h, w, l) ve (l, h, w) kombinasyonları eksikti. Bu, özellikle dar ve
    uzun parçaların yatay yerleşim fırsatlarını kaçırmasına neden oluyordu.

    Bir kutunun 6 benzersiz oryantasyonu (hangi yüzün taban olduğuna göre):
      Grup 1 — w×l taban, h yükseklik : (w,l,h)  ve  (l,w,h)
      Grup 2 — w×h taban, l yükseklik : (w,h,l)  ve  (h,w,l)  ← #4 ESKİDE EKSİKTİ
      Grup 3 — l×h taban, w yükseklik : (l,h,w)  ve  (h,l,w)  ← #5 ESKİDE EKSİKTİ

    YENİ YAKLAŞIM: Tüm 6 aday üretilir, görülmüş boyut kombinasyonları
    (seen set) ile tekrarlar filtrelenir ve izin flag'leri uygulanır.
    """
    if piece.shape == 'cylinder':
        # Çap her zaman w=l, yalnızca dikey rotasyon (yatırma) opsiyonel
        rotations = [(piece.width, piece.width, piece.height, (0, 0, 0))]
        if piece.allow_rotation_z and piece.width != piece.height:
            rotations.append((piece.height, piece.height, piece.width, (0, 90, 0)))
        return rotations

    w, l, h = piece.width, piece.length, piece.height
    seen: set = set()
    rotations: List[Tuple[int, int, int, Tuple]] = []

    def try_add(rw: int, rl: int, rh: int, rot: Tuple, needs_xy: bool = False,
                needs_z: bool = False) -> None:
        """Yinelenmeyen ve izin verilen rotasyonları ekle."""
        if needs_xy and not piece.allow_rotation_xy:
            return
        if needs_z and not piece.allow_rotation_z:
            return
        key = (rw, rl, rh)
        if key not in seen:
            seen.add(key)
            rotations.append((rw, rl, rh, rot))

    # ── Grup 1: w×l taban — h yükseklik ─────────────────────────────
    try_add(w, l, h, (0,   0,  0))               # Temel — her zaman
    try_add(l, w, h, (90,  0,  0), needs_xy=True)  # XY düzlem rotasyonu

    # ── Grup 2: w×h taban — l yükseklik ─────────────────────────────
    try_add(w, h, l, (0,   0, 90), needs_z=True)  # Eski kodda vardı
    try_add(h, w, l, (0, -90,  0), needs_z=True)  # ESKİ KODDA EKSİKTİ ← YENİ

    # ── Grup 3: l×h taban — w yükseklik ─────────────────────────────
    try_add(l, h, w, (90,  0, 90), needs_z=True)  # ESKİ KODDA EKSİKTİ ← YENİ
    try_add(h, l, w, (0,  90,  0), needs_z=True)  # Eski kodda vardı

    return rotations


# ============================================================================
# ÇAKIŞMA TESPİTİ — Şekil-farkında
# ============================================================================

def _z_overlap(z1: int, h1: int, z2: int, h2: int) -> bool:
    """İki nesnenin Z ekseni aralıkları örtüşüyor mu?"""
    return z1 < z2 + h2 and z2 < z1 + h1


def _circle_circle_overlap(cx1: float, cy1: float, r1: float,
                            cx2: float, cy2: float, r2: float) -> bool:
    """İki dairenin XY düzleminde çakışması"""
    dist2 = (cx1 - cx2) ** 2 + (cy1 - cy2) ** 2
    return dist2 < (r1 + r2) ** 2


def _circle_rect_overlap(cx: float, cy: float, r: float,
                          rx: int, ry: int, rw: int, rl: int) -> bool:
    """Daire ile dikdörtgenin XY düzleminde çakışması"""
    # Dikdörtgene en yakın noktayı bul, mesafeyi kontrol et
    nearest_x = max(rx, min(cx, rx + rw))
    nearest_y = max(ry, min(cy, ry + rl))
    dist2 = (cx - nearest_x) ** 2 + (cy - nearest_y) ** 2
    return dist2 < r * r


def check_collision_3d(p1: 'Placement3D', p2: 'Placement3D',
                       piece_info: Optional[Dict] = None) -> bool:
    """Şekil-farkında çarpışma tespiti"""
    # Önce Z ekseninde örtüşme
    if not _z_overlap(p1.z, p1.height, p2.z, p2.height):
        return False

    s1 = piece_info.get(p1.piece_id).shape if piece_info and p1.piece_id in piece_info else 'box'
    s2 = piece_info.get(p2.piece_id).shape if piece_info and p2.piece_id in piece_info else 'box'

    if s1 == 'cylinder' and s2 == 'cylinder':
        r1 = p1.width / 2.0;  cx1 = p1.x + r1;  cy1 = p1.y + r1
        r2 = p2.width / 2.0;  cx2 = p2.x + r2;  cy2 = p2.y + r2
        return _circle_circle_overlap(cx1, cy1, r1, cx2, cy2, r2)

    elif s1 == 'cylinder':
        r1 = p1.width / 2.0;  cx1 = p1.x + r1;  cy1 = p1.y + r1
        return _circle_rect_overlap(cx1, cy1, r1, p2.x, p2.y, p2.width, p2.length)

    elif s2 == 'cylinder':
        r2 = p2.width / 2.0;  cx2 = p2.x + r2;  cy2 = p2.y + r2
        return _circle_rect_overlap(cx2, cy2, r2, p1.x, p1.y, p1.width, p1.length)

    else:
        # Box vs Box — AABB
        return not (p1.x + p1.width  <= p2.x or p2.x + p2.width  <= p1.x or
                    p1.y + p1.length <= p2.y or p2.y + p2.length <= p1.y)


def check_collision_with_list(candidate: 'Placement3D',
                              placements: List['Placement3D'],
                              piece_info: Optional[Dict] = None) -> bool:
    for existing in placements:
        if check_collision_3d(candidate, existing, piece_info):
            return True
    return False


def is_within_bounds_3d(p: 'Placement3D', truck: 'Truck3D') -> bool:
    return (p.x >= 0 and p.y >= 0 and p.z >= 0 and
            p.x + p.width  <= truck.width and
            p.y + p.length <= truck.length and
            p.z + p.height <= truck.height)


# ============================================================================
# GRAVITY VE DESTEK
# ============================================================================

def find_lowest_z_position(x: int, y: int, width: int, length: int,
                           placements: List['Placement3D'],
                           overlap_threshold: float = GRAVITY_OVERLAP_THRESHOLD,
                           piece_info: Optional[Dict] = None,
                           placing_shape: str = 'box') -> int:
    """Gravity: en alttaki geçerli Z pozisyonu (şekil-farkında)"""
    max_z_below = 0
    new_area = width * length

    # Yerleştirilen nesnenin XY merkezi ve yarıçapı (silindir ise)
    px_cx = x + width  / 2.0
    px_cy = y + length / 2.0
    px_r  = width / 2.0

    for existing in placements:
        ex_shape = 'box'
        if piece_info and existing.piece_id in piece_info:
            ex_shape = piece_info[existing.piece_id].shape

        if ex_shape == 'cylinder':
            ex_cx = existing.x + existing.width  / 2.0
            ex_cy = existing.y + existing.length / 2.0
            ex_r  = existing.width / 2.0
            if placing_shape == 'cylinder':
                overlaps = _circle_circle_overlap(px_cx, px_cy, px_r, ex_cx, ex_cy, ex_r)
            else:
                overlaps = _circle_rect_overlap(ex_cx, ex_cy, ex_r, x, y, width, length)
            if overlaps:
                candidate_z = existing.z + existing.height
                max_z_below = max(max_z_below, candidate_z)
        else:
            ox = max(0, min(x + width,  existing.x + existing.width)  - max(x, existing.x))
            oy = max(0, min(y + length, existing.y + existing.length) - max(y, existing.y))
            overlap_area = ox * oy
            if new_area > 0 and overlap_area > new_area * overlap_threshold:
                candidate_z = existing.z + existing.height
                max_z_below = max(max_z_below, candidate_z)

    return max_z_below


def calculate_xy_overlap_area(x1, y1, w1, l1, x2, y2, w2, l2) -> float:
    overlap_x = max(0, min(x1 + w1, x2 + w2) - max(x1, x2))
    overlap_y = max(0, min(y1 + l1, y2 + l2) - max(y1, y2))
    return overlap_x * overlap_y


def check_support_3d(candidate: 'Placement3D',
                     placements: List['Placement3D'],
                     min_support_ratio: float = DEFAULT_SUPPORT_RATIO,
                     piece_info: Optional[Dict] = None) -> bool:
    """Destek kontrolü — şekil-farkında"""
    if candidate.z == 0:
        return True

    candidate_area = candidate.width * candidate.length
    c_shape = 'box'
    if piece_info and candidate.piece_id in piece_info:
        c_shape = piece_info[candidate.piece_id].shape
    if c_shape == 'cylinder':
        candidate_area = math.pi * (candidate.width / 2) ** 2

    total_support = 0.0
    for existing in placements:
        if abs(existing.z + existing.height - candidate.z) >= 1:
            continue
        ex_shape = 'box'
        if piece_info and existing.piece_id in piece_info:
            ex_shape = piece_info[existing.piece_id].shape

        if c_shape == 'cylinder' and ex_shape == 'cylinder':
            cx1 = candidate.x + candidate.width  / 2.0
            cy1 = candidate.y + candidate.length / 2.0
            r1  = candidate.width / 2.0
            cx2 = existing.x + existing.width  / 2.0
            cy2 = existing.y + existing.length / 2.0
            r2  = existing.width / 2.0
            if _circle_circle_overlap(cx1, cy1, r1, cx2, cy2, r2):
                total_support += math.pi * min(r1, r2) ** 2
        elif c_shape == 'cylinder':
            cx = candidate.x + candidate.width  / 2.0
            cy = candidate.y + candidate.length / 2.0
            r  = candidate.width / 2.0
            if _circle_rect_overlap(cx, cy, r, existing.x, existing.y,
                                    existing.width, existing.length):
                total_support += min(candidate_area,
                                     existing.width * existing.length)
        else:
            overlap = calculate_xy_overlap_area(
                candidate.x, candidate.y, candidate.width, candidate.length,
                existing.x,  existing.y,  existing.width,  existing.length)
            total_support += overlap

    support_ratio = total_support / candidate_area if candidate_area > 0 else 0
    return support_ratio >= min_support_ratio


def check_stacking_rules(candidate: 'Placement3D',
                         candidate_piece: 'Piece3D',
                         placements: List['Placement3D'],
                         piece_info: Dict) -> Tuple[bool, str]:
    """
    İstiflenme kuralları — 2 bağımsız kısıt:

    1) is_stackable=False  → "Altına yük konmasın" = Bu parça ZEMINE OTURUR.
       Candidate z>0 ise VE candidate_piece.is_stackable=False → reddedilir.

    2) is_fragile=True     → "Üstüne yük konmasın" = Bu parça hassas.
       Altındaki parça is_fragile ise candidate üstüne konamaz.
    """
    # KURAL 1: "Altına yük konmasın" — bu parçanın kendisi zemine oturmalı
    if not candidate_piece.is_stackable and candidate.z > 0:
        return False, (f"{candidate_piece.id} sadece zemine yerleştirilebilir "
                       f"(kural: altına yük konmasın, z=0 zorunlu)")

    if candidate.z == 0:
        return True, "OK"

    # z > 0: altındaki parçaları bul
    pallets_below = []
    for existing in placements:
        if abs(existing.z + existing.height - candidate.z) < 1:
            overlap = calculate_xy_overlap_area(
                candidate.x, candidate.y, candidate.width, candidate.length,
                existing.x,  existing.y,  existing.width,  existing.length)
            if overlap > 0:
                pallets_below.append(existing)

    for below in pallets_below:
        below_piece = piece_info.get(below.piece_id)
        if not below_piece:
            continue
        # KURAL 2: "Üstüne yük konmasın" — altındaki parça kırılgan ise üstüne yük konmaz
        if below_piece.is_fragile:
            return False, (f"{below_piece.id} parçasının üstüne yük konulamaz "
                           f"(kural: üstüne yük konmasın)")
        # Max istifleme ağırlığı kontrolü
        total_above = candidate_piece.weight
        for p in placements:
            if p.z >= candidate.z + candidate.height:
                ov = calculate_xy_overlap_area(
                    candidate.x, candidate.y, candidate.width, candidate.length,
                    p.x, p.y, p.width, p.length)
                if ov > 0:
                    pi = piece_info.get(p.piece_id)
                    if pi:
                        total_above += pi.weight
        if total_above > below_piece.max_stack_weight:
            return False, f"{below_piece.id} max istifleme ağırlığı aşılıyor"
    return True, "OK"


# ============================================================================
# GRAVITY SETTLE  [DÜZELTME: HATA-3]
# ============================================================================

def gravity_settle_placements(placements: List['Placement3D'],
                              piece_info: Optional[Dict] = None) -> List['Placement3D']:
    """
    Tüm yerleşimleri yerçekimine göre düzelt.

    DÜZELTME (HATA-3): Orijinal kod çakışma düzeltmesini tek geçişte
    yapıyordu. Bir parçayı yukarı taşımak, onun üzerindeki başka bir
    parçayla yeni bir çakışma yaratabilir; tek geçiş bu zincir etkisini
    yakalamıyordu.

    YENİ YAKLAŞIM — İki Aşama:
      Aşama 1 (Settle): Parçaları Z'ye göre sıralayarak her birini
        mevcut yerleşimlerin üzerine düşür. Bu adım büyük ölçüde doğru
        pozisyonu verir.
      Aşama 2 (Multi-pass Correction): Kalan çakışmaları gider.
        Hiç değişiklik olmayana kadar (yakınsama) tekrarlar.
        Maksimum iterasyon = N+1 (sonsuz döngü riski yok).
    """
    if not placements:
        return placements

    # ── Aşama 1: Gravity settle (Z'ye göre sıralı, single-pass) ──────────
    sorted_placements = sorted(placements, key=lambda p: p.z)
    settled: List[Placement3D] = []

    for p in sorted_placements:
        p_shape = 'box'
        if piece_info and p.piece_id in piece_info:
            p_shape = piece_info[p.piece_id].shape

        best_z = 0
        for existing in settled:
            ex_shape = 'box'
            if piece_info and existing.piece_id in piece_info:
                ex_shape = piece_info[existing.piece_id].shape

            existing_top = existing.z + existing.height
            if existing_top > p.z + p.height:
                continue  # bu nesne üstte kalır, destekleyemez

            # XY örtüşme (şekil-farkında)
            if p_shape == 'cylinder' and ex_shape == 'cylinder':
                pcx = p.x + p.width  / 2.0;  pcy = p.y + p.length / 2.0;  pr = p.width / 2.0
                ecx = existing.x + existing.width / 2.0
                ecy = existing.y + existing.length / 2.0
                er  = existing.width / 2.0
                overlaps = _circle_circle_overlap(pcx, pcy, pr, ecx, ecy, er)
            elif p_shape == 'cylinder':
                pcx = p.x + p.width  / 2.0;  pcy = p.y + p.length / 2.0;  pr = p.width / 2.0
                overlaps = _circle_rect_overlap(pcx, pcy, pr,
                                                existing.x, existing.y,
                                                existing.width, existing.length)
            elif ex_shape == 'cylinder':
                ecx = existing.x + existing.width / 2.0
                ecy = existing.y + existing.length / 2.0
                er  = existing.width / 2.0
                overlaps = _circle_rect_overlap(ecx, ecy, er,
                                                p.x, p.y, p.width, p.length)
            else:
                ox = max(0, min(p.x + p.width,  existing.x + existing.width)  - max(p.x, existing.x))
                oy = max(0, min(p.y + p.length, existing.y + existing.length) - max(p.y, existing.y))
                overlap_ratio = (ox * oy) / (p.width * p.length) if p.width * p.length > 0 else 0
                overlaps = overlap_ratio >= GRAVITY_OVERLAP_THRESHOLD

            if overlaps:
                best_z = max(best_z, existing_top)

        new_p = Placement3D(p.x, p.y, best_z, p.width, p.length, p.height,
                            p.piece_id, p.rotation, p.bin_id)
        settled.append(new_p)

    # ── Aşama 2: Multi-pass çakışma düzeltmesi  [DÜZELTME: HATA-3] ──────
    #
    # Eski tek-geçiş kodu: bir parçayı yukarı taşıdığında üstteki
    # parçayla yeni çakışma oluşup oluşmadığını kontrol etmiyordu.
    #
    # Yeni çok-geçiş kodu: hiç değişiklik olmayana kadar tekrarlar.
    # En kötü durumda N geçiş gerekir (N = parça sayısı).
    # Gerçek veriler için genellikle 1-3 geçiş yeterli.

    corrected: List[Placement3D] = list(settled)
    max_passes = len(corrected) + 1  # Sonsuz döngü güvencesi

    for pass_idx in range(max_passes):
        changed = False
        new_corrected: List[Placement3D] = []

        for p in corrected:
            z = p.z
            for existing in new_corrected:
                # Z aralıkları çakışıyor mu?
                if not (z < existing.z + existing.height and
                        existing.z < z + p.height):
                    continue
                # XY aralıkları çakışıyor mu?
                ox = max(0, min(p.x + p.width,  existing.x + existing.width)  - max(p.x, existing.x))
                oy = max(0, min(p.y + p.length, existing.y + existing.length) - max(p.y, existing.y))
                if ox > 0 and oy > 0:
                    # Çakışıyor → bu parçayı existing'in üstüne taşı
                    new_z = existing.z + existing.height
                    if new_z > z:
                        z = new_z
                        changed = True

            new_corrected.append(
                Placement3D(p.x, p.y, z, p.width, p.length, p.height,
                            p.piece_id, p.rotation, p.bin_id)
            )

        corrected = new_corrected

        if not changed:
            # Hiç değişiklik olmadı → yakınsadı, döngüden çık
            break

    if pass_idx > 1:
        print(f"  ℹ️  gravity_settle: {pass_idx + 1} geçiş gerekti "
              f"({len(corrected)} parça)")

    return corrected


# ============================================================================
# AĞIRLIK MERKEZİ
# ============================================================================

def calculate_center_of_gravity(placements, piece_info):
    total_weight = 0.0;  wx = wy = wz = 0.0
    for p in placements:
        piece = piece_info.get(p.piece_id)
        w = piece.weight if piece else 0
        cx, cy, cz = p.get_center()
        wx += w * cx;  wy += w * cy;  wz += w * cz
        total_weight += w
    if total_weight == 0:
        return (0.0, 0.0, 0.0)
    return (wx / total_weight, wy / total_weight, wz / total_weight)


# ============================================================================
# LİTERATÜR TABANLI AĞIRLIK DENGESİ
# ============================================================================
# Kaynaklar:
#   Synák & Nedeliaková (2024), Appl. Sci. 14(20):9328 — Araç eksen yükü analizi
#   Springer Compl. Intell. Syst. (2024) — 3D BPP CoG kısıtı (lateral ±350mm,
#     longitudinal ±100mm, vertical ±100mm — 40ft konteyner)
#   Erbayrak et al. (2021) — CoG sapmasını minimize eden ağırlıklı amaç fonksiyonu
#   beardown-logistics.com — Ağır yükler ön aksa yakın, CoG zemine yakın

# Toleranslar (fraksiyonel — araç boyutuna göre normalize)
COG_LATERAL_TOL    = 0.10   # X eksen: merkeze göre ±%10 (sol/sağ denge)
COG_LONG_TOL       = 0.15   # Y eksen: merkeze göre ±%15 (ön/arka denge)
COG_VERTICAL_MAX   = 0.60   # Z eksen: araç yüksekliğinin %60'ından aşağıda olmalı
COG_FRONT_BIAS     = 0.40   # İdeal boylamsal CoG = araç boyunun ön %40'ı
                             # (ön-ağır yükleme — fren stabilitesi + stabilite için)


def check_weight_balance(placements, piece_info, truck,
                         tolerance=COG_LATERAL_TOL):
    """
    Literatür tabanlı üç eksenli ağırlık merkezi kontrolü.

    Returns:
        (lateral_ok, long_ok, vertical_ok, details_dict)
    """
    if not placements:
        return True, True, True, {}

    cg_x, cg_y, cg_z = calculate_center_of_gravity(placements, piece_info)

    # ── Yanal denge (X) — tam merkez ────────────────────────────────────────
    center_x  = truck.width / 2
    x_dev     = abs(cg_x - center_x) / center_x if center_x > 0 else 0
    lateral_ok = x_dev <= tolerance

    # ── Boylamsal denge (Y) — ön-ağır ideal ─────────────────────────────────
    ideal_y   = truck.length * COG_FRONT_BIAS   # Ön aksa yakın ideal nokta
    y_dev     = abs(cg_y - ideal_y) / truck.length if truck.length > 0 else 0
    long_ok   = y_dev <= COG_LONG_TOL

    # ── Dikey denge (Z) — zemine yakın ──────────────────────────────────────
    z_frac    = cg_z / truck.height if truck.height > 0 else 0
    vertical_ok = z_frac <= COG_VERTICAL_MAX

    details = {
        "cog_x": cg_x, "cog_y": cg_y, "cog_z": cg_z,
        "x_dev": x_dev, "y_dev": y_dev, "z_frac": z_frac,
        "ideal_x": center_x, "ideal_y": ideal_y,
        "lateral_ok": lateral_ok, "long_ok": long_ok, "vertical_ok": vertical_ok,
    }
    return lateral_ok, long_ok, vertical_ok, details


def cog_penalty_score(placements, piece_info, truck):
    """
    Ağırlık merkezi sapma skoru — algoritmalar bu fonksiyonu minimize eder.
    Erbayrak et al. (2021) ağırlıklı sapma yaklaşımı baz alınmıştır.

    Dönen değer 0.0 (mükemmel) → 1.0+ (kötü).
    Algoritmalar bu skoru düşük tutan yerleşimi tercih etmelidir.
    """
    if not placements:
        return 0.0
    total_weight = sum(
        piece_info[pl.piece_id].weight
        for pl in placements if pl.piece_id in piece_info
    )
    if total_weight < 1e-6:
        return 0.0

    cg_x, cg_y, cg_z = calculate_center_of_gravity(placements, piece_info)

    # Normalize sapma skorları (0–1)
    cx   = truck.width / 2
    x_pen = abs(cg_x - cx) / cx if cx > 0 else 0          # lateral (ağırlık:0.4)

    ideal_y = truck.length * COG_FRONT_BIAS
    y_pen = abs(cg_y - ideal_y) / truck.length if truck.length > 0 else 0  # (ağırlık:0.35)

    z_frac = cg_z / truck.height if truck.height > 0 else 0
    z_pen = max(0.0, z_frac - COG_VERTICAL_MAX) / (1 - COG_VERTICAL_MAX)   # (ağırlık:0.25)

    # Ağırlıklar: yanal denge kritik (0.40), boylamsal/ön-ağır (0.50), dikey (0.10)
    return 0.40 * x_pen + 0.50 * y_pen + 0.10 * z_pen


# ─────────────────────────────────────────────────────────────────────────────
# ORTAK AMAÇ FONKSİYONU — tüm metaheuristikler aynı hedefi optimize eder
# ─────────────────────────────────────────────────────────────────────────────
# Tabu, SA, GA, Island GA ve Monte Carlo daha önce 3 ayrı fitness formülü
# kullanıyordu (kimi CoG'siz, kimi farklı araç cezası). Bu, adil karşılaştırmayı
# bozuyordu. Artık hepsi bu tek fonksiyonu kullanır.
#
# Bileşenler (düşük = daha iyi):
#   + num_bins   × W_BINS      : daha az araç tercih edilir
#   - util       × W_UTIL      : yüksek doluluk ödüllendirilir
#   + unplaced   × W_UNPLACED  : yerleşmeyen parça ağır ceza (baskın terim)
#   + overflow   × W_OVERFLOW  : kapasitenin üstünde araç açma cezası
#   + cog_pen    × W_COG       : ağırlık merkezi sapması cezası
#   + prio_pen                 : öncelik bölgesi ihlali (priority_utils'ten)

OBJ_W_BINS     = 100.0
OBJ_W_UTIL     = 100.0
OBJ_W_UNPLACED = 50_000.0
OBJ_W_OVERFLOW = 20_000.0
OBJ_W_COG      = 2_000.0


def _objective_used_volume(placement, piece_info):
    """Silindir için gerçek hacim, diğerleri için bounding-box hacmi."""
    if piece_info:
        pc = piece_info.get(placement.piece_id)
        if pc and getattr(pc, 'shape', 'box') == 'cylinder':
            return pc.get_actual_volume()
    return placement.get_volume()


def packing_objective(bins_list, truck_assignments, trucks, piece_info,
                      unplaced: int = 0, overflow_bins: int = 0):
    """
    TÜM algoritmalar için ortak amaç fonksiyonu. DÜŞÜK = DAHA İYİ.

    Args:
        bins_list        : List[List[Placement3D]] — her bin'in yerleşimleri
        truck_assignments: {bin_idx: truck_id}
        trucks           : List[Truck3D]
        piece_info       : {piece_id: Piece3D}
        unplaced         : yerleştirilemeyen parça sayısı
        overflow_bins    : kapasite üstü açılan araç sayısı

    Returns:
        (fitness, utilization)  — fitness düşük = iyi; utilization yüzde
    """
    from priority_utils import priority_violation_penalty  # lazy: döngüsel import önlenir

    total_volume = 0.0
    used_volume = 0.0
    for b_idx, placements in enumerate(bins_list):
        t_id = truck_assignments.get(b_idx)
        truck = next((t for t in trucks if t.id == t_id), None)
        if truck is None:
            continue
        total_volume += truck.get_volume()
        used_volume += sum(_objective_used_volume(p, piece_info) for p in placements)

    utilization = (used_volume / total_volume * 100.0) if total_volume > 0 else 0.0
    num_bins = len([b for b in bins_list if b])

    cog_pen = 0.0
    for b_idx, placements in enumerate(bins_list):
        if not placements:
            continue
        t_id = truck_assignments.get(b_idx)
        truck = next((t for t in trucks if t.id == t_id), None)
        if truck:
            cog_pen += cog_penalty_score(placements, piece_info, truck)

    prio_pen = priority_violation_penalty(
        bins_list, piece_info, trucks, truck_assignments)

    fitness = (num_bins      * OBJ_W_BINS
               - utilization * OBJ_W_UTIL
               + unplaced     * OBJ_W_UNPLACED
               + overflow_bins * OBJ_W_OVERFLOW
               + cog_pen      * OBJ_W_COG
               + prio_pen)
    return fitness, utilization


__all__ = [
    'DEFAULT_SUPPORT_RATIO', 'GRAVITY_OVERLAP_THRESHOLD', 'FRAGILE_MAX_WEIGHT',
    'WEIGHT_CENTER_TOLERANCE', 'SCORE_MISSING_PENALTY', 'SCORE_TRUCK_PENALTY',
    'SCORE_UTILIZATION_WEIGHT',
    'Piece3D', 'Placement3D', 'Truck3D', 'Cuboid', 'CuttingPlan3D',
    'get_all_rotations_3d',
    'check_collision_3d', 'check_collision_with_list', 'is_within_bounds_3d',
    'find_lowest_z_position', 'calculate_xy_overlap_area',
    'check_support_3d', 'check_stacking_rules',
    'calculate_center_of_gravity', 'check_weight_balance',
    'cog_penalty_score', 'COG_LATERAL_TOL', 'COG_LONG_TOL',
    'COG_VERTICAL_MAX', 'COG_FRONT_BIAS',
    'gravity_settle_placements',
    'packing_objective',
    'OBJ_W_BINS', 'OBJ_W_UTIL', 'OBJ_W_UNPLACED', 'OBJ_W_OVERFLOW', 'OBJ_W_COG',
]
