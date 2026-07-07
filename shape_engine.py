# -*- coding: utf-8 -*-
"""
Shape Engine — STEP / STL Dosya Okuma & Profil Üreteci
=======================================================
Destekler:
  · STL  → trimesh (her ortamda çalışır)
  · STEP → cadquery (cloud/Docker'da çalışır)
  · Parametrik profiller: L, T, I, Boru (içi boş silindir), Poligon

Her şeklin çıktısı:
  ShapeInfo — bounding box, gerçek hacim, ağırlık merkezi,
              2D kesit poligonu (Shapely Polygon), görsel mesh
"""

from __future__ import annotations
import math
import logging
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np

try:
    import trimesh
    HAS_TRIMESH = True
except ImportError:
    HAS_TRIMESH = False

try:
    from shapely.geometry import Polygon
    from shapely import affinity
    HAS_SHAPELY = True
except ImportError:
    HAS_SHAPELY = False

try:
    import cadquery as cq
    HAS_CADQUERY = True
except ImportError:
    HAS_CADQUERY = False

log = logging.getLogger(__name__)


# ============================================================================
# ÇIKTI VERİ YAPISI
# ============================================================================

@dataclass
class ShapeInfo:
    """
    Bir 3D şeklin tüm geometrik bilgileri.
    Bu yapı core_3d.Piece3D oluşturmak için kullanılır.
    """
    name: str = "Bilinmeyen"
    shape_type: str = "custom"           # box, cylinder, hollow_cylinder, l_profile, t_profile, i_profile, polygon, custom

    # Bounding box (cm)
    bbox_width: float  = 0.0
    bbox_length: float = 0.0
    bbox_height: float = 0.0

    # Gerçek fiziksel değerler
    actual_volume_cm3: float  = 0.0      # cm³
    surface_area_cm2: float   = 0.0      # cm²
    center_of_mass: Tuple[float, float, float] = (0.0, 0.0, 0.0)   # bbox'a göre göreli (0-1)

    # 2D Kesit poligonu (XY düzlemi, cm cinsinden, orijin = sol-alt köşe)
    cross_section: Optional[object] = None   # Shapely Polygon

    # Doluluk oranı = gerçek hacim / bounding box hacmi
    fill_ratio: float = 1.0

    # Görsel mesh (plotly için vertex/triangle listeleri)
    mesh_vertices: Optional[np.ndarray] = None   # (N, 3)
    mesh_faces:    Optional[np.ndarray] = None   # (M, 3) — üçgen indeksleri

    # Profil parametreleri (raporlama için)
    profile_params: dict = field(default_factory=dict)

    # Kaynak dosya
    source_file: Optional[str] = None

    @property
    def bbox_volume_cm3(self) -> float:
        return self.bbox_width * self.bbox_length * self.bbox_height

    @property
    def display_name(self) -> str:
        TYPE_LABELS = {
            "box":             "Dikdörtgen Kutu",
            "cylinder":        "Silindir",
            "hollow_cylinder": "İçi Boş Boru",
            "l_profile":       "L Profil",
            "t_profile":       "T Profil",
            "i_profile":       "I Profil",
            "polygon":         "Poligon Kesit",
            "custom":          "Özel (Dosyadan)",
        }
        return TYPE_LABELS.get(self.shape_type, self.shape_type)

    def to_piece_kwargs(self) -> dict:
        """core_3d.Piece3D(**kwargs) için hazır sözlük."""
        return {
            "width":  int(round(self.bbox_width)),
            "length": int(round(self.bbox_length)),
            "height": int(round(self.bbox_height)),
            "shape":  "cylinder" if self.shape_type == "cylinder" else "box",
            # Nested packing bu alan üzerinden devreye girer:
            "_cross_section": self.cross_section,
            "_fill_ratio":    self.fill_ratio,
            "_shape_type":    self.shape_type,
            "_mesh_vertices": self.mesh_vertices,
            "_mesh_faces":    self.mesh_faces,
        }


# ============================================================================
# STL OKUMA
# ============================================================================

def load_stl(path: str | Path, unit: str = "mm") -> ShapeInfo:
    """
    STL dosyasından ShapeInfo oluşturur.
    trimesh ile mesh yüklenir; kesit poligonu orta Z'den alınır.

    unit: STL dosyasının birimi — "mm" (SolidWorks varsayılanı), "cm", "m", "inch"
          Tüm birimler otomatik olarak cm'ye çevrilir.
    """
    if not HAS_TRIMESH:
        raise ImportError("trimesh yüklü değil: pip install trimesh")

    path = Path(path)
    mesh: trimesh.Trimesh = trimesh.load(str(path), force='mesh')
    if mesh is None or mesh.is_empty:
        raise ValueError(f"STL dosyası yüklenemedi veya boş: {path}")

    # Birim dönüşümü: unit parametresine göre ölçekle
    # SolidWorks varsayılanı: mm → cm için ÷10
    _scale_map = {"mm": 0.1, "cm": 1.0, "m": 100.0, "inch": 2.54}
    _scale = _scale_map.get(unit, 0.1)
    if abs(_scale - 1.0) > 1e-9:
        mesh.apply_scale(_scale)

    bounds = mesh.bounds          # [[xmin,ymin,zmin],[xmax,ymax,zmax]]
    dims = [
        float(bounds[1][0] - bounds[0][0]),
        float(bounds[1][1] - bounds[0][1]),
        float(bounds[1][2] - bounds[0][2]),
    ]
    # ── Optimal yönlendirme: en büyük yüzey alanı zemine gelsin ──────────────
    # Her eksen kombinasyonu için taban alanını hesapla; en büyüğü seç.
    # Bu sayede daha fazla ürün yan yana sığar ve yükleme daha kararlı olur.
    # _ax: mesh vertex dizisine uygulanacak sütun permütasyonu [idx_w, idx_l, idx_h]
    dim_orientations = [
        (dims[0], dims[1], dims[2], [0, 1, 2]),   # Orijinal (X=G, Y=U, Z=H)
        (dims[0], dims[2], dims[1], [0, 2, 1]),   # Y↔Z — geniş yüzey öne
        (dims[1], dims[2], dims[0], [1, 2, 0]),   # X→H, Y→G, Z→U
    ]
    # En büyük taban (G×U) alanına sahip orientasyonu seç
    best_orient = max(dim_orientations, key=lambda t: t[0] * t[1])
    w, l, h, _ax = best_orient

    # Ağırlık merkezi (göreli 0-1) — seçilen eksenlere göre
    com_raw = mesh.center_mass - np.array(bounds[0])   # mesh orijinine göre CoM
    com_perm = com_raw[_ax]                             # permütasyon uygula
    com_rel = (
        float(com_perm[0] / w) if w > 0 else 0.5,
        float(com_perm[1] / l) if l > 0 else 0.5,
        float(com_perm[2] / h) if h > 0 else 0.5,
    )

    # Kesit: orijinal mesh Z'sini koru (trimesh kesit Z ekseninde çalışır)
    cross_poly = _extract_cross_section(mesh, z_level=bounds[0][2] + dims[2] * 0.5)

    # Fill ratio
    vol = float(mesh.volume) if mesh.is_watertight else w * l * h * 0.8
    bbox_vol = w * l * h
    fill = min(1.0, vol / bbox_vol) if bbox_vol > 0 else 1.0

    # Mesh verisi: orijine taşı, ardından eksen permütasyonu uygula
    verts_raw = np.array(mesh.vertices, dtype=float)
    verts_raw -= verts_raw.min(axis=0)          # bbox köşesini (0,0,0)'a taşı
    verts = verts_raw[:, _ax]                   # eksen permütasyonu: w=ax[0], l=ax[1], h=ax[2]
    faces = np.array(mesh.faces, dtype=int)

    return ShapeInfo(
        name         = path.stem,
        shape_type   = "custom",
        bbox_width   = w,
        bbox_length  = l,
        bbox_height  = h,
        actual_volume_cm3 = vol,
        surface_area_cm2  = float(mesh.area),
        center_of_mass    = com_rel,
        cross_section     = cross_poly,
        fill_ratio        = fill,
        mesh_vertices     = verts,
        mesh_faces        = faces,
        source_file       = str(path),
    )


def _extract_cross_section(mesh: "trimesh.Trimesh", z_level: float) -> Optional["Polygon"]:
    """Belirli Z yüksekliğinde 2D kesit poligonu döndürür."""
    if not HAS_SHAPELY:
        return None
    try:
        section = mesh.section(plane_origin=[0, 0, z_level],
                               plane_normal=[0, 0, 1])
        if section is None:
            return None
        path2d, _ = section.to_planar()
        polygons = path2d.polygons_full
        if not polygons:
            return None
        if len(polygons) == 1:
            return Polygon(polygons[0].exterior.coords)
        # Birden fazla kontur → en büyüğü al
        return max(polygons, key=lambda p: p.area)
    except Exception as e:
        log.warning(f"Kesit alınamadı: {e}")
        return None


# ============================================================================
# STEP OKUMA
# ============================================================================

def load_step(path: str | Path) -> ShapeInfo:
    """
    STEP dosyasından ShapeInfo oluşturur.
    cadquery ile solid yüklenir, STL'e tessellate edilir.
    Birim: STEP'te genellikle mm → cm'ye dönüştürülür.
    """
    if not HAS_CADQUERY:
        raise ImportError(
            "cadquery yüklü değil: pip install cadquery\n"
            "Alternatif: SolidWorks'ten STL olarak dışa aktarın."
        )
    path = Path(path)

    try:
        result = cq.importers.importStep(str(path))
    except Exception as e:
        raise ValueError(f"STEP dosyası okunamadı: {e}")

    # Bounding box (mm)
    bb = result.val().BoundingBox()
    w_mm = bb.xmax - bb.xmin
    l_mm = bb.ymax - bb.ymin
    h_mm = bb.zmax - bb.zmin

    # cm'ye çevir
    w = w_mm * 0.1
    l = l_mm * 0.1
    h = h_mm * 0.1

    # Hacim (mm³ → cm³)
    try:
        vol_cm3 = result.val().Volume() * 0.001
    except Exception:
        vol_cm3 = w * l * h * 0.85

    # STL'e tessellate → trimesh → mesh verisi
    with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        cq.exporters.export(result, tmp_path)
        mesh_info = load_stl(tmp_path)
        # Boyutları STEP'ten al (daha doğru)
        mesh_info.name           = path.stem
        mesh_info.bbox_width     = w
        mesh_info.bbox_length    = l
        mesh_info.bbox_height    = h
        mesh_info.actual_volume_cm3 = vol_cm3
        mesh_info.fill_ratio     = min(1.0, vol_cm3 / (w * l * h)) if w * l * h > 0 else 1.0
        mesh_info.source_file    = str(path)
        mesh_info.shape_type     = "custom"
        return mesh_info
    except Exception as e:
        log.warning(f"STEP mesh oluşturulamadı: {e}")
        bbox_vol = w * l * h
        return ShapeInfo(
            name              = path.stem,
            shape_type        = "custom",
            bbox_width        = w,
            bbox_length       = l,
            bbox_height       = h,
            actual_volume_cm3 = vol_cm3,
            fill_ratio        = min(1.0, vol_cm3 / bbox_vol) if bbox_vol > 0 else 1.0,
            source_file       = str(path),
        )


# ============================================================================
# PARAMETRİK PROFİL ÜRETECİ
# ============================================================================

def l_profile(
    a: float,          # Uzun kanat yüksekliği (cm)
    b: float,          # Kısa kanat genişliği (cm)
    t1: float,         # Uzun kanat kalınlığı (cm)
    t2: float,         # Kısa kanat kalınlığı (cm)
    length: float,     # Profil boyu (cm) — bu Y eksenidir
) -> ShapeInfo:
    """
    L-profil kesit poligonu ve ShapeInfo üretir.

          b
    ┌────┐
    │    │ t2
    │    └──────────┐
    │               │ t1
    └───────────────┘
              a
    """
    # Kesit poligonu — sol-alt köşe = (0, 0)
    coords = [
        (0, 0), (a, 0), (a, t1),
        (t2, t1), (t2, b), (0, b), (0, 0)
    ]
    poly = Polygon(coords) if HAS_SHAPELY else None
    area = (a * t1) + ((b - t1) * t2)
    bbox_area = a * b
    fill = area / bbox_area if bbox_area > 0 else 1.0

    return ShapeInfo(
        name         = f"L-{a}x{b}x{t1}/{t2}",
        shape_type   = "l_profile",
        bbox_width   = a,
        bbox_length  = length,
        bbox_height  = b,
        actual_volume_cm3 = area * length,
        fill_ratio   = fill,
        cross_section = poly,
        profile_params = dict(a=a, b=b, t1=t1, t2=t2, length=length),
    )


def t_profile(
    w: float,          # Flanş genişliği (cm)
    h: float,          # Toplam yükseklik (cm)
    tf: float,         # Flanş kalınlığı (cm)
    tw: float,         # Gövde kalınlığı (cm)
    length: float,
) -> ShapeInfo:
    """
    T-profil.

         w
    ┌─────────┐  tf
    └──┬───┬──┘
       │   │ tw
       │   │
       └───┘
    """
    half_tw = tw / 2
    half_w  = w  / 2
    coords = [
        (0, 0),
        (w, 0),
        (w, tf),
        (half_w + half_tw, tf),
        (half_w + half_tw, h),
        (half_w - half_tw, h),
        (half_w - half_tw, tf),
        (0, tf),
        (0, 0),
    ]
    poly = Polygon(coords) if HAS_SHAPELY else None
    area = w * tf + tw * (h - tf)
    fill = area / (w * h) if w * h > 0 else 1.0
    return ShapeInfo(
        name         = f"T-{w}x{h}x{tf}/{tw}",
        shape_type   = "t_profile",
        bbox_width   = w,
        bbox_length  = length,
        bbox_height  = h,
        actual_volume_cm3 = area * length,
        fill_ratio   = fill,
        cross_section = poly,
        profile_params = dict(w=w, h=h, tf=tf, tw=tw, length=length),
    )


def i_profile(
    w: float,          # Flanş genişliği (cm)
    h: float,          # Toplam yükseklik (cm)
    tf: float,         # Flanş kalınlığı (cm)
    tw: float,         # Gövde (web) kalınlığı (cm)
    length: float,
) -> ShapeInfo:
    """
    I / H profil (çift simetrik).

         w
    ┌─────────┐  tf  (üst flanş)
    └──┬───┬──┘
       │   │ tw  (gövde)
    ┌──┴───┴──┐
    └─────────┘  tf  (alt flanş)
    """
    half_tw = tw / 2
    half_w  = w  / 2
    inner_h = h - 2 * tf
    coords = [
        (0, 0),
        (w, 0),
        (w, tf),
        (half_w + half_tw, tf),
        (half_w + half_tw, tf + inner_h),
        (w, tf + inner_h),
        (w, h),
        (0, h),
        (0, tf + inner_h),
        (half_w - half_tw, tf + inner_h),
        (half_w - half_tw, tf),
        (0, tf),
        (0, 0),
    ]
    poly = Polygon(coords) if HAS_SHAPELY else None
    area = 2 * (w * tf) + tw * inner_h
    fill = area / (w * h) if w * h > 0 else 1.0
    return ShapeInfo(
        name         = f"I-{w}x{h}x{tf}/{tw}",
        shape_type   = "i_profile",
        bbox_width   = w,
        bbox_length  = length,
        bbox_height  = h,
        actual_volume_cm3 = area * length,
        fill_ratio   = fill,
        cross_section = poly,
        profile_params = dict(w=w, h=h, tf=tf, tw=tw, length=length),
    )


def hollow_cylinder(
    outer_diameter: float,
    inner_diameter: float,
    height: float,
) -> ShapeInfo:
    """İçi boş boru (hollow cylinder / pipe)."""
    if not HAS_SHAPELY:
        raise ImportError("Shapely gerekli: pip install shapely")
    r_out = outer_diameter / 2
    r_in  = inner_diameter  / 2
    outer = Polygon([(r_out * math.cos(a * 2 * math.pi / 64) + r_out,
                      r_out * math.sin(a * 2 * math.pi / 64) + r_out)
                     for a in range(64)])
    inner_coords = [(r_in * math.cos(a * 2 * math.pi / 64) + r_out,
                     r_in * math.sin(a * 2 * math.pi / 64) + r_out)
                    for a in range(64)]
    # İçi boş ring
    poly = outer.difference(Polygon(inner_coords))

    area_ring  = math.pi * (r_out**2 - r_in**2)
    area_bbox  = outer_diameter ** 2
    fill       = area_ring / area_bbox if area_bbox > 0 else 1.0

    return ShapeInfo(
        name         = f"Boru-Ø{outer_diameter}xØ{inner_diameter}",
        shape_type   = "hollow_cylinder",
        bbox_width   = outer_diameter,
        bbox_length  = outer_diameter,
        bbox_height  = height,
        actual_volume_cm3 = area_ring * height,
        fill_ratio   = fill,
        cross_section = poly,
        profile_params = dict(
            outer_diameter=outer_diameter,
            inner_diameter=inner_diameter,
            height=height,
        ),
    )


def polygon_profile(
    coords: List[Tuple[float, float]],
    length: float,
    name: str = "Poligon",
) -> ShapeInfo:
    """
    Serbest poligon kesiti.
    coords: (x, y) listesi — cm cinsinden, saat yönünde veya tersi.
    """
    if not HAS_SHAPELY:
        raise ImportError("Shapely gerekli: pip install shapely")
    poly  = Polygon(coords)
    if not poly.is_valid:
        poly = poly.buffer(0)
    minx, miny, maxx, maxy = poly.bounds
    w = maxx - minx
    h = maxy - miny
    # Orijine taşı
    poly = affinity.translate(poly, -minx, -miny)
    area  = poly.area
    fill  = area / (w * h) if w * h > 0 else 1.0
    return ShapeInfo(
        name         = name,
        shape_type   = "polygon",
        bbox_width   = w,
        bbox_length  = length,
        bbox_height  = h,
        actual_volume_cm3 = area * length,
        fill_ratio   = fill,
        cross_section = poly,
    )


# ============================================================================
# DOSYA YÜKLEYICI (uzantıya göre dispatch)
# ============================================================================

def load_from_file(path: str | Path, unit: str = "mm") -> ShapeInfo:
    """
    Dosya uzantısına göre STL veya STEP yükler.
    unit: "mm", "cm", "m", "inch" — SolidWorks varsayılanı "mm"
    """
    path = Path(path)
    ext  = path.suffix.lower()
    if ext == ".stl":
        return load_stl(path, unit=unit)
    elif ext in (".step", ".stp"):
        return load_step(path)
    else:
        raise ValueError(
            f"Desteklenmeyen format: {ext}\n"
            "Desteklenen: .stl, .step, .stp\n"
            "SolidWorks'ten: Dosya → Dışa Aktar → STL veya STEP"
        )


# ============================================================================
# YARDIMCI
# ============================================================================

def shape_summary(info: ShapeInfo) -> str:
    lines = [
        f"🔷 {info.display_name}: {info.name}",
        f"   Bounding Box : {info.bbox_width:.1f} × {info.bbox_length:.1f} × {info.bbox_height:.1f} cm",
        f"   Gerçek Hacim : {info.actual_volume_cm3:.1f} cm³  "
        f"({info.actual_volume_cm3 / 1000:.3f} L)",
        f"   Doluluk Oranı: %{info.fill_ratio * 100:.1f}",
    ]
    if info.cross_section is not None:
        lines.append(f"   Kesit Alanı  : {info.cross_section.area:.1f} cm²")
    if info.source_file:
        lines.append(f"   Kaynak Dosya : {Path(info.source_file).name}")
    return "\n".join(lines)
