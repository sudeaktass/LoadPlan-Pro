# -*- coding: utf-8 -*-
"""
ALGORİTMA DENETİMİ — "Hangi algoritmalar gerçekten farklı iş yapıyor?"
=======================================================================
Amaç: Portföydeki yöntemlerden hangilerinin gerçekten kendi adının hakkını
verdiğini, hangilerinin başka bir yöntemin kopyası ya da etkisiz olduğunu
KANITA dayalı biçimde tespit etmek.

Yapılan üç test
---------------
1) ÇIKTI PARMAK İZİ
   Her çözümün (parça, araç, x, y, z) üçlülerinden bir SHA-256 özeti alınır.
   İki yöntem aynı parmak izini üretiyorsa, ürettikleri çözüm birebir aynıdır
   — isimleri farklı olsa da davranışları aynıdır.

2) TOHUMLU / TOHUMSUZ
   Her metasezgisel iki kez koşulur:
     (a) initial_solution = FFD çözümü   → "FFD + yöntem"
     (b) initial_solution = None         → yöntemin tek başına gücü
   Aradaki fark, yöntemin gerçekten arama yapıp yapmadığını gösterir.
   Ayrıca tohumla aynı sonucu döndüren yöntem, hiçbir iyileştirme yapmamıştır.

3) TOHUMA GÖRE KAYIP
   Sonuç, başlangıç tohumundan kötüyse bu bir kusurdur: yerel arama
   yöntemleri bulunan en iyi çözümü saklamalı, asla daha kötüsüyle
   dönmemelidir.

Çalıştırma:
    python deney/scripts/algoritma_denetimi.py --n 3 --butce 5
"""

import argparse
import contextlib
import csv
import hashlib
import io
import os
import sys
import time
from collections import defaultdict
from datetime import datetime

_HERE = os.path.dirname(os.path.abspath(__file__))
_DENEY = os.path.dirname(_HERE)
_ROOT = os.path.dirname(_DENEY)
for p in (_ROOT, _HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import benchmark_yukle as by   # noqa: E402
import metrikler               # noqa: E402


@contextlib.contextmanager
def _sessiz():
    e = sys.stdout
    sys.stdout = io.StringIO()
    try:
        yield
    finally:
        sys.stdout = e


def parmak_izi(plan):
    """Çözümün içeriğinden bağımsız bir özet üretir."""
    kayitlar = []
    atama = plan.truck_assignments or {}
    for b_idx, yerlesimler in enumerate(plan.bins):
        tid = atama.get(b_idx, "?")
        for pl in yerlesimler:
            kayitlar.append(f"{tid}|{pl.piece_id}|{pl.x}|{pl.y}|{pl.z}")
    kayitlar.sort()
    return hashlib.sha256("\n".join(kayitlar).encode()).hexdigest()[:16]


def kosucular(butce):
    """(ad, stokastik, tohumlu_cagri, tohumsuz_cagri)"""
    from tabu_search_3d import tabu_search_3d_optimization as TS
    from simulated_annealing_3d import simulated_annealing_3d_optimization as SA
    from genetic_3d import genetic_3d_optimization as GA
    from monte_carlo_3d import monte_carlo_3d_optimization as MC
    from island_genetic_3d import island_model_ga_3d as IGA
    from multistart_sa_3d import multistart_sa_3d as MSA

    B = butce
    return [
        ("Tabu Search",
         lambda p, t, s, sd: TS(p, t, initial_solution=s, max_time=B, seed=sd),
         lambda p, t, sd: TS(p, t, initial_solution=None, max_time=B, seed=sd)),
        ("Sim. Annealing",
         lambda p, t, s, sd: SA(p, t, initial_solution=s, max_time=B, seed=sd),
         lambda p, t, sd: SA(p, t, initial_solution=None, max_time=B, seed=sd)),
        ("Genetic",
         lambda p, t, s, sd: GA(p, t, population_size=40, generations=10**7,
                                initial_solution=s, max_time=B, seed=sd),
         lambda p, t, sd: GA(p, t, population_size=40, generations=10**7,
                             initial_solution=None, max_time=B, seed=sd)),
        ("Monte Carlo",
         lambda p, t, s, sd: MC(p, t, iterations=10**7, initial_solution=s,
                                max_time=B, seed=sd),
         lambda p, t, sd: MC(p, t, iterations=10**7, initial_solution=None,
                             max_time=B, seed=sd)),
        ("Island GA",
         lambda p, t, s, sd: IGA(p, t, n_islands=3, island_population=15,
                                 generations=10**7, initial_solution=s,
                                 max_time=B, seed=sd),
         lambda p, t, sd: IGA(p, t, n_islands=3, island_population=15,
                              generations=10**7, initial_solution=None,
                              max_time=B, seed=sd)),
        ("Multi-Start SA",
         lambda p, t, s, sd: MSA(p, t, n_starts=4, time_budget=B,
                                 initial_solution=s, seed=sd),
         lambda p, t, sd: MSA(p, t, n_starts=4, time_budget=B,
                              initial_solution=None, seed=sd)),
    ]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dosya", default="thpack1")
    ap.add_argument("--n", type=int, default=3)
    ap.add_argument("--butce", type=float, default=5.0)
    ap.add_argument("--seed", type=int, default=1001)
    args = ap.parse_args()

    from ffd_3d import ffd_3d_optimization
    from greedy_3d import greedy_3d_optimization
    from layer_building_3d import layer_building_3d_optimization

    problemler = by.dosya_oku(args.dosya)[:args.n]
    metotlar = kosucular(args.butce)

    print("=" * 96)
    print("  ALGORİTMA DENETİMİ")
    print("=" * 96)
    print(f"  Veri seti : {args.dosya}, {len(problemler)} problem")
    print(f"  Bütçe     : {args.butce}s · seed {args.seed}")
    print("=" * 96)

    satirlar = []

    import math
    coklu = args.dosya not in ("thpack1", "thpack2", "thpack3", "thpack4",
                               "thpack5", "thpack6", "thpack7", "thpack8")

    for pi, p in enumerate(problemler, 1):
        if coklu:
            kh, koh = by.problem_hacimleri(p)
            lb = math.ceil(kh / koh) if koh else 1
            pieces, trucks = by.probleme_donustur(p, arac_adedi=max(lb * 3, 10))
        else:
            lb = 1
            pieces, trucks = by.probleme_donustur(p, arac_adedi=1)

        # Yapıcı sezgiseller (tohumsuz, referans)
        temel = {}
        for ad, fn in [("FFD", ffd_3d_optimization),
                       ("Greedy", greedy_3d_optimization),
                       ("Layer Building", layer_building_3d_optimization)]:
            with _sessiz():
                plan = fn(pieces, trucks)
            m = metrikler.hesapla(plan, pieces, trucks)
            temel[ad] = (m["U_G"], parmak_izi(plan), m["yerlesen_parca"],
                         m["kullanilan_arac"], m["yerlesen_oran"])
            satirlar.append({
                "problem": p["no"], "algoritma": ad, "mod": "tohumsuz",
                "U_G": m["U_G"], "yerlesen": m["yerlesen_parca"],
                "konteyner": m["kullanilan_arac"],
                "alt_sinir": lb if coklu else "",
                "gecerli": int(m["yerlesen_oran"] >= 0.999),
                "parmak_izi": temel[ad][1], "sure_s": 0,
                "tohuma_gore": "", "tohumla_ayni": "",
            })

        ffd_util, ffd_iz, ffd_yer = temel["FFD"][:3]
        with _sessiz():
            ffd_plan = ffd_3d_optimization(pieces, trucks)

        print(f"\n[{pi}/{len(problemler)}] problem {p['no']} — {len(pieces)} parça"
              + (f", alt sınır {lb} konteyner" if coklu else ""))
        if coklu:
            print(f"    {'YAPICI':<17}{'konteyner':>10}{'U_G':>8}{'yerleşen':>10}"
                  f"{'geçerli':>9}  parmak izi")
            for ad in ("FFD", "Greedy", "Layer Building"):
                u, iz, y, k, o = temel[ad]
                g = "EVET" if o >= 0.999 else "HAYIR"
                print(f"    {ad:<17}{k:>10}{u:>8.2f}{y:>10}{g:>9}  {iz}")
        else:
            print(f"    {'YAPICI':<17}{'U_G':>8}{'yerleşen':>10}  parmak izi")
            for ad in ("FFD", "Greedy", "Layer Building"):
                u, iz, y = temel[ad][:3]
                print(f"    {ad:<17}{u:>8.2f}{y:>10}  {iz}")

        if coklu:
            print(f"\n    {'METASEZGİSEL':<17}{'kont.(t)':>9}{'kont.(ts)':>10}"
                  f"{'geçerli':>9}{'süre':>7}  parmak izi (tohumlu)")
        else:
            print(f"\n    {'METASEZGİSEL':<17}{'tohumlu':>9}{'tohumsuz':>10}"
                  f"{'tohuma göre':>13}{'süre':>7}  parmak izi (tohumlu)")
        for ad, f_tohumlu, f_tohumsuz in metotlar:
            # (a) tohumlu
            t0 = time.time()
            try:
                with _sessiz():
                    plan_a = f_tohumlu(pieces, trucks, ffd_plan, args.seed)
                sure_a = time.time() - t0
                m_a = metrikler.hesapla(plan_a, pieces, trucks)
                iz_a = parmak_izi(plan_a)
            except Exception as e:
                print(f"    {ad:<17} HATA(tohumlu): {type(e).__name__}")
                continue

            # (b) tohumsuz
            t0 = time.time()
            try:
                with _sessiz():
                    plan_b = f_tohumsuz(pieces, trucks, args.seed)
                sure_b = time.time() - t0
                m_b = metrikler.hesapla(plan_b, pieces, trucks)
                iz_b = parmak_izi(plan_b)
            except Exception as e:
                m_b, iz_b, sure_b = None, "HATA", 0
                print(f"    {ad:<17} HATA(tohumsuz): {type(e).__name__}")

            fark = m_a["U_G"] - ffd_util
            ayni = "EVET" if iz_a == ffd_iz else "hayır"
            isaret = ""
            if fark < -0.01:
                isaret = "  ← TOHUMDAN KÖTÜ"
            elif iz_a == ffd_iz:
                isaret = "  ← tohumu aynen döndürdü"

            if coklu:
                gec_a = "EVET" if m_a["yerlesen_oran"] >= 0.999 else "HAYIR"
                kb = m_b["kullanilan_arac"] if m_b else 0
                print(f"    {ad:<17}{m_a['kullanilan_arac']:>9}{kb:>10}"
                      f"{gec_a:>9}{sure_a:>7.1f}  {iz_a}"
                      + ("  ← tohumu aynen döndürdü" if iz_a == ffd_iz else ""))
            else:
                print(f"    {ad:<17}{m_a['U_G']:>9.2f}"
                      f"{(m_b['U_G'] if m_b else 0):>10.2f}"
                      f"{fark:>+13.2f}{sure_a:>7.1f}  {iz_a}{isaret}")

            for mod, m, iz, sr in (("tohumlu", m_a, iz_a, sure_a),
                                   ("tohumsuz", m_b, iz_b, sure_b)):
                if m is None:
                    continue
                satirlar.append({
                    "problem": p["no"], "algoritma": ad, "mod": mod,
                    "U_G": m["U_G"], "yerlesen": m["yerlesen_parca"],
                    "konteyner": m["kullanilan_arac"],
                    "alt_sinir": lb if coklu else "",
                    "gecerli": int(m["yerlesen_oran"] >= 0.999),
                    "parmak_izi": iz, "sure_s": round(sr, 2),
                    "tohuma_gore": round(m["U_G"] - ffd_util, 2) if mod == "tohumlu" else "",
                    "tohumla_ayni": ayni if mod == "tohumlu" else "",
                })

    # ── Parmak izi çakışmaları ────────────────────────────────────────────
    print("\n" + "=" * 96)
    print("  PARMAK İZİ ÇAKIŞMALARI — aynı çözümü üreten yöntemler")
    print("=" * 96)
    esler = defaultdict(list)
    for s in satirlar:
        esler[(s["problem"], s["mod"], s["parmak_izi"])].append(s["algoritma"])

    cakisma = defaultdict(int)
    for (prob, mod, iz), adlar in esler.items():
        if len(adlar) > 1:
            for i in range(len(adlar)):
                for j in range(i + 1, len(adlar)):
                    cakisma[tuple(sorted((adlar[i], adlar[j])))] += 1

    if cakisma:
        print(f"  {'Yöntem çifti':<42}{'Kaç kez aynı çözüm':>20}")
        print("  " + "-" * 62)
        for cift, n in sorted(cakisma.items(), key=lambda x: -x[1]):
            print(f"  {cift[0] + '  =  ' + cift[1]:<42}{n:>20}")
    else:
        print("  Çakışma yok — her yöntem farklı çözüm üretiyor.")

    out = os.path.join(_DENEY, "results", "raw",
                       f"algoritma_denetimi_{datetime.now().strftime('%Y%m%d_%H%M')}.csv")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(satirlar[0].keys()))
        w.writeheader(); w.writerows(satirlar)
    print(f"\n  CSV: {out}")
    print("=" * 96)


if __name__ == "__main__":
    main()
