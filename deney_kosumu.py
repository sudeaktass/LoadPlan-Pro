# -*- coding: utf-8 -*-
"""
Deney Koşumu — Karşılaştırmalı Deneysel Analiz Altyapısı
=========================================================
Örnek sınıfları × algoritmalar × N tekrar → ortalama±std + istatistiksel
anlamlılık (Friedman / Wilcoxon) + alt-sınır optimallik açığı (gap).

Tez "Deneysel Sonuçlar" bölümü için tablo/CSV üretir. Barr vd. (1995) ve
Demšar (2006) deneysel raporlama standartlarına dayanır.

Çalıştırma:  python deney_kosumu.py
Ölçeklemek için aşağıdaki SABİTLERİ değiştirin (tez için N_REPS=10+, BUTCE=30+).
"""

import sys, io, time, os, contextlib, csv, statistics, random

# ── YAPILANDIRMA (tez için bunları büyütün) ─────────────────────────────────
N_REPS   = 3       # stokastik algoritmalar için tekrar sayısı (tez: ≥10)
BUTCE    = 1.5     # her metasezgisel koşusu için saniye (tez: 20–30)
SEED0    = 100     # taban seed (tekrar = SEED0 + rep)
OUT_CSV  = "deney_sonuclari.csv"

from core_3d import Piece3D, Truck3D
from bounds_3d import compute_fleet_bounds


# ─────────────────────────────────────────────────────────────────────────────
# Yardımcılar
# ─────────────────────────────────────────────────────────────────────────────
@contextlib.contextmanager
def _quiet():
    old = sys.stdout
    sys.stdout = io.StringIO()
    try:
        yield
    finally:
        sys.stdout = old


def _fleet():
    """Deney filosu — sabit (araç seçimi deney değişkeni değil)."""
    return [Truck3D('Buyuk', 240, 600, 200, 24000, 4),
            Truck3D('Orta',  240, 420, 200, 16000, 3)]


def _make_instance(klass, n, seed):
    """
    Üç örnek SINIFI (Bischoff-Ratcliff tarzı dış geçerlilik için):
      homojen    : benzer boyutlu kalemler
      heterojen  : geniş boyut çeşitliliği
      yogun      : araç hacmine yakın büyük kalemler (sıkı)
    """
    rng = random.Random(seed)
    ps = []
    for i in range(n):
        if klass == "homojen":
            w, l, h = 80, 120, 100
            w += rng.choice([-10, 0, 10]); l += rng.choice([-10, 0, 10])
        elif klass == "heterojen":
            w = rng.choice([40, 60, 80, 120, 160])
            l = rng.choice([60, 80, 120, 200, 300])
            h = rng.choice([50, 70, 100, 150, 200])
        else:  # yogun
            w = rng.choice([120, 160, 200])
            l = rng.choice([200, 250, 300])
            h = rng.choice([150, 180, 200])
        ps.append(Piece3D(id=f'{klass[:3]}-{i}', shape='box',
                          width=w, length=l, height=h, quantity=1,
                          weight=rng.randint(80, 500)))
    return ps


def _trucks_used(plan):
    return sum(1 for b in plan.bins if b)


def _placed(plan):
    return sum(len(b) for b in plan.bins)


# ─────────────────────────────────────────────────────────────────────────────
# Algoritma koşucuları — hepsi (pieces, trucks, ffd_seed, seed) alır
# Bayesian DAHİL DEĞİL: paketleme çözücüsü değil, hiperparametre ayarlayıcıdır
# (kategori uyumsuzluğu) → adil head-to-head kıyasta yer almaz.
# ─────────────────────────────────────────────────────────────────────────────
def _runners():
    from ffd_3d import ffd_3d_optimization
    from greedy_3d import greedy_3d_optimization
    from layer_building_3d import layer_building_3d_optimization
    from tabu_search_3d import tabu_search_3d_optimization
    from simulated_annealing_3d import simulated_annealing_3d_optimization
    from genetic_3d import genetic_3d_optimization
    from monte_carlo_3d import monte_carlo_3d_optimization
    from island_genetic_3d import island_model_ga_3d
    from multistart_sa_3d import multistart_sa_3d

    # (ad, stokastik mi, fonksiyon)
    return [
        ("FFD",            False, lambda p, t, s, sd: ffd_3d_optimization(p, t)),
        ("Greedy",         False, lambda p, t, s, sd: greedy_3d_optimization(p, t)),
        ("Layer Building", False, lambda p, t, s, sd: layer_building_3d_optimization(p, t)),
        ("Tabu Search",    True,  lambda p, t, s, sd: tabu_search_3d_optimization(
                                      p, t, initial_solution=s, max_time=BUTCE, seed=sd)),
        ("Sim. Annealing", True,  lambda p, t, s, sd: simulated_annealing_3d_optimization(
                                      p, t, initial_solution=s, max_time=BUTCE, seed=sd)),
        ("Genetic",        True,  lambda p, t, s, sd: genetic_3d_optimization(
                                      p, t, population_size=40, generations=10_000_000,
                                      initial_solution=s, max_time=BUTCE, seed=sd)),
        ("Monte Carlo",    True,  lambda p, t, s, sd: monte_carlo_3d_optimization(
                                      p, t, iterations=10_000_000, initial_solution=s,
                                      max_time=BUTCE, seed=sd)),
        ("Island GA",      True,  lambda p, t, s, sd: island_model_ga_3d(
                                      p, t, n_islands=3, island_population=15,
                                      generations=10_000_000, initial_solution=s,
                                      max_time=BUTCE, seed=sd)),
        ("Multi-Start SA", True,  lambda p, t, s, sd: multistart_sa_3d(
                                      p, t, n_starts=4, time_budget=BUTCE,
                                      initial_solution=s, seed=sd)),
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Ana deney döngüsü
# ─────────────────────────────────────────────────────────────────────────────
def run_experiment():
    from ffd_3d import ffd_3d_optimization

    instances = []
    for klass, n in [("homojen", 24), ("heterojen", 28), ("yogun", 16)]:
        for k in range(1):                  # sınıf başına örnek sayısı (tez: 3–5)
            instances.append((f"{klass}-{k+1}", _make_instance(klass, n, SEED0 + k)))

    runners = _runners()
    trucks = _fleet()

    # results[algo][instance] = list of (util, waste_m3, time, trucks, placed/total)
    results = {name: {} for name, _, _ in runners}
    inst_bounds = {}

    print(f"Deney: {len(instances)} örnek × {len(runners)} algoritma × "
          f"N={N_REPS} tekrar, bütçe={BUTCE}s/koşu\n")

    for inst_name, pieces in instances:
        total = len(pieces)
        bnd = compute_fleet_bounds(pieces, trucks)
        inst_bounds[inst_name] = bnd
        with _quiet():
            ffd_seed = ffd_3d_optimization(pieces, trucks)
        print(f"▸ {inst_name} ({total} parça) — alt sınır: {bnd.lb_trucks} araç, "
              f"teorik maks doluluk %{bnd.max_util_at_lb:.1f}")

        for name, stochastic, fn in runners:
            reps = N_REPS if stochastic else 1
            rec = []
            for rep in range(reps):
                sd = SEED0 + rep
                t0 = time.time()
                try:
                    with _quiet():
                        plan = fn(pieces, trucks, ffd_seed, sd)
                    el = time.time() - t0
                    rec.append((plan.utilization, plan.total_waste / 1e6, el,
                                _trucks_used(plan), _placed(plan) / total))
                except Exception as e:
                    print(f"    ⚠️ {name}: {e}")
            results[name][inst_name] = rec
            if rec:
                us = [r[0] for r in rec]
                mu = statistics.mean(us)
                sd_ = statistics.pstdev(us) if len(us) > 1 else 0.0
                pr = statistics.mean(r[4] for r in rec) * 100   # yerleşen %
                flag = "" if pr >= 99.9 else f"  ⚠️ yalnız %{pr:.0f} yerleşti!"
                print(f"    {name:16s}: %{mu:5.1f} ± {sd_:4.1f}  "
                      f"(yerleşen %{pr:3.0f}, {rec[0][3]} araç, "
                      f"süre {statistics.mean(r[2] for r in rec):.1f}s){flag}")
        print()

    return results, inst_bounds, instances, runners


# ─────────────────────────────────────────────────────────────────────────────
# Özet tablo + istatistik
# ─────────────────────────────────────────────────────────────────────────────
def summarize(results, inst_bounds, instances, runners):
    inst_names = [n for n, _ in instances]

    # Algoritma başına: tüm örnekler üzerinden ortalama doluluk, fire, süre, gap
    print("=" * 78)
    print("  ÖZET — Algoritma Bazlı (tüm örnekler ortalaması)")
    print("=" * 78)
    print(f"  {'Algoritma':16s} {'Yerleşen%':>10s} {'Doluluk%':>9s} "
          f"{'Fire(m³)':>9s} {'Süre(s)':>8s} {'LB-açığı':>9s}")
    print("  " + "-" * 72)

    algo_inst_util = {}   # {algo: [her örneğin ortalama doluluğu]}
    for name, _, _ in runners:
        all_u, all_w, all_t, all_gap, all_pr = [], [], [], [], []
        per_inst = []
        for inst_name in inst_names:
            rec = results[name].get(inst_name, [])
            if not rec:
                per_inst.append(0.0); continue
            mu = statistics.mean(r[0] for r in rec)
            per_inst.append(mu)
            all_u.append(mu)
            all_w.append(statistics.mean(r[1] for r in rec))
            all_t.append(statistics.mean(r[2] for r in rec))
            all_pr.append(statistics.mean(r[4] for r in rec) * 100)
            all_gap.append(inst_bounds[inst_name].max_util_at_lb - mu)
        algo_inst_util[name] = per_inst
        _pr = statistics.mean(all_pr)
        _flag = "" if _pr >= 99.9 else "  ⚠️"
        print(f"  {name:16s} {_pr:9.0f} {statistics.mean(all_u):9.1f} "
              f"{statistics.mean(all_w):9.2f} {statistics.mean(all_t):8.1f} "
              f"{statistics.mean(all_gap):9.1f}{_flag}")
    print("\n  ⚠️ = bazı örneklerde tüm parçalar yerleşmedi → doluluğu doğrudan "
          "kıyaslanamaz (eksik çözüm). Tez koşumunda rescue/garanti katmanı ile "
          "tamlık sağlanmalı veya bu örnekler 'başarısız' raporlanmalı.")

    # ── İstatistiksel anlamlılık ─────────────────────────────────────────
    print("\n" + "=" * 78)
    print("  İSTATİSTİKSEL ANLAMLILIK")
    print("=" * 78)
    try:
        from scipy import stats
        # Friedman: algoritmalar örnekler üzerinde farklı mı? (parametrik olmayan)
        cols = [algo_inst_util[name] for name, _, _ in runners]
        if len(inst_names) >= 2 and all(len(c) == len(inst_names) for c in cols):
            try:
                fr_stat, fr_p = stats.friedmanchisquare(*cols)
                _verdict = ("anlamlı fark VAR (p<0.05)" if fr_p < 0.05
                            else "anlamlı fark YOK (p≥0.05)")
                print(f"  Friedman testi: χ²={fr_stat:.3f}, p={fr_p:.4f} → {_verdict}")
                print("  (Not: anlamlılık için tez koşumunda örnek sayısını artırın.)")
            except Exception as _fe:
                print(f"  Friedman uygulanamadı: {_fe} (daha çok örnek gerekir)")

        # Wilcoxon: en iyi iki algoritmayı eşleştirilmiş karşılaştır
        means = {name: statistics.mean(algo_inst_util[name]) for name, _, _ in runners}
        order = sorted(means, key=lambda k: -means[k])
        if len(order) >= 2 and len(inst_names) >= 2:
            a, b = order[0], order[1]
            xa, xb = algo_inst_util[a], algo_inst_util[b]
            if any(abs(x - y) > 1e-9 for x, y in zip(xa, xb)):
                try:
                    w_stat, w_p = stats.wilcoxon(xa, xb)
                    print(f"  Wilcoxon ({a} vs {b}): W={w_stat:.2f}, p={w_p:.4f} "
                          f"→ {'anlamlı' if w_p < 0.05 else 'anlamlı değil'}")
                except Exception as _we:
                    print(f"  Wilcoxon uygulanamadı: {_we}")
            else:
                print(f"  Wilcoxon ({a} vs {b}): değerler özdeş — test gereksiz")
    except ImportError:
        print("  scipy kurulu değil — istatistiksel test atlandı (pip install scipy)")

    # ── CSV çıktısı ──────────────────────────────────────────────────────
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), OUT_CSV)
    with open(path, "w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        wr.writerow(["ornek", "algoritma", "tekrar", "doluluk_%", "fire_m3",
                     "sure_s", "arac", "yerlesen_oran"])
        for name, _, _ in runners:
            for inst_name in inst_names:
                for rep, r in enumerate(results[name].get(inst_name, [])):
                    wr.writerow([inst_name, name, rep,
                                 f"{r[0]:.2f}", f"{r[1]:.3f}", f"{r[2]:.2f}",
                                 r[3], f"{r[4]:.2f}"])
    print(f"\n  📄 Ham veri kaydedildi: {OUT_CSV}")
    print("=" * 78)


if __name__ == "__main__":
    res, bnds, insts, runs = run_experiment()
    summarize(res, bnds, insts, runs)
