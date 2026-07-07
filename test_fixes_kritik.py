# -*- coding: utf-8 -*-
"""
test_fixes_kritik.py — Kritik Düzeltme Doğrulama (Tur 4)
==========================================================
K1: HybridPipeline.greedy_sa() — initial_temp sabit kaldırıldı
K2: app_3d sa_hybrid — sa_temp varsayılanı None
K3: app_3d greedy_sa pipeline — initial_temp: 1200.0 kaldırıldı
K4: app_3d pipeline döngüsü — prev_plan → best_plan_pipe

Çalıştırma:
    python test_fixes_kritik.py
"""

import sys, os, re, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from core_3d import Piece3D, Truck3D
    from iterative_optimizer_3d import (
        HybridPipeline, _run_algorithm, PARAM_SPACES)
    from ffd_3d import ffd_3d_optimization
    print("✅ Modüller import edildi\n")
except ImportError as e:
    print(f"❌ Import hatası: {e}")
    sys.exit(1)

results = []

def check(name, cond, detail=""):
    status = "✅ GEÇTI" if cond else "❌ BAŞARISIZ"
    print(f"  {status} — {name}")
    if detail: print(f"           {detail}")
    results.append((name, cond))
    return cond

def section(t):
    print(f"\n{'═'*60}\n  {t}\n{'═'*60}")

trucks = [Truck3D("T1", 240, 600, 260, 8000, 2),
          Truck3D("T2", 220, 400, 240, 4000, 2)]
pieces = [Piece3D("A", 120, 80, 100, 3, 100.0),
          Piece3D("B",  80, 60,  80, 3,  50.0),
          Piece3D("C",  60, 40,  60, 3,  20.0)]
total = sum(p.quantity for p in pieces)

# ═══════════════════════════════════════════════════════════
# K1: HybridPipeline.greedy_sa() factory
# ═══════════════════════════════════════════════════════════
section("K1: HybridPipeline.greedy_sa() — auto-T0 devreye giriyor mu?")
print("""
  Eski: {"max_time": sa_time, "cooling_rate": cooling, "initial_temp": 1000.0}
  Yeni: {"max_time": sa_time, "cooling_rate": cooling}
        → _run_algorithm params.get("initial_temp", None) = None → auto-kalibrasyon
""")

pipeline = HybridPipeline.greedy_sa(pieces, trucks, sa_time=3.0)
sa_stage  = pipeline.stages[1]

check("SA stage params'ında 'initial_temp' anahtarı yok",
      "initial_temp" not in sa_stage.params,
      f"Mevcut params: {sa_stage.params}")

check("PARAM_SPACES SA'da 'initial_temp' anahtarı yok",
      "initial_temp" not in PARAM_SPACES.get("SimulatedAnnealing", {}))

t0 = time.time()
plan_k1 = pipeline.run()
dt_k1 = time.time() - t0
placed_k1 = sum(len(b) for b in plan_k1.bins)

check(f"greedy_sa pipeline tüm parçaları yerleştiriyor ({placed_k1}/{total})",
      placed_k1 == total)
check("Pipeline 10 saniyede tamamlandı", dt_k1 < 10.0, f"{dt_k1:.1f}s")

# ═══════════════════════════════════════════════════════════
# K2: _run_algorithm SA default None
# ═══════════════════════════════════════════════════════════
section("K2: _run_algorithm SA — initial_temp default None")
print("""
  Eski: initial_temp=params.get("initial_temp", 1000.0)
  Yeni: initial_temp=params.get("initial_temp", None)  → auto-kalibrasyon
""")

import inspect
src_run = inspect.getsource(_run_algorithm)
check('_run_algorithm SA: params.get("initial_temp", None) kullanıyor',
      'params.get("initial_temp", None)' in src_run)

# Params'ta initial_temp olmadan çalıştır — kalibrasyon tetiklenmeli
t0 = time.time()
plan_k2, elapsed_k2 = _run_algorithm(
    "SimulatedAnnealing",
    {"max_time": 3.0, "cooling_rate": 0.995},  # initial_temp YOK
    pieces, trucks)
placed_k2 = sum(len(b) for b in plan_k2.bins)

check(f"SA auto-T0: {placed_k2}/{total} yerleşiyor", placed_k2 == total)
check("SA 5 saniyede tamamlandı", elapsed_k2 < 5.0, f"{elapsed_k2:.1f}s")

# ═══════════════════════════════════════════════════════════
# K3 + K4: 3app_3d.py kaynak doğrulaması
# ═══════════════════════════════════════════════════════════
section("K3 + K4: 3app_3d.py kaynak kontrolü")
print("""
  K3: greedy_sa pipeline SA aşaması initial_temp: 1200.0 kaldırıldı
  K4: Pipeline döngüsü prev_plan → best_plan_pipe
""")

app_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "3app_3d.py")
if not os.path.exists(app_file):
    print("  ⚠️  3app_3d.py bulunamadı — K3/K4 atlanıyor")
else:
    with open(app_file) as f:
        app_src = f.read()

    # K3: greedy_sa pipeline'da sabit sayısal initial_temp yok mu?
    bad_k3 = [l.strip() for l in app_src.splitlines()
              if '"initial_temp"' in l
              and re.search(r':\s*\d', l)
              and not l.lstrip().startswith('#')
              and 'FIX' not in l]
    check("K3: greedy_sa pipeline'da sabit initial_temp yok",
          len(bad_k3) == 0,
          f"Kalan: {bad_k3}" if bad_k3 else "Temiz")

    # K3: sa_hybrid None varsayılanı
    check("K3: sa_hybrid kw.get('sa_temp', None) kullanıyor",
          'kw.get("sa_temp", None)' in app_src)

    # K4: best_plan_pipe değişkeni eklendi mi?
    check("K4: best_plan_pipe değişkeni mevcut", "best_plan_pipe" in app_src)
    check("K4: best_util_pipe değişkeni mevcut", "best_util_pipe" in app_src)

    # K4: prev_plan = plan kalıbı yok mu?
    remaining_prev = [l.strip() for l in app_src.splitlines()
                      if l.strip() == "prev_plan = plan"]
    check("K4: 'prev_plan = plan' atama kalıbı kaldırıldı",
          len(remaining_prev) == 0,
          f"Kalan: {remaining_prev}" if remaining_prev else "Temiz")

# ═══════════════════════════════════════════════════════════
# Genel: Aktif dosyalarda sabit initial_temp kalmadı mı?
# ═══════════════════════════════════════════════════════════
section("Genel: Aktif dosyalar taraması")

ACTIVE = [
    '3app_3d.py', 'iterative_optimizer_3d.py', 'fleet_optimizer_3d.py',
    'simulated_annealing_3d.py', 'genetic_3d.py', 'comparison_3d.py',
    'core_3d.py', 'extreme_points_3d.py', 'ffd_3d.py', 'greedy_3d.py',
    'tabu_search_3d.py', 'bayesian_optimizer_3d.py',
]
pattern_bad = re.compile(r'"initial_temp"\s*:\s*\d+\.?\d*')
bad_active = {}
for fpath in ACTIVE:
    full = os.path.join(os.path.dirname(os.path.abspath(__file__)), fpath)
    if not os.path.exists(full):
        continue
    with open(full) as fh:
        lines = fh.readlines()
    hits = [f"satır {i+1}: {l.rstrip()}"
            for i, l in enumerate(lines)
            if pattern_bad.search(l) and not l.lstrip().startswith('#')]
    if hits:
        bad_active[fpath] = hits

check("Aktif dosyalarda sabit initial_temp kalmadı",
      len(bad_active) == 0,
      str(bad_active) if bad_active else "Tüm aktif dosyalar temiz")

# ═══════════════════════════════════════════════════════════
# SONUÇ
# ═══════════════════════════════════════════════════════════
section("SONUÇ ÖZETİ")
passed = sum(1 for _, ok in results if ok)
failed = sum(1 for _, ok in results if not ok)

print(f"\n  Toplam : {len(results)}")
print(f"  ✅ Geçti: {passed}")
print(f"  ❌ Hata : {failed}")

if failed == 0:
    print("""
  ════════════════════════════════════════════
  4 kritik düzeltme tamamen doğrulandı.
  Sistem genelinde sabit initial_temp kalmadı.
  ════════════════════════════════════════════""")
else:
    for name, ok in results:
        if not ok:
            print(f"  ✗ {name}")
