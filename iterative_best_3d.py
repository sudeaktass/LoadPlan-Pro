# -*- coding: utf-8 -*-
"""
Iterative Best 3D — Anytime Portföy Optimizasyonu (Kanıt-Tabanlı Durma)
=======================================================================
"Kesin en iyi" hedefi için ITERATIF / ANYTIME bir optimizer:

  • Her an en iyi çözümü (incumbent) saklar — istediğin an durdurabilirsin,
    elindeki o ana kadarki EN İYİ sonuçtur.
  • Bir PORTFÖYÜ döner (Multi-Start SA, Tabu, SA, Genetic); her tur incumbent'i
    seed alarak iyileştirmeye çalışır. Farklı operatörler farklı tuzaklardan
    kaçar → tek algoritmadan daha iyi yakınsama (Gomes & Selman 2001 portfolio).
  • Birden çok aday FİLO konfigürasyonunu paralel takip eder; global en iyi
    araç seçimini de bulur.
  • KANIT-TABANLI ERKEN DURMA: çözüm araç sayısı alt sınırına (bounds_3d)
    eşit ve doluluk teorik maksimuma yeterince yakınsa → "KANITLANMIŞ OPTİMUM"
    deyip durur (daha fazla aramak anlamsız, matematiksel olarak iyileştirilemez).
  • Aksi halde iyileşme durana (patience) veya bütçe bitene kadar sürer.

Tüm alt algoritmalar core_3d.packing_objective (ORTAK amaç) ile değerlendirilir
→ turlar/konfigürasyonlar arası karşılaştırma tutarlıdır.
"""

from __future__ import annotations
import time
from typing import List, Dict, Optional, Callable, Tuple

from core_3d import Piece3D, Truck3D, CuttingPlan3D, packing_objective
from bounds_3d import compute_fleet_bounds, optimality_report, FleetBounds

from ffd_3d import ffd_3d_optimization
from tabu_search_3d import tabu_search_3d_optimization
from simulated_annealing_3d import simulated_annealing_3d_optimization
from multistart_sa_3d import multistart_sa_3d
from genetic_3d import genetic_3d_optimization


# ─────────────────────────────────────────────────────────────────────────────
# Çözüm değerlendirme — ortak amaç fonksiyonuyla tutarlı karşılaştırma
# ─────────────────────────────────────────────────────────────────────────────

def _plan_fitness(plan: CuttingPlan3D,
                  trucks: List[Truck3D],
                  piece_info: Dict,
                  total_pieces: int) -> float:
    """Plan'ın ortak amaç fitness'ı (DÜŞÜK = daha iyi). Yerleşmeyen ağır cezalı."""
    if plan is None or not plan.bins:
        return float('inf')
    placed = sum(len(b) for b in plan.bins)
    unplaced = max(0, total_pieces - placed)
    ta = plan.truck_assignments or {}
    fit, _util = packing_objective(
        plan.bins, ta, trucks, piece_info, unplaced=unplaced)
    return fit


def _num_trucks(plan: CuttingPlan3D) -> int:
    return sum(1 for b in plan.bins if b) if (plan and plan.bins) else 0


def _try_consolidate(plan: CuttingPlan3D,
                     pieces: List[Piece3D],
                     trucks: List[Truck3D],
                     max_passes: int = 2) -> CuttingPlan3D:
    """
    Araç birleştirme (Vehicle Elimination): bir aracın içeriğini başka araçlara
    dağıtarak araç sayısını azaltmayı dener. İteratif optimizer her adayı bununla
    sıkılaştırır → fitness gerçek araç sayısını yansıtır, çözüm alt sınıra yaklaşır.
    """
    try:
        from placement_guarantee import consolidate_vehicles
        out = consolidate_vehicles(plan, pieces, trucks, max_passes=max_passes)
        return out if out is not None else plan
    except Exception:
        return plan


class _FleetConfigLite:
    """FleetConfig benzeri hafif sarmalayıcı (tam filo güvenlik konfigürasyonu)."""
    def __init__(self, trucks: List[Truck3D], label: str = "Tam filo"):
        self.trucks = trucks
        self._label = label

    def label(self) -> str:
        return self._label


# ─────────────────────────────────────────────────────────────────────────────
# Portföy — tek bir metaheuristik çağrısı (incumbent'i seed alır)
# ─────────────────────────────────────────────────────────────────────────────

def _run_one(algo: str,
             pieces: List[Piece3D],
             trucks: List[Truck3D],
             seed_plan: Optional[CuttingPlan3D],
             budget: float,
             seed: Optional[int]) -> Optional[CuttingPlan3D]:
    """Portföydeki bir algoritmayı seed_plan'dan başlatıp 'budget' sn çalıştır."""
    try:
        if algo == 'multistart':
            return multistart_sa_3d(
                pieces, trucks, n_starts=4, time_budget=budget,
                initial_solution=seed_plan, seed=seed)
        if algo == 'tabu':
            return tabu_search_3d_optimization(
                pieces, trucks, initial_solution=seed_plan,
                max_time=budget, seed=seed)
        if algo == 'sa':
            return simulated_annealing_3d_optimization(
                pieces, trucks, initial_solution=seed_plan,
                max_time=budget, cooling_rate=0.997, seed=seed)
        if algo == 'genetic':
            return genetic_3d_optimization(
                pieces, trucks, population_size=60, generations=10_000_000,
                initial_solution=seed_plan, max_time=budget, seed=seed)
    except Exception:
        return None
    return None


# ─────────────────────────────────────────────────────────────────────────────
# ANA İTERATİF OPTİMİZER
# ─────────────────────────────────────────────────────────────────────────────

def iterative_best_optimization(
    pieces: List[Piece3D],
    trucks: List[Truck3D],
    time_budget: float = 300.0,
    candidate_configs: Optional[List] = None,   # FleetConfig listesi (varsa filo aramasını atla)
    top_k_configs: int = 3,
    patience: int = 4,                # kaç turdur iyileşme yoksa dur
    util_epsilon: float = 0.05,       # bu kadar puan altı iyileşme "yok sayılır"
    call_budget: float = 0.0,         # tek çağrı süresi (0 = otomatik)
    target_util: float = 0.0,         # bu doluluğa ulaşılırsa erken dur (0 = kapalı)
    seed: Optional[int] = None,
    progress: Optional[Callable] = None,
) -> Tuple[CuttingPlan3D, object, FleetBounds, dict, int]:
    """
    İteratif anytime optimizer.

    Returns:
        (best_plan, best_config, bounds, optimality_report_dict, n_rounds)
    """
    start = time.time()
    piece_info = {p.id: p for p in pieces}
    total_pieces = sum(p.quantity for p in pieces)
    bounds = compute_fleet_bounds(pieces, trucks)

    # ── 1. Aday filo konfigürasyonları ───────────────────────────────────
    configs = []
    if candidate_configs:
        # Tekrarı temizle
        _seen = set()
        for cfg in candidate_configs:
            lbl = cfg.label()
            if lbl not in _seen:
                configs.append(cfg)
                _seen.add(lbl)
            if len(configs) >= top_k_configs:
                break
    else:
        # Filo aramasını kendimiz yap (bütçenin %20'si)
        try:
            from fleet_optimizer_3d import fleet_optimizer_3d
            _fb = max(15.0, time_budget * 0.20)
            _, _bcfg, _allr = fleet_optimizer_3d(
                pieces, trucks, time_budget=_fb, max_configs=300)
            _seen = set()
            for r in sorted(_allr, key=lambda r: -r.score):
                lbl = r.config.label()
                if lbl not in _seen:
                    configs.append(r.config)
                    _seen.add(lbl)
                if len(configs) >= top_k_configs:
                    break
            if not configs and _bcfg:
                configs = [_bcfg]
        except Exception:
            configs = []

    # ── GÜVENLİK: her zaman tam-filo konfigürasyonu ekle ─────────────────
    # Aday konfigler az araçlı olup tüm parçaları sığdıramayabilir. Tam filo
    # daima eklenir → tamlık garanti edilir; ortak amaç fonksiyonu en küçük
    # TAM çözümü zaten tercih eder (araçları kendiliğinden konsolide eder).
    _full = _FleetConfigLite(sorted(trucks, key=lambda t: t.get_volume(), reverse=True))
    _cfg_labels = {c.label() for c in configs}
    if _full.label() not in _cfg_labels:
        configs.append(_full)
    if not configs:
        configs = [_full]

    # ── 2. Her config için FFD başlangıcı + global incumbent ─────────────
    incumbent: Optional[CuttingPlan3D] = None
    incumbent_fit = float('inf')
    incumbent_cfg = None
    incumbent_trucks: List[Truck3D] = []

    for cfg in configs:
        ctrucks = sorted(cfg.trucks, key=lambda t: t.get_volume(), reverse=True)
        try:
            p0 = ffd_3d_optimization(pieces, ctrucks)
            p0 = _try_consolidate(p0, pieces, ctrucks)   # araç sayısını sıkılaştır
            f0 = _plan_fitness(p0, ctrucks, piece_info, total_pieces)
            if f0 < incumbent_fit:
                incumbent, incumbent_fit, incumbent_cfg, incumbent_trucks = (
                    p0, f0, cfg, ctrucks)
        except Exception:
            pass

    if progress:
        progress({"phase": "init", "round": 0, "best": incumbent,
                  "best_util": incumbent.utilization if incumbent else 0,
                  "best_trucks": _num_trucks(incumbent),
                  "bounds": bounds, "elapsed": time.time() - start,
                  "budget": time_budget, "proven": False})

    # ── 3. Anytime portföy döngüsü ───────────────────────────────────────
    portfolio = ['multistart', 'tabu', 'sa', 'genetic']
    round_idx = 0
    stale = 0
    last_util = incumbent.utilization if incumbent else -1.0

    def _converged_proof() -> bool:
        """
        Kanıt-tabanlı durma — TÜM koşullar sağlanmalı:
          1. Tüm parçalar yerleşmiş (eksik yerleşim varken asla 'optimum' deme)
          2. Araç sayısı alt sınıra eşit/altında
          3. Doluluk teorik maksimuma yeterince yakın
        """
        if incumbent is None or not bounds.feasible or bounds.lb_trucks <= 0:
            return False
        placed = sum(len(b) for b in incumbent.bins)
        if placed < total_pieces:          # eksik yerleşim → optimum değil
            return False
        t = _num_trucks(incumbent)
        return (t <= bounds.lb_trucks and
                (bounds.max_util_at_lb - incumbent.utilization) < util_epsilon)

    def _target_reached() -> bool:
        """Hedef doluluğa ulaşıldı + tüm parçalar yerleşti → erken dur."""
        if target_util <= 0 or incumbent is None:
            return False
        placed = sum(len(b) for b in incumbent.bins)
        return (placed >= total_pieces and
                incumbent.utilization >= target_util)

    while time.time() - start < time_budget:
        if _converged_proof() or _target_reached():
            break

        improved = False
        algo = portfolio[round_idx % len(portfolio)]

        for cfg in configs:
            remaining = time_budget - (time.time() - start)
            if remaining <= 2.0:
                break
            ctrucks = sorted(cfg.trucks, key=lambda t: t.get_volume(), reverse=True)

            # Tek çağrı süresi: otomatik → bütçeyi turlara böl ama makul taban
            if call_budget > 0:
                slice_t = min(call_budget, remaining)
            else:
                slice_t = min(remaining, max(8.0, time_budget * 0.06))

            # Bu config için seed: global incumbent (varsa) onu iyileştir
            seed_plan = incumbent
            _sd = (seed + round_idx) if seed is not None else None
            cand = _run_one(algo, pieces, ctrucks, seed_plan, slice_t, _sd)
            if cand is None:
                continue
            cand = _try_consolidate(cand, pieces, ctrucks)   # araç sayısını sıkılaştır
            f = _plan_fitness(cand, ctrucks, piece_info, total_pieces)
            if f < incumbent_fit - 1e-9:
                incumbent, incumbent_fit, incumbent_cfg, incumbent_trucks = (
                    cand, f, cfg, ctrucks)
                improved = True

            if progress:
                progress({"phase": "search", "round": round_idx + 1, "algo": algo,
                          "best": incumbent,
                          "best_util": incumbent.utilization if incumbent else 0,
                          "best_trucks": _num_trucks(incumbent),
                          "bounds": bounds, "elapsed": time.time() - start,
                          "budget": time_budget, "proven": _converged_proof()})

            if time.time() - start >= time_budget:
                break

        # ── Yakınsama kontrolü ───────────────────────────────────────────
        cur_util = incumbent.utilization if incumbent else 0.0
        if (not improved) or abs(cur_util - last_util) < util_epsilon:
            stale += 1
        else:
            stale = 0
        last_util = cur_util
        round_idx += 1

        if stale >= patience:
            break

    # ── 4. Sonuç + optimallik raporu ─────────────────────────────────────
    cur_trucks = _num_trucks(incumbent)
    cur_util = incumbent.utilization if incumbent else 0.0
    report = optimality_report(cur_trucks, cur_util, bounds)
    # Eksik yerleşim varsa 'optimum' iddiası geçersizdir
    _placed_final = sum(len(b) for b in incumbent.bins) if incumbent else 0
    report["incomplete"] = (_placed_final < total_pieces)
    if report["incomplete"]:
        report["proven_optimal_trucks"] = False
    report["rounds"] = round_idx
    report["converged_proof"] = _converged_proof()
    return incumbent, incumbent_cfg, bounds, report, round_idx
