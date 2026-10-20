# -*- coding: utf-8 -*-
"""
ÖRNEK ÜRETECİ — Pilot Geometri Veri Seti
=========================================
Silindir HACİM payı kontrollü biçimde değiştirilerek problem örnekleri üretir.

Neden hacim payı (adet payı değil)?
    Bounding-box yanlılığı, silindirlerin KAÇ TANE olduğuna değil, toplam
    hacmin ne kadarını kapladığına bağlıdır. 40 küçük silindir ile 3 büyük
    silindir aynı yanlılığı üretmez. Bu nedenle hedef, silindirlerin
    bounding-box hacminin toplam bounding-box hacmine oranıdır.

Tekrarlanabilirlik:
    Her örnek, kendi seed'i ile üretilir (taban seed + seviye + tekrar).
    Aynı config + aynı seed → birebir aynı örnek.

Çalıştırma:
    python deney/scripts/ornek_ureteci.py
    python deney/scripts/ornek_ureteci.py --config deney/configs/pilot_geometri.yaml
"""

import argparse
import json
import math
import os
import random
import sys
from datetime import datetime

# Proje kökünü (enterprise_backup_20260410) yola ekle
_HERE = os.path.dirname(os.path.abspath(__file__))
_DENEY = os.path.dirname(_HERE)
_ROOT = os.path.dirname(_DENEY)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import yaml  # noqa: E402

# Windows'ta konsol kod sayfası (cp1254) Türkçe dışı karakterlerde hata verir.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

VARSAYILAN_CONFIG = os.path.join(_DENEY, "configs", "pilot_geometri.yaml")


# ═══════════════════════════════════════════════════════════════════════════
# Hacim yardımcıları
# ═══════════════════════════════════════════════════════════════════════════
def bbox_hacim(p):
    """Bounding-box hacmi (cm³) — yerleştirme motorunun gördüğü hacim."""
    return p["genislik"] * p["uzunluk"] * p["yukseklik"]


def gercek_hacim(p):
    """Gerçek geometrik hacim (cm³). Silindir için π·r²·h."""
    if p["sekil"] == "silindir":
        return math.pi * (p["genislik"] / 2.0) ** 2 * p["yukseklik"]
    return float(bbox_hacim(p))


def silindir_hacim_payi(parcalar):
    """Silindirlerin bounding-box hacminin toplam bbox hacmine oranı."""
    toplam = sum(bbox_hacim(p) for p in parcalar)
    if toplam <= 0:
        return 0.0
    sil = sum(bbox_hacim(p) for p in parcalar if p["sekil"] == "silindir")
    return sil / toplam


# ═══════════════════════════════════════════════════════════════════════════
# Parça üretimi
# ═══════════════════════════════════════════════════════════════════════════
def _kutu_uret(rng, cfg, idx):
    b = cfg["kutu_boyutlari"]
    a_min, a_max = cfg["agirlik_araligi"]
    return {
        "id": f"K{idx:03d}",
        "sekil": "kutu",
        "genislik": rng.choice(b["genislik"]),
        "uzunluk": rng.choice(b["uzunluk"]),
        "yukseklik": rng.choice(b["yukseklik"]),
        "agirlik": rng.randint(a_min, a_max),
        "adet": 1,
    }


def _silindir_uret(rng, cfg, idx):
    s = cfg["silindir_boyutlari"]
    a_min, a_max = cfg["agirlik_araligi"]
    cap = rng.choice(s["cap"])
    return {
        "id": f"S{idx:03d}",
        "sekil": "silindir",
        "genislik": cap,      # silindirde genişlik = uzunluk = çap
        "uzunluk": cap,
        "yukseklik": rng.choice(s["yukseklik"]),
        "agirlik": rng.randint(a_min, a_max),
        "adet": 1,
    }


def ornek_uret(hedef_pay, seed, cfg):
    """
    Hedef silindir hacim payına en yakın örneği üretir.

    Yöntem: n parçanın k tanesi silindir olacak şekilde, k'yı 0..n arasında
    tarayarak elde edilen gerçek hacim payını ölçer ve hedefe en yakın k'yı
    seçer. Boyutlar rastgele olduğu için hedef paya tam olarak ulaşılamaz;
    ULAŞILAN pay örnek meta verisine yazılır ve analizde bu değer kullanılır.
    """
    n = cfg["parca_sayisi"]

    # Sabit seed ile aday havuzları üret (k değiştikçe parçalar değişmesin)
    rng = random.Random(seed)
    kutu_havuz = [_kutu_uret(rng, cfg, i) for i in range(n)]
    sil_havuz = [_silindir_uret(rng, cfg, i) for i in range(n)]

    en_iyi, en_iyi_fark = None, float("inf")
    for k in range(n + 1):
        aday = sil_havuz[:k] + kutu_havuz[k:]
        pay = silindir_hacim_payi(aday)
        fark = abs(pay - hedef_pay)
        if fark < en_iyi_fark:
            en_iyi_fark, en_iyi = fark, (k, aday, pay)

    k, parcalar, ulasilan_pay = en_iyi

    # Kimlikleri yeniden numaralandır (okunabilirlik)
    for i, p in enumerate(parcalar):
        onek = "SIL" if p["sekil"] == "silindir" else "KUT"
        p["id"] = f"{onek}-{i + 1:03d}"

    return parcalar, k, ulasilan_pay


# ═══════════════════════════════════════════════════════════════════════════
# Sıkılık göstergeleri (danışman raporu Bölüm 3.2)
# ═══════════════════════════════════════════════════════════════════════════
def sikilik_hesapla(parcalar, filo):
    """T_V (hacim sıkılığı) ve T_W (ağırlık sıkılığı)."""
    filo_hacim = sum(a["genislik"] * a["uzunluk"] * a["yukseklik"] * a["adet"]
                     for a in filo)
    filo_kapasite = sum(a["kapasite_kg"] * a["adet"] for a in filo)

    yuk_hacim = sum(gercek_hacim(p) for p in parcalar)
    yuk_agirlik = sum(p["agirlik"] for p in parcalar)

    return {
        "T_V": yuk_hacim / filo_hacim if filo_hacim else 0.0,
        "T_W": yuk_agirlik / filo_kapasite if filo_kapasite else 0.0,
        "yuk_gercek_hacim_cm3": yuk_hacim,
        "yuk_bbox_hacim_cm3": sum(bbox_hacim(p) for p in parcalar),
        "filo_hacim_cm3": filo_hacim,
        "filo_kapasite_kg": filo_kapasite,
    }


def hacim_olcekle(parcalar, filo, hedef_TV):
    """
    Parça boyutlarını ortak bir katsayıyla ölçekleyerek hedef hacim sıkılığına
    (T_V) yaklaştırır. Şekil oranları korunur, dolayısıyla silindir hacim payı
    değişmez.
    """
    s = sikilik_hesapla(parcalar, filo)
    if s["T_V"] <= 0:
        return parcalar
    katsayi = (hedef_TV / s["T_V"]) ** (1.0 / 3.0)
    for p in parcalar:
        p["genislik"] = max(20, int(round(p["genislik"] * katsayi)))
        p["yukseklik"] = max(20, int(round(p["yukseklik"] * katsayi)))
        if p["sekil"] == "silindir":
            p["uzunluk"] = p["genislik"]      # çap eşitliği korunmalı
        else:
            p["uzunluk"] = max(20, int(round(p["uzunluk"] * katsayi)))
    return parcalar


# ═══════════════════════════════════════════════════════════════════════════
# Kaydetme
# ═══════════════════════════════════════════════════════════════════════════
def json_kaydet(yol, ornek):
    with open(yol, "w", encoding="utf-8") as f:
        json.dump(ornek, f, ensure_ascii=False, indent=2)


def xlsx_kaydet(yol, ornek):
    """LoadPlan Pro'nun içe aktarma formatında Excel yazar."""
    import openpyxl

    wb = openpyxl.Workbook()

    ws = wb.active
    ws.title = "Araçlar"
    ws.append(["ID", "Genişlik (cm)", "Uzunluk (cm)", "Yükseklik (cm)",
               "Kapasite (kg)", "Adet"])
    for a in ornek["filo"]:
        ws.append([a["id"], a["genislik"], a["uzunluk"], a["yukseklik"],
                   a["kapasite_kg"], a["adet"]])

    ws2 = wb.create_sheet("Yükler")
    ws2.append(["ID", "Şekil", "Genişlik (cm)", "Uzunluk (cm)", "Yükseklik (cm)",
                "Ağırlık (kg)", "Adet", "Müşteri", "Altına yerleştirilemez",
                "Üstüne yerleştirilemez", "Rotasyon", "Min. Aralık (cm)", "Öncelik"])
    for p in ornek["parcalar"]:
        ws2.append([
            p["id"],
            "Silindir" if p["sekil"] == "silindir" else "Dikdörtgen",
            p["genislik"], p["uzunluk"], p["yukseklik"],
            p["agirlik"], p["adet"], "", "HAYIR", "HAYIR", "EVET", 0, 0,
        ])

    for w, col in zip([16, 12, 14, 14, 15, 13, 8], "ABCDEFG"):
        ws.column_dimensions[col].width = w
        ws2.column_dimensions[col].width = w

    wb.save(yol)


# ═══════════════════════════════════════════════════════════════════════════
# Ana akış
# ═══════════════════════════════════════════════════════════════════════════
def main():
    ap = argparse.ArgumentParser(description="Pilot geometri veri seti üreteci")
    ap.add_argument("--config", default=VARSAYILAN_CONFIG)
    ap.add_argument("--taban-seed", type=int, default=7000,
                    help="Örnek üretimi için taban seed (koşum seed'lerinden ayrıdır)")
    args = ap.parse_args()

    with open(args.config, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    ucfg = config["ornek_uretimi"]
    filo = config["filo"]
    json_dizin = os.path.join(_DENEY, config["cikti"]["ornek_json_dizini"])
    xlsx_dizin = os.path.join(_DENEY, config["cikti"]["ornek_xlsx_dizini"])
    os.makedirs(json_dizin, exist_ok=True)
    os.makedirs(xlsx_dizin, exist_ok=True)

    paylar = ucfg["silindir_hacim_paylari"]
    tekrar = ucfg["seviye_basina_ornek"]
    hedef_TV = ucfg["hedef_hacim_sikiligi"]

    print("=" * 78)
    print("  PİLOT GEOMETRİ VERİ SETİ ÜRETİMİ")
    print("=" * 78)
    print(f"  Config      : {os.path.basename(args.config)}")
    print(f"  Seviye      : {len(paylar)} silindir payı × {tekrar} örnek "
          f"= {len(paylar) * tekrar} örnek")
    print(f"  Parça/örnek : {ucfg['parca_sayisi']}")
    print(f"  Hedef T_V   : {hedef_TV}")
    print(f"  Taban seed  : {args.taban_seed}")
    print("-" * 78)
    print(f"  {'Örnek':<26}{'Hedef':>8}{'Ulaşılan':>10}{'Silindir':>10}"
          f"{'T_V':>8}{'T_W':>8}")
    print("-" * 78)

    kayit = []
    for si, pay in enumerate(paylar):
        for r in range(tekrar):
            seed = args.taban_seed + si * 100 + r
            parcalar, k, _ = ornek_uret(pay, seed, ucfg)
            parcalar = hacim_olcekle(parcalar, filo, hedef_TV)

            ulasilan = silindir_hacim_payi(parcalar)
            sik = sikilik_hesapla(parcalar, filo)

            ad = f"geo_p{int(pay * 100):03d}_r{r + 1}"
            ornek = {
                "ornek_id": ad,
                "uretim_zamani": datetime.now().isoformat(timespec="seconds"),
                "config_dosyasi": os.path.basename(args.config),
                "seed": seed,
                "hedef_silindir_hacim_payi": pay,
                "ulasilan_silindir_hacim_payi": round(ulasilan, 4),
                "silindir_adedi": k,
                "parca_sayisi": len(parcalar),
                "sikilik": {kk: (round(vv, 4) if isinstance(vv, float) else vv)
                            for kk, vv in sik.items()},
                "filo": filo,
                "parcalar": parcalar,
            }

            json_kaydet(os.path.join(json_dizin, ad + ".json"), ornek)
            xlsx_kaydet(os.path.join(xlsx_dizin, ad + ".xlsx"), ornek)
            kayit.append(ornek)

            print(f"  {ad:<26}{pay:>8.2f}{ulasilan:>10.3f}{k:>10d}"
                  f"{sik['T_V']:>8.3f}{sik['T_W']:>8.3f}")

    ozet = os.path.join(json_dizin, "_ozet.json")
    with open(ozet, "w", encoding="utf-8") as f:
        json.dump([{
            "ornek_id": o["ornek_id"],
            "seed": o["seed"],
            "hedef_silindir_hacim_payi": o["hedef_silindir_hacim_payi"],
            "ulasilan_silindir_hacim_payi": o["ulasilan_silindir_hacim_payi"],
            "silindir_adedi": o["silindir_adedi"],
            "parca_sayisi": o["parca_sayisi"],
            "T_V": o["sikilik"]["T_V"],
            "T_W": o["sikilik"]["T_W"],
        } for o in kayit], f, ensure_ascii=False, indent=2)

    print("-" * 78)
    print(f"  TAMAM: {len(kayit)} örnek üretildi")
    print(f"     JSON : {json_dizin}")
    print(f"     Excel: {xlsx_dizin}")
    print(f"     Özet : {ozet}")
    print("=" * 78)


if __name__ == "__main__":
    main()
