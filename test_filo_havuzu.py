# -*- coding: utf-8 -*-
"""
Ortak araç açma testleri (2. adım)
===================================
Plan: Makaleler/FILO_UYGULAMA_PLANI.md Bölüm 13, testler 9–11.

    python -X utf8 -m pytest test_filo_havuzu.py -q

Dondurulmuş algoritmalar (Multi-Start SA, Island GA, BO-HPO) bu testlere
DÂHİL DEĞİLDİR (karar A): mantıklarına dokunulmuyor, ana karşılaştırmadan
çıktılar.
"""

from __future__ import annotations

import contextlib
import io

import pytest

import filo_havuzu
from core_3d import Piece3D, Truck3D
from filo_havuzu import (
    ACMA_SIRASI,
    FiloHavuzu,
    arac_ac,
    arac_sirala,
    eslesme_to_truck3d,
    havuz_olustur_cekici_dorse,
    mm_to_cm,
    parca_sigabilir_mi,
)
from filo_modeli import eski_aractan_donustur, eslesme_hesapla
from ornek_filo import ford_fmax_4x2, schmitz_scs_24l


@contextlib.contextmanager
def _sessiz():
    with contextlib.redirect_stdout(io.StringIO()):
        yield


def _filo():
    return [Truck3D("Buyuk", 240, 600, 200, 24_000, 2),
            Truck3D("Orta",  240, 420, 200, 16_000, 2),
            Truck3D("Kucuk", 170, 260, 180,  6_000, 2)]


def _parcalar(n=20, w=80, l=120, h=100, agirlik=200):
    return [Piece3D(id=f"p{i}", width=w, length=l, height=h,
                    quantity=1, weight=agirlik) for i in range(n)]


# ═════════════════════════════════════════════════════════════════════════════
# Havuzun kendisi
# ═════════════════════════════════════════════════════════════════════════════

def test_varsayilan_sira_buyukten_kucuge():
    """Sude'nin kararı (21 Ekim 2026). Değişirse bu test uyarır."""
    assert ACMA_SIRASI == "buyukten_kucuge"
    assert [t.id for t in arac_sirala(_filo())] == ["Buyuk", "Orta", "Kucuk"]
    assert [t.id for t in arac_sirala(_filo(), "kucukten_buyuge")] == \
        ["Kucuk", "Orta", "Buyuk"]


def test_bilinmeyen_sira_hata_veriyor():
    with pytest.raises(ValueError):
        arac_sirala(_filo(), "rastgele")


def test_esit_hacimli_tipler_giris_sirasini_koruyor():
    """Kararlı sıralama → tekrarlanabilirlik."""
    a = Truck3D("A", 100, 100, 100, 1_000, 1)
    b = Truck3D("B", 100, 100, 100, 1_000, 1)
    assert [t.id for t in arac_sirala([a, b])] == ["A", "B"]


def test_tavan_asilamaz():
    havuz = FiloHavuzu(_filo())
    acilan = []
    while True:
        t = havuz.ac()
        if t is None:
            break
        acilan.append(t.id)
    assert len(acilan) == 6                      # 2+2+2
    assert havuz.toplam_kullanilan() == havuz.tavan() == 6
    assert acilan[:2] == ["Buyuk", "Buyuk"]      # büyükten küçüğe


def test_geri_al_araci_serbest_birakiyor():
    havuz = FiloHavuzu(_filo())
    t = havuz.ac()
    assert havuz.kullanilan[t.id] == 1
    havuz.geri_al(t)
    assert havuz.kullanilan[t.id] == 0


def test_sigabilir_mi_olcu_ve_agirlik():
    kucuk = Truck3D("Kucuk", 170, 260, 180, 6_000, 1)
    # Döndürülünce sığan parça (260 uzunluk ekseni)
    assert parca_sigabilir_mi(kucuk, Piece3D(id="x", width=250, length=160,
                                             height=100, quantity=1, weight=10))
    # Hiçbir yöne sığmaz
    assert not parca_sigabilir_mi(kucuk, Piece3D(id="y", width=300, length=300,
                                                 height=100, quantity=1, weight=10))
    # Ağırlık aşıyor
    assert not parca_sigabilir_mi(kucuk, Piece3D(id="z", width=50, length=50,
                                                 height=50, quantity=1,
                                                 weight=9_000))


def test_adaylar_sigmayan_tipi_atliyor():
    havuz = FiloHavuzu(_filo())
    buyuk_parca = Piece3D(id="B", width=230, length=580, height=190,
                          quantity=1, weight=100)
    adaylar = [t.id for t in havuz.adaylar(buyuk_parca)]
    assert adaylar == ["Buyuk"]                  # Orta ve Kucuk elendi


# ═════════════════════════════════════════════════════════════════════════════
# TEST 11 — ortak açma fonksiyonu: boş araç + düşen parça oluşmamalı
# ═════════════════════════════════════════════════════════════════════════════

def test_11a_parcayi_alamayan_aday_geri_veriliyor():
    """Yeni açılan araç parçayı alamazsa araç GERİ VERİLİR, sıradaki denenir.

    Eski davranış (ffd_3d ~279 ve kopyaları): parça düşüyor VE boş araç
    planda kalıyordu.
    """
    havuz = FiloHavuzu(_filo())
    binler = {}
    denenen = []

    def bin_olustur(truck):
        bid = len(binler)
        binler[bid] = truck
        denenen.append(truck.id)
        return bid

    def yerlestir(bid):
        # Yalnız "Kucuk" kabul etsin → Buyuk ve Orta geri verilmeli
        return binler[bid].id == "Kucuk"

    def bin_iptal(bid):
        binler.pop(bid, None)

    piece = Piece3D(id="p", width=10, length=10, height=10,
                    quantity=1, weight=1)
    bid = arac_ac(havuz, piece, bin_olustur, yerlestir, bin_iptal)

    assert bid is not None
    assert denenen == ["Buyuk", "Orta", "Kucuk"]
    assert len(binler) == 1 and binler[bid].id == "Kucuk"
    # Geri verilen araçlar tavanı tüketmemeli
    assert havuz.kullanilan["Buyuk"] == 0
    assert havuz.kullanilan["Orta"] == 0
    assert havuz.kullanilan["Kucuk"] == 1


def test_11b_hicbiri_alamazsa_none_ve_bos_bin_kalmiyor():
    havuz = FiloHavuzu(_filo())
    binler = {}

    def bin_olustur(truck):
        bid = len(binler)
        binler[bid] = truck
        return bid

    bid = arac_ac(havuz,
                  Piece3D(id="p", width=10, length=10, height=10,
                          quantity=1, weight=1),
                  bin_olustur,
                  lambda _bid: False,                 # hiçbir araç alamıyor
                  lambda _bid: binler.pop(_bid, None))
    assert bid is None
    assert binler == {}, "geri alınmayan boş bin kaldı"
    assert havuz.toplam_kullanilan() == 0


def test_11c_sonsuz_donguye_girmiyor():
    """Aday listesi baştan dondurulduğu için aynı tip tekrar denenmez."""
    havuz = FiloHavuzu([Truck3D("Tek", 240, 600, 200, 24_000, 5)])
    sayac = {"n": 0}

    def bin_olustur(truck):
        sayac["n"] += 1
        return sayac["n"]

    bid = arac_ac(havuz, Piece3D(id="p", width=1, length=1, height=1,
                                 quantity=1, weight=1),
                  bin_olustur, lambda bid: False, lambda bid: None)
    assert bid is None
    assert sayac["n"] == 1, "aynı tip yalnız bir kez denenmeli"


def test_11d_ffd_bos_arac_birakmiyor():
    """Uçtan uca: FFD'de boş bin kalmamalı."""
    trucks = _filo()
    pieces = _parcalar(15)
    from ffd_3d import ffd_3d_optimization
    with _sessiz():
        plan = ffd_3d_optimization(pieces, trucks)
    assert all(b for b in plan.bins), "planda boş araç var"
    assert not plan.unfitted_pieces


# ═════════════════════════════════════════════════════════════════════════════
# TEST 9 — entegrasyon: 7 algoritmanın hepsi ortak fonksiyonu çağırıyor
# ═════════════════════════════════════════════════════════════════════════════

def _algoritmalar():
    from ffd_3d import ffd_3d_optimization
    from greedy_3d import greedy_3d_optimization
    from layer_building_3d import layer_building_3d_optimization
    from tabu_search_3d import tabu_search_3d_optimization
    from simulated_annealing_3d import simulated_annealing_3d_optimization
    from genetic_3d import genetic_3d_optimization
    from monte_carlo_3d import monte_carlo_3d_optimization
    return {
        "FFD": lambda p, t: ffd_3d_optimization(p, t),
        "Greedy": lambda p, t: greedy_3d_optimization(p, t),
        "Layer Building": lambda p, t: layer_building_3d_optimization(p, t),
        "Tabu": lambda p, t: tabu_search_3d_optimization(
            p, t, max_time=1.0, seed=1001),
        "SA": lambda p, t: simulated_annealing_3d_optimization(
            p, t, max_time=1.0, seed=1001),
        "Genetic": lambda p, t: genetic_3d_optimization(
            p, t, population_size=8, generations=3, max_time=1.0, seed=1001),
        "Monte Carlo": lambda p, t: monte_carlo_3d_optimization(
            p, t, iterations=5, max_time=1.0, seed=1001),
    }


@pytest.mark.parametrize("ad", list(_algoritmalar().keys()))
def test_9_algoritma_ortak_havuzu_kullaniyor(ad, monkeypatch):
    """Her algoritma araçları FiloHavuzu üzerinden ayırmalı.

    Kendi `truck_used_count` kopyasını kullanan bir algoritma bu testte
    yakalanır (sayaç 0 kalır).
    """
    sayac = {"n": 0}
    orijinal = FiloHavuzu.ayir

    def sayan_ayir(self, truck):
        sayac["n"] += 1
        return orijinal(self, truck)

    monkeypatch.setattr(FiloHavuzu, "ayir", sayan_ayir)

    calistir = _algoritmalar()[ad]
    with _sessiz():
        calistir(_parcalar(12), _filo())

    assert sayac["n"] > 0, f"{ad} ortak araç açma fonksiyonunu kullanmıyor"


def test_9b_dondurulmus_algoritmalar_kapsam_disi():
    """Karar A: bu üçü ana karşılaştırmada yok, mantıklarına dokunulmadı."""
    assert set(_algoritmalar()) == {
        "FFD", "Greedy", "Layer Building",
        "Tabu", "SA", "Genetic", "Monte Carlo"}


@pytest.mark.parametrize("ad", list(_algoritmalar().keys()))
def test_9c_hicbir_algoritma_tavani_asmiyor(ad):
    """Açılan araç sayısı filo tavanını aşamaz."""
    trucks = _filo()
    tavan = sum(t.available for t in trucks)
    with _sessiz():
        plan = _algoritmalar()[ad](_parcalar(12), trucks)
    assert len([b for b in plan.bins if b]) <= tavan


# ═════════════════════════════════════════════════════════════════════════════
# TEST 10 — göç regresyonu (H kararı)
# ═════════════════════════════════════════════════════════════════════════════

def test_10a_goc_edilmis_arac_ayni_truck3d_yi_veriyor():
    """Eski araç → dorse + tanımsız çekici → Truck3D: ölçü ve kapasite aynı."""
    eski = Truck3D("Buyuk", 240, 600, 200, 24_000, 1)
    dorse, cekici = eski_aractan_donustur(
        "Buyuk", genislik_cm=240, uzunluk_cm=600, yukseklik_cm=200,
        kapasite_kg=24_000)
    yeni = eslesme_to_truck3d(eslesme_hesapla(cekici, dorse))

    assert (yeni.width, yeni.length, yeni.height) == \
           (eski.width, eski.length, eski.height)
    assert yeni.capacity == eski.capacity
    assert yeni.get_volume() == eski.get_volume()
    assert yeni.eslesme is not None
    assert not yeni.eslesme.dingil_kontrol_edilebilir


@pytest.mark.parametrize("ad", ["FFD", "Greedy"])
def test_10b_goc_sonrasi_ayni_plan(ad):
    """thpack / deney örnekleri göçten sonra AYNEN çalışmalı.

    Araç kimliği değişir (ESKI-... öneki), ama yerleşimler birebir aynı
    olmalı — yani göçün kendisi sonucu değiştirmiyor.
    """
    pieces = _parcalar(14)
    eski_filo = [Truck3D("Buyuk", 240, 600, 200, 24_000, 2)]
    yeni_filo = []
    for kopya in range(1, 3):
        dorse, cekici = eski_aractan_donustur(
            "Buyuk", 240, 600, 200, 24_000, kopya_no=kopya)
        yeni_filo.append(eslesme_to_truck3d(eslesme_hesapla(cekici, dorse)))

    calistir = _algoritmalar()[ad]
    with _sessiz():
        plan_eski = calistir(pieces, eski_filo)
        plan_yeni = calistir(pieces, yeni_filo)

    def imza(plan):
        return [[(p.piece_id, p.x, p.y, p.z, p.width, p.length, p.height)
                 for p in b] for b in plan.bins if b]

    assert imza(plan_eski) == imza(plan_yeni)
    assert len(plan_eski.unfitted_pieces or []) == \
        len(plan_yeni.unfitted_pieces or [])


def test_10c_benchmark_kapasitesi_kirpilmiyor():
    """thpack'te kapasite bilerek çok yüksek; KTY 18 t'ye kırpmamalı."""
    dorse, cekici = eski_aractan_donustur("BENCH", 233, 587, 220, 9_999_999.0)
    truck = eslesme_to_truck3d(eslesme_hesapla(cekici, dorse))
    assert truck.capacity == pytest.approx(9_999_999.0)


# ═════════════════════════════════════════════════════════════════════════════
# Çekici + dorse köprüsü (S10: aşağı yuvarlama)
# ═════════════════════════════════════════════════════════════════════════════

def test_mm_cm_asagi_yuvarliyor():
    assert mm_to_cm(13_620) == 1_362          # tam
    assert mm_to_cm(13_629) == 1_362          # aşağı
    assert mm_to_cm(2_480) == 248
    assert mm_to_cm(2_709) == 270


def test_kopru_schmitz_olculeri():
    es = eslesme_hesapla(ford_fmax_4x2(), schmitz_scs_24l())
    t = eslesme_to_truck3d(es)
    assert (t.width, t.length, t.height) == (248, 1_362, 270)
    assert t.capacity == pytest.approx(25_757.0)
    assert t.available == 1
    assert t.id == "54 XYZ 456"               # dorse plakası
    assert t.eslesme is es


def test_havuz_cekici_dorse_eslestirmesi():
    """İki ayrı tavan: çekici ve dorse listeleri."""
    c1, c2 = ford_fmax_4x2(), ford_fmax_4x2()
    c1.cekici_id, c1.plaka = "C1", "34 AAA 111"
    c2.cekici_id, c2.plaka = "C2", "34 BBB 222"
    d1, d2 = schmitz_scs_24l(), schmitz_scs_24l()
    d1.dorse_id, d1.plaka = "D1", "34 XXX 111"
    d2.dorse_id, d2.plaka = "D2", "34 YYY 222"

    havuz = havuz_olustur_cekici_dorse([c1, c2], [d1, d2])
    assert havuz.tavan() == 2
    assert {t.id for t in havuz.trucks} == {"34 XXX 111", "34 YYY 222"}
    # Her çekici en çok bir sefer
    plakalar = {t.eslesme.cekici.plaka for t in havuz.trucks}
    assert plakalar == {"34 AAA 111", "34 BBB 222"}


def test_havuz_bos_cekici_yoksa_dorse_acilamiyor():
    """Çekici sayısı dorse sayısından azsa fazla dorseler havuza girmez."""
    c1 = ford_fmax_4x2()
    d1, d2 = schmitz_scs_24l(), schmitz_scs_24l()
    d1.plaka, d2.plaka = "34 XXX 111", "34 YYY 222"
    havuz = havuz_olustur_cekici_dorse([c1], [d1, d2])
    assert havuz.tavan() == 1


def test_havuz_cekicisiz_filo_bos():
    havuz = havuz_olustur_cekici_dorse([], [schmitz_scs_24l()])
    assert havuz.tavan() == 0
    assert havuz.ac() is None


# ═════════════════════════════════════════════════════════════════════════════
# Eşleştirme dökümü — "bunlar neye göre eşleşti?" (21 Ekim 2026)
# ═════════════════════════════════════════════════════════════════════════════

def _cekici(plaka, bos_agirlik=7_908.0, e=600.0):
    c = ford_fmax_4x2()
    c.cekici_id = c.plaka = plaka
    c.bos_agirlik_kg = bos_agirlik
    c.besinci_teker_ofset_mm = e
    return c


def _dorse(plaka, uzunluk=13_620.0):
    d = schmitz_scs_24l()
    d.dorse_id = d.plaka = plaka
    d.ic_uzunluk_mm = uzunluk
    return d


def test_dokum_havuzla_ayni_eslestirmeyi_veriyor():
    from filo_havuzu import eslestirme_dokumu
    ck = [_cekici("34 A"), _cekici("34 B")]
    dr = [_dorse("34 X"), _dorse("34 Y")]
    dokum = eslestirme_dokumu(ck, dr)
    havuz = havuz_olustur_cekici_dorse(ck, dr)
    assert [(s["cekici"].plaka, s["dorse"].plaka) for s in dokum] == \
        [(t.eslesme.cekici.plaka, t.eslesme.dorse.plaka)
         for t in havuz.trucks]


def test_dokum_esit_adaylarda_liste_sirasi_diyor():
    """Hepsi aynıysa karar üçüncü ölçüte (liste sırası) kalır."""
    from filo_havuzu import eslestirme_dokumu
    dokum = eslestirme_dokumu([_cekici("34 A"), _cekici("34 B")],
                              [_dorse("34 X"), _dorse("34 Y")])
    assert all("liste sırası" in s["neden"] for s in dokum)
    assert [s["cekici"].plaka for s in dokum] == ["34 A", "34 B"]


def test_dokum_faydali_yuk_farkliysa_onu_soyluyor():
    from filo_havuzu import eslestirme_dokumu
    hafif = _cekici("34 HAFIF", bos_agirlik=7_000.0)
    agir = _cekici("34 AGIR", bos_agirlik=8_500.0)
    dokum = eslestirme_dokumu([agir, hafif], [_dorse("34 X")])
    assert dokum[0]["cekici"] is hafif
    assert dokum[0]["neden"] == "en yüksek faydalı yük"


def test_dokum_dingil_payi_esitlik_bozucusunu_soyluyor():
    from filo_havuzu import eslestirme_dokumu
    dar = _cekici("34 DAR", e=900.0)        # kingpin kapasitesi 7.560
    genis = _cekici("34 GENIS", e=600.0)    # kingpin kapasitesi 11.042
    dokum = eslestirme_dokumu([dar, genis], [_dorse("34 X")])
    assert dokum[0]["cekici"] is genis
    assert "dingil payı" in dokum[0]["neden"]


def test_dokum_cekici_yetmezse_soyluyor():
    from filo_havuzu import eslestirme_dokumu
    dokum = eslestirme_dokumu([_cekici("34 A")],
                              [_dorse("34 X"), _dorse("34 Y")])
    assert dokum[0]["cekici"] is not None
    assert dokum[1]["cekici"] is None
    assert "sefer yapamaz" in dokum[1]["neden"]


def test_dokum_dorseleri_hacme_gore_siraliyor():
    """Açma sırası: büyükten küçüğe."""
    from filo_havuzu import eslestirme_dokumu
    kucuk = _dorse("34 KUCUK", uzunluk=7_000.0)
    buyuk = _dorse("34 BUYUK", uzunluk=13_620.0)
    dokum = eslestirme_dokumu([_cekici("34 A"), _cekici("34 B")],
                              [kucuk, buyuk])
    assert [s["dorse"].plaka for s in dokum] == ["34 BUYUK", "34 KUCUK"]
