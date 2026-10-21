# -*- coding: utf-8 -*-
"""
Filo veri modeli — çekici (traktör) + dorse (yarı römork)
==========================================================
Karar V-B: çekici ve dorse AYRI varlıklar. Her birinin kendi kimliği,
plakası, boş ağırlığı ve dingil verisi var. Yük alanı dorsedir; seferi
(ve dolayısıyla araç sayısını) çekici belirler.

Birimler: **mm ve kg** (araç föyleriyle aynı). Yerleştirme motoru cm ile
çalışıyor; mm → cm dönüşümü ortak motor köprüsünde yapılacak (2. adım,
karar S10 bekliyor) — bu dosyada dönüşüm YOK.

Kütle kapasitesi K-b: sistem hesaplar (bkz. eslesme_hesapla).
  faydali_yuk = min(yasal_toplam, çekici teknik GCW)
                − çekici boş ağırlığı − dorse boş ağırlığı
  faydali_yuk = min(faydali_yuk, dorse teknik azami − dorse boş ağırlığı)

Kaynaklar: FILO_VERI_MODELI_REHBERI.md (Bölüm 2–4), KTY md.128
(mevzuat_kty.py), Pollaris ve ark. 2016/2017/2021.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from mevzuat_kty import (
    TAHRIKLI_TEK_DINGIL,
    TAHRIKSIZ_TEK_DINGIL,
    dingil_grubu_siniri,
    kucugunu_uygula,
    yasal_toplam_agirlik,
)

# Göç (H kararı) için: eski tek parça araçların plaka öneki
ESKI_ARAC_ONEKI = "ESKI"
TANIMSIZ_CEKICI_ONEKI = "TANIMSIZ-CEKICI"


# ─────────────────────────────────────────────────────────────────────────────
# Çekici
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Cekici:
    """Çekici (traktör). Ölçüler mm, ağırlıklar kg.

    Zorunlu alanlar: plaka, bos_agirlik_kg, dingil_sayisi,
    besinci_teker_ofset_mm (e — D kararı).

    "Dingil kontrolü grubu" (bos_on_dingil_kg, bos_arka_dingil_kg,
    on_dingil_izin_kg, tahrik_dingil_izin_kg, dingil_mesafesi_mm):
    eksikse dingil kontrolü YAPILAMAZ. Zorunlu olup olmayacağı S16'da
    karara bağlanacak; bu sınıf şimdilik eksikliği yalnızca RAPORLAR.
    """
    cekici_id: str
    plaka: str
    bos_agirlik_kg: float
    dingil_sayisi: int = 2
    # e — beşinci tekerin tahrik dingiline yatay uzaklığı.
    # İŞARET KURALI: beşinci teker tahrik dingilinin ÖNÜNDE (kabine
    # doğru) ise POZİTİF. e = 0 → kingpin yükünün tamamı tahrik
    # dingiline biner. e < 0 geçerlidir (ön dingil yük kaybeder).
    besinci_teker_ofset_mm: float = 0.0
    marka_model: str = ""

    # ── dingil kontrolü grubu ──
    bos_on_dingil_kg: Optional[float] = None
    bos_arka_dingil_kg: Optional[float] = None
    on_dingil_izin_kg: Optional[float] = None
    tahrik_dingil_izin_kg: Optional[float] = None
    dingil_mesafesi_mm: Optional[float] = None          # WB

    # ── isteğe bağlı ──
    teknik_gcw_kg: Optional[float] = None

    # ── üstveri ──
    # Serbest metin iki alan: Excel şablonunda da sütun olarak var.
    # `kaynak_notlari` alan BAZINDA kaynak tutar; bunlar KAYDIN tamamı için.
    kaynak: str = ""                     # ör. "Ford Trucks F-MAX Euro 6E föyü"
    dogrulama_durumu: str = ""           # ör. "föy PDF'i arşivde yok"
    tanimsiz: bool = False                              # H: göç edilmiş kayıt
    varsayim_alanlari: Dict[str, str] = field(default_factory=dict)
    kaynak_notlari: Dict[str, str] = field(default_factory=dict)

    @property
    def tahrikli_dingil_siniri_kg(self) -> float:
        """min(KTY tahrikli tek dingil, föy tahrik izni)."""
        deger, _, _ = kucugunu_uygula(
            TAHRIKLI_TEK_DINGIL.deger_kg, TAHRIKLI_TEK_DINGIL.kaynak,
            self.tahrik_dingil_izin_kg, "çekici föyü, tahrik dingil izni")
        return float(deger)

    @property
    def on_dingil_siniri_kg(self) -> float:
        """min(KTY tahriksiz tek dingil, föy ön dingil izni).

        4x2 ve 6x2 çekicilerde ön dingil tahriksizdir → KTY 10 t.
        Ford F-MAX föyü 7.500 kg veriyor → bağlayan föy değeri.
        """
        deger, _, _ = kucugunu_uygula(
            TAHRIKSIZ_TEK_DINGIL.deger_kg, TAHRIKSIZ_TEK_DINGIL.kaynak,
            self.on_dingil_izin_kg, "çekici föyü, ön dingil izni")
        return float(deger)

    def eksik_dingil_alanlari(self) -> List[str]:
        """Dingil kontrolü için eksik olan alanlar."""
        eksik: List[str] = []
        if self.tanimsiz:
            return ["çekici tanımsız"]
        for ad in ("bos_on_dingil_kg", "bos_arka_dingil_kg",
                   "dingil_mesafesi_mm"):
            if getattr(self, ad) is None:
                eksik.append(ad)
        if self.dingil_mesafesi_mm is not None and self.dingil_mesafesi_mm <= 0:
            eksik.append("dingil_mesafesi_mm (sıfır veya negatif)")
        return eksik

    def kingpin_kapasitesi_kg(self) -> Optional[float]:
        """
        Bu çekicinin taşıyabileceği EN BÜYÜK kingpin yükü.

        Moment dengesinden: kingpin yükü K, ön dingile K·e/WB, tahrik
        dingiline K·(WB−e)/WB biner. İki sınırdan küçüğü bağlar.

        C kararındaki "dingil payı en geniş" eşitlik bozucu ölçütü bu
        değeri kullanır. Veri eksikse None.
        """
        if self.eksik_dingil_alanlari():
            return None
        wb = float(self.dingil_mesafesi_mm or 0.0)
        e = float(self.besinci_teker_ofset_mm)
        if wb <= 0:
            return None

        adaylar: List[float] = []
        on_bosluk = self.on_dingil_siniri_kg - float(self.bos_on_dingil_kg or 0.0)
        arka_bosluk = (self.tahrikli_dingil_siniri_kg
                       - float(self.bos_arka_dingil_kg or 0.0))
        if e > 0:
            adaylar.append(on_bosluk * wb / e)
        if (wb - e) > 0:
            adaylar.append(arka_bosluk * wb / (wb - e))
        if not adaylar:
            return None
        return max(0.0, min(adaylar))


# ─────────────────────────────────────────────────────────────────────────────
# Dorse
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Dorse:
    """Yarı römork (dorse). İç ölçüler mm, ağırlıklar kg.

    İç hacim HESAPLANIR, girilmez (ic_hacim_m3).

    kingpin_on_kenar_mesafe_mm: föydeki gibi dorsenin DIŞ ön kenarından
    ölçülür (F kararı). Motorun ekseni iç ön duvardan başladığı için
    c_mm özelliği on_duvar_kalinligi_mm'i düşerek dönüştürür.
    """
    dorse_id: str
    plaka: str
    tip: str                                   # tenteli / frigorifik / kapalı kasa / mega
    ic_uzunluk_mm: float
    ic_genislik_mm: float
    ic_yukseklik_mm: float
    bos_agirlik_kg: float
    dingil_sayisi: int

    # ── dingil kontrolü grubu ──
    dingil_araligi_mm: Optional[float] = None
    dingil_grubu_izin_kg: Optional[float] = None            # föy
    kingpin_izin_kg: Optional[float] = None                 # föy
    kingpin_on_kenar_mesafe_mm: Optional[float] = None      # föy, DIŞ ön kenardan
    on_duvar_kalinligi_mm: float = 0.0                      # F kararı
    kingpin_dingil_grubu_mesafe_mm: Optional[float] = None  # d

    # ── boş ağırlığın kingpin / grup paylaşımı (E kararı) ──
    # Sıra: 1) föydeki boş dingil yükleri  2) bu iki alan  3) yük alanının
    # ortası varsayımı + uyarı. Kaynak etiketi bos_payi_kaynagi'nda.
    bos_kingpin_payi_kg: Optional[float] = None
    bos_dingil_grubu_payi_kg: Optional[float] = None
    bos_payi_kaynagi: str = ""                 # "föy" | "elle" | "" (boş → varsayım)

    # ── isteğe bağlı ──
    teknik_azami_kg: Optional[float] = None
    iso_40ft_konteyner: bool = False

    # ── üstveri ──
    kaynak: str = ""                           # ör. "Schmitz SCS 24/L föyü"
    dogrulama_durumu: str = ""
    eski_arac_mi: bool = False                 # H: göç edilmiş kayıt
    varsayim_alanlari: Dict[str, str] = field(default_factory=dict)
    kaynak_notlari: Dict[str, str] = field(default_factory=dict)

    @property
    def ic_hacim_mm3(self) -> float:
        return float(self.ic_uzunluk_mm) * float(self.ic_genislik_mm) * \
            float(self.ic_yukseklik_mm)

    @property
    def ic_hacim_m3(self) -> float:
        """İç hacim (m³) — hesaplanır, girilmez."""
        return self.ic_hacim_mm3 / 1_000_000_000.0

    @property
    def c_mm(self) -> Optional[float]:
        """Kingpinin iç ön duvara uzaklığı (motorun y eksenine göre).

        F kararı: kullanıcı föydeki gibi DIŞ ön kenardan girer;
        ön duvar kalınlığı düşülerek iç eksene çevrilir.
        """
        if self.kingpin_on_kenar_mesafe_mm is None:
            return None
        return float(self.kingpin_on_kenar_mesafe_mm) - \
            float(self.on_duvar_kalinligi_mm)

    @property
    def d_mm(self) -> Optional[float]:
        """Kingpin ile dingil grubunun orta dingili arası (arkaya pozitif)."""
        if self.kingpin_dingil_grubu_mesafe_mm is None:
            return None
        return float(self.kingpin_dingil_grubu_mesafe_mm)

    def dingil_grubu_siniri_kg(self) -> Tuple[Optional[float], str, List[str]]:
        """min(KTY grup sınırı, föy grup izni)."""
        kty, kty_kaynak, uyarilar = dingil_grubu_siniri(
            self.dingil_sayisi, self.dingil_araligi_mm)
        deger, kaynak, ek = kucugunu_uygula(
            kty, kty_kaynak, self.dingil_grubu_izin_kg,
            "dorse föyü, dingil grubu izni")
        return deger, kaynak, uyarilar + ek

    def eksik_dingil_alanlari(self) -> List[str]:
        eksik: List[str] = []
        if self.c_mm is None:
            eksik.append("kingpin_on_kenar_mesafe_mm")
        if self.d_mm is None:
            eksik.append("kingpin_dingil_grubu_mesafe_mm")
        elif self.d_mm <= 0:
            eksik.append("kingpin_dingil_grubu_mesafe_mm (sıfır veya negatif)")
        if self.kingpin_izin_kg is None:
            eksik.append("kingpin_izin_kg")
        if self.dingil_grubu_siniri_kg()[0] is None:
            eksik.append("dingil grubu sınırı (ne KTY ne föy değeri var)")
        return eksik

    def bos_agirlik_payi(self) -> Tuple[float, float, str, List[str]]:
        """
        Boş dorse ağırlığının kingpin ve dingil grubu arasındaki paylaşımı.

        E kararındaki sıra:
          1) föydeki boş dingil yükleri (bos_payi_kaynagi == "föy")
          2) elle girilen iki alan
          3) ağırlık merkezi yük alanının ORTASINDA varsayılır → kaldıraç
             kuralıyla bölünür + uyarı

        Returns:
            (kingpin_payi_kg, grup_payi_kg, kaynak, uyarilar)
        """
        if (self.bos_kingpin_payi_kg is not None
                and self.bos_dingil_grubu_payi_kg is not None):
            kaynak = self.bos_payi_kaynagi or "elle"
            return (float(self.bos_kingpin_payi_kg),
                    float(self.bos_dingil_grubu_payi_kg), kaynak, [])

        c, d = self.c_mm, self.d_mm
        if c is None or d is None or d <= 0:
            return (0.0, 0.0, "hesaplanamadı",
                    ["Boş dorse ağırlığının kingpin/grup paylaşımı "
                     "hesaplanamadı: kingpin mesafeleri eksik."])

        # 3) Varsayım: boş dorsenin ağırlık merkezi yük alanının ortasında
        cg = float(self.ic_uzunluk_mm) / 2.0
        grup = float(self.bos_agirlik_kg) * (cg - c) / d
        kingpin = float(self.bos_agirlik_kg) - grup
        return (kingpin, grup, "varsayım",
                [f"VARSAYIM: boş dorsenin ağırlık merkezi yük alanının "
                 f"ortasında ({cg:.0f} mm) kabul edildi → kingpin "
                 f"{kingpin:,.0f} kg, dingil grubu {grup:,.0f} kg. "
                 f"Föydeki boş dingil yükleri girilirse bu varsayım kalkar."
                 .replace(",", ".")])

    def tutarlilik_uyarilari(self) -> List[str]:
        """Veri girişindeki mantık hatalarını yakalar."""
        uyarilar: List[str] = []
        c, d = self.c_mm, self.d_mm
        if c is not None and c < 0:
            uyarilar.append(
                f"Kingpin iç ön duvarın önünde çıkıyor (c = {c:.0f} mm). "
                f"Ön duvar kalınlığı kingpin mesafesinden büyük olamaz.")
        if c is not None and d is not None:
            grup_merkezi = c + d
            if grup_merkezi > self.ic_uzunluk_mm:
                uyarilar.append(
                    f"Dingil grubunun orta dingili yük alanının dışında "
                    f"çıkıyor (c + d = {grup_merkezi:.0f} mm > iç uzunluk "
                    f"{self.ic_uzunluk_mm:.0f} mm). Ölçüleri kontrol edin.")
        if self.teknik_azami_kg is not None and \
                self.teknik_azami_kg <= self.bos_agirlik_kg:
            uyarilar.append(
                "Dorse teknik azami ağırlığı boş ağırlığından küçük veya eşit.")
        return uyarilar


# ─────────────────────────────────────────────────────────────────────────────
# Eşleşme (çekici + dorse = bir sefer)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class DingilSinirlari:
    """Bir eşleşmenin bağlayıcı dingil sınırları ve kaynakları."""
    on_dingil_kg: float
    tahrik_dingil_kg: float
    kingpin_kg: Optional[float]
    dingil_grubu_kg: Optional[float]
    toplam_kg: float
    kaynaklar: Dict[str, str] = field(default_factory=dict)


@dataclass
class Eslesme:
    """Bir çekici ile bir dorsenin eşleşmesi = bir sefer."""
    cekici: Cekici
    dorse: Dorse
    yasal_toplam_kg: float
    yasal_toplam_kaynak: str
    faydali_yuk_kg: float
    faydali_yuk_kaynak: str
    dingil_sinirlari: DingilSinirlari
    dingil_kontrol_edilebilir: bool
    eksik_alanlar: List[str] = field(default_factory=list)
    uyarilar: List[str] = field(default_factory=list)
    baglamayan_sinirlar: List[str] = field(default_factory=list)

    @property
    def etiket(self) -> str:
        return f"{self.cekici.plaka} + {self.dorse.plaka}"

    def faydali_yuk_aciklamasi(self) -> str:
        """Arayüzde gösterilecek izlenebilir metin.

        NOT: binlik ayracı düzeltmesi YALNIZ sayıya uygulanır. Metnin
        tamamına uygulanırsa kaynak metnindeki virgüller de bozulur
        (örnek: "...29329), 5+ dingilli" → "...29329). 5+ dingilli").
        """
        sayi = f"{self.faydali_yuk_kg:,.0f}".replace(",", ".")
        metin = f"Faydalı yük {sayi} kg. Bağlayan: {self.faydali_yuk_kaynak}."
        if self.baglamayan_sinirlar:
            metin += " Bağlamayan: " + "; ".join(self.baglamayan_sinirlar) + "."
        return metin


def _eski_kayit_eslesmesi(cekici: Cekici, dorse: Dorse) -> Eslesme:
    """Göç edilmiş eski araç kaydı için eşleşme (H kararı).

    Kütle kapasitesi K-b ile HESAPLANMAZ; eski kayıttaki "Kapasite (kg)"
    değeri aynen kullanılır. Dingil kontrolü yapılamaz ve bu durum
    sessizce geçilmez: uyarı listesine yazılır.
    """
    kapasite = float(dorse.teknik_azami_kg or 0.0)
    sinirlar = DingilSinirlari(
        on_dingil_kg=0.0, tahrik_dingil_kg=0.0,
        kingpin_kg=None, dingil_grubu_kg=None,
        toplam_kg=kapasite,
        kaynaklar={"toplam": "eski araç kaydı, elle girilen kapasite"},
    )
    return Eslesme(
        cekici=cekici, dorse=dorse,
        yasal_toplam_kg=kapasite,
        yasal_toplam_kaynak="eski araç kaydı, elle girilen kapasite",
        faydali_yuk_kg=kapasite,
        faydali_yuk_kaynak="eski araç kaydı, elle girilen kapasite",
        dingil_sinirlari=sinirlar,
        dingil_kontrol_edilebilir=False,
        eksik_alanlar=["çekici tanımsız"],
        uyarilar=[
            "çekici tanımsız — kütle kapasitesi elle girilen değer, "
            "KTY md.128 ile hesaplanmadı",
            "dingil kontrolü yapılamadı: çekici tanımsız",
        ],
    )


def eslesme_hesapla(cekici: Cekici, dorse: Dorse) -> Eslesme:
    """
    K-b: kütle kapasitesini sistem hesaplar.

        yasal_toplam = KTY(toplam dingil, konteyner bayrağı, çekici dingil)
        faydali_yuk  = min(yasal_toplam, çekici teknik GCW)
                       − çekici boş − dorse boş
        faydali_yuk  = min(faydali_yuk, dorse teknik azami − dorse boş)

    Eşleşme her değiştiğinde yeniden çağrılmalıdır.
    """
    uyarilar: List[str] = []
    baglamayan: List[str] = []

    # ── 0. GÖÇ EDİLMİŞ KAYIT (H kararı) ─────────────────────────────────
    # Eski tek parça araçlarda dingil sayısı bilinmiyor (0). KTY tablosunu
    # uygulamak yanlış olur: 0 dingil "2 dingilli motorlu araç" satırına
    # düşer ve kapasiteyi 18 t'ye kırpar. Benchmark'ta (thpack) kapasite
    # bilerek çok yüksek verildiği için bu, eski sonuçları bozardı.
    # Bu yüzden göç edilmiş kayıtlarda eski kapasite AYNEN korunur.
    if dorse.eski_arac_mi and cekici.tanimsiz:
        return _eski_kayit_eslesmesi(cekici, dorse)

    # ── 1. Yasal azami toplam ───────────────────────────────────────────
    yasal_toplam, yasal_kaynak, kty_uyarilar = yasal_toplam_agirlik(
        cekici.dingil_sayisi, dorse.dingil_sayisi, dorse.iso_40ft_konteyner)
    uyarilar.extend(kty_uyarilar)

    # ── 2. min(yasal, çekici teknik GCW) ────────────────────────────────
    ust_sinir = yasal_toplam
    ust_kaynak = yasal_kaynak
    if cekici.teknik_gcw_kg is None:
        uyarilar.append(
            "Çekici teknik GCW girilmedi → yalnız yasal toplam kullanıldı.")
    elif cekici.teknik_gcw_kg < yasal_toplam:
        ust_sinir = float(cekici.teknik_gcw_kg)
        ust_kaynak = "çekici föyü, teknik GCW"
        baglamayan.append(f"yasal toplam {yasal_toplam:,.0f} kg ({yasal_kaynak})"
                          .replace(",", "."))
    else:
        baglamayan.append(
            f"çekici teknik GCW {cekici.teknik_gcw_kg:,.0f} kg".replace(",", "."))

    # ── 3. Boş ağırlıkları düş ──────────────────────────────────────────
    faydali = ust_sinir - float(cekici.bos_agirlik_kg) - float(dorse.bos_agirlik_kg)
    faydali_kaynak = ust_kaynak

    # ── 4. Dorse teknik azami sınırı ────────────────────────────────────
    if dorse.teknik_azami_kg is None:
        uyarilar.append(
            "Dorse teknik azami ağırlığı girilmedi → bu sınır kontrol edilmedi.")
    else:
        dorse_faydali = float(dorse.teknik_azami_kg) - float(dorse.bos_agirlik_kg)
        if dorse_faydali < faydali:
            baglamayan.append(f"{faydali_kaynak} üzerinden {faydali:,.0f} kg"
                              .replace(",", "."))
            faydali = dorse_faydali
            faydali_kaynak = "dorse föyü, teknik azami ağırlık"
        else:
            baglamayan.append(
                f"dorse teknik sınırı {dorse_faydali:,.0f} kg".replace(",", "."))

    if faydali <= 0:
        uyarilar.append(
            f"Faydalı yük sıfır veya negatif çıktı ({faydali:,.0f} kg). "
            f"Boş ağırlıkları ve sınırları kontrol edin.".replace(",", "."))

    # ── 5. Dingil sınırları ─────────────────────────────────────────────
    grup_sinir, grup_kaynak, grup_uyarilar = dorse.dingil_grubu_siniri_kg()
    uyarilar.extend(grup_uyarilar)
    kingpin_sinir, kingpin_kaynak, _ = kucugunu_uygula(
        None, "", dorse.kingpin_izin_kg, "dorse föyü, kingpin izni")

    sinirlar = DingilSinirlari(
        on_dingil_kg=cekici.on_dingil_siniri_kg,
        tahrik_dingil_kg=cekici.tahrikli_dingil_siniri_kg,
        kingpin_kg=kingpin_sinir,
        dingil_grubu_kg=grup_sinir,
        toplam_kg=yasal_toplam,
        kaynaklar={
            "on_dingil": "çekici föyü / KTY tahriksiz tek dingil",
            "tahrik_dingil": "KTY tahrikli tek dingil / çekici föyü",
            "kingpin": kingpin_kaynak,
            "dingil_grubu": grup_kaynak,
            "toplam": yasal_kaynak,
        },
    )

    # ── 6. Dingil kontrolü yapılabilir mi ───────────────────────────────
    eksik = cekici.eksik_dingil_alanlari() + dorse.eksik_dingil_alanlari()
    _, _, _, bos_uyarilar = dorse.bos_agirlik_payi()
    uyarilar.extend(bos_uyarilar)
    uyarilar.extend(dorse.tutarlilik_uyarilari())

    kontrol_edilebilir = not eksik
    if not kontrol_edilebilir:
        if cekici.tanimsiz:
            uyarilar.append("dingil kontrolü yapılamadı: çekici tanımsız")
        else:
            uyarilar.append(
                "dingil kontrolü yapılamadı: eksik veri (" +
                ", ".join(eksik) + ")")

    return Eslesme(
        cekici=cekici, dorse=dorse,
        yasal_toplam_kg=yasal_toplam, yasal_toplam_kaynak=yasal_kaynak,
        faydali_yuk_kg=faydali, faydali_yuk_kaynak=faydali_kaynak,
        dingil_sinirlari=sinirlar,
        dingil_kontrol_edilebilir=kontrol_edilebilir,
        eksik_alanlar=eksik, uyarilar=uyarilar,
        baglamayan_sinirlar=baglamayan,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Çekici eşleştirme kuralı (C kararı)
# ─────────────────────────────────────────────────────────────────────────────

ESLESTIRME_VARSAYIM_NOTU = (
    "VARSAYIM: Çekici-dorse eşleştirmesi için literatürde hazır bir kural "
    "bulunamadı. Pollaris ve ark. (2016, 2017) tek bir referans araç "
    "kullanıyor; Pollaris ve ark. (2021) karışık filoda araç tiplerini ayrı "
    "ele alıyor ama eşleştirme kuralı vermiyor. Buradaki sıralama "
    "(1. en yüksek faydalı yük, 2. en geniş dingil payı, 3. liste sırası) "
    "bizim varsayımımızdır — bkz. karar_gerekceleri.md K7."
)


def cekici_ata(dorse: Dorse,
               bos_cekiciler: Sequence[Cekici]
               ) -> Tuple[Optional[Cekici], Optional[Eslesme]]:
    """
    Bir dorseye, boş çekiciler arasından en uygun olanı ata.

    Sıralama (C kararı):
      1) en yüksek faydalı yük
      2) eşitlikte en geniş dingil payı (kingpin kapasitesi)
      3) hâlâ eşitse liste sırası → tekrarlanabilirlik

    Dingil verisi eksik çekicilerde 2. ölçüt hesaplanamaz; o çekiciler
    bu ölçütte en sona düşer (ama 1. ölçütte kazanabilirler).

    Returns:
        (secilen_cekici, eslesme) — boş çekici yoksa (None, None)
    """
    en_iyi: Optional[Tuple[float, float, int]] = None
    secilen: Optional[Cekici] = None
    secilen_eslesme: Optional[Eslesme] = None

    for sira, cekici in enumerate(bos_cekiciler):
        es = eslesme_hesapla(cekici, dorse)
        kapasite = cekici.kingpin_kapasitesi_kg()
        anahtar = (-es.faydali_yuk_kg,
                   -(kapasite if kapasite is not None else -1.0),
                   sira)
        if en_iyi is None or anahtar < en_iyi:
            en_iyi = anahtar
            secilen = cekici
            secilen_eslesme = es

    return secilen, secilen_eslesme


# ─────────────────────────────────────────────────────────────────────────────
# Göç: eski tek parça araçlar (H kararı)
# ─────────────────────────────────────────────────────────────────────────────

def eski_aractan_donustur(arac_id: str,
                          genislik_cm: float,
                          uzunluk_cm: float,
                          yukseklik_cm: float,
                          kapasite_kg: float,
                          kopya_no: int = 1) -> Tuple[Dorse, Cekici]:
    """
    Eski tek parça araç kaydını (cm, tek kapasite) yeni modele çevirir.

    H kararı: her eski araç → bir dorse + bir "tanımsız çekici".
      - İç ölçü = eski ölçü (cm → mm, tam çarpım, yuvarlama yok)
      - Faydalı yük = eski "Kapasite (kg)" (K-b hesaplanamaz)
      - Dingil kontrolü YAPILAMAZ, ama sessizce değil: uyarı metni
        eslesme_hesapla içinde üretilir ("çekici tanımsız").

    Böylece thpack9 ve deney/instances örnekleri aynen çalışmaya devam eder.
    """
    etiket = f"{ESKI_ARAC_ONEKI}-{arac_id}-{kopya_no}"
    dorse = Dorse(
        dorse_id=etiket,
        plaka=etiket,
        tip="eski kayıt",
        ic_uzunluk_mm=float(uzunluk_cm) * 10.0,
        ic_genislik_mm=float(genislik_cm) * 10.0,
        ic_yukseklik_mm=float(yukseklik_cm) * 10.0,
        bos_agirlik_kg=0.0,
        dingil_sayisi=0,
        teknik_azami_kg=float(kapasite_kg),
        eski_arac_mi=True,
        kaynak_notlari={
            "teknik_azami_kg": "eski araç kaydındaki 'Kapasite (kg)' değeri; "
                               "K-b ile hesaplanmadı",
        },
    )
    cekici = Cekici(
        cekici_id=f"{TANIMSIZ_CEKICI_ONEKI}-{arac_id}-{kopya_no}",
        plaka=f"{TANIMSIZ_CEKICI_ONEKI}-{arac_id}-{kopya_no}",
        bos_agirlik_kg=0.0,
        dingil_sayisi=0,
        besinci_teker_ofset_mm=0.0,
        marka_model="tanımsız (eski kayıttan göç)",
        tanimsiz=True,
    )
    return dorse, cekici
