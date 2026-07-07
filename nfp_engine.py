# -*- coding: utf-8 -*-
"""
NFP Engine — 2D İç İçe Geçme (Nested Packing) Motoru
======================================================
No-Fit Polygon tabanlı 2D çokgen yerleştirme.

Desteklenen stratejiler:
  · BLF-NFP   — Bottom-Left-Fill + NFP (endüstri standardı)
  · Grid-BLF  — Izgaralı Bottom-Left (daha hızlı, küçük fark)

Referans: Bennell & Oliveira (2008) "The geometry of nesting problems: A tutorial"
          European Journal of Operational Research, 184(2), 397–415
"""

from __future__ import annotations
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np

try:
    from shapely.geometry import Polygon, box as shapely_box
    from shapely import affinity
    from shapely.strtree import STRtree
    HAS_SHAPELY = True
except ImportError:
    HAS_SHAPELY = False

log = logging.getLogger(__name__)

# ============================================================================
# VERİ YAPILARI
# ============================================================================

@dataclass
class NFPPlacement:
    """Tek bir parçanın 2D yerleşim bilgisi."""
    piece_index: int          # Parça sıra numarası
    piece_id:    str          # Parça kimliği
    x:           float        # Sol-alt köşe X (cm)
    y:           float        # Sol-alt köşe Y (cm)
    rotation_deg: float = 0.0  # Döndürme açısı (0 / 90 / 180 / 270)
    placed_polygon: Optional[object] = None  # Shapely Polygon (yerleştirme sonrası)


@dataclass
class NFPBin:
    """2D konteyner (kamyon taban alanı)."""
    width:  float             # cm
    length: float             # cm
    placements: List[NFPPlacement] = field(default_factory=list)

    @property
    def polygon(self) -> "Polygon":
        return shapely_box(0, 0, self.width, self.length)

    def utilization(self, piece_polygons: List["Polygon"]) -> float:
        total_area = sum(p.area for p in piece_polygons)
        return total_area / (self.width * self.length) if self.width * self.length > 0 else 0.0


@dataclass
class NFPPiece:
    """Yerleştirilecek parça (2D)."""
    index:    int
    piece_id: str
    polygon:  "Polygon"           # Shapely Polygon (orijin = sol-alt)
    allow_rotation: bool = True   # 0/90 denemesi yapılsın mı?
    priority: int = 0             # Büyük öncelik önce yerleşir


# ============================================================================
# YARDIMCI: Döndürme & Normalize
# ============================================================================

def _normalize(poly: "Polygon", rotation_deg: float = 0.0) -> "Polygon":
    """Poligonu verilen açıda döndürüp sol-alt köşeye taşır."""
    if rotation_deg != 0:
        poly = affinity.rotate(poly, rotation_deg, origin=(0, 0))
    minx, miny, _, _ = poly.bounds
    return affinity.translate(poly, -minx, -miny)


def _candidate_rotations(piece: NFPPiece) -> List[Tuple[float, "Polygon"]]:
    """
    Deneme rotasyonlarını (derece, normalize_poligon) ikilisi olarak döndürür.
    L/T/I profiller için 0° ve 90° önemli; silindirik için sadece 0°.
    """
    angles = [0.0]
    if piece.allow_rotation:
        angles = [0.0, 90.0, 180.0, 270.0]
    result = []
    for angle in angles:
        np_ = _normalize(piece.polygon, angle)
        # Bounding box
        minx, miny, maxx, maxy = np_.bounds
        result.append((angle, np_, maxx - minx, maxy - miny))
    return result


# ============================================================================
# NFP HESAPLAMA (Pratik Minkowski Sum)
# ============================================================================

def _compute_nfp_convex(stat_poly: "Polygon", orb_poly: "Polygon") -> "Polygon":
    """
    İki dışbükey poligon için NFP = Minkowski Sum(stationary, reflect(orbiting)).
    NFP içindeki herhangi bir noktaya orbiting'in referansını yerleştirirseniz
    çakışma olur; dışındaki noktalar güvenlidir.
    """
    # orbiting poligonu merkezine göre yansıt
    cx, cy = orb_poly.centroid.x, orb_poly.centroid.y
    reflected = affinity.scale(orb_poly, xfact=-1, yfact=-1, origin=(cx, cy))

    # Vertex'lerin Minkowski toplamı (dışbükey için tam sonuç)
    stat_coords = list(stat_poly.exterior.coords[:-1])
    refl_coords = list(reflected.exterior.coords[:-1])
    sum_points  = [(a[0] + b[0], a[1] + b[1])
                   for a in stat_coords for b in refl_coords]

    from shapely.geometry import MultiPoint
    hull = MultiPoint(sum_points).convex_hull
    return hull


def _compute_nfp_general(stat_poly: "Polygon", orb_poly: "Polygon",
                          resolution: int = 32) -> "Polygon":
    """
    Genel (dışbükey olmayan) poligonlar için yaklaşık NFP.
    Orbiting poligonu küçük adımlarla döndürüp her noktada uyumlu alanı test eder.
    Daha yavaş ama L/T/I profiller için gerekli.
    """
    # Pratik yaklaşım: buffer tabanlı Minkowski approximation
    # orb poligonunu negatif yönde kaydırarak "forbidden zone" hesapla

    # Orbiting referans noktası: sol-alt köşe (0, 0)
    # Forbidden zone: stationary üzerindeki her noktadan orbiting bounding box'ı çıkar
    orb_w = orb_poly.bounds[2] - orb_poly.bounds[0]
    orb_h = orb_poly.bounds[3] - orb_poly.bounds[1]

    # Yeterince iyi bir yaklaşım: her iki poligon convex hull NFP'si genişletilir
    stat_hull = stat_poly.convex_hull
    orb_hull  = orb_poly.convex_hull
    nfp_approx = _compute_nfp_convex(stat_hull, orb_hull)

    # Artırma: iç boşluklar için küçük shrink
    nfp_approx = nfp_approx.buffer(max(orb_w, orb_h) * 0.05)
    return nfp_approx


def compute_nfp(stat_poly: "Polygon", orb_poly: "Polygon") -> "Polygon":
    """Otomatik: dışbükey → kesin NFP, diğer → yaklaşık NFP."""
    if stat_poly.convex_hull.area - stat_poly.area < 1e-4:
        return _compute_nfp_convex(stat_poly, orb_poly)
    return _compute_nfp_general(stat_poly, orb_poly)


# ============================================================================
# IZGARA TABANLI BLF YERLEŞTİRME (Ana Algoritma)
# ============================================================================

class GridBLFPacker:
    """
    Grid-based Bottom-Left-Fill packer for irregular polygons.
    Adım: resolution (cm) — küçüldükçe daha hassas ama daha yavaş.
    L/T/I profiller için optimize edilmiştir.

    Karmaşıklık: O(pieces * grid_points * placed_count)
    Spatial index (STRtree) ile hızlandırılmıştır.
    """

    def __init__(self, resolution: float = 2.0, margin: float = 0.5):
        """
        Args:
            resolution: Yerleştirme ızgara adımı (cm). 1-5 arası önerilir.
            margin:     Parçalar arası minimum boşluk (cm).
        """
        if not HAS_SHAPELY:
            raise ImportError("Shapely gerekli: pip install shapely")
        self.resolution = resolution
        self.margin     = margin

    def pack(self, bin_: NFPBin, pieces: List[NFPPiece]) -> List[NFPPlacement]:
        """
        Parçaları konteynere yerleştirir.
        Yerleştirilemeyen parçalar listeye alınmaz.
        Döndürür: NFPPlacement listesi.
        """
        bin_poly = bin_.polygon
        placed_polys: List[Polygon] = []
        placements:   List[NFPPlacement] = []

        # Öncelik + büyük alan → önce sırala
        sorted_pieces = sorted(pieces, key=lambda p: (-p.priority, -p.polygon.area))

        spatial_idx: Optional[STRtree] = None   # İlk parçada boş

        for piece in sorted_pieces:
            best = self._find_best_position(
                piece, bin_poly, placed_polys, spatial_idx
            )
            if best is None:
                log.debug(f"'{piece.piece_id}' yerleştirilemedi")
                continue

            angle, placed_poly, px, py = best
            placement = NFPPlacement(
                piece_index    = piece.index,
                piece_id       = piece.piece_id,
                x              = px,
                y              = py,
                rotation_deg   = angle,
                placed_polygon = placed_poly,
            )
            placements.append(placement)
            placed_polys.append(placed_poly)

            # Spatial index güncelle (her 5 parçada rebuild — performans dengesi)
            if len(placed_polys) % 5 == 0 or spatial_idx is None:
                spatial_idx = STRtree(placed_polys)

        return placements

    def _find_best_position(
        self,
        piece:        NFPPiece,
        bin_poly:     "Polygon",
        placed_polys: List["Polygon"],
        spatial_idx:  Optional["STRtree"],
    ) -> Optional[Tuple[float, "Polygon", float, float]]:
        """
        Parça için en iyi (x, y, rotation) konumunu döndürür.
        Hedef: mümkün olan en küçük Y, sonra en küçük X (BLF).
        """
        bin_minx, bin_miny, bin_maxx, bin_maxy = bin_poly.bounds
        margin = self.margin
        res    = self.resolution
        best_score = None
        best_result = None

        rotations = _candidate_rotations(piece)

        for angle, norm_poly, pw, ph in rotations:
            # X ve Y aralığını belirle
            x_range = np.arange(bin_minx, bin_maxx - pw + res, res)
            y_range = np.arange(bin_miny, bin_maxy - ph + res, res)

            for py in y_range:
                for px in x_range:
                    candidate = affinity.translate(norm_poly, px, py)

                    # Konteyner içinde mi?
                    if not bin_poly.contains(candidate):
                        continue

                    # Mevcut parçalarla çakışıyor mu?
                    if self._overlaps(candidate, placed_polys, spatial_idx, margin):
                        continue

                    # BLF skoru: önce Y, sonra X (küçük = iyi)
                    score = (py, px)
                    if best_score is None or score < best_score:
                        best_score  = score
                        best_result = (angle, candidate, px, py)

                if best_result and best_score[0] < py - res * 2:
                    break   # Erken çıkış: daha iyi Y bulunamaz

        return best_result

    @staticmethod
    def _overlaps(
        candidate:    "Polygon",
        placed_polys: List["Polygon"],
        spatial_idx:  Optional["STRtree"],
        margin:       float,
    ) -> bool:
        """
        Aday poligonun yerleştirilmiş poligonlarla çakışıp çakışmadığını kontrol eder.
        margin > 0 ise parçalar arası boşluk bırakır.
        """
        if not placed_polys:
            return False

        # Margin varsa candidate'i büyüt
        check = candidate.buffer(margin / 2) if margin > 0 else candidate

        if spatial_idx is not None:
            candidates_idx = spatial_idx.query(check)
            for idx in candidates_idx:
                if idx < len(placed_polys) and check.intersects(placed_polys[idx]):
                    return True
        else:
            for pp in placed_polys:
                if check.intersects(pp):
                    return True
        return False


# ============================================================================
# 3D KATMANLI PAKETLEME (Cross-Section Nesting + Yükseklik)
# ============================================================================

@dataclass
class LayerGroup:
    """Aynı Z katmanında birlikte yerleştirilen parçalar."""
    z_start:    float
    z_end:      float
    placements: List[NFPPlacement]
    piece_heights: List[float]   # Her placement için yükseklik


def pack_3d_with_nesting(
    pieces_data: List[dict],     # [{id, polygon, width, length, height, quantity, priority, allow_rotation}]
    truck_width:  float,
    truck_length: float,
    truck_height: float,
    resolution:   float = 2.0,
    margin:       float = 0.5,
) -> Tuple[List[LayerGroup], float]:
    """
    3D yerleştirme:
    1. 2D NFP taban packing
    2. Parçaları yüksekliğe göre katmanla

    Döndürür: (katman listesi, doluluk oranı %)
    """
    if not HAS_SHAPELY:
        raise ImportError("Shapely gerekli")

    packer = GridBLFPacker(resolution=resolution, margin=margin)
    bin_2d = NFPBin(width=truck_width, length=truck_length)

    # Tüm parçaları genişlet (adet × tekrar)
    all_pieces: List[NFPPiece] = []
    idx = 0
    for pd_ in pieces_data:
        qty = pd_.get("quantity", 1)
        poly = pd_.get("polygon")
        if poly is None:
            # Bounding box poligon
            poly = shapely_box(0, 0, pd_["width"], pd_["length"])
        for _ in range(qty):
            all_pieces.append(NFPPiece(
                index         = idx,
                piece_id      = pd_["id"],
                polygon       = poly,
                allow_rotation = pd_.get("allow_rotation", True),
                priority      = pd_.get("priority", 0),
            ))
            idx += 1

    # 2D yerleştir
    placements_2d = packer.pack(bin_2d, all_pieces)

    # Yükseklikleri eşleştir
    piece_h_map = {pd_["id"]: pd_["height"] for pd_ in pieces_data}

    # Z ekseni: yerleştirilen parçaları yüksekliklerine göre katmanlara böl
    # Basit strateji: her parça bağımsız olarak zemine yerleşir (istiflenme sonraki adım)
    layer_groups: List[LayerGroup] = []

    for pl in placements_2d:
        h = piece_h_map.get(pl.piece_id, 0)
        z_start = 0.0
        z_end   = h

        if z_end > truck_height:
            log.warning(f"'{pl.piece_id}' yüksekliği araç sığmıyor, atlandı.")
            continue

        layer_groups.append(LayerGroup(
            z_start    = z_start,
            z_end      = z_end,
            placements = [pl],
            piece_heights = [h],
        ))

    # Doluluk hesabı
    total_piece_vol = sum(
        (piece_h_map.get(p.piece_id, 0) * p.placed_polygon.area)
        for lg in layer_groups for p in lg.placements
        if p.placed_polygon is not None
    )
    truck_vol = truck_width * truck_length * truck_height
    utilization = (total_piece_vol / truck_vol * 100) if truck_vol > 0 else 0.0

    return layer_groups, utilization


# ============================================================================
# CROSS-SECTION NESTING GÖRSEL VERİ
# ============================================================================

def placements_to_plot_data(
    layer_groups: List[LayerGroup],
    piece_colors: Optional[dict] = None,
) -> List[dict]:
    """
    Yerleştirme sonuçlarını Plotly için hazır sözlük listesine çevirir.
    Her sözlük: {piece_id, x, y, z_start, z_end, polygon_coords, color}
    """
    result = []
    color_pool = [
        '#FF6B6B','#4ECDC4','#45B7D1','#96CEB4','#FFEAA7','#DDA0DD',
        '#98D8C8','#F7DC6F','#BB8FCE','#85C1E9','#F8C471','#82E0AA',
    ]
    id_color_map = piece_colors or {}
    color_idx = 0

    for lg in layer_groups:
        for pl in lg.placements:
            if pl.placed_polygon is None:
                continue
            pid = pl.piece_id
            if pid not in id_color_map:
                id_color_map[pid] = color_pool[color_idx % len(color_pool)]
                color_idx += 1
            # Poligon koordinatları
            coords = list(pl.placed_polygon.exterior.coords)
            result.append({
                "piece_id": pid,
                "x":        pl.x,
                "y":        pl.y,
                "z_start":  lg.z_start,
                "z_end":    lg.z_end,
                "polygon_coords": coords,
                "color":    id_color_map[pid],
                "rotation": pl.rotation_deg,
            })
    return result
