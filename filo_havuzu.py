# -*- coding: utf-8 -*-
"""
Filo havuzu — TÜM algoritmalar için ortak "gerektikçe araç aç" kuralı
======================================================================
Karar B (21 Ekim 2026):
  * Araç sayısı baştan verilmez. Parça mevcut açık araçlara sığmazsa
    filodan (tavan içinde) yeni bir araç açılır. Araç sayısı algoritmanın
    SONUCUDUR.
  * Hangi tipte aracın açılacağı TEK bir parametredir (ACMA_SIRASI) ve
    bütün algoritmalar aynı değeri kullanır. Algoritma başına farklı sıra
    YOKTUR.

Dayanak (araç sayısı = çıktı, gerektikçe aç): Crainic ve ark. 2008,
Gonçalves & Resende 2013, Alvarez-Valdes ve ark. 2012/2013, Che ve ark.
2011, Toffolo ve ark. 2017, Alonso ve ark. 2016, Paquay ve ark. 2017,
Heßler ve ark. 2025. Sınırlı arz = tavan kısıtı (Koç ve ark. 2016).

Varsayılan sıra (Sude'nin kararı, 21 Ekim 2026): BÜYÜKTEN KÜÇÜĞE.
  * K1'in BİRİNCİ ölçütü araç sayısı; bu sıra onu doğrudan iyileştirir.
  * Parça düşürme riski sıfırlanır: en büyük araç almıyorsa hiçbiri almaz.
  * Kang & Park (2003) IFFD de en büyükten başlıyor.
  Değiştirmek için YALNIZCA aşağıdaki ACMA_SIRASI satırı değişir.

ÖNCE/SONRA notu: bu modülden önce FFD, Greedy, Tabu, SA, GA ve Monte Carlo
küçükten büyüğe, Layer Building ise büyükten küçüğe açıyordu. Bu fark
kaldırıldı.
"""

from __future__ import annotations

from typing import (Callable, Dict, Iterator, List, Optional,
                    Sequence, Tuple)

from core_3d import Piece3D, Truck3D

# ── TEK PARAMETRE: açma sırası ──────────────────────────────────────────────
ACMA_SIRASI = "buyukten_kucuge"      # seçenek: "kucukten_buyuge"

ACMA_SIRASI_SECENEKLERI = ("buyukten_kucuge", "kucukten_buyuge")


def arac_sirala(trucks: Sequence[Truck3D],
                sira: str = ACMA_SIRASI) -> List[Truck3D]:
    """Araç tiplerini açma sırasına göre dizer.

    Sıralama anahtarı yalnız hacimdir ve Python'un kararlı (stable)
    sıralaması kullanılır; böylece eşit hacimli tipler kullanıcının
    girdiği sırayı korur (tekrarlanabilirlik).
    """
    if sira not in ACMA_SIRASI_SECENEKLERI:
        raise ValueError(f"Bilinmeyen açma sırası: {sira}")
    return sorted(trucks, key=lambda t: t.get_volume(),
                  reverse=(sira == "buyukten_kucuge"))


def parca_sigabilir_mi(truck: Truck3D, piece: Piece3D) -> bool:
    """Parça bu araca HİÇ sığabilir mi? (gevşek üst sınır)

    Serbest döndürme varsayılarak sıralı boyutlar karşılaştırılır. False
    dönerse parça o araca KESİNLİKLE sığmaz; True dönmesi sığacağını
    garanti etmez (döndürme kısıtları, istifleme kuralları, dolu alan).
    Bu yüzden çağıran taraf yerleştirmeyi deneyip başarısız olursa aracı
    geri verir (bkz. arac_ac).
    """
    if piece is None:
        return True
    if piece.weight > truck.capacity:
        return False
    p = sorted((piece.width, piece.length, piece.height))
    t = sorted((truck.width, truck.length, truck.height))
    return all(pi <= ti for pi, ti in zip(p, t))


# ─────────────────────────────────────────────────────────────────────────────
# Havuz
# ─────────────────────────────────────────────────────────────────────────────

class FiloHavuzu:
    """Kullanıcının girdiği filo = TAVAN. Hangi araçların açılacağına
    algoritma karar verir (K4).

    Kullanım (tüm algoritmalarda aynı):
        havuz = FiloHavuzu(trucks)
        truck = havuz.ac()                 # ilk aracı aç
        ...
        bid = arac_ac(havuz, piece, bin_olustur, yerlestir, bin_iptal)
    """

    def __init__(self, trucks: Sequence[Truck3D], sira: str = ACMA_SIRASI):
        self.trucks: List[Truck3D] = list(trucks)
        self.sira = sira
        self.sirali: List[Truck3D] = arac_sirala(trucks, sira)
        self.kullanilan: Dict[str, int] = {t.id: 0 for t in trucks}

    # ── Sorgular ────────────────────────────────────────────────────────
    def musait_mi(self, truck: Truck3D) -> bool:
        return self.kullanilan.get(truck.id, 0) < truck.available

    def adaylar(self, piece: Optional[Piece3D] = None) -> Iterator[Truck3D]:
        """Açılabilecek araç TİPLERİNİ sırayla verir (henüz ayırmaz).

        Bir tip listede bir kez geçer; o tipten `available` adet açılabilir.
        Parça verilirse, parçayı kesinlikle alamayacak tipler atlanır.
        """
        for t in self.sirali:
            if self.musait_mi(t) and parca_sigabilir_mi(t, piece):
                yield t

    def toplam_kullanilan(self) -> int:
        """Açılan araç (sefer) sayısı — K1'in 1. ölçütü."""
        return sum(self.kullanilan.values())

    def tavan(self) -> int:
        return sum(t.available for t in self.trucks)

    def en_buyuk(self) -> Optional[Truck3D]:
        """Filodaki en büyük araç (tavan aşımında yedek atama için)."""
        return max(self.trucks, key=lambda t: t.get_volume(), default=None)

    # ── Ayırma / geri verme ─────────────────────────────────────────────
    def ayir(self, truck: Truck3D) -> None:
        self.kullanilan[truck.id] = self.kullanilan.get(truck.id, 0) + 1

    def geri_al(self, truck: Truck3D) -> None:
        self.kullanilan[truck.id] = max(0, self.kullanilan.get(truck.id, 0) - 1)

    def ac(self, piece: Optional[Piece3D] = None) -> Optional[Truck3D]:
        """Sıradaki uygun aracı aç ve ayır. Yoksa None."""
        for truck in self.adaylar(piece):
            self.ayir(truck)
            return truck
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Ortak "gerektikçe araç aç" akışı
# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────
# Lift-Top — ayarlanabilir tavan inisiyatifi
# ─────────────────────────────────────────────────────────────────────────────

# Deneyde KAPALI, uygulamada AÇIK olmalıdır: araç boyutunun koşu içinde
# değişmesi, sabit kutulara yerleştirme problemini değiştirir ve aynı
# koşudaki doluluk karşılaştırmasını bozar. deney/scripts bu bayrağı
# False yaparak çalıştırır.
LIFT_TOP_ACIK = True

# KTY md.128: azami yükseklik 4,00 m (dış ölçü).
AZAMI_DIS_YUKSEKLIK_MM = 4_000.0


def tavan_yukseltilebilir_mi(truck: Truck3D) -> Tuple[bool, str]:
    """Bu aracın tavanı kaldırılabilir mi?

    Returns:
        (uygun_mu, gerekçe)
    """
    if not LIFT_TOP_ACIK:
        return False, "Lift-Top kapalı"
    if not getattr(truck, "tavan_ayarlanabilir", False):
        return False, "araç sabit tavanlı"
    if getattr(truck, "tavan_yukseltildi", False):
        return False, "tavan zaten kaldırılmış"

    # Dış yükseklik sınırı — sessizce aşılmasın
    es = getattr(truck, "eslesme", None)
    dorse = getattr(es, "dorse", None) if es is not None else None
    dis = getattr(dorse, "dis_yukseklik_mm", None) if dorse else None
    if dis is not None:
        artis = (truck.yukseklik_max - truck.height) * 10.0      # cm → mm
        if float(dis) + artis > AZAMI_DIS_YUKSEKLIK_MM:
            return False, (f"dış yükseklik {float(dis) + artis:.0f} mm > "
                           f"{AZAMI_DIS_YUKSEKLIK_MM:.0f} mm (KTY md.128)")
    return True, ""


def tavan_yukselterek_dene(acik_binler: Dict[int, object],
                           yerlestir: Callable[[int], bool],
                           kayit: Optional[List[str]] = None
                           ) -> Optional[int]:
    """
    YENİ ARAÇ AÇMADAN ÖNCE: açık araçların tavanını kaldırıp dene.

    Sude'nin tanımladığı akış (21 Ekim 2026):
      1. Parça açık araçlara sığmadı
      2. Yeni araç açmadan önce tavanı `yukseklik_max`'a kadar kaldır,
         tekrar dene
      3. Sığdıysa aktif yükseklik güncellenir ve kayda geçer
      4. Sığmadıysa tavan eski hâline iner, yeni araç açılır

    Args:
        acik_binler: {bin_id: {"truck": Truck3D, "packer": motor}}
        yerlestir  : yerlestir(bin_id) -> bool
        kayit      : yükseltme kayıtlarının yazılacağı liste

    Returns:
        Parçanın yerleştiği bin kimliği, ya da None.
    """
    if not LIFT_TOP_ACIK:
        return None

    for bid, veri in list(acik_binler.items()):
        truck = veri.get("truck") if isinstance(veri, dict) else None
        packer = veri.get("packer") if isinstance(veri, dict) else None
        if truck is None or packer is None:
            continue
        uygun, _gerekce = tavan_yukseltilebilir_mi(truck)
        if not uygun:
            continue

        eski_h = truck.height
        yeni_h = int(truck.yukseklik_max)
        if not packer.tavani_yukselt(yeni_h):
            continue
        truck.height = yeni_h

        if yerlestir(bid):
            truck.tavan_yukseltildi = True
            if kayit is not None:
                kayit.append(
                    f"{truck.id}: tavan {eski_h} → {yeni_h} cm kaldırıldı, "
                    f"yeni araç açılması önlendi")
            return bid

        # 4) Sığmadı → eski hâline döndür
        packer.tavani_indir(eski_h)
        truck.height = eski_h

    return None


def arac_ac(havuz: FiloHavuzu,
            piece: Optional[Piece3D],
            bin_olustur: Callable[[Truck3D], int],
            yerlestir: Optional[Callable[[int], bool]] = None,
            bin_iptal: Optional[Callable[[int], None]] = None
            ) -> Optional[int]:
    """
    TÜM algoritmaların kullandığı tek araç açma fonksiyonu.

    Args:
        piece       : açmayı tetikleyen parça (None → yalnız araç aç)
        bin_olustur : seçilen aracı alıp yeni bin kimliği döndürür
        yerlestir   : parçayı yeni bine koymayı dener (True/False)
        bin_iptal   : başarısız bini geri alır

    DÜZELTİLEN HATA: Eskiden yeni açılan araç parçayı alamazsa parça
    düşüyor VE boş araç planda kalıyordu (ffd_3d ~279 ve aynı kalıbın
    Greedy / Monte Carlo / Genetic kopyaları). Artık parçayı alamayan
    aday atlanır, sıradaki tip denenir; hiçbiri alamıyorsa parça gerçekten
    yerleştirilemez demektir.

    Returns:
        yeni bin kimliği, ya da açılabilecek araç kalmadıysa None.
    """
    # Adaylar baştan dondurulur: bir tip parçayı alamadıysa aynı tipten
    # ikinci bir araç da alamaz → sonsuz döngü olmaz.
    for truck in list(havuz.adaylar(piece)):
        if not havuz.musait_mi(truck):
            continue
        havuz.ayir(truck)
        bid = bin_olustur(truck)
        if piece is None or yerlestir is None or yerlestir(bid):
            return bid
        # Yeni araç parçayı alamadı → aracı ve bini geri ver, sıradakini dene
        if bin_iptal is not None:
            bin_iptal(bid)
        havuz.geri_al(truck)
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Küçültme (karar S19'un kardeşi: S18) — Kang & Park 2003, IFFD 2. adımı
# ─────────────────────────────────────────────────────────────────────────────

KUCULTME_ACIK = True


def kucult(plan, trucks: Sequence[Truck3D], piece_info: Dict,
           havuz: Optional[FiloHavuzu] = None) -> int:
    """
    Plan bitince her aracı, içindekileri alabilen EN KÜÇÜK araca indir.

    Kang & Park (2003) IFFD'nin ikinci adımı: büyükten başla, sonra küçült.
    "Gerektikçe aç" kuralı araç SAYISINI iyi tutuyor, ama son araç tek bir
    parça için açıldığında en büyüğü seçiliyor ve K1'in 2. ölçütü (toplam
    araç hacmi) ile doluluk gereksiz kötüleşiyor.

    YALNIZCA araç TİPİNİ değiştirir; parçalar yerinde kalır. Bu yüzden:
      * araç sayısı DEĞİŞMEZ (K1'in 1. ölçütü korunur)
      * yerleşimler yeniden hesaplanmaz → yeni bir geçersizlik doğmaz
      * yalnız o yerleşimleri SIĞDIRAN ve ağırlığı taşıyan tipler aday olur

    Returns:
        küçültülen araç sayısı
    """
    if not KUCULTME_ACIK or not plan or not plan.truck_assignments:
        return 0

    tid = {t.id: t for t in trucks}
    kucuk_once = sorted(trucks, key=lambda t: t.get_volume())
    kullanim: Dict[str, int] = {}
    for _tid in plan.truck_assignments.values():
        kullanim[_tid] = kullanim.get(_tid, 0) + 1

    degisen = 0
    for bid, bps in enumerate(plan.bins or []):
        if not bps:
            continue
        mevcut = tid.get(plan.truck_assignments.get(bid))
        if mevcut is None:
            continue

        # Bu bindeki yerleşimlerin gerektirdiği en küçük kutu ve ağırlık
        gereken_w = max(p.x + p.width for p in bps)
        gereken_l = max(p.y + p.length for p in bps)
        gereken_h = max(p.z + p.height for p in bps)
        gereken_kg = sum(piece_info[p.piece_id].weight
                         for p in bps if p.piece_id in piece_info)

        for aday in kucuk_once:
            if aday.id == mevcut.id:
                break                     # mevcut araçtan küçüğü kalmadı
            if aday.get_volume() >= mevcut.get_volume():
                break
            if (aday.width < gereken_w or aday.length < gereken_l
                    or aday.height < gereken_h):
                continue
            if aday.capacity < gereken_kg:
                continue
            # Tavan: o tipten boş araç var mı?
            if kullanim.get(aday.id, 0) >= aday.available:
                continue
            # Dingil kontrolü yapılabilen araçlarda yeni araç da geçerli olmalı
            if getattr(aday, "eslesme", None) is not None:
                from dingil_yuku import arac_dingil_raporu, cm_to_mm_cg
                yukler = [(piece_info[p.piece_id].weight,
                           cm_to_mm_cg(p.y, p.length))
                          for p in bps if p.piece_id in piece_info]
                if not arac_dingil_raporu(aday.eslesme, yukler).gecerli:
                    continue

            kullanim[mevcut.id] = kullanim.get(mevcut.id, 1) - 1
            kullanim[aday.id] = kullanim.get(aday.id, 0) + 1
            plan.truck_assignments[bid] = aday.id
            if havuz is not None:
                havuz.geri_al(mevcut)
                havuz.ayir(aday)
            degisen += 1
            break

    if degisen:
        _doluluk_yenile(plan, trucks, piece_info)
    return degisen


def _doluluk_yenile(plan, trucks: Sequence[Truck3D], piece_info: Dict) -> None:
    """Küçültme araç hacmini değiştirdiği için doluluğu yeniden hesapla.

    Hacim tanımı DEĞİŞMİYOR: `core_3d.piece_used_volume` (silindirde πr²h)
    ÷ kullanılan araçların hacmi — yani mevcut U_G/U_V tanımı.
    """
    from core_3d import piece_used_volume

    tid = {t.id: t for t in trucks}
    kullanilan = 0.0
    arac_hacim = 0.0
    for bid, bps in enumerate(plan.bins or []):
        if not bps:
            continue
        t = tid.get((plan.truck_assignments or {}).get(bid))
        if t is None:
            continue
        arac_hacim += t.get_volume()
        kullanilan += sum(piece_used_volume(p, piece_info) for p in bps)

    if arac_hacim > 0:
        plan.utilization = kullanilan / arac_hacim * 100.0
        plan.total_waste = arac_hacim - kullanilan


# ─────────────────────────────────────────────────────────────────────────────
# Çekici + dorse köprüsü (V-B veri modeli → motorun Truck3D'si)
# ─────────────────────────────────────────────────────────────────────────────

def kapasiteye_gore_suz(agirliklar: Sequence[float],
                        kapasite_kg: float) -> Tuple[List[int], float]:
    """
    Sırayla gelen parçalardan kapasiteyi AŞMAYANLARI seçer.

    Ortak EP motorundaki kuralın aynısı (`extreme_points_3d.py`: parça
    eklenince `_weight_sum + piece.weight > truck.capacity` ise konmaz),
    ama kendi motorunu kullanan yollar için (NFP) ayrı ve test edilebilir
    bir fonksiyon olarak.

    Sığmayan parça ATLANIR, sonrakiler denenmeye devam eder — böylece
    ağır bir parça yüzünden arkasındaki hafif parçalar boşuna elenmez.

    Args:
        agirliklar: parçaların ağırlıkları, yerleştirme sırasında

    Returns:
        (secilen_indisler, toplam_agirlik)
    """
    secilen: List[int] = []
    toplam = 0.0
    for i, w in enumerate(agirliklar):
        w = float(w or 0.0)
        if toplam + w > kapasite_kg:
            continue
        toplam += w
        secilen.append(i)
    return secilen, toplam


def mm_to_cm(mm: float) -> int:
    """mm → cm, AŞAĞI yuvarlayarak (karar S10).

    Araç hiçbir zaman gerçeğinden büyük görünmez; kaybın üst sınırı her
    kenarda 9 mm. U_V'nin paydası da bu cm hacmidir (motorun kullandığı
    hacim), böylece kusursuz dolu bir araç %100 gösterir.
    """
    return int(float(mm) // 10)


def eslesme_to_truck3d(eslesme) -> Truck3D:
    """Bir çekici+dorse eşleşmesini motorun anladığı Truck3D'ye çevirir."""
    d = eslesme.dorse
    _min_h = mm_to_cm(d.ic_yukseklik_mm)
    _max_h = (mm_to_cm(d.yukseklik_max_mm)
              if (d.ayarlanabilir_tavan and d.yukseklik_max_mm) else None)
    t = Truck3D(
        id=d.plaka,
        width=mm_to_cm(d.ic_genislik_mm),
        length=mm_to_cm(d.ic_uzunluk_mm),
        height=_min_h,                 # AKTİF yükseklik: tavan indirilmiş hâl
        capacity=float(eslesme.faydali_yuk_kg),
        available=1,
        yukseklik_min=_min_h,
        yukseklik_max=(_max_h if (_max_h and _max_h > _min_h) else None),
    )
    t.eslesme = eslesme
    return t


def eslestirme_dokumu(cekiciler: Sequence, dorseler: Sequence,
                      sira: str = ACMA_SIRASI) -> List[Dict[str, object]]:
    """
    Sistemin yapacağı çekici-dorse eşleştirmesini GEREKÇESİYLE döndürür.

    `havuz_olustur_cekici_dorse` ile AYNI sırayı ve aynı kuralı kullanır;
    farkı, her satır için "neden bu çekici seçildi" bilgisini de vermesi.
    Arayüzde kullanıcı "bunlar neye göre eşleşti?" diye sorduğunda
    cevabı göstermek için.

    Returns:
        [{dorse, cekici, faydali_yuk_kg, neden}, ...]
    """
    from filo_modeli import cekici_ata, eslesme_hesapla

    ters = (sira == "buyukten_kucuge")
    dorse_sirali = sorted(dorseler, key=lambda d: d.ic_hacim_mm3,
                          reverse=ters)
    bos = list(cekiciler)
    dokum: List[Dict[str, object]] = []

    for dorse in dorse_sirali:
        if not bos:
            dokum.append({"dorse": dorse, "cekici": None,
                          "faydali_yuk_kg": None,
                          "neden": "boş çekici kalmadı → sefer yapamaz"})
            continue

        # Adayların ölçütleri — gerekçeyi buradan çıkarıyoruz
        yukler = [eslesme_hesapla(c, dorse).faydali_yuk_kg for c in bos]
        paylar = [c.kingpin_kapasitesi_kg() for c in bos]
        cekici, es = cekici_ata(dorse, bos)
        if cekici is None or es is None:
            dokum.append({"dorse": dorse, "cekici": None,
                          "faydali_yuk_kg": None,
                          "neden": "uygun çekici bulunamadı"})
            continue

        if len(set(yukler)) > 1:
            neden = "en yüksek faydalı yük"
        elif len({p for p in paylar if p is not None}) > 1:
            neden = "faydalı yük eşit → en geniş dingil payı"
        else:
            neden = ("faydalı yük ve dingil payı eşit → liste sırası "
                     "(plakaya göre)")

        bos.remove(cekici)
        dokum.append({"dorse": dorse, "cekici": cekici,
                      "faydali_yuk_kg": es.faydali_yuk_kg, "neden": neden})

    return dokum


def havuz_olustur_cekici_dorse(cekiciler: Sequence,
                               dorseler: Sequence,
                               sira: str = ACMA_SIRASI) -> FiloHavuzu:
    """
    Çekici ve dorse listelerinden (iki AYRI tavan) havuz kurar.

    Eşleştirme kuralı C: her dorseye, boş çekiciler arasından en yüksek
    faydalı yükü veren çekici atanır; eşitlikte dingil payı en geniş olan;
    hâlâ eşitse liste sırası.

    Eşleştirme açma SIRASINDA yapılır: dorseler açma sırasına dizilir ve
    her birine o anda boş olan en iyi çekici verilir. Boş çekici kalmazsa
    o dorse açılamaz (sefer yapılamaz) ve havuza girmez.
    """
    from filo_modeli import cekici_ata

    # Dorseler açma sırasına göre: hacme göre (büyükten küçüğe varsayılan)
    ters = (sira == "buyukten_kucuge")
    dorse_sirali = sorted(dorseler,
                          key=lambda d: d.ic_hacim_mm3, reverse=ters)

    bos_cekiciler = list(cekiciler)
    trucks: List[Truck3D] = []
    for dorse in dorse_sirali:
        if not bos_cekiciler:
            break                       # boş çekici yok → dorse açılamaz
        cekici, eslesme = cekici_ata(dorse, bos_cekiciler)
        if cekici is None or eslesme is None:
            break
        bos_cekiciler.remove(cekici)
        trucks.append(eslesme_to_truck3d(eslesme))

    return FiloHavuzu(trucks, sira=sira)
