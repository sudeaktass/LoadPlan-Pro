# -*- coding: utf-8 -*-
"""
DENEY KOŞUMU — Konfigürasyon Tabanlı
=====================================
Ayarlar bu dosyanın içine gömülü DEĞİLDİR; configs/ altındaki YAML dosyasından
ve seeds/ altındaki sabit seed listesinden okunur. Aynı config + aynı seed
listesi → birebir aynı sonuç.

Algoritma tanımları mevcut deney_kosumu.py dosyasından IMPORT edilir; burada
kopyalanmaz. Böylece "hangi algoritmalar, hangi parametrelerle çağrılıyor"
sorusunun tek bir cevabı olur.

Her koşum için kaydedilen alanlar (danışman raporu Bölüm 10.2):
  Kimlik   : ornek_id, algoritma, kosum_no, seed, commit_hash
  Ortam    : OS, Python sürümü, işlemci
  Bütçe    : zaman_butcesi_s, sure_s
  Çözüm    : yerlesen/toplam parça, kullanılan araç
  Metrikler: U_BB, U_G, U_Fleet, T_V, T_W

Çalıştırma:
    python deney/scripts/kosum.py --pilot            # hızlı altyapı denemesi
    python deney/scripts/kosum.py --pilot --limit 3  # sadece 3 örnek
    python deney/scripts/kosum.py                    # tam koşum (uzun sürer)
"""

import argparse
import csv
import glob
import io
import json
import os
import platform
import subprocess
import sys
import time
import contextlib
from datetime import datetime

_HERE = os.path.dirname(os.path.abspath(__file__))
_DENEY = os.path.dirname(_HERE)
_ROOT = os.path.dirname(_DENEY)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import yaml  # noqa: E402
from core_3d import Piece3D, Truck3D  # noqa: E402
import metrikler  # noqa: E402

# Lift-Top (ayarlanabilir tavan) DENEYDE KAPALI: araç boyutunun koşu
# içinde değişmesi sabit kutulara yerleştirme problemini değiştirir ve
# aynı koşudaki doluluk karşılaştırmasını bozar. Uygulamada açıktır.
import filo_havuzu as _fh  # noqa: E402
_fh.LIFT_TOP_ACIK = False

VARSAYILAN_CONFIG = os.path.join(_DENEY, "configs", "pilot_geometri.yaml")


@contextlib.contextmanager
def _sessiz():
    eski = sys.stdout
    sys.stdout = io.StringIO()
    try:
        yield
    finally:
        sys.stdout = eski


# ═══════════════════════════════════════════════════════════════════════════
# Yükleme
# ═══════════════════════════════════════════════════════════════════════════
def seed_listesi_oku(yol):
    seeds = []
    with open(yol, encoding="utf-8") as f:
        for satir in f:
            satir = satir.strip()
            if satir and not satir.startswith("#"):
                seeds.append(int(satir))
    return seeds


def ornek_yukle(json_yolu):
    """JSON örneğini Piece3D / Truck3D nesnelerine dönüştürür."""
    with open(json_yolu, encoding="utf-8") as f:
        d = json.load(f)

    pieces = [
        Piece3D(
            id=p["id"],
            width=p["genislik"], length=p["uzunluk"], height=p["yukseklik"],
            quantity=p.get("adet", 1),
            weight=p["agirlik"],
            shape="cylinder" if p["sekil"] == "silindir" else "box",
        )
        for p in d["parcalar"]
    ]
    trucks = [
        Truck3D(id=a["id"], width=a["genislik"], length=a["uzunluk"],
                height=a["yukseklik"], capacity=a["kapasite_kg"],
                available=a["adet"])
        for a in d["filo"]
    ]
    return d, pieces, trucks


def commit_hash():
    try:
        r = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                           cwd=_ROOT, capture_output=True, text=True, timeout=10)
        h = r.stdout.strip()
        # calisma agacinda kaydedilmemis degisiklik var mi?
        d = subprocess.run(["git", "status", "--porcelain"],
                           cwd=_ROOT, capture_output=True, text=True, timeout=10)
        return (h + "+kirli") if d.stdout.strip() else h
    except Exception:
        return "bilinmiyor"


# ═══════════════════════════════════════════════════════════════════════════
# Ana koşum
# ═══════════════════════════════════════════════════════════════════════════
def main():
    ap = argparse.ArgumentParser(description="Konfigürasyon tabanlı deney koşumu")
    ap.add_argument("--config", default=VARSAYILAN_CONFIG)
    ap.add_argument("--pilot", action="store_true",
                    help="pilot_tekrar_sayisi kullan (hızlı altyapı denemesi)")
    ap.add_argument("--limit", type=int, default=0,
                    help="yalnızca ilk N örneği koş (0 = hepsi)")
    ap.add_argument("--out", default=None, help="çıktı CSV yolu")
    args = ap.parse_args()

    with open(args.config, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    kcfg = config["kosum"]
    tekrar = kcfg["pilot_tekrar_sayisi"] if args.pilot else kcfg["tekrar_sayisi"]
    butce = kcfg["zaman_butcesi_s"]
    seeds = seed_listesi_oku(os.path.join(_DENEY, kcfg["seed_dosyasi"]))

    if tekrar > len(seeds):
        raise SystemExit(
            f"Seed listesinde {len(seeds)} seed var ama {tekrar} tekrar isteniyor. "
            f"seeds/ dosyasına seed ekleyin."
        )

    # Algoritma tanımlarını mevcut koşucudan al (tek kaynak).
    import deney_kosumu as dk
    dk.BUTCE = butce            # zaman bütçesini config'ten uygula
    runners = dk._runners()

    json_dizin = os.path.join(_DENEY, config["cikti"]["ornek_json_dizini"])
    ornekler = sorted(glob.glob(os.path.join(json_dizin, "geo_*.json")))
    if args.limit:
        ornekler = ornekler[:args.limit]
    if not ornekler:
        raise SystemExit(f"Örnek bulunamadı: {json_dizin}\n"
                         f"Önce: python deney/scripts/ornek_ureteci.py")

    ch = commit_hash()
    ortam = f"{platform.system()} {platform.release()} / Python {platform.python_version()}"

    out_yol = args.out or os.path.join(
        _DENEY, config["cikti"]["ham_sonuc_dizini"],
        f"kosum_{'pilot' if args.pilot else 'tam'}_"
        f"{datetime.now().strftime('%Y%m%d_%H%M')}.csv")
    os.makedirs(os.path.dirname(out_yol), exist_ok=True)

    print("=" * 78)
    print("  DENEY KOŞUMU")
    print("=" * 78)
    print(f"  Config       : {os.path.basename(args.config)}")
    print(f"  Örnek        : {len(ornekler)}")
    print(f"  Algoritma    : {len(runners)}  ({', '.join(a for a, _, _ in runners)})")
    print(f"  Tekrar       : {tekrar} (stokastik yöntemler için)")
    print(f"  Zaman bütçesi: {butce}s")
    print(f"  Seed         : {seeds[:tekrar]}")
    print(f"  Commit       : {ch}")
    print(f"  Ortam        : {ortam}")
    print(f"  Çıktı        : {out_yol}")
    print("=" * 78)

    alanlar = [
        "ornek_id", "algoritma", "kosum_no", "seed",
        "U_BB", "U_G", "U_Fleet", "T_V", "T_W",
        "kullanilan_arac", "yerlesen_parca", "toplam_parca", "yerlesen_oran",
        "sure_s", "zaman_butcesi_s", "stokastik",
        "hedef_silindir_payi", "ulasilan_silindir_payi",
        "commit_hash", "ortam", "config", "uyarilar",
    ]

    t_basla = time.time()
    satirlar = []

    for oi, oyol in enumerate(ornekler, 1):
        meta, pieces, trucks = ornek_yukle(oyol)
        oid = meta["ornek_id"]

        # Metasezgiseller için ortak başlangıç çözümü (adil karşılaştırma)
        from ffd_3d import ffd_3d_optimization
        with _sessiz():
            ffd_seed_plan = ffd_3d_optimization(pieces, trucks)

        print(f"\n[{oi}/{len(ornekler)}] {oid}  "
              f"(silindir payı {meta['ulasilan_silindir_hacim_payi']:.3f}, "
              f"{len(pieces)} parça)")

        for ad, stokastik, fn in runners:
            n = tekrar if stokastik else 1
            u_bb_list, u_g_list = [], []

            for k in range(n):
                sd = seeds[k]
                t0 = time.time()
                try:
                    with _sessiz():
                        plan = fn(pieces, trucks, ffd_seed_plan, sd)
                    sure = time.time() - t0
                    m = metrikler.hesapla(plan, pieces, trucks)
                    uy = metrikler.gecerlilik_kontrolu(m)
                except Exception as e:
                    print(f"      HATA {ad}: {type(e).__name__}: {e}")
                    continue

                satirlar.append({
                    "ornek_id": oid, "algoritma": ad, "kosum_no": k + 1,
                    "seed": sd if stokastik else "",
                    "U_BB": m["U_BB"], "U_G": m["U_G"], "U_Fleet": m["U_Fleet"],
                    "T_V": m["T_V"], "T_W": m["T_W"],
                    "kullanilan_arac": m["kullanilan_arac"],
                    "yerlesen_parca": m["yerlesen_parca"],
                    "toplam_parca": m["toplam_parca"],
                    "yerlesen_oran": m["yerlesen_oran"],
                    "sure_s": round(sure, 3),
                    "zaman_butcesi_s": butce if stokastik else "",
                    "stokastik": int(stokastik),
                    "hedef_silindir_payi": meta["hedef_silindir_hacim_payi"],
                    "ulasilan_silindir_payi": meta["ulasilan_silindir_hacim_payi"],
                    "commit_hash": ch, "ortam": ortam,
                    "config": os.path.basename(args.config),
                    "uyarilar": "; ".join(uy),
                })
                u_bb_list.append(m["U_BB"])
                u_g_list.append(m["U_G"])

            if u_g_list:
                ort_g = sum(u_g_list) / len(u_g_list)
                ort_bb = sum(u_bb_list) / len(u_bb_list)
                fark = ort_bb - ort_g
                print(f"      {ad:16s} U_G %{ort_g:5.2f} | U_BB %{ort_bb:5.2f} "
                      f"| fark {fark:+5.2f} puan  ({len(u_g_list)} koşum)")

    with open(out_yol, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=alanlar)
        w.writeheader()
        w.writerows(satirlar)

    print("\n" + "=" * 78)
    print(f"  TAMAM: {len(satirlar)} koşum kaydı, "
          f"toplam süre {time.time() - t_basla:.1f}s")
    print(f"  CSV: {out_yol}")
    uyarili = [s for s in satirlar if s["uyarilar"]]
    if uyarili:
        print(f"  ⚠ {len(uyarili)} kayıtta metrik uyarısı var — CSV'deki "
              f"'uyarilar' sütununa bakın.")
    else:
        print("  Metrik tutarlılık kontrolü: tüm kayıtlar temiz.")
    print("=" * 78)


if __name__ == "__main__":
    main()
