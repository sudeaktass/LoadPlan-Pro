# -*- coding: utf-8 -*-
"""
Çözüm Olurluluk Doğrulayıcısı (Independent Feasibility Validator)
==================================================================
Bir yerleştirme planının TÜM fiziksel kısıtları sağladığını BAĞIMSIZ olarak
doğrular. KRİTİK: yerleştirme motorunun (core_3d/extreme_points) fonksiyonları
KULLANILMAZ — geometrik kontroller sıfırdan, bağımsız yazılmıştır. Böylece
motorun KENDİ hatalarını (çakışma, havada parça, aşırı yük) yakalayabilir.

Doğrulanan kısıtlar:
  1. Sınır içi (containment)       — parça araç hacmini taşmıyor
  2. Çakışmasızlık (non-overlap)   — hiçbir parça çifti üst üste binmiyor
  3. Destek (support)              — havadaki (z>0) parça alttan destekli
  4. İstif (stacking)              — kırılgan/istiflenemez parçanın üstü boş
  5. Ağırlık kapasitesi            — araç toplam ağırlığı kapasiteyi aşmıyor
  6. (Yumuşak) Ağırlık merkezi     — yanal CoG sapması rapor edilir

Tezin "Doğrulama ve Geçerleme (V&V)" bölümü için kanıt üretir.
"""

from __future__ import annotations
from typing import List, Dict
from dataclasses import dataclass, field

TOL = 1.0          # cm — temas/sınır toleransı
MIN_SUPPORT = 0.80 # havadaki parça için minimum destekli taban oranı (motorla aynı)
COG_LAT_TOL = 0.25 # yanal CoG sapma uyarı eşiği (araç yarı-genişliğine göre)


# ─────────────────────────────────────────────────────────────────────────────
# BAĞIMSIZ GEOMETRİ (motordan import EDİLMEZ)
# ─────────────────────────────────────────────────────────────────────────────
def _is_cyl(pid, piece_info):
    p = piece_info.get(pid)
    return bool(p and getattr(p, 'shape', 'box') == 'cylinder')


def _xy_overlap_area(a, b) -> float:
    """İki yerleşimin XY düzlemindeki örtüşme alanı (eksen-hizalı kutu)."""
    ox = max(0.0, min(a.x + a.width,  b.x + b.width)  - max(a.x, b.x))
    oy = max(0.0, min(a.y + a.length, b.y + b.length) - max(a.y, b.y))
    return ox * oy


def _overlap_3d(a, b, a_cyl=False, b_cyl=False) -> float:
    """
    İki yerleşimin örtüşme HACMİ (pozitif → çakışma). Silindirler için XY'de
    daire yaklaşımı kullanılır (yanlış-pozitif önlemek için).
    Dönen değer > eşik ise çakışma vardır.
    """
    # Z aralığı örtüşmesi (her şekil için aynı)
    oz = min(a.z + a.height, b.z + b.height) - max(a.z, b.z)
    if oz <= TOL:
        return 0.0
    if a_cyl or b_cyl:
        # Daire(ler) — merkez mesafesi yarıçap toplamından küçükse örtüşür
        ra = a.width / 2.0; rb = b.width / 2.0
        cax, cay = a.x + ra, a.y + ra
        cbx, cby = b.x + rb, b.y + rb
        if a_cyl and b_cyl:
            import math
            d = math.hypot(cax - cbx, cay - cby)
            if d >= ra + rb - TOL:
                return 0.0
            # kaba örtüşme alanı yaklaşımı
            xy = min(math.pi * ra * ra, math.pi * rb * rb) * 0.5
        else:
            # silindir-kutu: daire merkezi kutuya yakın mı (kaba)
            cx, cy, r = (cax, cay, ra) if a_cyl else (cbx, cby, rb)
            box = b if a_cyl else a
            nx = max(box.x, min(cx, box.x + box.width))
            ny = max(box.y, min(cy, box.y + box.length))
            import math
            if math.hypot(cx - nx, cy - ny) >= r - TOL:
                return 0.0
            xy = r * r
        return xy * oz
    # Kutu-kutu: XY örtüşme alanı
    ox = min(a.x + a.width,  b.x + b.width)  - max(a.x, b.x)
    oy = min(a.y + a.length, b.y + b.length) - max(a.y, b.y)
    if ox <= TOL or oy <= TOL:
        return 0.0
    return ox * oy * oz


# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class ValidationReport:
    overlaps:      List[str] = field(default_factory=list)
    out_of_bounds: List[str] = field(default_factory=list)
    floating:      List[str] = field(default_factory=list)   # desteksiz
    stacking:      List[str] = field(default_factory=list)
    overweight:    List[str] = field(default_factory=list)
    cog_warnings:  List[str] = field(default_factory=list)
    n_placements:  int = 0

    @property
    def feasible(self) -> bool:
        # CoG yumuşak kısıt → olurluluğu bozmaz (yalnız uyarı)
        return not (self.overlaps or self.out_of_bounds or
                    self.floating or self.stacking or self.overweight)

    def summary(self) -> str:
        return (f"çakışma={len(self.overlaps)} sınır-dışı={len(self.out_of_bounds)} "
                f"havada={len(self.floating)} istif-ihlali={len(self.stacking)} "
                f"aşırı-yük={len(self.overweight)} cog-uyarı={len(self.cog_warnings)}")


def validate_plan(plan, piece_info: Dict, trucks: List) -> ValidationReport:
    """Bir CuttingPlan3D'yi bağımsız olarak doğrula."""
    rep = ValidationReport()
    truck_by_id = {t.id: t for t in trucks}
    ta = plan.truck_assignments or {}

    for bid, placements in enumerate(plan.bins):
        if not placements:
            continue
        rep.n_placements += len(placements)
        truck = truck_by_id.get(ta.get(bid))
        if truck is None:
            continue

        # ── 1. Sınır içi ─────────────────────────────────────────────────
        for p in placements:
            if (p.x < -TOL or p.y < -TOL or p.z < -TOL or
                    p.x + p.width  > truck.width  + TOL or
                    p.y + p.length > truck.length + TOL or
                    p.z + p.height > truck.height + TOL):
                rep.out_of_bounds.append(
                    f"bin{bid}/{p.piece_id}: ({p.x},{p.y},{p.z})+"
                    f"({p.width},{p.length},{p.height}) araç "
                    f"{truck.width}×{truck.length}×{truck.height} dışında")

        # ── 2. Çakışmasızlık (her çift) ──────────────────────────────────
        for i in range(len(placements)):
            for j in range(i + 1, len(placements)):
                a, b = placements[i], placements[j]
                ov = _overlap_3d(a, b,
                                 _is_cyl(a.piece_id, piece_info),
                                 _is_cyl(b.piece_id, piece_info))
                if ov > TOL ** 3:
                    rep.overlaps.append(
                        f"bin{bid}: {a.piece_id} ↔ {b.piece_id} "
                        f"örtüşme hacmi≈{ov:.0f} cm³")

        # ── 3. Destek (havadaki parça) ───────────────────────────────────
        for p in placements:
            if p.z <= TOL:
                continue   # zeminde
            base = p.width * p.length
            if base <= 0:
                continue
            supported = 0.0
            for q in placements:
                if q is p:
                    continue
                if abs((q.z + q.height) - p.z) <= TOL:   # q'nun üstü p'nin altı
                    supported += _xy_overlap_area(p, q)
            frac = min(1.0, supported / base)
            if frac < MIN_SUPPORT:
                rep.floating.append(
                    f"bin{bid}/{p.piece_id}: z={p.z}, destek %{frac*100:.0f} "
                    f"(< %{MIN_SUPPORT*100:.0f}) — havada/yetersiz destek")

        # ── 4. İstif kuralları (motor semantiğiyle birebir) ──────────────
        #   KURAL 1: is_stackable=False = "Altına yük konmasın" → parça ZEMINE
        #            oturmalı (z≈0). Yükseltilmişse ihlal.
        #   KURAL 2: is_fragile=True   = "Üstüne yük konmasın" → üstünde yük
        #            varsa ihlal.
        for p in placements:
            pc = piece_info.get(p.piece_id)
            if pc is None:
                continue
            # KURAL 1
            if not getattr(pc, 'is_stackable', True) and p.z > TOL:
                rep.stacking.append(
                    f"bin{bid}/{p.piece_id} (altına yük konmaz) z={p.z}>0 "
                    f"— zeminde değil")
            # KURAL 2
            if getattr(pc, 'is_fragile', False):
                for q in placements:
                    if q is p:
                        continue
                    if (abs(q.z - (p.z + p.height)) <= TOL and
                            _xy_overlap_area(p, q) > TOL ** 2):
                        rep.stacking.append(
                            f"bin{bid}/{p.piece_id} (üstüne yük konmaz/kırılgan) "
                            f"üstünde {q.piece_id} var")
                        break

        # ── 5. Ağırlık kapasitesi ────────────────────────────────────────
        total_w = sum(getattr(piece_info.get(p.piece_id), 'weight', 0) or 0
                      for p in placements)
        if total_w > truck.capacity + 1e-6:
            rep.overweight.append(
                f"bin{bid}: {total_w:.0f} kg > kapasite {truck.capacity:.0f} kg")

        # ── 6. (Yumuşak) Yanal ağırlık merkezi ───────────────────────────
        tw = sum(getattr(piece_info.get(p.piece_id), 'weight', 0) or 0 for p in placements)
        if tw > 1e-6:
            cog_x = sum((getattr(piece_info.get(p.piece_id), 'weight', 0) or 0) *
                        (p.x + p.width / 2) for p in placements) / tw
            dev = abs(cog_x - truck.width / 2) / (truck.width / 2 + 1e-9)
            if dev > COG_LAT_TOL:
                rep.cog_warnings.append(
                    f"bin{bid}: yanal CoG sapması %{dev*100:.0f} "
                    f"(> %{COG_LAT_TOL*100:.0f})")

    return rep


# ─────────────────────────────────────────────────────────────────────────────
# Birden çok algoritmanın çıktısını doğrula (test)
# ─────────────────────────────────────────────────────────────────────────────
def _run_validation_suite():
    import sys, io, contextlib
    from core_3d import Piece3D, Truck3D

    @contextlib.contextmanager
    def quiet():
        old = sys.stdout; sys.stdout = io.StringIO()
        try: yield
        finally: sys.stdout = old

    import random
    def inst(n, seed):
        rng = random.Random(seed)
        ps = []
        for i in range(n):
            w = rng.choice([60, 80, 120]); l = rng.choice([80, 120, 200])
            h = rng.choice([60, 100, 150])
            ps.append(Piece3D(id=f'P{i}', shape='box', width=w, length=l, height=h,
                              quantity=1, weight=rng.randint(80, 400),
                              is_fragile=(i % 7 == 0), is_stackable=(i % 5 != 0)))
        return ps

    trucks = [Truck3D('T1', 240, 600, 200, 20000, 5)]
    from ffd_3d import ffd_3d_optimization
    from greedy_3d import greedy_3d_optimization
    from tabu_search_3d import tabu_search_3d_optimization
    from simulated_annealing_3d import simulated_annealing_3d_optimization
    from genetic_3d import genetic_3d_optimization

    algos = [
        ("FFD",            lambda p, t, s: ffd_3d_optimization(p, t)),
        ("Greedy",         lambda p, t, s: greedy_3d_optimization(p, t)),
        ("Tabu Search",    lambda p, t, s: tabu_search_3d_optimization(
                               p, t, initial_solution=s, max_time=2, seed=1)),
        ("Sim. Annealing", lambda p, t, s: simulated_annealing_3d_optimization(
                               p, t, initial_solution=s, max_time=2, seed=1)),
        ("Genetic",        lambda p, t, s: genetic_3d_optimization(
                               p, t, population_size=20, generations=15,
                               initial_solution=s, seed=1)),
    ]

    print("=" * 74)
    print("  ÇÖZÜM OLURLULUK DOĞRULAMASI (bağımsız geometrik kontrol)")
    print("=" * 74)
    all_ok = True
    for iseed in (1, 2):
        pieces = inst(22, iseed)
        piece_info = {p.id: p for p in pieces}
        with quiet():
            seed_plan = ffd_3d_optimization(pieces, trucks)
        print(f"\n▸ Örnek-{iseed} ({len(pieces)} parça)")
        for name, fn in algos:
            with quiet():
                plan = fn(pieces, trucks, seed_plan)
            rep = validate_plan(plan, piece_info, trucks)
            mark = "GEÇERLİ ✓" if rep.feasible else "GEÇERSİZ ✗"
            if not rep.feasible:
                all_ok = False
            print(f"    [{mark}] {name:16s} — {rep.summary()}")
            for kind in (rep.overlaps, rep.out_of_bounds, rep.floating,
                         rep.stacking, rep.overweight):
                for v in kind[:2]:
                    print(f"          • {v}")
    print("\n" + "-" * 74)
    print(f"  SONUÇ: {'TÜM ÇÖZÜMLER OLURLU ✓' if all_ok else 'OLURSUZ ÇÖZÜM VAR ✗'}")
    print("=" * 74)
    return all_ok


if __name__ == "__main__":
    import sys
    ok = _run_validation_suite()
    sys.exit(0 if ok else 1)
