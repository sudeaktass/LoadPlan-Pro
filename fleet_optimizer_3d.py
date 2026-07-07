# -*- coding: utf-8 -*-
"""
🚛 Akıllı Araç Seçimi
=======================
Kullanıcının filo tablosundaki araçları kullanarak en iyi kombinasyonu bulur.

TEMEL KURAL:
  - Araç ölçüleri (genişlik/uzunluk/yükseklik) KESİNLİKLE değiştirilemez
  - Her araç tipinden en fazla "Adet" kadar kullanılabilir
  - Sadece hangi tipleri, kaç adet kullanmak en iyi → bunu optimize eder

ARAMA STRATEJİSİ (3 aşamalı huni):
  Aşama A: Tüm geçerli kombinasyonlar → FFD ile hızlı elek → Top 10
  Aşama B: Top 10 → FFD+Greedy+Layer+MC → güvenilir sıralama → Top 5
  Aşama C: Top 5 → kısa SA (12s) → gerçekçi skor → Top 3
  Phase 2 (Tam Optimizasyon'da): Top 3 → uzun SA/GA

SKOR KURALLARI:
  1. Tüm parçalar yerleşmeli (zorunlu kısıt — eksik varsa skor ≈ 0)
  2. Az araç kullanılmalı
  3. Yüksek doluluk oranı
  4. %40 altı doluluk cezalandırılır
"""

import itertools
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional, Callable

from core_3d import Piece3D, Truck3D, CuttingPlan3D
from ffd_3d import ffd_3d_optimization


# ─────────────────────────────────────────────────────────────────────────────
# VERİ YAPILARI
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class FleetConfig:
    counts: Dict[str, int]   # {truck_id: kullanılan_adet}
    trucks: List[Truck3D]    # Gerçek Truck3D nesneleri — ölçüler DEĞİŞMEZ

    def total_trucks(self) -> int:
        return sum(self.counts.values())

    def total_volume(self) -> int:
        return sum(t.get_volume() for t in self.trucks)

    def total_capacity(self) -> float:
        return sum(t.capacity for t in self.trucks)

    def label(self) -> str:
        parts = [f"{v}×{k}" for k, v in self.counts.items() if v > 0]
        return " + ".join(parts) if parts else "Boş"


@dataclass
class FleetResult:
    config:      FleetConfig
    plan:        CuttingPlan3D
    score:       float
    placed:      int
    total:       int
    utilization: float
    num_trucks:  int

    def __str__(self):
        status = "✅" if self.placed == self.total else f"⚠️ {self.placed}/{self.total}"
        return (f"{status} [{self.config.label()}]  "
                f"Doluluk: %{self.utilization:.1f}  "
                f"Araç: {self.num_trucks}  Skor: {self.score:.4f}")


# ─────────────────────────────────────────────────────────────────────────────
# KOMBİNASYON ÜRETİCİ
# ─────────────────────────────────────────────────────────────────────────────

def _generate_configs(
    trucks: List[Truck3D],
    pieces: List[Piece3D],
    max_configs: int = 300,
) -> List[FleetConfig]:
    """
    Kullanıcı tablosundaki araçlardan geçerli tüm kombinasyonları üretir.
    Araç ölçülerine dokunulmaz — sadece hangi tipten kaç adet kullanılacağı değişir.
    """
    # Her araç tipini bir kez al (ölçüler bu nesneden gelir — DEĞİŞMEZ)
    unique: Dict[str, Truck3D] = {}
    for t in trucks:
        if t.id not in unique:
            unique[t.id] = t

    total_piece_vol    = sum(p.width * p.length * p.height * p.quantity for p in pieces)
    total_piece_weight = sum(p.weight * p.quantity for p in pieces)

    truck_ids    = list(unique.keys())
    truck_ranges = [range(0, unique[tid].available + 1) for tid in truck_ids]

    # Her parça en az bir araca sığabiliyor mu? (boyut uyumluluk ön kontrolü)
    def _piece_fits_truck(piece: Piece3D, truck: Truck3D) -> bool:
        """Parça bu aracın boyutlarına sığar mı? (rotasyon dahil)"""
        dims = sorted([piece.width, piece.length, piece.height])
        tdims = sorted([truck.width, truck.length, truck.height])
        # En küçük boyut en küçük boyuta, vs. sığmalı
        return all(dims[i] <= tdims[i] for i in range(3))

    # Her parça için hangi araç tipleri uygun?
    piece_compatible: Dict[str, List[str]] = {}
    for p in pieces:
        compat = [tid for tid in truck_ids if _piece_fits_truck(p, unique[tid])]
        piece_compatible[p.id] = compat

    configs = []
    for combo in itertools.product(*truck_ranges):
        if sum(combo) == 0:
            continue

        # Toplam hacim yeterli mi?
        total_vol = sum(unique[truck_ids[i]].get_volume() * combo[i]
                        for i in range(len(truck_ids)))
        if total_vol < total_piece_vol * 0.45:
            continue

        # Toplam kapasite yeterli mi?
        total_cap = sum(unique[truck_ids[i]].capacity * combo[i]
                        for i in range(len(truck_ids)))
        if total_cap < total_piece_weight * 0.75:
            continue

        # BOYUT UYUMLULUK: Her parça bu konfigürasyondaki en az bir araç tipine sığmalı
        # Sığmayan parça varsa bu config ASLA tam çözüm veremez → atla
        active_tids = {truck_ids[i] for i in range(len(truck_ids)) if combo[i] > 0}
        skip = False
        for p in pieces:
            if not any(tid in active_tids for tid in piece_compatible[p.id]):
                skip = True
                break
        if skip:
            continue

        counts = {truck_ids[i]: combo[i] for i in range(len(truck_ids))}

        import copy as _copy
        truck_list = []
        for tid, cnt in counts.items():
            for k in range(cnt):
                t = _copy.copy(unique[tid])
                t.available = 1
                t.id = tid if cnt == 1 else f"{tid}#{k+1}"
                truck_list.append(t)
        truck_list.sort(key=lambda t: t.get_volume(), reverse=True)

        configs.append(FleetConfig(counts=counts, trucks=truck_list))
        if len(configs) >= max_configs:
            break

    # Önce az araçlı, eşit araç sayısında büyük hacimli
    configs.sort(key=lambda c: (c.total_trucks(), -c.total_volume()))
    return configs


# ─────────────────────────────────────────────────────────────────────────────
# SKOR FONKSİYONU
# ─────────────────────────────────────────────────────────────────────────────

def _score(plan: CuttingPlan3D, pieces: List[Piece3D], config: FleetConfig) -> float:
    """
    Yüksek = daha iyi.

    Öncelik:
      1. Tüm parçalar sığmış olmalı (zorunlu — eksik varsa skor ≈ 0)
      2. Az araç
      3. Yüksek doluluk (%40 altı cezalı)
    """
    from core_3d import cog_penalty_score

    total  = sum(p.quantity for p in pieces)
    placed = sum(len(b) for b in plan.bins)
    piece_info = {p.id: p for p in pieces}

    # Eksik parça → büyük negatif ceza (her eksik ürün -1000 puan)
    # Bu kural KESİN: eksik çözüm hiçbir zaman tam çözümü yenemez
    if placed < total:
        return -1000.0 * (total - placed)

    util = plan.utilization / 100.0

    # %40 altı doluluk karesel ceza
    if util < 0.40:
        util = util * (util / 0.40)

    n_trucks  = max(1, config.total_trucks())
    truck_pen = n_trucks ** 2.0   # Daha agresif ceza → daha az araç tercih edilir

    # CoG bonusu
    cog_total = 0.0
    trucks_by_id = {t.id: t for t in config.trucks}
    for bid, bpl in enumerate(plan.bins):
        if not bpl:
            continue
        tid   = plan.truck_assignments.get(bid) if plan.truck_assignments else None
        truck = trucks_by_id.get(tid) if tid else (config.trucks[0] if config.trucks else None)
        if truck:
            cog_total += cog_penalty_score(bpl, piece_info, truck)
    active = sum(1 for b in plan.bins if b)
    cog_factor = max(0.1, 1.0 - 0.4 * cog_total / max(1, active))

    return util * cog_factor / truck_pen


# ─────────────────────────────────────────────────────────────────────────────
# HUNİ STRATEJİSİ — YARDIMCILAR
# ─────────────────────────────────────────────────────────────────────────────

def _run_plan(pieces, truck_list, algo="ffd"):
    """
    Verilen araç listesi üzerinde algoritmayı çalıştır.
    Sonuçta yerleştirilemeyen yük varsa kurtarma zinciri tetiklenir.
    """
    if algo == "greedy":
        from greedy_3d import greedy_3d_optimization
        plan = greedy_3d_optimization(pieces, truck_list)
    elif algo == "layer":
        from layer_building_3d import layer_building_3d_optimization
        plan = layer_building_3d_optimization(pieces, truck_list)
    elif algo == "mc":
        from monte_carlo_3d import monte_carlo_3d_optimization
        plan = monte_carlo_3d_optimization(pieces, truck_list, iterations=100)
    elif algo == "sa":
        from simulated_annealing_3d import simulated_annealing_3d_optimization
        plan = simulated_annealing_3d_optimization(
            pieces, truck_list, max_time=12.0,
            initial_temp=None, cooling_rate=0.995)
    else:
        plan = ffd_3d_optimization(pieces, truck_list)

    # Yerleştirme garantisi — hiçbir ürün eksik kalmamalı
    try:
        from fallback_strategy import get_unplaced_pieces, rescue_placement
        from placement_guarantee import guarantee_all_placed, force_place_remaining
        _u = get_unplaced_pieces(pieces, plan)
        if _u:
            try:
                plan = rescue_placement(pieces, plan, truck_list)
                _u = get_unplaced_pieces(pieces, plan)
            except Exception:
                pass
            if _u:
                plan, _, _ = guarantee_all_placed(pieces, plan, truck_list)
                _u = get_unplaced_pieces(pieces, plan)
            if _u:
                plan = force_place_remaining(pieces, plan, truck_list)
    except Exception:
        pass
    return plan


def _best_plan(plans):
    valid = [p for p in plans if p is not None]
    if not valid:
        return None
    return max(valid, key=lambda p: (
        sum(len(b) for b in p.bins),
        p.utilization,
    ))


def _eval(cfg: FleetConfig, pieces: List[Piece3D], algos=("ffd",)) -> FleetResult:
    """Bir konfigürasyonu verilen algoritmalarla değerlendir."""
    total = sum(p.quantity for p in pieces)
    plans = []
    for algo in algos:
        try:
            plans.append(_run_plan(pieces, cfg.trucks, algo))
        except Exception:
            pass
    plan = _best_plan(plans)
    if plan is None:
        dummy = CuttingPlan3D([], 0, 0, 0, "failed", {})
        return FleetResult(cfg, dummy, 0, 0, total, 0, 0)
    placed = sum(len(b) for b in plan.bins)
    return FleetResult(
        config=cfg, plan=plan,
        score=_score(plan, pieces, cfg),
        placed=placed, total=total,
        utilization=plan.utilization,
        num_trucks=sum(1 for b in plan.bins if b),
    )


# ─────────────────────────────────────────────────────────────────────────────
# ANA FONKSİYON
# ─────────────────────────────────────────────────────────────────────────────

def fleet_optimizer_3d(
    pieces:            List[Piece3D],
    trucks:            List[Truck3D],
    time_budget:       float = 120.0,
    max_configs:       int   = 300,
    packing_algo:      str   = "auto",   # kullanılmıyor — huni kendi seçiyor
    use_bayesian:      bool  = True,     # kullanılmıyor — huni yeterli
    progress_callback: Optional[Callable] = None,
) -> Tuple[CuttingPlan3D, FleetConfig, List[FleetResult]]:
    """
    Araç seçimi optimizasyonu.
    Araç ölçüleri değiştirilmez — sadece hangi tipten kaç adet kullanılacağı seçilir.
    """
    start = time.time()
    total_pieces = sum(p.quantity for p in pieces)

    print(f"\n🚛 Araç Seçimi Başlıyor")
    print(f"   Parça: {total_pieces} | Araç tipi: {len(set(t.id for t in trucks))}")
    print(f"   Araçlar: {[(t.id, f'{t.width}×{t.length}×{t.height}cm', f'×{t.available}') for t in trucks]}")

    configs = _generate_configs(trucks, pieces, max_configs)
    print(f"   Geçerli kombinasyon: {len(configs)}")

    if not configs:
        plan = ffd_3d_optimization(pieces, trucks)
        cfg  = FleetConfig(
            counts={t.id: t.available for t in trucks},
            trucks=sorted(trucks, key=lambda t: t.get_volume(), reverse=True),
        )
        return plan, cfg, []

    # Araç sayısına göre grupla — az araçtan başla
    by_count: dict = defaultdict(list)
    for cfg in configs:
        by_count[cfg.total_trucks()].append(cfg)
    for cnt in by_count:
        by_count[cnt].sort(key=lambda c: -c.total_volume())

    print(f"   Gruplar: {dict((k, len(v)) for k, v in sorted(by_count.items()))}")

    all_results: List[FleetResult] = []
    best: Optional[FleetResult] = None

    for truck_count in sorted(by_count.keys()):
        group = by_count[truck_count]
        budget_left = time_budget - (time.time() - start)
        if budget_left <= 5:
            break

        print(f"\n   ── {truck_count} araçlı {len(group)} konfigürasyon ──")

        # FIX-Y2: Phase A — FFD + Greedy minimum skoru.
        # Tek algoritmayla elek yanıltıcı: FFD bazı parça setlerinde
        # optimumdan %20-30 saparak iyi config'leri hatalı eler.
        # Çözüm: her config için FFD ve Greedy çalıştırılır, daha yüksek
        # doluluk veren sonuç Phase A skoru olarak kullanılır.
        # Ek maliyet: Phase A süresinin ~2× olması — time_budget * 0.45
        # ile sınırlandırılıyor (Phase B/C'ye yeterli pay kalır).
        stage_a = []
        for cfg in group:
            if time.time() - start >= time_budget * 0.45:
                break
            r_ffd    = _eval(cfg, pieces, algos=("ffd",))
            r_greedy = _eval(cfg, pieces, algos=("greedy",))
            # Daha yüksek skoru al (conservative elek: ikisi de kötüyse elensin)
            r = r_ffd if r_ffd.score >= r_greedy.score else r_greedy
            stage_a.append(r)
            all_results.append(r)
            if best is None or r.score > best.score:
                best = r
        stage_a.sort(key=lambda r: -r.score)
        top10 = [r.config for r in stage_a[:10]]

        if progress_callback:
            done = sum(len(by_count[c]) for c in by_count if c < truck_count) + len(stage_a)
            progress_callback(done, len(configs), best.score if best else 0)

        if time.time() - start >= time_budget * 0.6:
            break

        # Aşama B: Top 10 → 4 algoritma
        stage_b = []
        for cfg in top10:
            if time.time() - start >= time_budget * 0.75:
                break
            r = _eval(cfg, pieces, algos=("ffd", "greedy", "layer", "mc"))
            stage_b.append(r)
            all_results.append(r)
            if best is None or r.score > best.score:
                best = r
                print(f"   ⭐ Aşama B: {r}")
        stage_b.sort(key=lambda r: -r.score)
        top5 = [r.config for r in stage_b[:5]]

        if time.time() - start >= time_budget * 0.85:
            break

        # Aşama C: Top 5 → kısa SA
        for cfg in top5:
            if time.time() - start >= time_budget * 0.95:
                break
            r = _eval(cfg, pieces, algos=("ffd", "sa"))
            all_results.append(r)
            if best is None or r.score > best.score:
                best = r
                print(f"   ⭐ Aşama C: {r}")

        if progress_callback:
            done = sum(len(by_count[c]) for c in by_count if c <= truck_count)
            progress_callback(min(done, len(configs)), len(configs), best.score if best else 0)

        # Tüm parçalar sığdıysa daha fazla araç deneme
        if best and best.placed == best.total:
            print(f"   ✅ {truck_count} araçla tüm parçalar sığıyor — daha fazla araç gereksiz")
            break

        if time.time() - start >= time_budget:
            break

    # Tam çözüm yoksa → tüm araçlarla son çare SA
    full_fits = [r for r in all_results if r.placed == r.total]
    if not full_fits:
        print(f"\n   ⚠️ Tam çözüm bulunamadı — maksimum araçla son çare SA deneniyor…")
        import copy as _copy
        _all = []
        for t in trucks:
            for k in range(t.available):
                _tc = _copy.copy(t)
                _tc.available = 1
                _tc.id = t.id if t.available == 1 else f"{t.id}#{k+1}"
                _all.append(_tc)
        _all.sort(key=lambda t: t.get_volume(), reverse=True)
        _max_cfg = FleetConfig(
            counts={t.id: t.available for t in trucks},
            trucks=_all,
        )
        try:
            from simulated_annealing_3d import simulated_annealing_3d_optimization
            _seed  = ffd_3d_optimization(pieces, _all)
            _final = simulated_annealing_3d_optimization(
                pieces, _all,
                initial_solution=_seed,
                max_time=min(30.0, time_budget * 0.3),
                cooling_rate=0.997,
            )
            _r = FleetResult(
                config=_max_cfg, plan=_final,
                score=_score(_final, pieces, _max_cfg),
                placed=sum(len(b) for b in _final.bins), total=total_pieces,
                utilization=_final.utilization,
                num_trucks=sum(1 for b in _final.bins if b),
            )
            all_results.append(_r)
            if best is None or _r.score > best.score:
                best = _r
            if _r.placed == total_pieces:
                print(f"   ✅ Maksimum araçla tam çözüm bulundu: %{_final.utilization:.1f}")
            else:
                print(f"   ⚠️ {total_pieces - _r.placed} parça hâlâ sığmadı")
        except Exception as e:
            print(f"   ⚠️ Son çare SA hatası: {e}")

    if best is None:
        plan = ffd_3d_optimization(pieces, trucks)
        cfg  = FleetConfig(
            counts={t.id: t.available for t in trucks},
            trucks=sorted(trucks, key=lambda t: t.get_volume(), reverse=True),
        )
        return plan, cfg, []

    all_results.sort(key=lambda r: -r.score)
    elapsed = time.time() - start

    print(f"\n📊 Sonuç ({elapsed:.1f}s)")
    print(f"   🏆 {best}")
    print(f"   Deneme: {len(all_results)}")
    if not full_fits:
        print(f"   ⚠️ Hiçbir kombinasyonla tüm parçalar sığmadı — filo büyütün!")

    return best.plan, best.config, all_results
