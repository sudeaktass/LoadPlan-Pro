# -*- coding: utf-8 -*-
"""
ANALİZ — Silindir payı ile ölçüm yanlılığı arasındaki ilişki
=============================================================
Ham koşum CSV'sini okur ve şu soruyu yanıtlayan tabloyu üretir:

    "Yükteki silindir oranı arttıkça, bounding-box tabanlı doluluk ölçümü
     gerçek geometri tabanlı ölçümden ne kadar sapıyor?"

Teorik beklenti:
    U_BB − U_G  =  U_BB × silindir_hacim_payı × (1 − π/4)

Bu betik, ölçülen farkı teorik beklentiyle karşılaştırır. İkisi örtüşüyorsa
fark ALGORİTMİK değil, salt geometri temsilinden kaynaklanıyor demektir.

Çalıştırma:
    python deney/scripts/analiz.py                      # en yeni CSV'yi kullanır
    python deney/scripts/analiz.py --csv <yol>
"""

import argparse
import csv
import glob
import math
import os
import statistics
import sys
from collections import defaultdict

_HERE = os.path.dirname(os.path.abspath(__file__))
_DENEY = os.path.dirname(_HERE)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

PI4 = math.pi / 4.0


def en_yeni_csv():
    adaylar = glob.glob(os.path.join(_DENEY, "results", "raw", "*.csv"))
    if not adaylar:
        raise SystemExit("results/raw altında CSV yok. Önce kosum.py çalıştırın.")
    return max(adaylar, key=os.path.getmtime)


def oku(yol):
    with open(yol, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=None)
    args = ap.parse_args()

    yol = args.csv or en_yeni_csv()
    satirlar = oku(yol)
    if not satirlar:
        raise SystemExit("CSV boş.")

    print("=" * 84)
    print("  ANALİZ — Silindir Payı ve Ölçüm Yanlılığı")
    print("=" * 84)
    print(f"  Kaynak : {os.path.basename(yol)}")
    print(f"  Kayıt  : {len(satirlar)} koşum")

    # ── 1) Silindir payı seviyesine göre özet ──────────────────────────────
    gruplar = defaultdict(list)
    for s in satirlar:
        gruplar[float(s["hedef_silindir_payi"])].append(s)

    print("\n" + "-" * 84)
    print("  TABLO 1 — Silindir hacim payına göre ölçüm farkı (tüm algoritmalar)")
    print("-" * 84)
    print(f"  {'Silindir payı':>14}{'U_BB':>10}{'U_G':>10}{'Ölçülen':>10}"
          f"{'Teorik':>10}{'Sapma':>9}{'Koşum':>8}")
    print(f"  {'(hedef)':>14}{'%':>10}{'%':>10}{'fark':>10}{'fark':>10}{'':>9}{'':>8}")
    print("  " + "-" * 78)

    tablo = []
    for pay in sorted(gruplar):
        g = gruplar[pay]
        u_bb = statistics.mean(float(s["U_BB"]) for s in g)
        u_g = statistics.mean(float(s["U_G"]) for s in g)
        ulasilan = statistics.mean(float(s["ulasilan_silindir_payi"]) for s in g)
        olculen = u_bb - u_g
        teorik = u_bb * ulasilan * (1 - PI4)
        sapma = olculen - teorik
        tablo.append({
            "hedef_silindir_payi": pay,
            "ulasilan_silindir_payi": round(ulasilan, 4),
            "U_BB_ort": round(u_bb, 3),
            "U_G_ort": round(u_g, 3),
            "olculen_fark": round(olculen, 3),
            "teorik_fark": round(teorik, 3),
            "sapma": round(sapma, 3),
            "kosum_sayisi": len(g),
        })
        print(f"  {pay:>14.2f}{u_bb:>10.2f}{u_g:>10.2f}{olculen:>10.2f}"
              f"{teorik:>10.2f}{sapma:>+9.2f}{len(g):>8d}")

    # ── 2) Algoritma bazlı özet ────────────────────────────────────────────
    print("\n" + "-" * 84)
    print("  TABLO 2 — Algoritma bazlı ortalama doluluk (tüm örnekler)")
    print("-" * 84)
    print(f"  {'Algoritma':<18}{'U_G %':>9}{'std':>8}{'U_BB %':>9}"
          f"{'U_Fleet %':>11}{'Yerleşen':>10}{'Süre s':>9}{'Koşum':>7}")
    print("  " + "-" * 78)

    algo = defaultdict(list)
    for s in satirlar:
        algo[s["algoritma"]].append(s)

    algo_tablo = []
    for ad in sorted(algo, key=lambda a: -statistics.mean(
            float(s["U_G"]) for s in algo[a])):
        g = algo[ad]
        ug = [float(s["U_G"]) for s in g]
        satir = {
            "algoritma": ad,
            "U_G_ort": round(statistics.mean(ug), 3),
            "U_G_std": round(statistics.pstdev(ug), 3) if len(ug) > 1 else 0.0,
            "U_BB_ort": round(statistics.mean(float(s["U_BB"]) for s in g), 3),
            "U_Fleet_ort": round(statistics.mean(float(s["U_Fleet"]) for s in g), 3),
            "yerlesen_oran_ort": round(
                statistics.mean(float(s["yerlesen_oran"]) for s in g), 4),
            "sure_ort_s": round(statistics.mean(float(s["sure_s"]) for s in g), 3),
            "kosum_sayisi": len(g),
        }
        algo_tablo.append(satir)
        print(f"  {ad:<18}{satir['U_G_ort']:>9.2f}{satir['U_G_std']:>8.2f}"
              f"{satir['U_BB_ort']:>9.2f}{satir['U_Fleet_ort']:>11.2f}"
              f"{satir['yerlesen_oran_ort'] * 100:>9.1f}%{satir['sure_ort_s']:>9.2f}"
              f"{satir['kosum_sayisi']:>7d}")

    # ── 3) Kaydet ──────────────────────────────────────────────────────────
    cikti_dizin = os.path.join(_DENEY, "results", "processed")
    os.makedirs(cikti_dizin, exist_ok=True)

    y1 = os.path.join(cikti_dizin, "tablo1_silindir_payi_vs_fark.csv")
    with open(y1, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(tablo[0].keys()))
        w.writeheader(); w.writerows(tablo)

    y2 = os.path.join(cikti_dizin, "tablo2_algoritma_ozeti.csv")
    with open(y2, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(algo_tablo[0].keys()))
        w.writeheader(); w.writerows(algo_tablo)

    # ── 4) Yorum ───────────────────────────────────────────────────────────
    sifir = next((t for t in tablo if t["hedef_silindir_payi"] == 0.0), None)
    tam = next((t for t in tablo if t["hedef_silindir_payi"] == 1.0), None)

    print("\n" + "=" * 84)
    print("  YORUM")
    print("=" * 84)
    if sifir:
        durum = "EVET" if abs(sifir["olculen_fark"]) < 0.01 else "HAYIR"
        print(f"  • Silindir yokken (pay=0) U_BB ile U_G eşit mi? {durum} "
              f"(fark {sifir['olculen_fark']:+.3f} puan)")
    if tam:
        print(f"  • Yalnız silindirken (pay=1) fark {tam['olculen_fark']:.2f} puan "
              f"(teorik beklenti {tam['teorik_fark']:.2f})")
    max_sapma = max(abs(t["sapma"]) for t in tablo)
    print(f"  • Ölçülen fark ile teorik beklenti arasındaki en büyük sapma: "
          f"{max_sapma:.2f} puan")
    if max_sapma < 1.0:
        print("    → Ölçülen fark teorik beklentiyle örtüşüyor. Bu, farkın")
        print("      ALGORİTMİK bir boşluk değil, geometri temsilinden")
        print("      kaynaklandığını doğrular.")

    print(f"\n  Kaydedildi:\n    {y1}\n    {y2}")
    print("=" * 84)


if __name__ == "__main__":
    main()
