# -*- coding: utf-8 -*-
"""
BENCHMARK OKUYUCU — OR-Library "thpack" veri setleri
=====================================================
Kaynak: J.E. Beasley, OR-Library (Brunel Üniversitesi)
        people.brunel.ac.uk/~mastjjb/jeb/orlib/thpackinfo.html
Katkıda bulunan: M.S.W. Ratcliff

DOSYALAR
--------
thpack1-7 : Bischoff & Ratcliff (1995) — TEK konteyner, doluluğu en çoklama.
            Her dosyada 100 problem. Kutu tipi çeşitliliği thpack1'den 7'ye
            doğru artar (zayıf → güçlü heterojen).
thpack8   : Loh & Nee (1992) — tek konteyner.
thpack9   : Ivancic, Mathur & Mohanty (1989) — ÇOKLU konteyner, konteyner
            sayısını en azlama. Bu çalışmanın problem tipiyle (girdi en azlama)
            birebir örtüşen tek settir.

DOSYA BİÇİMİ
------------
    <problem sayısı>
    <problem no> <seed>              (thpack8-9'da seed yok)
    <uzunluk> <genişlik> <yükseklik> (konteyner)
    <kutu tipi sayısı>
    <tip no> <b1> <f1> <b2> <f2> <b3> <f3> <adet>   ← her kutu tipi için

    b1,b2,b3 : kutunun üç boyutu
    f1,f2,f3 : 0/1 — o boyutun DİKEY eksende durmasına izin var mı

ÖNEMLİ SADELEŞTİRME
-------------------
Bu depodaki yerleştirme motoru, boyut bazında dikey yönelim bayrağını
desteklemiyor; yalnızca "XY düzleminde 90° dönebilir mi" (allow_rotation_xy)
bilgisini kullanıyor. Bu nedenle bayraklar şöyle eşlenir:
    allow_rotation_xy = True  (her zaman)
    dikey yönelim kısıtı      = UYGULANMIYOR
Bu sadeleştirme, bayrakların kısıtlayıcı olduğu örneklerde bizim lehimize
çalışır; sonuç raporlanırken AÇIKÇA belirtilmelidir.

Çalıştırma:
    python deney/scripts/benchmark_yukle.py --ozet
    python deney/scripts/benchmark_yukle.py --dosya thpack1 --problem 1 --goster
"""

import argparse
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_DENEY = os.path.dirname(_HERE)
_ROOT = os.path.dirname(_DENEY)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from core_3d import Piece3D, Truck3D  # noqa: E402

HAM_DIZIN = os.path.join(_DENEY, "benchmark", "ham")

# Hangi dosya hangi problem tipinde?
DOSYA_BILGI = {
    "thpack1": ("Bischoff & Ratcliff (1995)", "tek", "BR1 — 3 kutu tipi (zayıf heterojen)"),
    "thpack2": ("Bischoff & Ratcliff (1995)", "tek", "BR2 — 5 kutu tipi"),
    "thpack3": ("Bischoff & Ratcliff (1995)", "tek", "BR3 — 8 kutu tipi"),
    "thpack4": ("Bischoff & Ratcliff (1995)", "tek", "BR4 — 10 kutu tipi"),
    "thpack5": ("Bischoff & Ratcliff (1995)", "tek", "BR5 — 12 kutu tipi"),
    "thpack6": ("Bischoff & Ratcliff (1995)", "tek", "BR6 — 15 kutu tipi"),
    "thpack7": ("Bischoff & Ratcliff (1995)", "tek", "BR7 — 20 kutu tipi (güçlü heterojen)"),
    "thpack8": ("Loh & Nee (1992)", "tek", "LN — tek konteyner"),
    "thpack9": ("Ivancic, Mathur & Mohanty (1989)", "coklu",
                "IMM — ÇOKLU konteyner, konteyner sayısını en azlama"),
}


# ═══════════════════════════════════════════════════════════════════════════
# Ayrıştırma
# ═══════════════════════════════════════════════════════════════════════════
def _sayilar(satir):
    return [int(x) for x in satir.split()]


# Kaynak dosyadaki biçim bozukluklarının kaydı (raporlanmak üzere).
BICIM_UYARILARI = []


def _kutu_satiri_coz(v, dosya_adi, satir_no):
    """
    Bir kutu tipi satırını çözer: [tip, b1, f1, b2, f2, b3, f3, adet]

    thpack9 dosyasında ÜÇ satırda bir bayrak eksiktir (8 yerine 7 sayı):
        "3 6 1 9 12 1 20"   (problem 18, 19 ve 20'de aynı satır)
    Bu, OR-Library kaynak dosyasındaki bir biçim hatasıdır.

    Eksik değer sessizce tamamlanmaz: alternasyonu (boyut, bayrak, boyut,
    bayrak, boyut, bayrak) bozmayan tek konum bulunur, oraya bayrak 1
    yerleştirilir ve durum BICIM_UYARILARI listesine kaydedilir.
    Komşu satırlarda tüm bayraklar 1 olduğu için bu yeniden kurulum
    veriyle tutarlıdır.
    """
    if len(v) == 8:
        return v

    if len(v) == 7:
        tip, adet = v[0], v[-1]
        orta = v[1:-1]                      # 5 değer; 6 olmalı
        adaylar = []
        for konum in range(len(orta) + 1):
            deneme = orta[:konum] + [1] + orta[konum:]
            boyutlar = deneme[0::2]
            bayraklar = deneme[1::2]
            if all(b > 1 for b in boyutlar) and all(f in (0, 1) for f in bayraklar):
                adaylar.append((konum, deneme))
        if len(adaylar) == 1:
            konum, deneme = adaylar[0]
            BICIM_UYARILARI.append(
                f"{dosya_adi} satır {satir_no}: 7 sayı bulundu (8 bekleniyordu). "
                f"'{' '.join(map(str, v))}' → eksik bayrak {konum + 1}. konuma "
                f"1 olarak eklendi."
            )
            return [tip] + deneme + [adet]
        raise SystemExit(
            f"{dosya_adi} satır {satir_no}: bozuk kutu satırı tek biçimde "
            f"onarılamadı ({len(adaylar)} olası yorum): {v}"
        )

    raise SystemExit(f"{dosya_adi} satır {satir_no}: beklenmeyen sayı adedi "
                     f"({len(v)}): {v}")


def dosya_oku(dosya_adi):
    """
    Bir thpack dosyasını okur ve problem listesi döndürür.

    Her problem:
      {
        "no": int, "seed": int|None,
        "konteyner": (uzunluk, genislik, yukseklik),
        "kutu_tipleri": [ {"tip":int, "boyutlar":(b1,b2,b3),
                           "bayraklar":(f1,f2,f3), "adet":int}, ... ]
      }
    """
    yol = os.path.join(HAM_DIZIN, dosya_adi + ".txt")
    if not os.path.exists(yol):
        raise SystemExit(f"Dosya yok: {yol}")

    with open(yol, encoding="utf-8") as f:
        satirlar = [s for s in (x.strip() for x in f) if s]

    i = 0
    problem_sayisi = _sayilar(satirlar[i])[0]
    i += 1

    seedli = dosya_adi not in ("thpack8", "thpack9")
    problemler = []

    for _ in range(problem_sayisi):
        bas = _sayilar(satirlar[i]); i += 1
        no = bas[0]
        seed = bas[1] if (seedli and len(bas) > 1) else None

        konteyner = tuple(_sayilar(satirlar[i])[:3]); i += 1
        tip_sayisi = _sayilar(satirlar[i])[0]; i += 1

        tipler = []
        for _ in range(tip_sayisi):
            v = _kutu_satiri_coz(_sayilar(satirlar[i]), dosya_adi, i); i += 1
            tipler.append({
                "tip": v[0],
                "boyutlar": (v[1], v[3], v[5]),
                "bayraklar": (v[2], v[4], v[6]),
                "adet": v[7],
            })

        problemler.append({
            "no": no, "seed": seed,
            "konteyner": konteyner,
            "kutu_tipleri": tipler,
        })

    return problemler


# ═══════════════════════════════════════════════════════════════════════════
# Dönüştürme
# ═══════════════════════════════════════════════════════════════════════════
def probleme_donustur(problem, arac_adedi=1, arac_kapasitesi=10**9):
    """
    Bir benchmark problemini (pieces, trucks) ikilisine çevirir.

    arac_adedi:
      thpack1-8 (tek konteyner) için 1.
      thpack9 (çoklu konteyner) için, gereken en fazla konteyner sayısından
      büyük bir değer verilmelidir (alt sınır hesabıyla belirlenebilir).

    Ağırlık kısıtı benchmark'ta yoktur; kapasite bilerek çok yüksek verilir
    ki ağırlık bağlayıcı olmasın (bkz. danışman raporu Bölüm 3.2).
    """
    L, W, H = problem["konteyner"]
    trucks = [Truck3D(id="BENCH", width=W, length=L, height=H,
                      capacity=arac_kapasitesi, available=arac_adedi)]

    pieces = []
    for t in problem["kutu_tipleri"]:
        b1, b2, b3 = t["boyutlar"]
        for k in range(t["adet"]):
            pieces.append(Piece3D(
                id=f"t{t['tip']}-{k+1:03d}",
                width=b2, length=b1, height=b3,   # (genişlik, uzunluk, yükseklik)
                quantity=1, weight=0.0, shape="box",
                allow_rotation_xy=True,
            ))
    return pieces, trucks


def problem_hacimleri(problem):
    """Kutuların toplam hacmi ve konteyner hacmi."""
    L, W, H = problem["konteyner"]
    kutu_hacim = sum(
        t["boyutlar"][0] * t["boyutlar"][1] * t["boyutlar"][2] * t["adet"]
        for t in problem["kutu_tipleri"]
    )
    return kutu_hacim, L * W * H


# ═══════════════════════════════════════════════════════════════════════════
# Özet
# ═══════════════════════════════════════════════════════════════════════════
def ozet_yazdir():
    print("=" * 92)
    print("  OR-LIBRARY BENCHMARK ÖZETİ")
    print("=" * 92)
    print(f"  {'Dosya':<10}{'Problem':>9}{'Kutu tipi':>12}{'Ort. parça':>12}"
          f"{'Konteyner':>16}{'Yük/Kont.':>11}   Kaynak")
    print("  " + "-" * 88)

    for ad, (kaynak, tip, aciklama) in DOSYA_BILGI.items():
        try:
            ps = dosya_oku(ad)
        except SystemExit:
            print(f"  {ad:<10}  (dosya yok)")
            continue

        tip_sayilari = [len(p["kutu_tipleri"]) for p in ps]
        parca_sayilari = [sum(t["adet"] for t in p["kutu_tipleri"]) for p in ps]
        oranlar = []
        for p in ps:
            kh, koh = problem_hacimleri(p)
            oranlar.append(kh / koh if koh else 0)

        konteynerler = {p["konteyner"] for p in ps}
        knt = (f"{list(konteynerler)[0]}" if len(konteynerler) == 1
               else f"{len(konteynerler)} farklı")

        tip_araligi = (f"{min(tip_sayilari)}"
                       if min(tip_sayilari) == max(tip_sayilari)
                       else f"{min(tip_sayilari)}-{max(tip_sayilari)}")
        print(f"  {ad:<10}{len(ps):>9}{tip_araligi:>12}"
              f"{sum(parca_sayilari)/len(parca_sayilari):>12.0f}"
              f"{knt:>16}"
              f"{sum(oranlar)/len(oranlar):>11.2f}   {kaynak}")

    print("  " + "-" * 88)
    print("  'Yük/Kont.' = kutuların toplam hacmi ÷ konteyner hacmi.")
    print("  Bu oran 1'e yakınsa problem tek konteynere ancak kusursuz yerleşimle sığar;")
    print("  1'i aşıyorsa birden fazla konteyner zorunludur.")

    if BICIM_UYARILARI:
        print()
        print("  ⚠ KAYNAK DOSYA BİÇİM UYARILARI (raporda belirtilmelidir):")
        for u in dict.fromkeys(BICIM_UYARILARI):
            print(f"    - {u}")
    print("=" * 92)


def problem_goster(dosya, no):
    ps = dosya_oku(dosya)
    p = next((x for x in ps if x["no"] == no), None)
    if p is None:
        raise SystemExit(f"{dosya} içinde {no} numaralı problem yok "
                         f"(1..{len(ps)} arası).")
    kh, koh = problem_hacimleri(p)
    kaynak, tip, aciklama = DOSYA_BILGI[dosya]

    print("=" * 78)
    print(f"  {dosya} — problem {p['no']}")
    print("=" * 78)
    print(f"  Kaynak        : {kaynak}")
    print(f"  Açıklama      : {aciklama}")
    print(f"  Problem tipi  : {'ÇOKLU konteyner' if tip == 'coklu' else 'TEK konteyner'}")
    print(f"  Seed          : {p['seed']}")
    print(f"  Konteyner     : {p['konteyner']} (uzunluk × genişlik × yükseklik)")
    print(f"  Konteyner hac.: {koh:,}")
    print(f"  Kutu tipi     : {len(p['kutu_tipleri'])}")
    print(f"  Toplam parça  : {sum(t['adet'] for t in p['kutu_tipleri'])}")
    print(f"  Kutu hacmi    : {kh:,}")
    print(f"  Yük / Konteyner oranı: {kh/koh:.3f}")
    print("-" * 78)
    print(f"  {'Tip':>4}{'Boyutlar':>18}{'Dikey bayraklar':>18}{'Adet':>7}")
    for t in p["kutu_tipleri"]:
        print(f"  {t['tip']:>4}{str(t['boyutlar']):>18}"
              f"{str(t['bayraklar']):>18}{t['adet']:>7}")
    print("=" * 78)


def main():
    ap = argparse.ArgumentParser(description="OR-Library thpack okuyucu")
    ap.add_argument("--ozet", action="store_true", help="tüm dosyaların özeti")
    ap.add_argument("--dosya", default=None, help="örn. thpack1")
    ap.add_argument("--problem", type=int, default=1)
    ap.add_argument("--goster", action="store_true")
    args = ap.parse_args()

    if args.ozet or not args.dosya:
        ozet_yazdir()
    if args.dosya and args.goster:
        problem_goster(args.dosya, args.problem)


if __name__ == "__main__":
    main()
