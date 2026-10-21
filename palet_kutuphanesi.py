# -*- coding: utf-8 -*-
"""
Standart palet kütüphanesi — kaynağa dayalı
============================================
TEK RESMÎ KAYNAK. Palet ölçülerinin kopyasını başka dosyalarda
TANIMLAMAYIN; arayüz ve testler buradan import etmelidir.

Kurallar:
  * Bilinmeyen değer **None**'dır. Asla tahmini değer yazılmaz.
  * Her kaydın `kaynak` ve `dogrulama_durumu` alanı vardır; böylece
    "bu sayı nereden geliyor" sorusu her zaman cevaplanabilir.
  * Ölçüler **mm**; arayüz cm ile çalıştığı için dönüşüm
    `olculer_cm()` ile yapılır ve **aşağı yuvarlanır** (karar S-C):
    palet hiçbir zaman gerçeğinden büyük görünmez.

UYGULAMADAKİ PALET KAVRAMI — dikkat:
  LoadPlan Pro paleti "yerleştirilecek parça" olarak modelliyor ve
  **yüklü paleti tek bir kutu** sayıyor (varsayılan satır "Euro-1":
  80×120×140 cm, 250 kg → 140 cm palet + üstündeki yükün TOPLAMI).
  Bu yüzden kütüphanedeki yükseklik (144 mm) ve ağırlık (25 kg) BOŞ
  paletindir ve doğrudan forma yazılmaz. Kullanıcı paletin ÜSTÜNDEKİ
  yükün yüksekliğini ve ağırlığını girer; palet darası `toplam_*`
  fonksiyonlarıyla otomatik EKLENİR (karar S-A).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

# mm → cm dönüşümünün TEK tanımı filo_havuzu'ndadır (aşağı yuvarlama,
# karar S10). Burada kopyası tanımlanmıyor ki iki yerde ayrışmasın.
from filo_havuzu import mm_to_cm

KAYNAK_EUR = "UIC 435-2 / EPAL (EUR paleti)"
KAYNAK_ISO = "ISO 6780:2003"

DOGRULAMA_EUR = "ikincil kaynak; EPAL resmî föyünden teyit edilecek"
DOGRULAMA_ISO = ("taban ölçüleri ikincil kaynakla doğrulandı; "
                 "standart metni paralı")


@dataclass(frozen=True)
class Palet:
    """Standart palet kaydı. Bilinmeyen alanlar None."""
    kod: str
    ad: str
    uzunluk_mm: float
    genislik_mm: float
    yukseklik_mm: Optional[float]
    bos_agirlik_kg: Optional[float]
    dinamik_yuk_kg: Optional[float]
    statik_yuk_kg: Optional[float]
    kaynak: str
    dogrulama_durumu: str

    @property
    def taban_metni(self) -> str:
        return f"{self.uzunluk_mm:.0f} × {self.genislik_mm:.0f} mm"

    @property
    def eksik_alanlar(self) -> List[str]:
        eksik = []
        for ad in ("yukseklik_mm", "bos_agirlik_kg",
                   "dinamik_yuk_kg", "statik_yuk_kg"):
            if getattr(self, ad) is None:
                eksik.append(ad)
        return eksik


# ─────────────────────────────────────────────────────────────────────────────
# Kayıtlar — bu listenin dışında araç/palet UYDURULMAZ
# ─────────────────────────────────────────────────────────────────────────────

PALETLER: Tuple[Palet, ...] = (
    Palet(
        kod="EUR",
        ad="EUR / EPAL 1",
        uzunluk_mm=1200.0,
        genislik_mm=800.0,
        yukseklik_mm=144.0,
        bos_agirlik_kg=25.0,        # föyde "~25 kg" — bkz. dogrulama_durumu
        dinamik_yuk_kg=1500.0,
        statik_yuk_kg=4000.0,
        kaynak=KAYNAK_EUR,
        dogrulama_durumu=DOGRULAMA_EUR + "; boş ağırlık kaynakta '~25 kg'",
    ),
    # ── ISO 6780:2003 taban ölçüleri ────────────────────────────────────
    # Standart yalnız TABAN ölçüsü veriyor; yükseklik, ağırlık ve yük
    # kapasitesi paletin üreticisine göre değişir → None bırakıldı.
    Palet("ISO-1200x1000", "ISO 6780 — 1200 × 1000",
          1200.0, 1000.0, None, None, None, None, KAYNAK_ISO, DOGRULAMA_ISO),
    Palet("ISO-1219x1016", "ISO 6780 — 1219 × 1016 (48 × 40 inç)",
          1219.0, 1016.0, None, None, None, None, KAYNAK_ISO, DOGRULAMA_ISO),
    Palet("ISO-1165x1165", "ISO 6780 — 1165 × 1165",
          1165.0, 1165.0, None, None, None, None, KAYNAK_ISO, DOGRULAMA_ISO),
    Palet("ISO-1067x1067", "ISO 6780 — 1067 × 1067",
          1067.0, 1067.0, None, None, None, None, KAYNAK_ISO, DOGRULAMA_ISO),
    Palet("ISO-1100x1100", "ISO 6780 — 1100 × 1100",
          1100.0, 1100.0, None, None, None, None, KAYNAK_ISO, DOGRULAMA_ISO),
)


def tum_paletler() -> List[Palet]:
    return list(PALETLER)


def palet_bul(kod: str) -> Optional[Palet]:
    for p in PALETLER:
        if p.kod == kod:
            return p
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Arayüz için dönüşümler
# ─────────────────────────────────────────────────────────────────────────────

def olculer_cm(palet: Palet) -> Tuple[int, int]:
    """
    Taban ölçüsü (genislik_cm, uzunluk_cm) — AŞAĞI yuvarlanır (karar S-C).

    Örnek: ISO 1219 × 1016 mm → 121 × 101 cm. En yakına yuvarlansaydı
    122 × 102 olur ve palet gerçeğinden ~4 mm büyük görünürdü; yerleştirme
    motoru tam cm ile çalıştığı için bu aracın içine sığmayan bir plan
    üretebilirdi.
    """
    return mm_to_cm(palet.genislik_mm), mm_to_cm(palet.uzunluk_mm)


def palet_yuksekligi_cm(palet: Palet) -> Optional[float]:
    """Boş paletin yüksekliği (cm). Bilinmiyorsa None."""
    if palet.yukseklik_mm is None:
        return None
    return palet.yukseklik_mm / 10.0


def toplam_yukseklik_cm(palet: Palet, yuk_yuksekligi_cm: float
                        ) -> Tuple[float, str, List[str]]:
    """
    Paletin ÜSTÜNDEKİ yükün yüksekliğine palet darasını ekler (karar S-A).

    Returns:
        (toplam_cm, hesap_aciklamasi, uyarilar)
    """
    uyarilar: List[str] = []
    palet_cm = palet_yuksekligi_cm(palet)
    if palet_cm is None:
        uyarilar.append(
            f"{palet.ad}: paletin kendi yüksekliği bu standartta verilmiyor "
            f"→ eklenemedi. Girdiğiniz değer TOPLAM yükseklik sayılıyor.")
        return (float(yuk_yuksekligi_cm),
                f"{yuk_yuksekligi_cm:.1f} cm (yalnız yük — palet yüksekliği "
                f"bilinmiyor)", uyarilar)

    toplam = float(yuk_yuksekligi_cm) + palet_cm
    return (toplam,
            f"{toplam:.1f} cm = {yuk_yuksekligi_cm:.1f} (yük) + "
            f"{palet_cm:.1f} (palet)", uyarilar)


def toplam_agirlik_kg(palet: Palet, yuk_agirligi_kg: float
                      ) -> Tuple[float, str, List[str]]:
    """
    Paletin ÜSTÜNDEKİ yükün ağırlığına palet darasını ekler (karar S-A).

    Returns:
        (toplam_kg, hesap_aciklamasi, uyarilar)
    """
    uyarilar: List[str] = []
    if palet.bos_agirlik_kg is None:
        uyarilar.append(
            f"{palet.ad}: paletin boş ağırlığı bu standartta verilmiyor "
            f"→ eklenemedi. Girdiğiniz değer TOPLAM ağırlık sayılıyor.")
        return (float(yuk_agirligi_kg),
                f"{yuk_agirligi_kg:.1f} kg (yalnız yük — palet ağırlığı "
                f"bilinmiyor)", uyarilar)

    toplam = float(yuk_agirligi_kg) + float(palet.bos_agirlik_kg)
    return (toplam,
            f"{toplam:.1f} kg = {yuk_agirligi_kg:.1f} (yük) + "
            f"{palet.bos_agirlik_kg:.1f} (palet)", uyarilar)


def istif_limiti_kg(palet: Palet) -> Optional[float]:
    """
    Bu paletin üstüne konabilecek azami ağırlık (karar S-B).

    `Piece3D.max_stack_weight` buradan doldurulur. Dinamik yük seçilir:
    istiflemede palet hareket hâlinde yük taşır (forklift/taşıma), statik
    yük yalnız sabit depolamada geçerlidir — daha güvenli olan dinamiktir.
    Bilinmiyorsa None → uygulamanın bugünkü varsayılanı (1000 kg) kalır.
    """
    return palet.dinamik_yuk_kg


def istif_limiti_oku(deger) -> Optional[float]:
    """
    Yük Listesi'ndeki "İstif limiti (kg)" hücresini okur.

    Boş, sıfır, negatif, "nan" ya da sayıya çevrilemeyen değer → None
    demektir: o parçada uygulamanın bugünkü varsayılanı
    (`Piece3D.max_stack_weight` = 1000 kg) korunur, yani eski davranış
    değişmez. Ayrı bir fonksiyon olmasının nedeni test edilebilirliktir;
    `app_3d.build_pieces_from_load_rules` bunu çağırır.
    """
    if deger is None:
        return None
    if isinstance(deger, bool):
        return None
    try:
        sayi = float(deger)
    except (TypeError, ValueError):
        return None
    if sayi != sayi:          # NaN
        return None
    return sayi if sayi > 0 else None


def bilgi_notu(palet: Palet) -> str:
    """Arayüzde paletin yanında gösterilecek kısa kaynak notu."""
    parcalar = [f"**{palet.ad}** — taban {palet.taban_metni}"]
    if palet.yukseklik_mm is not None:
        parcalar.append(f"palet yüksekliği {palet.yukseklik_mm:.0f} mm")
    if palet.bos_agirlik_kg is not None:
        parcalar.append(f"boş ağırlık {palet.bos_agirlik_kg:.0f} kg")
    if palet.dinamik_yuk_kg is not None:
        parcalar.append(f"dinamik yük {palet.dinamik_yuk_kg:.0f} kg")
    if palet.statik_yuk_kg is not None:
        parcalar.append(f"statik yük {palet.statik_yuk_kg:.0f} kg")
    metin = " · ".join(parcalar)
    return (f"{metin}\n\nKaynak: {palet.kaynak} — "
            f"*{palet.dogrulama_durumu}*")
