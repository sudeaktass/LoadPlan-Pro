# -*- coding: utf-8 -*-
"""
Ağırlık dağılımı ölçüleri — TEK RESMÎ KAYNAK (1. adım: ÖLÇ)
===========================================================
Bu modül YALNIZCA ÖLÇER ve RAPORLAR. Hiçbir algoritmanın davranışını
değiştirmez, hiçbir amaç fonksiyonuna girmez. Amacı, "ağırlık merkezi
şu an ne kadar kötü?" sorusunu sayıyla cevaplamak — sonradan dengeleme
(2. adım) uygulanınca önce/sonra karşılaştırması yapılabilsin diye.

Ölçüler (hepsi CM cinsinden — yüzde değil):
  sapma_y   : Ağırlık merkezinin BİZİM hedefimize uzaklığı.
              Hedef = araç boyunun ön %40'ı (core_3d.COG_FRONT_BIAS).
              Yarı römorkta bu nokta kingpin ile dingil grubunun ortasıdır.
  sapma_orta: Ağırlık merkezinin araç boyunun TAM ORTASINA uzaklığı.
              Literatürle karşılaştırmak için — Davies & Bischoff (1999)
              ölçüsünü bu noktaya göre verir.
  sapma_x   : Yanal (sol/sağ) sapma; hedef her iki tanımda da genişliğin
              ortasıdır.
  cog_z     : Ağırlık merkezinin zeminden yüksekliği.

Yayılma (kümelenme) ölçüsü:
  Yük, araç boyunca METRE dilimlerine bölünür. Her parçanın ağırlığı,
  kendi y uzunluğu boyunca DÜZGÜN yayılmış sayılır (kütle noktası gibi
  tek bir metreye yığılmaz) — yük dağılım planlarındaki "metre başına kg"
  mantığı budur.
  yogunlasma = en ağır metre ÷ (toplam yük ÷ metre sayısı)
               1,0 = tam düzgün dağılmış · büyüdükçe kümelenme artar.

Bölüm sayısı:
  Yerleşimin, hiçbir parçanın kesmediği y düzlemlerinden kaç ayrık
  bölüme (blok/duvar) ayrıldığı. 2. ADIMIN ÖN KOŞULU BUDUR: Davies &
  Bischoff'un yöntemi blokların sırasını değiştirip aynalayarak çalışır;
  tek bölüm varsa takas edecek bir şey yoktur. Burada ölçülüyor ki
  2. adıma geçmeden önce uygulanabilir mi bilelim.

Dayanak:
  Davies, A.P. & Bischoff, E.E. (1999). "Weight distribution considerations
    in container loading." EJOR 114(3), 509-527.
    - Ölçü: ağırlık merkezinin konteyner boyunun orta noktasına CM
      cinsinden uzaklığı.
    - Kümelenme: az kutu çeşidinde aynı tipten kutular yan yana düşüyor,
      "çok ağır ya da çok hafif kutu kümeleri" oluşuyor.
    - Blokları araç boyuna YAYMAK dengeyi düzeltir ama "daha kararsız
      yerleşimlere yol açar" — bu yüzden yayma değil, SIRA DEĞİŞTİRME.
    - Sonuçları: dengelemeden önce ortalama 77-122 cm; sonra kutu çeşidi
      arttıkça 17,8 → 10,7 → 4,7 → 1,3 → 0,0 cm.
  Trivella, A. & Pisinger, D. (2016). COR 74, 152-164.
    - Ağırlık merkezi sapması L1 normuyla (eksen başına mutlak fark)
      ölçülür; biz de eksenleri ayrı ayrı veriyoruz.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

METRE_CM = 100          # Bir "metre dilimi" kaç cm

ACIKLAMA_NOTU = (
    "Sapmalar **cm** cinsindendir. **Hedef**: araç boyunun ön %40'ı "
    "(kingpin ile dingil grubunun ortası). **Orta**: araç boyunun tam "
    "ortası — literatürle (Davies & Bischoff 1999) karşılaştırmak için. "
    "**Yoğunlaşma** 1,0 ise yük boy boyunca düzgün dağılmış demektir; "
    "büyüdükçe bir yerde kümelenme artar."
)


# ─────────────────────────────────────────────────────────────────────────────
# Araç başına
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class AracAgirlikDagilimi:
    """Tek bir aracın ağırlık dağılımı ölçüleri. Tüm uzunluklar cm."""
    etiket: str = ""
    parca_sayisi: int = 0
    yuk_kg: float = 0.0

    arac_boy_cm: float = 0.0
    arac_en_cm: float = 0.0
    arac_yukseklik_cm: float = 0.0

    cog_x_cm: float = 0.0
    cog_y_cm: float = 0.0
    cog_z_cm: float = 0.0

    hedef_x_cm: float = 0.0          # genişliğin ortası
    hedef_y_cm: float = 0.0          # ön %40 (bizim hedefimiz)
    orta_y_cm: float = 0.0           # boyun tam ortası (literatür)

    metre_kg: List[float] = field(default_factory=list)
    bolum_sinirlari_cm: List[Tuple[float, float]] = field(default_factory=list)

    # ── Sapmalar ────────────────────────────────────────────────────────
    @property
    def sapma_x_cm(self) -> float:
        return abs(self.cog_x_cm - self.hedef_x_cm)

    @property
    def sapma_y_cm(self) -> float:
        """Bizim hedefimize (ön %40) uzaklık."""
        return abs(self.cog_y_cm - self.hedef_y_cm)

    @property
    def sapma_orta_y_cm(self) -> float:
        """Boyun tam ortasına uzaklık — Davies & Bischoff ölçüsü."""
        return abs(self.cog_y_cm - self.orta_y_cm)

    @property
    def one_mi_arkaya_mi(self) -> str:
        """Ağırlık merkezi hedefin önünde mi arkasında mı?"""
        if abs(self.cog_y_cm - self.hedef_y_cm) < 1e-9:
            return "tam hedefte"
        return "önde" if self.cog_y_cm < self.hedef_y_cm else "arkada"

    @property
    def cog_z_orani(self) -> Optional[float]:
        """Ağırlık merkezinin yüksekliği ÷ araç yüksekliği."""
        if self.arac_yukseklik_cm <= 0:
            return None
        return self.cog_z_cm / self.arac_yukseklik_cm

    # ── Yayılma ─────────────────────────────────────────────────────────
    @property
    def metre_sayisi(self) -> int:
        return len(self.metre_kg)

    @property
    def en_agir_metre_kg(self) -> float:
        return max(self.metre_kg) if self.metre_kg else 0.0

    @property
    def en_agir_metre_no(self) -> Optional[int]:
        """Kaçıncı metre (1'den başlar, ön duvardan sayılır)."""
        if not self.metre_kg:
            return None
        return self.metre_kg.index(self.en_agir_metre_kg) + 1

    @property
    def ortalama_metre_kg(self) -> Optional[float]:
        if not self.metre_kg or self.yuk_kg <= 0:
            return None
        return self.yuk_kg / len(self.metre_kg)

    @property
    def yogunlasma(self) -> Optional[float]:
        """En ağır metre ÷ ortalama metre. 1,0 = düzgün dağılmış."""
        ort = self.ortalama_metre_kg
        if not ort:
            return None
        return self.en_agir_metre_kg / ort

    # ── 2. adımın ön koşulu ─────────────────────────────────────────────
    @property
    def bolum_sayisi(self) -> int:
        return len(self.bolum_sinirlari_cm)

    @property
    def dengelenebilir_mi(self) -> bool:
        """Blok takası yapılabilmesi için en az iki ayrık bölüm gerekir."""
        return self.bolum_sayisi >= 2


# ─────────────────────────────────────────────────────────────────────────────
# Plan düzeyi
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class PlanAgirlikDagilimi:
    """Bütün planın ağırlık dağılımı raporu."""
    araclar: List[AracAgirlikDagilimi] = field(default_factory=list)

    @property
    def arac_sayisi(self) -> int:
        return len(self.araclar)

    @property
    def sapma_y_ortalama_cm(self) -> Optional[float]:
        return _ortalama([a.sapma_y_cm for a in self.araclar])

    @property
    def sapma_y_en_kotu_cm(self) -> Optional[float]:
        return _en_buyuk([a.sapma_y_cm for a in self.araclar])

    @property
    def sapma_orta_y_ortalama_cm(self) -> Optional[float]:
        """Davies & Bischoff ile doğrudan karşılaştırılabilir ölçü."""
        return _ortalama([a.sapma_orta_y_cm for a in self.araclar])

    @property
    def sapma_x_ortalama_cm(self) -> Optional[float]:
        return _ortalama([a.sapma_x_cm for a in self.araclar])

    @property
    def sapma_x_en_kotu_cm(self) -> Optional[float]:
        return _en_buyuk([a.sapma_x_cm for a in self.araclar])

    @property
    def yogunlasma_ortalama(self) -> Optional[float]:
        return _ortalama([a.yogunlasma for a in self.araclar])

    @property
    def yogunlasma_en_kotu(self) -> Optional[float]:
        return _en_buyuk([a.yogunlasma for a in self.araclar])

    @property
    def dengelenebilir_arac_sayisi(self) -> int:
        """Kaç araçta blok takası uygulanabilir (≥2 bölüm)."""
        return sum(1 for a in self.araclar if a.dengelenebilir_mi)


def _ortalama(degerler: Sequence[Optional[float]]) -> Optional[float]:
    gecerli = [d for d in degerler if d is not None]
    return sum(gecerli) / len(gecerli) if gecerli else None


def _en_buyuk(degerler: Sequence[Optional[float]]) -> Optional[float]:
    gecerli = [d for d in degerler if d is not None]
    return max(gecerli) if gecerli else None


# ─────────────────────────────────────────────────────────────────────────────
# Yardımcılar
# ─────────────────────────────────────────────────────────────────────────────

def metre_dagilimi(yerlesimler, piece_info, arac_boy_cm: float) -> List[float]:
    """Araç boyunca metre başına kg.

    Her parçanın ağırlığı KENDİ y uzunluğu boyunca düzgün yayılmış
    sayılır; tek bir metreye yığılmaz. Yük dağılım planlarında
    ("metre başına kg") kullanılan yaklaşım budur.
    """
    if arac_boy_cm <= 0:
        return []
    dilim_sayisi = max(1, math.ceil(arac_boy_cm / METRE_CM))
    dilimler = [0.0] * dilim_sayisi
    for p in yerlesimler:
        parca = piece_info.get(p.piece_id)
        agirlik = float(getattr(parca, "weight", 0) or 0.0)
        if agirlik <= 0:
            continue
        bas, boy = float(p.y), float(p.length)
        if boy <= 0:
            continue
        son = bas + boy
        for k in range(dilim_sayisi):
            d_bas, d_son = k * METRE_CM, (k + 1) * METRE_CM
            ortak = min(son, d_son) - max(bas, d_bas)
            if ortak > 0:
                dilimler[k] += agirlik * (ortak / boy)
    return dilimler


def bolumleri_bul(yerlesimler) -> List[Tuple[float, float]]:
    """Yerleşimi, hiçbir parçanın kesmediği y düzlemlerinden ayır.

    Davies & Bischoff'un yöntemi "kesişmeyen bölümlerin" takas
    edilmesine dayanır. Burada bu bölümler SONRADAN bulunur; böylece
    yöntem yalnız duvar-inşa (layer building) için değil, Extreme Points
    tabanlı algoritmaların çıktısı için de uygulanabilir olur.

    Döner: [(baslangic_y, bitis_y), ...] — y'ye göre sıralı.
    """
    araliklar = sorted((float(p.y), float(p.y) + float(p.length))
                       for p in yerlesimler if float(p.length) > 0)
    if not araliklar:
        return []
    bolumler: List[Tuple[float, float]] = []
    bas, son = araliklar[0]
    for a_bas, a_son in araliklar[1:]:
        if a_bas < son - 1e-9:        # örtüşüyor → aynı bölüm
            son = max(son, a_son)
        else:                          # temiz kesim düzlemi
            bolumler.append((bas, son))
            bas, son = a_bas, a_son
    bolumler.append((bas, son))
    return bolumler


# ─────────────────────────────────────────────────────────────────────────────
# ANA GİRİŞ — arayüz ve raporlar yalnızca bunu çağırır
# ─────────────────────────────────────────────────────────────────────────────

def plan_agirlik_dagilimi(plan, pieces, trucks) -> PlanAgirlikDagilimi:
    """Bir yerleşim planının ağırlık dağılımı ölçülerini hesaplar.

    Boş araçlar atlanır (doluluk.py ile aynı kural).
    """
    from core_3d import calculate_center_of_gravity, COG_FRONT_BIAS

    rapor = PlanAgirlikDagilimi()
    if plan is None or not getattr(plan, "bins", None) or not trucks:
        return rapor

    piece_info = {p.id: p for p in pieces}
    tid = {t.id: t for t in trucks}
    atama = plan.truck_assignments or {}

    for bid, yerlesimler in enumerate(plan.bins):
        if not yerlesimler:
            continue
        truck = tid.get(atama.get(bid))
        if truck is None:
            continue

        eslesme = getattr(truck, "eslesme", None)
        etiket = (f"{eslesme.cekici.plaka} + {eslesme.dorse.plaka}"
                  if eslesme is not None else truck.id)

        cog_x, cog_y, cog_z = calculate_center_of_gravity(
            yerlesimler, piece_info)
        boy = float(truck.length)

        rapor.araclar.append(AracAgirlikDagilimi(
            etiket=etiket,
            parca_sayisi=len(yerlesimler),
            # Palet darası parçanın ağırlığına ZATEN dâhil (bkz. doluluk.py)
            yuk_kg=sum(float(getattr(piece_info.get(p.piece_id), "weight", 0)
                             or 0.0) for p in yerlesimler),
            arac_boy_cm=boy,
            arac_en_cm=float(truck.width),
            arac_yukseklik_cm=float(truck.height),
            cog_x_cm=cog_x, cog_y_cm=cog_y, cog_z_cm=cog_z,
            hedef_x_cm=float(truck.width) / 2.0,
            hedef_y_cm=boy * COG_FRONT_BIAS,
            orta_y_cm=boy / 2.0,
            metre_kg=metre_dagilimi(yerlesimler, piece_info, boy),
            bolum_sinirlari_cm=bolumleri_bul(yerlesimler),
        ))

    return rapor


# ─────────────────────────────────────────────────────────────────────────────
# Biçimlendirme — arayüz ve raporlar aynı metni göstersin
# ─────────────────────────────────────────────────────────────────────────────

def cm(deger: Optional[float], basamak: int = 0) -> str:
    """Uzunluğu cm metnine çevirir. Bilinmiyorsa '—' (sıfır DEĞİL)."""
    if deger is None:
        return "—"
    return f"{deger:.{basamak}f} cm"


def sayi(deger: Optional[float], basamak: int = 2) -> str:
    if deger is None:
        return "—"
    return f"{deger:.{basamak}f}"


def arac_satirlari(rapor: PlanAgirlikDagilimi) -> List[Dict[str, object]]:
    """Araç başına tablo satırları — arayüz ve raporlar ortak kullanır."""
    satirlar: List[Dict[str, object]] = []
    for a in rapor.araclar:
        satirlar.append({
            "Araç": a.etiket,
            "Yük (kg)": round(a.yuk_kg, 1),
            "CoG Y (cm)": round(a.cog_y_cm, 1),
            "Hedeften (cm)": round(a.sapma_y_cm, 1),
            "Yön": a.one_mi_arkaya_mi,
            "Ortadan (cm)": round(a.sapma_orta_y_cm, 1),
            "Yanal (cm)": round(a.sapma_x_cm, 1),
            "CoG Z (cm)": round(a.cog_z_cm, 1),
            "En ağır metre": (f"{a.en_agir_metre_no}. · "
                              f"{a.en_agir_metre_kg:,.0f} kg"
                              .replace(",", ".")
                              if a.en_agir_metre_no else "—"),
            "Yoğunlaşma": sayi(a.yogunlasma),
            "Bölüm": a.bolum_sayisi,
        })
    return satirlar
