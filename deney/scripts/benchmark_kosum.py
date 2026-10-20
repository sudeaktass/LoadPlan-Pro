# -*- coding: utf-8 -*-
"""
BENCHMARK KOŞUMU — Literatürle karşılaştırma
=============================================
LoadPlan Pro algoritmalarını OR-Library standart problemleri üzerinde koşturur
ve yayımlanmış sonuçlarla yan yana koyar.

İKİ AYRI PROBLEM TİPİ, İKİ AYRI ÖLÇÜT
--------------------------------------
thpack1-8 (BR, LN) — TEK konteyner, "çıktı en çoklama":
    Bütün kutular sığmaz; amaç konteynere en çok hacmi yüklemektir.
    Ölçüt: hacim doluluğu = yerleşen kutuların hacmi / konteyner hacmi
    Yerleşmeyen kutu OLAĞANDIR, hata değildir.

thpack9 (IMM) — ÇOKLU konteyner, "girdi en azlama":
    Bütün kutular yüklenmek zorundadır; amaç konteyner sayısını azaltmaktır.
    Ölçüt: kullanılan konteyner sayısı (ikincil: doluluk)
    Yerleşmeyen kutu GEÇERSİZ çözüm demektir.

Bu ayrım Wäscher, Haußner & Schumann (2007) sınıflandırmasına dayanır.

ÖNEMLİ: Bu koşum algoritmaları DOĞRUDAN çağırır; uygulamanın "hepsi yerleşsin"
boru hattını (minimum araç seçimi + kurtarma zinciri) kullanmaz. Çünkü tek
konteyner problemlerinde tüm kutuların yerleşmesi zaten mümkün değildir.

Çalıştırma:
    python deney/scripts/benchmark_kosum.py --dosya thpack1 --n 10
    python deney/scripts/benchmark_kosum.py --dosya thpack1 --n 10 --hizli
    python deney/scripts/benchmark_kosum.py --dosya thpack9 --n 10
"""

import argparse
import contextlib
import csv
import io
import os
import statistics
import sys
import time
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


# ═══════════════════════════════════════════════════════════════════════════
# Yayımlanmış referans değerler
# ═══════════════════════════════════════════════════════════════════════════
# Kaynak: Transportation Safety and Environment 8(1), tdaf078 (2026),
#         "Optimization of container-balanced loading layout with stacking
#          and corner-casting constraints", Tablo 1.
#         Ortalama hacim doluluğu (%), BR setlerinin 100'er probleminde.
# BRGA     : Biased Random-Key Genetic Algorithm
# MPBRKGA  : Multi-Population BRKGA
# MLHCBLA  : Mixed Light/Heavy Cargo Balanced Loading Algorithm
YAYIMLANMIS = {
    "thpack1": {"BRGA": 94.39, "MPBRKGA": 91.31, "MLHCBLA": 90.73},
    "thpack2": {"BRGA": 94.91, "MPBRKGA": 92.42, "MLHCBLA": 91.45},
    "thpack3": {"BRGA": 95.10, "MPBRKGA": 93.35, "MLHCBLA": 91.96},
    "thpack4": {"BRGA": 94.82, "MPBRKGA": 93.58, "MLHCBLA": 92.23},
    "thpack5": {"BRGA": 94.61, "MPBRKGA": 93.66, "MLHCBLA": 92.39},
    "thpack6": {"BRGA": 94.42, "MPBRKGA": 93.51, "MLHCBLA": 91.55},
    "thpack7": {"BRGA": 93.79, "MPBRKGA": 93.43, "MLHCBLA": 91.29},
}

TEK_KONTEYNER = {"thpack1", "thpack2", "thpack3", "thpack4",
                 "thpack5", "thpack6", "thpack7", "thpack8"}


@contextlib.contextmanager
def _sessiz():
    eski = sys.stdout
    sys.stdout = io.StringIO()
    try:
        yield
    finally:
        sys.stdout = eski


def _kosucular(hizli, butce, seed):
    """(ad, stokastik, fonksiyon) listesi. Tanımlar deney_kosumu'ndan gelir."""
    import deney_kosumu as dk
    dk.BUTCE = butce
    hepsi = dk._runners()
    if hizli:
        return [r for r in hepsi if not r[1]]     # yalnız deterministikler
    return hepsi


def _alt_sinir_konteyner(problem):
    """Çoklu konteyner problemleri için hacim tabanlı alt sınır."""
    kutu_hacim, kont_hacim = by.problem_hacimleri(problem)
    import math
    return math.ceil(kutu_hacim / kont_hacim) if kont_hacim else 0


def main():
    ap = argparse.ArgumentParser(description="OR-Library benchmark koşumu")
    ap.add_argument("--dosya", default="thpack1")
    ap.add_argument("--n", type=int, default=10, help="kaç problem koşulacak")
    ap.add_argument("--hizli", action="store_true",
                    help="yalnız deterministik algoritmalar (FFD/Greedy/Layer)")
    ap.add_argument("--butce", type=float, default=5.0,
                    help="metasezgisel başına saniye")
    ap.add_argument("--tekrar", type=int, default=1,
                    help="stokastik yöntemler için tekrar sayısı")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    dosya = args.dosya
    problemler = by.dosya_oku(dosya)[:args.n]
    coklu = dosya not in TEK_KONTEYNER
    kaynak, _tip, aciklama = by.DOSYA_BILGI[dosya]

    seeds = [1001 + i for i in range(args.tekrar)]
    kosucular = _kosucular(args.hizli, args.butce, seeds[0])

    out = args.out or os.path.join(
        _DENEY, "results", "raw",
        f"benchmark_{dosya}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv")
    os.makedirs(os.path.dirname(out), exist_ok=True)

    print("=" * 88)
    print(f"  BENCHMARK KOŞUMU — {dosya}")
    print("=" * 88)
    print(f"  Kaynak       : {kaynak}")
    print(f"  Açıklama     : {aciklama}")
    print(f"  Problem tipi : {'ÇOKLU konteyner (konteyner sayısını azalt)' if coklu else 'TEK konteyner (doluluğu artır)'}")
    print(f"  Problem      : {len(problemler)} adet")
    print(f"  Algoritma    : {len(kosucular)} ({', '.join(a for a,_,_ in kosucular)})")
    print(f"  Bütçe        : {args.butce}s · tekrar {args.tekrar}")
    if by.BICIM_UYARILARI:
        print(f"  ⚠ Kaynak dosyada {len(set(by.BICIM_UYARILARI))} biçim uyarısı var")
    print("=" * 88)

    satirlar = []
    from ffd_3d import ffd_3d_optimization

    for pi, p in enumerate(problemler, 1):
        if coklu:
            lb = _alt_sinir_konteyner(p)
            arac = max(lb * 3, 10)      # bol pay: alt sınırın 3 katı
        else:
            lb, arac = 1, 1

        pieces, trucks = by.probleme_donustur(p, arac_adedi=arac)
        kutu_hacim, kont_hacim = by.problem_hacimleri(p)

        with _sessiz():
            ffd_tohum = ffd_3d_optimization(pieces, trucks)

        print(f"\n[{pi}/{len(problemler)}] problem {p['no']} — "
              f"{len(pieces)} parça, {len(p['kutu_tipleri'])} tip"
              + (f", alt sınır {lb} konteyner" if coklu else ""))

        for ad, stokastik, fn in kosucular:
            n = args.tekrar if stokastik else 1
            olcumler = []
            for k in range(n):
                t0 = time.time()
                try:
                    with _sessiz():
                        plan = fn(pieces, trucks, ffd_tohum, seeds[k])
                    sure = time.time() - t0
                    m = metrikler.hesapla(plan, pieces, trucks)
                except Exception as e:
                    print(f"      HATA {ad}: {type(e).__name__}: {str(e)[:50]}")
                    continue

                # Tek konteynerde literatür ölçütü: yerleşen hacim / konteyner hacmi
                lit_doluluk = (sum(
                    pc.get_actual_volume()
                    for b in plan.bins for pl in b
                    for pc in [next((x for x in pieces if x.id == pl.piece_id), None)]
                    if pc is not None) / kont_hacim * 100.0) if kont_hacim else 0.0

                satirlar.append({
                    "dosya": dosya, "problem": p["no"], "algoritma": ad,
                    "kosum_no": k + 1, "seed": seeds[k] if stokastik else "",
                    "parca_sayisi": len(pieces),
                    "kutu_tipi": len(p["kutu_tipleri"]),
                    "yerlesen": m["yerlesen_parca"],
                    "yerlesen_oran": m["yerlesen_oran"],
                    "kullanilan_konteyner": m["kullanilan_arac"],
                    "alt_sinir_konteyner": lb if coklu else "",
                    "literatur_doluluk": round(lit_doluluk, 3),
                    "U_G": m["U_G"], "U_BB": m["U_BB"],
                    "sure_s": round(sure, 3), "stokastik": int(stokastik),
                })
                olcumler.append((lit_doluluk, m["kullanilan_arac"],
                                 m["yerlesen_parca"], sure))

            if olcumler:
                od = statistics.mean(o[0] for o in olcumler)
                ok = statistics.mean(o[1] for o in olcumler)
                oy = statistics.mean(o[2] for o in olcumler)
                osr = statistics.mean(o[3] for o in olcumler)
                if coklu:
                    print(f"      {ad:16s} konteyner {ok:5.1f} (alt sınır {lb})  "
                          f"yerleşen {oy:5.1f}/{len(pieces)}  {osr:5.2f}s")
                else:
                    print(f"      {ad:16s} doluluk %{od:5.2f}  "
                          f"yerleşen {oy:5.1f}/{len(pieces)}  {osr:5.2f}s")

    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(satirlar[0].keys()))
        w.writeheader(); w.writerows(satirlar)

    # ── Özet + literatür karşılaştırması ──────────────────────────────────
    print("\n" + "=" * 88)
    print("  ÖZET")
    print("=" * 88)

    algolar = sorted({s["algoritma"] for s in satirlar})
    if coklu:
        print(f"  {'Algoritma':<18}{'Ort. konteyner':>16}{'Ort. alt sınır':>16}"
              f"{'Açık':>8}{'Yerleşen %':>12}")
        print("  " + "-" * 70)
        for a in algolar:
            g = [s for s in satirlar if s["algoritma"] == a]
            ok = statistics.mean(s["kullanilan_konteyner"] for s in g)
            lb = statistics.mean(float(s["alt_sinir_konteyner"]) for s in g)
            yo = statistics.mean(s["yerlesen_oran"] for s in g) * 100
            print(f"  {a:<18}{ok:>16.2f}{lb:>16.2f}{ok-lb:>8.2f}{yo:>12.1f}")
    else:
        print(f"  {'Algoritma':<18}{'Ort. doluluk %':>16}{'std':>8}"
              f"{'Yerleşen %':>12}{'Ort. süre s':>13}")
        print("  " + "-" * 70)
        bizim = {}
        for a in algolar:
            g = [s for s in satirlar if s["algoritma"] == a]
            d = [s["literatur_doluluk"] for s in g]
            bizim[a] = statistics.mean(d)
            sd = statistics.pstdev(d) if len(d) > 1 else 0.0
            yo = statistics.mean(s["yerlesen_oran"] for s in g) * 100
            sr = statistics.mean(s["sure_s"] for s in g)
            print(f"  {a:<18}{bizim[a]:>16.2f}{sd:>8.2f}{yo:>12.1f}{sr:>13.2f}")

        ref = YAYIMLANMIS.get(dosya)
        if ref:
            print("\n  " + "-" * 70)
            print("  LİTERATÜRDE YAYIMLANMIŞ SONUÇLAR (aynı veri seti, 100 problem)")
            print("  " + "-" * 70)
            for ad, deger in sorted(ref.items(), key=lambda x: -x[1]):
                print(f"  {ad:<18}{deger:>16.2f}")
            en_iyi_biz = max(bizim.values())
            en_iyi_lit = max(ref.values())
            print("  " + "-" * 70)
            print(f"  Bizim en iyimiz : %{en_iyi_biz:.2f}")
            print(f"  Literatür en iyi: %{en_iyi_lit:.2f}")
            print(f"  FARK            : {en_iyi_biz - en_iyi_lit:+.2f} puan")
            print("\n  NOT: Yayımlanmış değerler 100 problemin tamamının ortalamasıdır;")
            print(f"       bizimki {len(problemler)} problem. Kesin kıyas için tüm set koşulmalıdır.")

    print(f"\n  CSV: {out}")
    print("=" * 88)


if __name__ == "__main__":
    main()
