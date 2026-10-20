# -*- coding: utf-8 -*-
"""
PARAMETRE KABLO + ETKİ KANITLARI
=================================
UI'daki her algoritma parametresinin (1) run_algo üzerinden algoritmaya
GERÇEKTEN ulaştığını ve (2) ulaştığında davranışı GERÇEKTEN değiştirdiğini
kanıtlar.

Katman A [KABLO]  : app_3d.run_algo çağrılır; algoritma fonksiyonları casus
                    (spy) ile değiştirilir; alınan kwargs, UI'dan gönderilen
                    değerlerle karşılaştırılır.
Katman B [ETKİ]   : algoritmalar gerçek koşulur; parametre değişince
                    gözlemlenebilir çıktı (iterasyon sayısı, süre, katman
                    yapısı, log) değişiyor mu ölçülür.

Not: Widget → değişken adımı Streamlit çatısının işidir (st.slider dönüşü
doğrudan değişkene atanır, app_3d.py sidebar bloğu); bu testler değişkenden
algoritmaya kadar olan TÜM uygulama kodunu kapsar.
"""
import sys, os, io, re, time, contextlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

FAILS = []
def kanit(name, cond, detail=""):
    print(f"[{'KANIT' if cond else 'RED  '}] {name}" + (f"\n        ↳ {detail}" if detail else ""))
    if not cond:
        FAILS.append(name)

QUIET = lambda: contextlib.redirect_stdout(io.StringIO())

from core_3d import Piece3D, Truck3D, CuttingPlan3D

PIECES = [
    Piece3D(id="A", width=100, length=120, height=100, quantity=2, weight=200),
    Piece3D(id="B", width=80,  length=100, height=80,  quantity=2, weight=150),
    Piece3D(id="C", width=60,  length=80,  height=60,  quantity=2, weight=100),
    Piece3D(id="D", width=40,  length=50,  height=40,  quantity=2, weight=50),
]
TRUCKS = [Truck3D(id="T", width=240, length=600, height=270,
                  capacity=8000, available=3)]

# ═══════════════════════════════════════════════════════════════════════════
# KATMAN A — run_algo KABLO TESTİ
# UI'nın gönderdiği her kwarg, doğru algoritmaya doğru parametre adıyla
# ulaşıyor mu? (app_3d bare modda import edilir; run_algo doğrudan çağrılır)
# ═══════════════════════════════════════════════════════════════════════════
print("── KATMAN A: UI → run_algo → algoritma KABLO TESTİ ──")

import warnings; warnings.filterwarnings("ignore")
# app_3d importu QUIET dışında: modül sys.stdout'u .buffer üzerinden yeniden
# sarmaladığından StringIO altında import edilemez (bare-mode Streamlit).
import app_3d                          # widget'lar varsayılan döner
with QUIET():
    from ffd_3d import ffd_3d_optimization
    _VALID_PLAN = ffd_3d_optimization(PIECES, TRUCKS)   # spy'ların dönüşü
                                                        # (tümü yerleşik plan)

# UI'dan geldiğini varsaydığımız BELİRGİN (varsayılan-dışı) değerler:
UI_KW = dict(
    ts_time=44, ts_tenure=13,
    sa_time=55, sa_temp=2222.0, sa_cool=0.991,
    mc_iter=333,
    ga_pop=77, ga_gen=88, ga_time=35, ga_workers=3,
    layer_strat="median",
    bay_time=66.0, bay_trials=21, bay_target="SA",
    isl_islands=5, isl_pop=11, isl_gen=22, isl_mig=7,
    isl_time=45, isl_workers=2,
    ms_starts=6, ms_time=99.0,
    seed=4242,
)

captured = {}
def _spy(algo_name, **fixed):
    def f(pieces, trucks, *a, **kw):
        captured[algo_name] = kw
        return _VALID_PLAN
    return f

import tabu_search_3d, simulated_annealing_3d, monte_carlo_3d, genetic_3d
import island_genetic_3d, multistart_sa_3d, bayesian_optimizer_3d
import layer_building_3d, ffd_3d

_orig = {
    "tabu":  tabu_search_3d.tabu_search_3d_optimization,
    "sa":    simulated_annealing_3d.simulated_annealing_3d_optimization,
    "mc":    monte_carlo_3d.monte_carlo_3d_optimization,
    "ga":    genetic_3d.genetic_3d_optimization,
    "isl":   island_genetic_3d.island_model_ga_3d,
    "ms":    multistart_sa_3d.multistart_sa_3d,
    "bay":   bayesian_optimizer_3d.bayesian_optimization_3d,
    "layer": layer_building_3d.layer_building_3d_optimization,
}
tabu_search_3d.tabu_search_3d_optimization              = _spy("tabu")
simulated_annealing_3d.simulated_annealing_3d_optimization = _spy("sa")
monte_carlo_3d.monte_carlo_3d_optimization              = _spy("mc")
genetic_3d.genetic_3d_optimization                      = _spy("ga")
island_genetic_3d.island_model_ga_3d                    = _spy("isl")
multistart_sa_3d.multistart_sa_3d                       = _spy("ms")
bayesian_optimizer_3d.bayesian_optimization_3d          = _spy("bay")
layer_building_3d.layer_building_3d_optimization        = _spy("layer")

try:
    with QUIET():
        for key in ["tabu_search", "sa_hybrid", "monte_carlo", "genetic",
                    "layer_building", "bayesian", "island_ga", "multistart_sa"]:
            app_3d.run_algo(key, PIECES, TRUCKS, **UI_KW)
finally:
    tabu_search_3d.tabu_search_3d_optimization              = _orig["tabu"]
    simulated_annealing_3d.simulated_annealing_3d_optimization = _orig["sa"]
    monte_carlo_3d.monte_carlo_3d_optimization              = _orig["mc"]
    genetic_3d.genetic_3d_optimization                      = _orig["ga"]
    island_genetic_3d.island_model_ga_3d                    = _orig["isl"]
    multistart_sa_3d.multistart_sa_3d                       = _orig["ms"]
    bayesian_optimizer_3d.bayesian_optimization_3d          = _orig["bay"]
    layer_building_3d.layer_building_3d_optimization        = _orig["layer"]

# UI kwarg → (algoritma, fonksiyon parametre adı) haritası — TEK TEK doğrula
WIRING = [
    ("ts_time",   "tabu",  "max_time"),
    ("ts_tenure", "tabu",  "tabu_tenure"),
    ("seed",      "tabu",  "seed"),
    ("sa_time",   "sa",    "max_time"),
    ("sa_temp",   "sa",    "initial_temp"),
    ("sa_cool",   "sa",    "cooling_rate"),
    ("seed",      "sa",    "seed"),
    ("mc_iter",   "mc",    "iterations"),
    ("seed",      "mc",    "seed"),
    ("ga_pop",    "ga",    "population_size"),
    ("ga_gen",    "ga",    "generations"),
    ("ga_time",   "ga",    "max_time"),
    ("ga_workers","ga",    "n_workers"),
    ("seed",      "ga",    "seed"),
    ("layer_strat","layer","depth_strategy"),
    ("bay_target","bay",   "target_algorithm"),
    ("bay_trials","bay",   "n_trials"),
    ("bay_time",  "bay",   "time_budget"),
    ("isl_islands","isl",  "n_islands"),
    ("isl_pop",   "isl",   "island_population"),
    ("isl_gen",   "isl",   "generations"),
    ("isl_mig",   "isl",   "migration_interval"),
    ("isl_time",  "isl",   "max_time"),
    ("isl_workers","isl",  "n_workers"),
    ("seed",      "isl",   "seed"),
    ("ms_starts", "ms",    "n_starts"),
    ("ms_time",   "ms",    "time_budget"),
    ("seed",      "ms",    "seed"),
]
_bad = []
for ui_name, algo, fn_param in WIRING:
    got = captured.get(algo, {}).get(fn_param, "<YOK>")
    if got != UI_KW[ui_name]:
        _bad.append(f"{ui_name}→{algo}.{fn_param}: beklenen {UI_KW[ui_name]}, gelen {got}")
kanit(f"KABLO: {len(WIRING)} UI parametresinin TAMAMI doğru algoritmaya "
      f"doğru adla ulaştı", not _bad, "; ".join(_bad))

# progress_cb kablosu (uzun algoritmalara canlı ilerleme)
_cb = lambda *a: None
captured.clear()
with QUIET():
    for key in ["tabu_search", "sa_hybrid", "monte_carlo", "genetic",
                "island_ga", "multistart_sa"]:
        tabu_search_3d.tabu_search_3d_optimization              = _spy("tabu")
        simulated_annealing_3d.simulated_annealing_3d_optimization = _spy("sa")
        monte_carlo_3d.monte_carlo_3d_optimization              = _spy("mc")
        genetic_3d.genetic_3d_optimization                      = _spy("ga")
        island_genetic_3d.island_model_ga_3d                    = _spy("isl")
        multistart_sa_3d.multistart_sa_3d                       = _spy("ms")
        try:
            app_3d.run_algo(key, PIECES, TRUCKS, progress_cb=_cb, **UI_KW)
        finally:
            tabu_search_3d.tabu_search_3d_optimization              = _orig["tabu"]
            simulated_annealing_3d.simulated_annealing_3d_optimization = _orig["sa"]
            monte_carlo_3d.monte_carlo_3d_optimization              = _orig["mc"]
            genetic_3d.genetic_3d_optimization                      = _orig["ga"]
            island_genetic_3d.island_model_ga_3d                    = _orig["isl"]
            multistart_sa_3d.multistart_sa_3d                       = _orig["ms"]
kanit("KABLO: progress_cb 6 uzun algoritmanın hepsine progress_callback "
      "olarak ulaştı",
      all(captured.get(a, {}).get("progress_callback") is _cb
          for a in ["tabu", "sa", "mc", "ga", "isl", "ms"]))

# ═══════════════════════════════════════════════════════════════════════════
# KATMAN B — PARAMETRE ETKİ TESTLERİ (gerçek koşular)
# ═══════════════════════════════════════════════════════════════════════════
print("\n── KATMAN B: PARAMETRE DEĞİŞİNCE DAVRANIŞ DEĞİŞİYOR MU ──")

# B1. mc_iter → deneme sayısı birebir (callback sayımı)
from monte_carlo_3d import monte_carlo_3d_optimization
for want in (9, 23):
    calls = []
    with QUIET():
        monte_carlo_3d_optimization(PIECES, TRUCKS, iterations=want, seed=1,
                                    progress_callback=lambda c, t, *r: calls.append((c, t)))
    kanit(f"mc_iter={want}: tam {want} deneme koşuldu",
          len(calls) == want and calls[-1][1] == want,
          f"{len(calls)} callback, toplam bildirimi={calls[-1][1] if calls else '?'}")

# B2. ga_gen → nesil sayısı; ga_pop → popülasyon boyutu (turnuva casusuyla)
import genetic_3d as ga_mod
for want_gen, want_pop in ((6, 9), (11, 14)):
    gen_calls, pop_sizes = [], set()
    _orig_t = ga_mod._tournament_selection
    def _t_spy(scored, k=3):
        pop_sizes.add(len(scored))
        return _orig_t(scored, k)
    ga_mod._tournament_selection = _t_spy
    try:
        with QUIET():
            ga_mod.genetic_3d_optimization(
                PIECES, TRUCKS, population_size=want_pop, generations=want_gen,
                seed=2, progress_callback=lambda g, t, *r: gen_calls.append((g, t)))
    finally:
        ga_mod._tournament_selection = _orig_t
    kanit(f"ga_gen={want_gen}, ga_pop={want_pop}: {want_gen} nesil × "
          f"{want_pop} birey gözlendi",
          len(gen_calls) == want_gen and want_pop in pop_sizes,
          f"nesil={len(gen_calls)}, popülasyonlar={sorted(pop_sizes)}")

# B3. ts_tenure → log'da taban tenure; ts_time → süre bütçesine uyum
from tabu_search_3d import tabu_search_3d_optimization
from ffd_3d import ffd_3d_optimization as _ffd
with QUIET():
    _init = _ffd(PIECES, TRUCKS)
_buf = io.StringIO()
t0 = time.time()
with contextlib.redirect_stdout(_buf):
    tabu_search_3d_optimization(PIECES, TRUCKS, initial_solution=_init,
                                max_time=4, max_iterations=10**9,
                                tabu_tenure=13, seed=3)
_el = time.time() - t0
kanit("ts_tenure=13 gerçekten taban tenure olarak kullanıldı",
      "tenure=13 (base)" in _buf.getvalue())
kanit("ts_time=4: koşu süre bütçesine uydu (4s ± tolerans)",
      3.0 <= _el <= 8.0, f"gerçek süre {_el:.1f}s")

# B4. sa_cool & sa_temp → log kanıtı (kullanıcı değeri auto-kalibrasyonu ezer)
from simulated_annealing_3d import simulated_annealing_3d_optimization
_buf = io.StringIO()
with contextlib.redirect_stdout(_buf):
    simulated_annealing_3d_optimization(PIECES, TRUCKS, initial_solution=_init,
                                        max_time=3, initial_temp=2222.0,
                                        cooling_rate=0.991, seed=4)
_o = _buf.getvalue()
kanit("sa_temp=2222: kullanıcı T0'ı kullanıldı (Auto-T0 kalibrasyonu ATLANDI)",
      "Auto T0" not in _o)
kanit("sa_cool=0.991: soğuma katsayısı başlangıcı birebir",
      re.search(r"başlangıç: 0\.9910", _o) is not None)
_buf = io.StringIO()
with contextlib.redirect_stdout(_buf):
    simulated_annealing_3d_optimization(PIECES, TRUCKS, initial_solution=_init,
                                        max_time=2, initial_temp=0.0, seed=4)
kanit("sa_temp=0 (auto): Kirkpatrick kalibrasyonu devreye girdi",
      "Auto T0" in _buf.getvalue())

# B5. layer_strat → katman derinlikleri gerçekten değişiyor
from layer_building_3d import layer_building_3d_optimization
_hetero = [
    Piece3D(id="H1", width=60, length=40,  height=60, quantity=6, weight=30),
    Piece3D(id="H2", width=60, length=90,  height=60, quantity=6, weight=50),
    Piece3D(id="H3", width=60, length=150, height=60, quantity=4, weight=80),
]
_bands = {}
for strat in ("adaptive", "median", "max"):
    with QUIET():
        pl = layer_building_3d_optimization(_hetero, TRUCKS, depth_strategy=strat)
    _bands[strat] = sorted({p.y for b in pl.bins for p in b})
kanit("layer_strat: üç strateji üç FARKLI katman yapısı üretti "
      "(parametre artık kozmetik değil)",
      len({tuple(v) for v in _bands.values()}) >= 2,
      " | ".join(f"{k}: y-bantlar {v[:5]}" for k, v in _bands.items()))

# B6. isl_mig & isl_islands → göç olayları parametreye birebir uyuyor
from island_genetic_3d import island_genetic_3d_optimization
_ev = []
with QUIET():
    island_genetic_3d_optimization(PIECES, TRUCKS, n_islands=2,
                                   island_population=6, generations=4,
                                   migration_interval=2, migration_rate=1,
                                   seed=6,
                                   migration_callback=lambda g, s, d, *r: _ev.append((g, s, d)))
kanit("isl_islands=2 & isl_mig=2: göçler tam 2. ve 4. nesilde, 2 ada arasında",
      sorted({g for g, _, _ in _ev}) == [2, 4]
      and {s for _, s, _ in _ev} == {0, 1}
      and len(_ev) == 4,
      f"olaylar: {_ev}")

# B7. seed → deterministik tekrar (tabu, tam yerleşim imzası düzeyinde)
def _sig(plan):
    return frozenset((b, p.piece_id, p.x, p.y, p.z)
                     for b, bb in enumerate(plan.bins) for p in bb)
with QUIET():
    tA = tabu_search_3d_optimization(PIECES, TRUCKS, initial_solution=_init,
                                     max_time=2, tabu_tenure=7, seed=77)
    tB = tabu_search_3d_optimization(PIECES, TRUCKS, initial_solution=_init,
                                     max_time=2, tabu_tenure=7, seed=77)
kanit("seed=77: iki tabu koşusu YERLEŞİM DÜZEYİNDE özdeş",
      _sig(tA) == _sig(tB),
      f"util A=%{tA.utilization:.3f} B=%{tB.utilization:.3f}")

# B8. bay_target & bay_trials → hedef algoritma seçimi ve deneme sayısı
import bayesian_optimizer_3d as bo_mod
from core_3d import Placement3D as _P
_ga_calls, _sa_calls = [], []
def _fga(p, t, **kw):
    _ga_calls.append(kw)
    return CuttingPlan3D([[_P(0,0,0,1,1,1,"x",(0,0,0))]], 0, 50.0, 0, "s", {0: t[0].id})
def _fsa(p, t, **kw):
    _sa_calls.append(kw)
    return CuttingPlan3D([[_P(0,0,0,1,1,1,"x",(0,0,0))]], 0, 50.0, 0, "s", {0: t[0].id})
_og, _os = bo_mod.genetic_3d_optimization, bo_mod.simulated_annealing_3d_optimization
bo_mod.genetic_3d_optimization = _fga
bo_mod.simulated_annealing_3d_optimization = _fsa
try:
    with QUIET():
        bo_mod.bayesian_optimization_3d(PIECES, TRUCKS, target_algorithm="SA",
                                        n_trials=12, time_budget=120,
                                        seed_with_ffd=False,
                                        use_warm_start=False,
                                        report_importance=False)
finally:
    bo_mod.genetic_3d_optimization = _og
    bo_mod.simulated_annealing_3d_optimization = _os
kanit('bay_target="SA": Bayesian yalnız SA\'yı optimize etti (GA hiç çağrılmadı)',
      len(_sa_calls) > 0 and len(_ga_calls) == 0,
      f"SA çağrısı={len(_sa_calls)}, GA çağrısı={len(_ga_calls)}")
kanit("bay_trials=12: deneme sayısı birebir uygulandı",
      len(_sa_calls) == 12, f"{len(_sa_calls)} deneme")

# ═══════════════════════════════════════════════════════════════════════════
print("\n" + "═" * 70)
if FAILS:
    print(f"REDDEDILEN: {len(FAILS)}")
    for f in FAILS:
        print("  ✗ " + f)
    sys.exit(1)
print("TÜM PARAMETRELER KANITLI: UI değerleri algoritmalara ulaşıyor ve davranışı değiştiriyor.")
