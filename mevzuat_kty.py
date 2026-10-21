# -*- coding: utf-8 -*-
"""
Mevzuat — Karayolları Trafik Yönetmeliği (KTY) ağırlık ve boyut sınırları
=========================================================================
TEK RESMÎ KAYNAK. Yasal sınır değerlerinin kopyasını başka dosyalarda
TANIMLAMAYIN; her modül buradan import etmelidir.

Ana dayanak:
  KTY md. 128 (Değişik: RG 17/4/2015-29329), mevzuat.gov.tr güncel metin
  Yükleme Yönetmeliği (RG 8/11/2012-28461) md. 6, 7, 8

Her değer `Kural` nesnesinde kaynağıyla birlikte saklanır; böylece
arayüzde "40.000 kg — KTY md.128, 5+ dingil" gibi izlenebilir bir metin
gösterilebilir.

TEMEL İLKE: Yasal sınır ile teknik (föy/ruhsat) sınırın KÜÇÜĞÜ bağlar.
KTY md.128 bunu açıkça söylüyor: dingil kapasitesi daha yüksek olan
çekiciler için "karayolunda seyrederken azami dingil ağırlıkları ile
azami yüklü ağırlık değerleri aşılamaz."
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

KTY_KAYNAK = "KTY md.128 (Değişik: RG 17/4/2015-29329)"
YUKLEME_KAYNAK = "Yükleme Yönetmeliği (RG 8/11/2012-28461)"


# ─────────────────────────────────────────────────────────────────────────────
# Kaynaklı değer
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Kural:
    """Bir yasal sınır ve geldiği mevzuat satırı."""
    deger_kg: float
    kaynak: str

    def __str__(self) -> str:
        return f"{self.deger_kg:,.0f} kg — {self.kaynak}".replace(",", ".")


# ── Dingil ağırlıkları (KTY md.128) ─────────────────────────────────────────
TAHRIKLI_TEK_DINGIL = Kural(
    11_500, KTY_KAYNAK + ", tahrikli tek dingil")
TAHRIKSIZ_TEK_DINGIL = Kural(
    10_000, KTY_KAYNAK + ", tahriksiz tek dingil")

# ── İki ve üç dingilli grup sınırları ──────────────────────────────────────
# Aralık sınırlarının kapsayıcılığı iki tabloda FARKLI olduğu için tek bir
# genel tablo yürüyüşü yerine açık karşılaştırma kullanılıyor (bkz.
# _iki_dingilli_grup / _uc_dingilli_grup). KTY metnindeki aralıklar:
#   iki dingilli grup : d < 1,0 → 11 t · 1,0–1,3 → 16 t ·
#                       1,3–1,8 → 18 t · d ≥ 1,8 → 20 t
#   üç dingilli grup  : d ≤ 1,3 → 21 t · 1,3 < d ≤ 1,4 → 24 t
#
# ⚠ MEVZUAT BOŞLUĞU: üç dingilli grupta d > 1,4 m için KTY tablosunda değer
# YOK. Metin yalnız iki aralık veriyor (indirilen PDF'te de böyle).
# Uydurulmaz; föy değeri kullanılır ve kullanıcıya uyarı gösterilir.
UC_DINGIL_KTY_BOSLUGU = (
    "KTY md.128'de üç dingilli grup için d > 1,4 m aralığında değer yok. "
    "Föydeki dingil grubu izni kullanıldı — doğrulanmış bir yasal değer değil."
)

# ── Boyut sınırları (KTY md.128) ───────────────────────────────────────────
AZAMI_GENISLIK_MM = 2_550
AZAMI_GENISLIK_FRIGORIFIK_MM = 2_600   # yalnız frigorifik yapısında
AZAMI_YUKSEKLIK_MM = 4_000
AZAMI_UZUNLUK_YARI_ROMORKLU_MM = 16_500

# ── Tartı toleransı: BİLEREK KULLANILMIYOR ─────────────────────────────────
TARTI_TOLERANSI_NOTU = (
    f"{YUKLEME_KAYNAK} md.7: tartı toleransı = azami ağırlığın %3,75'i + 500 kg. "
    "BU DEĞER PLANLAMADA KULLANILMIYOR: ölçüm cihazı payıdır, yükleme hakkı "
    "değildir. Plan her zaman sınırın altında kalır."
)
BOYUT_TOLERANSI_NOTU = (
    f"{YUKLEME_KAYNAK} md.8: boyut ölçüm toleransı %2. Planlamada kullanılmıyor."
)
DINGIL_BAGIMSIZ_KURAL_NOTU = (
    f"{YUKLEME_KAYNAK} md.6(1)(b): ruhsattaki azami yüklü ağırlık aşılamaz; "
    "AŞILMASA BİLE dingil ağırlıkları aşılamaz. Dingil kontrolünün yasal dayanağı."
)


# ─────────────────────────────────────────────────────────────────────────────
# Yasal azami toplam ağırlık
# ─────────────────────────────────────────────────────────────────────────────

def yasal_toplam_agirlik(cekici_dingil_sayisi: int,
                         dorse_dingil_sayisi: int,
                         iso_40ft_konteyner: bool = False
                         ) -> Tuple[float, str, List[str]]:
    """
    Çekici + yarı römork kombinasyonu için yasal azami yüklü ağırlık.

    Args:
        cekici_dingil_sayisi: çekicinin dingil sayısı (4x2 → 2, 6x2/6x4 → 3)
        dorse_dingil_sayisi : dorsenin dingil sayısı
        iso_40ft_konteyner  : dorse 40 ft ISO konteyner taşıyor mu

    Returns:
        (deger_kg, kaynak_metni, uyarilar)

    44 t istisnası YALNIZCA iki koşul birlikteyse uygulanır:
      - konteyner bayrağı açık, VE
      - çekici 3 dingilli
    (KTY md.128: "40 ft ISO konteyner taşıyan 3 dingilli çekici + 2-3
     dingilli yarı römork → 44 t")
    """
    uyarilar: List[str] = []
    toplam_dingil = int(cekici_dingil_sayisi) + int(dorse_dingil_sayisi)

    # ── 44 t konteyner istisnası ────────────────────────────────────────
    if iso_40ft_konteyner:
        kosullar_tam = True
        if cekici_dingil_sayisi != 3:
            kosullar_tam = False
            uyarilar.append(
                f"40 ft ISO konteyner bayrağı açık, ancak çekici "
                f"{cekici_dingil_sayisi} dingilli. 44 t istisnası 3 dingilli "
                f"çekici gerektiriyor → uygulanmadı."
            )
        if not 2 <= dorse_dingil_sayisi <= 3:
            kosullar_tam = False
            uyarilar.append(
                f"40 ft ISO konteyner bayrağı açık, ancak dorse "
                f"{dorse_dingil_sayisi} dingilli. 44 t istisnası 2-3 dingilli "
                f"yarı römork gerektiriyor → uygulanmadı."
            )
        if kosullar_tam:
            return (44_000,
                    KTY_KAYNAK + ", 40 ft ISO konteyner + 3 dingilli çekici",
                    uyarilar)

    # ── Dingil sayısına göre toplam ─────────────────────────────────────
    if toplam_dingil <= 2:
        return (18_000, KTY_KAYNAK + ", 2 dingilli motorlu araç ve römork",
                uyarilar)
    if toplam_dingil == 3:
        return (28_000, KTY_KAYNAK + ", 3 dingilli yarı römorklu araç",
                uyarilar)
    if toplam_dingil == 4:
        # ⚠ KARAR BEKLİYOR (S12): KTY "4 dingilli römorklu/yarı römorklu
        # 36 t (yarı römork grubu 20 t ise 38 t)" diyor. 38 t'nin hangi
        # koşulda uygulanacağı henüz karara bağlanmadı → şimdilik 36 t.
        uyarilar.append(
            "4 dingilli kombinasyon: KTY md.128 'yarı römork grubu 20 t ise "
            "38 t' diyor. Bu istisnanın uygulanması henüz karara bağlanmadı "
            "(S12) → 36 t kullanıldı."
        )
        return (36_000, KTY_KAYNAK + ", 4 dingilli yarı römorklu araç",
                uyarilar)
    return (40_000, KTY_KAYNAK + ", 5+ dingilli yarı römorklu araç", uyarilar)


# ─────────────────────────────────────────────────────────────────────────────
# Dingil ve dingil grubu sınırları
# ─────────────────────────────────────────────────────────────────────────────

def tek_dingil_siniri(tahrikli: bool) -> Kural:
    """Tek dingil yasal sınırı."""
    return TAHRIKLI_TEK_DINGIL if tahrikli else TAHRIKSIZ_TEK_DINGIL


def _iki_dingilli_grup(aralik_mm: float) -> Kural:
    """İki dingilli grup (römork / yarı römork), KTY md.128."""
    if aralik_mm < 1_000:
        return Kural(11_000, KTY_KAYNAK + ", iki dingilli grup, d < 1,0 m")
    if aralik_mm <= 1_300:
        return Kural(16_000, KTY_KAYNAK + ", iki dingilli grup, 1,0 ≤ d ≤ 1,3 m")
    if aralik_mm < 1_800:
        return Kural(18_000, KTY_KAYNAK + ", iki dingilli grup, 1,3 < d < 1,8 m")
    return Kural(20_000, KTY_KAYNAK + ", iki dingilli grup, d ≥ 1,8 m")


def _uc_dingilli_grup(aralik_mm: float) -> Optional[Kural]:
    """Üç dingilli grup (dorsenin tridemi), KTY md.128.

    d > 1,4 m → None (KTY'de değer yok, bkz. UC_DINGIL_KTY_BOSLUGU).
    Sınır noktaları: tam 1.300 mm → 21 t, tam 1.400 mm → 24 t.
    """
    if aralik_mm <= 1_300:
        return Kural(21_000, KTY_KAYNAK + ", üç dingilli grup, d ≤ 1,3 m")
    if aralik_mm <= 1_400:
        return Kural(24_000, KTY_KAYNAK + ", üç dingilli grup, 1,3 < d ≤ 1,4 m")
    return None


def dingil_grubu_siniri(dingil_sayisi: int,
                        aralik_mm: Optional[float]
                        ) -> Tuple[Optional[float], str, List[str]]:
    """
    Dorsenin dingil grubu için yasal sınır.

    Returns:
        (deger_kg | None, kaynak_metni, uyarilar)
        None → KTY'de bu durum için doğrulanmış değer yok; föy değeri
        kullanılmalı (uydurulmaz).
    """
    uyarilar: List[str] = []
    n = int(dingil_sayisi)

    if n <= 0:
        return (None, "geçersiz dingil sayısı", ["Dingil sayısı 0 veya negatif."])

    if n == 1:
        k = TAHRIKSIZ_TEK_DINGIL
        return (k.deger_kg, k.kaynak, uyarilar)

    if aralik_mm is None:
        return (None, "dingil aralığı girilmedi",
                [f"{n} dingilli grup için dingil aralığı girilmedi → KTY "
                 f"tablosundan sınır belirlenemedi; föy değeri kullanılmalı."])

    if n == 2:
        k = _iki_dingilli_grup(aralik_mm)
    elif n == 3:
        k = _uc_dingilli_grup(aralik_mm)
        if k is None:
            return (None, "KTY'de değer yok", [UC_DINGIL_KTY_BOSLUGU])
    else:
        return (None, "KTY'de değer yok",
                [f"KTY md.128'de {n} dingilli grup için tablo değeri yok. "
                 f"Föydeki dingil grubu izni kullanıldı."])

    if k is None:
        return (None, "KTY'de değer yok",
                [f"{n} dingilli grup, d = {aralik_mm:.0f} mm için KTY "
                 f"tablosunda değer bulunamadı."])
    return (k.deger_kg, k.kaynak, uyarilar)


def kucugunu_uygula(yasal_kg: Optional[float], yasal_kaynak: str,
                    teknik_kg: Optional[float], teknik_kaynak: str = "föy"
                    ) -> Tuple[Optional[float], str, List[str]]:
    """
    min(yasal, teknik) — her sınır için geçerli temel ilke.

    Returns:
        (deger | None, bağlayan sınırın kaynağı, uyarilar)
    """
    uyarilar: List[str] = []
    if yasal_kg is None and teknik_kg is None:
        return (None, "veri yok",
                ["Ne yasal ne teknik sınır bilinmiyor."])
    if yasal_kg is None:
        return (teknik_kg, teknik_kaynak, uyarilar)
    if teknik_kg is None:
        return (yasal_kg, yasal_kaynak, uyarilar)
    if teknik_kg < yasal_kg:
        return (teknik_kg, teknik_kaynak, uyarilar)
    return (yasal_kg, yasal_kaynak, uyarilar)


# ─────────────────────────────────────────────────────────────────────────────
# Boyut kontrolü
# ─────────────────────────────────────────────────────────────────────────────

def boyut_kontrolu(dis_genislik_mm: Optional[float] = None,
                   dis_yukseklik_mm: Optional[float] = None,
                   katar_uzunluk_mm: Optional[float] = None,
                   frigorifik: bool = False) -> Tuple[List[str], List[str]]:
    """
    KTY md.128 boyut sınırları. DIŞ ölçülere uygulanır.

    NOT: Yükleme planı aracın dış ölçüsünü değiştirmez; bu kontrol aracın
    kendisine ait bir uygunluk kontrolüdür, planın çıktısını etkilemez.

    Returns:
        (ihlaller, yapilmayan_kontroller)
    """
    ihlaller: List[str] = []
    yapilmayan: List[str] = []

    if dis_genislik_mm is None:
        yapilmayan.append("genişlik — dış ölçü girilmedi")
    else:
        sinir = (AZAMI_GENISLIK_FRIGORIFIK_MM if frigorifik
                 else AZAMI_GENISLIK_MM)
        etiket = "frigorifik yapı" if frigorifik else "genel"
        if dis_genislik_mm > sinir:
            ihlaller.append(
                f"Genişlik {dis_genislik_mm:.0f} mm > {sinir} mm "
                f"({KTY_KAYNAK}, {etiket})")

    if dis_yukseklik_mm is None:
        yapilmayan.append("yükseklik — dış ölçü girilmedi")
    elif dis_yukseklik_mm > AZAMI_YUKSEKLIK_MM:
        ihlaller.append(
            f"Yükseklik {dis_yukseklik_mm:.0f} mm > {AZAMI_YUKSEKLIK_MM} mm "
            f"({KTY_KAYNAK})")

    if katar_uzunluk_mm is None:
        yapilmayan.append("uzunluk — katar dış uzunluğu girilmedi")
    elif katar_uzunluk_mm > AZAMI_UZUNLUK_YARI_ROMORKLU_MM:
        ihlaller.append(
            f"Yarı römorklu araç uzunluğu {katar_uzunluk_mm:.0f} mm > "
            f"{AZAMI_UZUNLUK_YARI_ROMORKLU_MM} mm ({KTY_KAYNAK})")

    return ihlaller, yapilmayan
