# -*- coding: utf-8 -*-
"""
Dingil yükü — kaldıraç kuralı ve moment dengesi (karar D-b)
============================================================
Yasal dayanak:
  Yükleme Yönetmeliği (RG 8/11/2012-28461) md. 6(1)(b): ruhsattaki azami
  yüklü ağırlık aşılamaz; AŞILMASA BİLE dingil ağırlıkları aşılamaz.
  Yani toplam 40 t'nin altında kalan bir plan, yük öne yığıldığında
  çekicinin tahrik dingilini (11,5 t) aşarak YASAL OLMAYAN hâle gelebilir.

Hesap yöntemi:
  Dorse tarafı — Pollaris ve ark. (2016), EURO J. Transp. Logist.,
  Denklem 1–2 (kaldıraç kuralı):
      dorse_grubuna = w × (CG − c) / d
      kingpine      = w − dorse_grubuna
  Çekici tarafı — moment dengesi:
      on_dingile       = K × e / WB
      tahrik_dingiline = K × (WB − e) / WB

İŞARET KURALLARI (açıkça):
  * y ekseni: y = 0 dorsenin ÖN İÇ DUVARI (çekici tarafı), y artınca
    kapıya doğru gidilir. (extreme_points_3d.py'de doğrulandı.)
  * CG: parçanın ağırlık merkezinin ön iç duvara uzaklığı (mm).
  * c  : kingpinin ön iç duvara uzaklığı (Dorse.c_mm — föydeki dış kenar
         ölçüsünden ön duvar kalınlığı düşülerek bulunur).
  * d  : kingpin ile dingil grubunun ORTA dingili arası, arkaya pozitif.
  * e  : beşinci tekerin tahrik dingiline yatay uzaklığı; beşinci teker
         tahrik dingilinin ÖNÜNDE (kabine doğru) ise POZİTİF.
         e = 0 → kingpin yükünün tamamı tahrik dingiline biner.
         e < 0 → ön dingil yük kaybeder (geçerli bir durum).
  * NEGATİF PAY GEÇERLİDİR: parça kingpinin önündeyse grup payı negatif,
    dingil grubunun arkasındaysa kingpin payı negatif çıkar. Bu fiziksel
    olarak doğrudur (dorse o uçta kaldırmaya çalışır) ve kırpılmaz.

Bu modül SAF hesaptır; yerleştirme motoruna bağlanması 3. adımda.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from filo_modeli import Eslesme

# Kontrol kipleri (G kararının "ek iş" ölçümü için)
KIP_HER_YERLESTIRME = "her_yerlestirme"   # aday konum sınırı aşıyorsa REDDET
KIP_YALNIZCA_RAPOR = "yalnizca_rapor"     # reddetme, yalnızca kaydet

POLLARIS_KAYNAK = ("Pollaris ve ark. (2016), EURO J. Transp. Logist., "
                   "Denklem 1–2 (kaldıraç kuralı)")


# ─────────────────────────────────────────────────────────────────────────────
# Saf kaldıraç ve moment hesapları
# ─────────────────────────────────────────────────────────────────────────────

def parca_payi(agirlik_kg: float, cg_mm: float,
               c_mm: float, d_mm: float) -> Tuple[float, float]:
    """
    Bir parçanın ağırlığını kingpin ile dorse dingil grubu arasında böler.

    Pollaris ve ark. (2016), Denk. 1–2:
        grup    = w × (CG − c) / d
        kingpin = w − grup

    Returns:
        (kingpin_payi_kg, dingil_grubu_payi_kg) — negatif değer geçerlidir.
    """
    if d_mm == 0:
        raise ValueError("d (kingpin–dingil grubu mesafesi) sıfır olamaz.")
    grup = float(agirlik_kg) * (float(cg_mm) - float(c_mm)) / float(d_mm)
    kingpin = float(agirlik_kg) - grup
    return kingpin, grup


def kingpin_cekiciye_dagit(kingpin_kg: float, e_mm: float,
                           wb_mm: float) -> Tuple[float, float]:
    """
    Kingpine binen toplam yükü çekicinin iki dingiline moment dengesiyle böler.

        on_dingile       = K × e / WB
        tahrik_dingiline = K × (WB − e) / WB

    Returns:
        (on_dingil_kg, tahrik_dingil_kg)
    """
    if wb_mm == 0:
        raise ValueError("WB (dingil mesafesi) sıfır olamaz.")
    on = float(kingpin_kg) * float(e_mm) / float(wb_mm)
    tahrik = float(kingpin_kg) * (float(wb_mm) - float(e_mm)) / float(wb_mm)
    return on, tahrik


# ─────────────────────────────────────────────────────────────────────────────
# Sonuç yapıları
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class DingilYukleri:
    """Bir aracın (çekici + dorse) dingil yükleri, kg."""
    on_dingil_kg: float = 0.0
    tahrik_dingil_kg: float = 0.0
    kingpin_kg: float = 0.0
    dingil_grubu_kg: float = 0.0
    toplam_kg: float = 0.0


@dataclass
class Ihlal:
    ad: str
    yuk_kg: float
    sinir_kg: float
    kaynak: str = ""

    @property
    def asim_kg(self) -> float:
        return max(0.0, self.yuk_kg - self.sinir_kg)

    def __str__(self) -> str:
        return (f"{self.ad}: {self.yuk_kg:,.0f} kg > {self.sinir_kg:,.0f} kg"
                .replace(",", ".") + (f" ({self.kaynak})" if self.kaynak else ""))


@dataclass
class DingilSonucu:
    """Bir aracın dingil kontrolü sonucu."""
    yukler: DingilYukleri
    ihlaller: List[Ihlal] = field(default_factory=list)
    kontrol_edildi: bool = True
    eksik_alanlar: List[str] = field(default_factory=list)
    uyarilar: List[str] = field(default_factory=list)

    @property
    def ihlal_kg(self) -> float:
        """Aşılan kg'ların TOPLAMI.

        K1 geldiğinde Deb (2000) kuralında kullanılacak: geçerli > geçersiz;
        geçersizler arasında ihlal toplamı küçük olan daha iyi. CEZA
        KATSAYISI YOK.
        """
        return sum(i.asim_kg for i in self.ihlaller)

    @property
    def gecerli(self) -> bool:
        """Kontrol yapılamadıysa 'geçerli' DENMEZ — bilinmiyor demektir."""
        return self.kontrol_edildi and not self.ihlaller

    def oran_tablosu(self) -> Dict[str, Optional[float]]:
        """Dingil başına yük/sınır oranı (R-a ek ölçüsü)."""
        return {i.ad: (i.yuk_kg / i.sinir_kg if i.sinir_kg else None)
                for i in self._tum_kontroller}

    _tum_kontroller: List[Ihlal] = field(default_factory=list, repr=False)


# ─────────────────────────────────────────────────────────────────────────────
# Artımlı izleyici — motor içinde kullanılacak (3. adım)
# ─────────────────────────────────────────────────────────────────────────────

class DingilIzleyici:
    """
    Yerleştirme sırasında dingil yüklerini ARTIMLI tutar.

    Her aday konum için O(1) kontrol yapar; yerleşim sayısı arttıkça
    yavaşlamaz (extreme_points_3d.py'deki ağırlık/CoG toplamlarıyla aynı
    yaklaşım).

    Kipler:
      KIP_HER_YERLESTIRME : aday konum sınırı aşıyorsa reddedilir (G kararı)
      KIP_YALNIZCA_RAPOR  : reddedilmez, yalnızca kaydedilir — "ara durum
                            reti" ölçümü için (G ek işi, plan Bölüm 6.4)
    """

    def __init__(self, eslesme: Eslesme, kip: str = KIP_HER_YERLESTIRME):
        self.eslesme = eslesme
        self.kip = kip
        self.uyarilar: List[str] = []
        self.red_sayisi = 0          # kaç aday konum reddedildi
        self.ara_durum_reti = 0      # reddedilen ama planda geçerli olabilecekler

        d = eslesme.dorse
        c_ = eslesme.cekici
        self.eksik_alanlar = list(eslesme.eksik_alanlar)
        self.kontrol_edilebilir = eslesme.dingil_kontrol_edilebilir

        self._c = d.c_mm
        self._d = d.d_mm
        self._e = float(c_.besinci_teker_ofset_mm)
        self._wb = c_.dingil_mesafesi_mm

        # ── Boş ağırlıkların sabit katkısı ──────────────────────────────
        bos_kingpin, bos_grup, bos_kaynak, bos_uyarilar = d.bos_agirlik_payi()
        self.uyarilar.extend(bos_uyarilar)
        self._bos_kingpin = bos_kingpin
        self._bos_grup = bos_grup
        self._bos_payi_kaynagi = bos_kaynak
        self._bos_on = float(c_.bos_on_dingil_kg or 0.0)
        self._bos_arka = float(c_.bos_arka_dingil_kg or 0.0)
        self._bos_toplam = float(c_.bos_agirlik_kg) + float(d.bos_agirlik_kg)

        # ── Yükün artımlı toplamları ────────────────────────────────────
        self._yuk_kingpin = 0.0
        self._yuk_grup = 0.0
        self._yuk_toplam = 0.0

    # ── İç hesap ────────────────────────────────────────────────────────

    def _paylari_hesapla(self, agirlik_kg: float,
                         cg_mm: float) -> Tuple[float, float]:
        return parca_payi(agirlik_kg, cg_mm, self._c, self._d)

    def _yukleri_hesapla(self, ek_kingpin: float = 0.0,
                         ek_grup: float = 0.0,
                         ek_agirlik: float = 0.0) -> DingilYukleri:
        kingpin = self._bos_kingpin + self._yuk_kingpin + ek_kingpin
        grup = self._bos_grup + self._yuk_grup + ek_grup
        on, tahrik = kingpin_cekiciye_dagit(kingpin, self._e, self._wb)
        return DingilYukleri(
            on_dingil_kg=self._bos_on + on,
            tahrik_dingil_kg=self._bos_arka + tahrik,
            kingpin_kg=kingpin,
            dingil_grubu_kg=grup,
            toplam_kg=self._bos_toplam + self._yuk_toplam + ek_agirlik,
        )

    def _kontrolleri_uret(self, y: DingilYukleri) -> List[Ihlal]:
        s = self.eslesme.dingil_sinirlari
        k = s.kaynaklar
        kontroller = [
            Ihlal("ön dingil", y.on_dingil_kg, s.on_dingil_kg,
                  k.get("on_dingil", "")),
            Ihlal("tahrik dingili", y.tahrik_dingil_kg, s.tahrik_dingil_kg,
                  k.get("tahrik_dingil", "")),
            Ihlal("toplam", y.toplam_kg, s.toplam_kg, k.get("toplam", "")),
        ]
        if s.kingpin_kg is not None:
            kontroller.append(
                Ihlal("kingpin", y.kingpin_kg, s.kingpin_kg,
                      k.get("kingpin", "")))
        if s.dingil_grubu_kg is not None:
            kontroller.append(
                Ihlal("dingil grubu", y.dingil_grubu_kg, s.dingil_grubu_kg,
                      k.get("dingil_grubu", "")))
        return kontroller

    # ── Dışa açık arayüz ────────────────────────────────────────────────

    def aday_uygun_mu(self, agirlik_kg: float,
                      cg_mm: float) -> Tuple[bool, float, List[Ihlal]]:
        """
        Bir parçayı verilen konuma koymak dingil sınırlarını aşar mı?

        YAN ETKİSİZDİR: yerleştirme motoru bunu her aday konum için
        çağırıyor; sayaçlar burada artsaydı "kaç parça reddedildi" değil
        "kaç aday nokta elendi" sayılırdı. Sayaçları çağıran taraf parça
        düzeyinde günceller (kaydet_red / kaydet_ara_durum).

        KIP_YALNIZCA_RAPOR kipinde her zaman True döner, ama ihlal listesi
        yine doldurulur — "ara durum reti" ölçümü bunu kullanır.

        Returns:
            (uygun_mu, ihlal_kg, ihlaller)
        """
        if not self.kontrol_edilebilir:
            # Veri eksik → kontrol YAPILAMIYOR. Sessizce "uygun" demek
            # yanlış olurdu; bu yüzden eksiklik eslesme ve sonuç ekranında
            # uyarı olarak görünür (bkz. sonuc()).
            return True, 0.0, []

        ek_kingpin, ek_grup = self._paylari_hesapla(agirlik_kg, cg_mm)
        y = self._yukleri_hesapla(ek_kingpin, ek_grup, agirlik_kg)
        ihlaller = [i for i in self._kontrolleri_uret(y) if i.asim_kg > 0]
        ihlal_kg = sum(i.asim_kg for i in ihlaller)

        if ihlaller and self.kip == KIP_HER_YERLESTIRME:
            return False, ihlal_kg, ihlaller
        return True, ihlal_kg, ihlaller

    def kaydet_red(self) -> None:
        """Bir PARÇA dingil kısıtı yüzünden reddedildi."""
        self.red_sayisi += 1

    def kaydet_ara_durum(self) -> None:
        """Yalnızca rapor kipinde: ihlalli bir konum kabul edildi.

        Bu sayı, "her yerleştirmede kontrol" kipinde kaç ret olacağının
        karşılığıdır (plan Bölüm 6.4 ölçümü).
        """
        self.ara_durum_reti += 1

    def ekle(self, agirlik_kg: float, cg_mm: float) -> None:
        """Parçayı kalıcı olarak ekle (artımlı toplamları güncelle)."""
        self._yuk_toplam += float(agirlik_kg)
        if not self.kontrol_edilebilir:
            return
        ek_kingpin, ek_grup = self._paylari_hesapla(agirlik_kg, cg_mm)
        self._yuk_kingpin += ek_kingpin
        self._yuk_grup += ek_grup

    def sonuc(self) -> DingilSonucu:
        """Şu anki durumun tam raporu."""
        if not self.kontrol_edilebilir:
            metin = ("dingil kontrolü yapılamadı: çekici tanımsız"
                     if self.eslesme.cekici.tanimsiz else
                     "dingil kontrolü yapılamadı: eksik veri ("
                     + ", ".join(self.eksik_alanlar) + ")")
            return DingilSonucu(
                yukler=DingilYukleri(
                    toplam_kg=self._bos_toplam + self._yuk_toplam),
                ihlaller=[], kontrol_edildi=False,
                eksik_alanlar=list(self.eksik_alanlar),
                uyarilar=self.uyarilar + [metin],
            )

        y = self._yukleri_hesapla()
        tum = self._kontrolleri_uret(y)
        sonuc = DingilSonucu(
            yukler=y,
            ihlaller=[i for i in tum if i.asim_kg > 0],
            kontrol_edildi=True,
            eksik_alanlar=[],
            uyarilar=list(self.uyarilar),
        )
        sonuc._tum_kontroller = tum
        return sonuc


# ─────────────────────────────────────────────────────────────────────────────
# Motor tarafı yardımcıları
# ─────────────────────────────────────────────────────────────────────────────

# Varsayılan kip. Plan Bölüm 6.4'teki ölçüm bunu geçici olarak
# KIP_YALNIZCA_RAPOR yaparak "ara durum reti" sayısını ölçer.
VARSAYILAN_KIP = KIP_HER_YERLESTIRME


def izleyici_olustur(truck, kip: Optional[str] = None
                     ) -> Optional["DingilIzleyici"]:
    """
    Bir Truck3D için dingil izleyicisi kur — mümkünse.

    None döner (yani kontrol yapılmaz) şu durumlarda:
      * araçta eşleşme yok (eski araç tablosu, Excel, deney betikleri)
      * eşleşme var ama dingil verisi eksik (göç edilmiş kayıtlar dâhil)

    İkinci durumda sessiz kalınmaz: uyarı metni eşleşmenin `uyarilar`
    listesinde durur ve sonuç ekranında gösterilir.
    """
    eslesme = getattr(truck, "eslesme", None)
    if eslesme is None:
        return None
    if not getattr(eslesme, "dingil_kontrol_edilebilir", False):
        return None
    return DingilIzleyici(eslesme, kip=kip or VARSAYILAN_KIP)


def konum_uygun_mu(truck,
                   yuklu_parcalar: Sequence[Tuple[float, float]],
                   aday_agirlik_kg: float,
                   aday_cg_mm: float) -> bool:
    """
    ARTIMLI OLMAYAN dingil kontrolü — kendi motorunu kullanan yerleştiriciler
    için (Layer Building, MaxRects, kurtarma adımları).

    Bu yerleştiriciler `place_piece_3d` çağırmadığı için DingilIzleyici'nin
    artımlı durumunu besleyemiyorlar; onun yerine o anda yüklü olan
    parçalardan her seferinde yeniden hesaplanır. Maliyet O(n) — bu
    modüllerin zaten yaptığı ağırlık toplamıyla aynı mertebede.

    Args:
        yuklu_parcalar: [(agirlik_kg, cg_mm), ...] hâlihazırda yüklü olanlar

    Returns:
        True → konum uygun (ya da kontrol yapılamıyor)
    """
    izleyici = izleyici_olustur(truck)
    if izleyici is None:
        return True
    for agirlik, cg in yuklu_parcalar:
        izleyici.ekle(agirlik, cg)
    uygun, _ihlal_kg, _ihlaller = izleyici.aday_uygun_mu(
        aday_agirlik_kg, aday_cg_mm)
    return uygun


def cm_to_mm_cg(y_cm: float, uzunluk_cm: float) -> float:
    """Motor koordinatından (cm) parçanın ağırlık merkezine (mm).

    Motorda y = 0 dorsenin ÖN İÇ DUVARI; parçanın ağırlık merkezi
    y + uzunluk/2 noktasındadır.

    NOT: dorse ölçüsü mm'den cm'ye AŞAĞI yuvarlanarak geliyor (karar S10),
    bu yüzden buradan dönen mm değeri föydeki mm'den en çok 9 mm sapabilir.
    Kaldıraç kolu metrelerle ölçüldüğü için bu sapma ihmal edilebilir.
    """
    return (float(y_cm) + float(uzunluk_cm) / 2.0) * 10.0


# ─────────────────────────────────────────────────────────────────────────────
# Bitmiş araç için tek seferlik rapor
# ─────────────────────────────────────────────────────────────────────────────

def arac_dingil_raporu(eslesme: Eslesme,
                       parca_yukleri: Sequence[Tuple[float, float]]
                       ) -> DingilSonucu:
    """
    Bitmiş bir araç için dingil raporu.

    Args:
        parca_yukleri: [(agirlik_kg, cg_mm), ...] — cg_mm, parçanın ağırlık
            merkezinin dorsenin ön iç duvarına uzaklığı.

    Plan düzeyindeki sarmalayıcı (yerleşimlerden cg çıkaran) 3. adımda
    eklenecek; bu fonksiyon motordan bağımsız kalır.
    """
    izleyici = DingilIzleyici(eslesme, kip=KIP_YALNIZCA_RAPOR)
    for agirlik, cg in parca_yukleri:
        izleyici.ekle(agirlik, cg)
    return izleyici.sonuc()
