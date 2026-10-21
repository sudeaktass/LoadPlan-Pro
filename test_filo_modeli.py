# -*- coding: utf-8 -*-
"""
Filo veri modeli testleri (1. adım)
====================================
Plan: Makaleler/FILO_UYGULAMA_PLANI.md Bölüm 13, testler 1–8.

Çalıştırma:
    python -X utf8 -m pytest test_filo_modeli.py -q

Kapsam dışı (sonraki adımlarda):
  * test 9  — entegrasyon (7 algoritma ortak fonksiyonu çağırıyor mu) → 2. adım
  * test 10 — göç regresyonu (thpack9) → 2. adım
  * test 11 — ortak açma fonksiyonu → 2. adım
  * test 12 — "her yerleştirme" ↔ "yalnız rapor" karşılaştırması → 3. adım
  * "bağlayıcı ölçü" seçimi → S11 kararı bekliyor
"""

from __future__ import annotations

import pytest

from dingil_yuku import (
    KIP_HER_YERLESTIRME,
    KIP_YALNIZCA_RAPOR,
    DingilIzleyici,
    arac_dingil_raporu,
    kingpin_cekiciye_dagit,
    parca_payi,
)
from doluluk import AracDoluluk, PlanDoluluk
from filo_modeli import (
    Cekici,
    Dorse,
    cekici_ata,
    eski_aractan_donustur,
    eslesme_hesapla,
)
from mevzuat_kty import dingil_grubu_siniri, yasal_toplam_agirlik
from ornek_filo import POLLARIS_2016, ford_fmax_4x2, schmitz_scs_24l

T = 1_000.0   # ton → kg


# ═════════════════════════════════════════════════════════════════════════════
# TEST 1 — Ford + Schmitz: yasal toplam ve faydalı yük
# ═════════════════════════════════════════════════════════════════════════════

def test_1_ford_schmitz_faydali_yuk():
    es = eslesme_hesapla(ford_fmax_4x2(), schmitz_scs_24l())

    # 2 + 3 = 5 dingil → KTY md.128, 5+ dingilli yarı römorklu → 40 t
    assert es.yasal_toplam_kg == 40_000
    assert "5+ dingilli" in es.yasal_toplam_kaynak
    assert "KTY md.128" in es.yasal_toplam_kaynak

    # 40.000 − 7.908 − 6.335 = 25.757
    assert es.faydali_yuk_kg == pytest.approx(25_757.0)

    # Dorse teknik sınırı (39.000 − 6.335 = 32.665) BAĞLAMAZ
    assert "5+ dingilli" in es.faydali_yuk_kaynak
    assert any("32.665" in s for s in es.baglamayan_sinirlar)

    # Çekici teknik GCW 44.000 da bağlamaz (yasal 40.000 daha küçük)
    assert any("44.000" in s for s in es.baglamayan_sinirlar)


def test_1b_ic_hacim_hesaplaniyor():
    d = schmitz_scs_24l()
    # 13.620 × 2.480 × 2.700 mm ≈ 91,2 m³
    assert d.ic_hacim_m3 == pytest.approx(91.20, abs=0.01)


def test_1c_dorse_teknik_siniri_baglarsa():
    """Teknik azami düşükse faydalı yükü o bağlar."""
    d = schmitz_scs_24l()
    d.teknik_azami_kg = 30_000.0        # 30.000 − 6.335 = 23.665 < 25.757
    es = eslesme_hesapla(ford_fmax_4x2(), d)
    assert es.faydali_yuk_kg == pytest.approx(23_665.0)
    assert "dorse föyü" in es.faydali_yuk_kaynak


# ═════════════════════════════════════════════════════════════════════════════
# TEST 2 — 44 t konteyner istisnası
# ═════════════════════════════════════════════════════════════════════════════

def test_2a_konteyner_bayragi_iki_dingilli_cekici():
    """Bayrak açık ama çekici 2 dingilli → 40 t + uyarı."""
    deger, kaynak, uyarilar = yasal_toplam_agirlik(
        cekici_dingil_sayisi=2, dorse_dingil_sayisi=3, iso_40ft_konteyner=True)
    assert deger == 40_000
    assert uyarilar, "uyarı verilmeli"
    assert any("3 dingilli çekici" in u for u in uyarilar)


def test_2b_konteyner_bayragi_uc_dingilli_cekici():
    """Bayrak açık ve çekici 3 dingilli → 44 t."""
    deger, kaynak, uyarilar = yasal_toplam_agirlik(
        cekici_dingil_sayisi=3, dorse_dingil_sayisi=3, iso_40ft_konteyner=True)
    assert deger == 44_000
    assert "konteyner" in kaynak
    assert not uyarilar


def test_2c_konteyner_bayragi_eslesmede():
    """Eşleşme üzerinden: uyarı kullanıcıya ulaşıyor mu."""
    d = schmitz_scs_24l()
    d.iso_40ft_konteyner = True
    es = eslesme_hesapla(ford_fmax_4x2(), d)       # çekici 2 dingilli
    assert es.yasal_toplam_kg == 40_000
    assert any("44 t istisnası" in u for u in es.uyarilar)


# ═════════════════════════════════════════════════════════════════════════════
# TEST 3 — Tridem dingil aralığı ve KTY boşluğu
# ═════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("aralik_mm, beklenen", [
    (1_300.0, 21_000),      # sınır noktası: tam 1,30 m → 21 t
    (1_250.0, 21_000),
    (1_310.0, 24_000),      # Schmitz SCS 24/L
    (1_400.0, 24_000),      # sınır noktası: tam 1,40 m → 24 t
])
def test_3a_tridem_kty_degerleri(aralik_mm, beklenen):
    deger, kaynak, uyarilar = dingil_grubu_siniri(3, aralik_mm)
    assert deger == beklenen
    assert "KTY md.128" in kaynak


def test_3b_tridem_kty_boslugu():
    """d > 1,4 m → KTY'de değer YOK; uydurulmaz."""
    deger, kaynak, uyarilar = dingil_grubu_siniri(3, 1_450.0)
    assert deger is None
    assert uyarilar
    assert any("1,4 m" in u for u in uyarilar)


def test_3c_boslukta_foy_degeri_kullaniliyor():
    """KTY değeri yoksa föy değeri bağlar ve uyarı taşınır."""
    d = schmitz_scs_24l()
    d.dingil_araligi_mm = 1_450.0
    deger, kaynak, uyarilar = d.dingil_grubu_siniri_kg()
    assert deger == 24_000                  # föydeki değer
    assert "föy" in kaynak
    assert any("1,4 m" in u for u in uyarilar)


def test_3d_iki_dingilli_grup_sinirlari():
    """İki dingilli grup tablosunun sınır noktaları."""
    assert dingil_grubu_siniri(2, 900.0)[0] == 11_000      # d < 1,0
    assert dingil_grubu_siniri(2, 1_000.0)[0] == 16_000    # 1,0 ≤ d ≤ 1,3
    assert dingil_grubu_siniri(2, 1_300.0)[0] == 16_000
    assert dingil_grubu_siniri(2, 1_301.0)[0] == 18_000    # 1,3 < d < 1,8
    assert dingil_grubu_siniri(2, 1_800.0)[0] == 20_000    # d ≥ 1,8


def test_3e_dingil_araligi_girilmemis():
    deger, kaynak, uyarilar = dingil_grubu_siniri(3, None)
    assert deger is None
    assert any("aralığı girilmedi" in u for u in uyarilar)


# ═════════════════════════════════════════════════════════════════════════════
# TEST 4 — Pollaris ve ark. (2016) sayıları
# ═════════════════════════════════════════════════════════════════════════════

def test_4a_pollaris_faydali_yuk():
    """44 − 6,82 − 3 − 2 = 32,18 t; makale 32,2 t olarak yuvarlıyor.

    Makaledeki iki yuvarlama (not):
      * faydalı yük 32,18 → 32,2 t
      * boş çekici 6,82 t, ama dingil dağılımı 4,88 + 1,97 = 6,85 t
    Bu farklar makalenin kendi yuvarlamalarıdır, bizim hesabımızda değil.
    """
    p = POLLARIS_2016
    faydali = (p["yasal_toplam_t"] - p["bos_cekici_t"]
               - p["konteyner_dara_t"] - p["bos_dorse_t"])
    assert faydali == pytest.approx(32.18, abs=0.001)
    assert round(faydali, 1) == p["faydali_yuk_t"]      # makaledeki 32,2
    # Dingil dağılımındaki yuvarlama farkı 0,03 t'yi aşmıyor
    assert abs((p["bos_cekici_on_t"] + p["bos_cekici_tahrik_t"])
               - p["bos_cekici_t"]) <= 0.03


def test_4b_pollaris_kaplin_ve_tridem():
    """Kaplin: 13,6 − 2 = 11,6 t · Tridem: 24 − 2 − 1 = 21 t"""
    p = POLLARIS_2016
    kaplin_yuk = p["kaplin_sinir_t"] - p["konteyner_dara_kingpin_t"]
    assert kaplin_yuk == pytest.approx(11.6)

    tridem_yuk = (p["tridem_sinir_t"] - p["bos_dorse_t"]
                  - p["konteyner_dara_grup_t"])
    assert tridem_yuk == pytest.approx(21.0)


def test_4c_pollaris_kaldirac_c1_d55():
    """Kaldıraç kuralı, c = 1 m ve d = 5,5 m ile."""
    c, d = POLLARIS_2016["c_mm"], POLLARIS_2016["d_mm"]
    w = 1_000.0

    # Kingpinin tam üstünde (CG = c) → grup payı 0
    kingpin, grup = parca_payi(w, cg_mm=c, c_mm=c, d_mm=d)
    assert grup == pytest.approx(0.0)
    assert kingpin == pytest.approx(w)

    # Dingil grubunun tam üstünde (CG = c + d) → kingpin payı 0
    kingpin, grup = parca_payi(w, cg_mm=c + d, c_mm=c, d_mm=d)
    assert kingpin == pytest.approx(0.0)
    assert grup == pytest.approx(w)

    # Tam ortada → yarı yarıya
    kingpin, grup = parca_payi(w, cg_mm=c + d / 2, c_mm=c, d_mm=d)
    assert kingpin == pytest.approx(500.0)
    assert grup == pytest.approx(500.0)


def test_4d_pollaris_kingpin_80_20():
    """Pollaris kingpini sabit %80 tahrik / %20 ön bölüyor.

    Bizim moment yöntemimiz e/WB = 0,20 alındığında aynı sonucu verir.
    """
    p = POLLARIS_2016
    kingpin = 500.0
    wb = 3_600.0
    e = wb * p["kingpin_on_payi"]          # e/WB = 0,20

    on, tahrik = kingpin_cekiciye_dagit(kingpin, e_mm=e, wb_mm=wb)
    assert on == pytest.approx(kingpin * p["kingpin_on_payi"])
    assert tahrik == pytest.approx(kingpin * p["kingpin_tahrik_payi"])
    assert on + tahrik == pytest.approx(kingpin)


# ═════════════════════════════════════════════════════════════════════════════
# TEST 5 — Kaldıraç uç durumları (negatif pay geçerli)
# ═════════════════════════════════════════════════════════════════════════════

def test_5a_grubun_arkasinda_kingpin_payi_negatif():
    d = schmitz_scs_24l()
    c, dd = d.c_mm, d.d_mm                  # 1.690 / 7.700
    grup_merkezi = c + dd                   # 9.390 mm

    kingpin, grup = parca_payi(1_000.0, cg_mm=grup_merkezi + 2_000.0,
                               c_mm=c, d_mm=dd)
    assert kingpin < 0, "grubun arkasındaki parça kingpini kaldırır"
    assert grup > 1_000.0
    assert kingpin + grup == pytest.approx(1_000.0)


def test_5b_kingpinin_onunde_grup_payi_negatif():
    d = schmitz_scs_24l()
    c, dd = d.c_mm, d.d_mm
    kingpin, grup = parca_payi(1_000.0, cg_mm=0.0, c_mm=c, d_mm=dd)
    assert grup < 0, "kingpinin önündeki parça grubu kaldırır"
    assert kingpin > 1_000.0
    assert kingpin + grup == pytest.approx(1_000.0)


def test_5c_paylarin_toplami_korunur():
    """Her konumda kingpin + grup = parça ağırlığı."""
    d = schmitz_scs_24l()
    for cg in (0.0, 1_690.0, 5_000.0, 9_390.0, 13_620.0):
        kingpin, grup = parca_payi(850.0, cg, d.c_mm, d.d_mm)
        assert kingpin + grup == pytest.approx(850.0)


def test_5d_d_sifir_hata_veriyor():
    with pytest.raises(ValueError):
        parca_payi(100.0, 5_000.0, 1_000.0, 0.0)


# ═════════════════════════════════════════════════════════════════════════════
# TEST 6 — e duyarlılığı (D kararının dayanağı)
# ═════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("e_mm, beklenen_kapasite", [
    (0.0,   9_202.0 * 3_600.0 / 3_600.0),                 # yalnız tahrik bağlar
    (600.0, 9_202.0 * 3_600.0 / 3_000.0),                 # 11.042,4
    (900.0, 1_890.0 * 3_600.0 / 900.0),                   # 7.560 — ön dingil bağlar
])
def test_6a_kingpin_kapasitesi_e_ile_degisiyor(e_mm, beklenen_kapasite):
    """Çekicinin kaldırabileceği en büyük kingpin yükü e'ye bağlı.

    Ön dingil boşluğu  : 7.500 − 5.610 = 1.890 kg
    Tahrik boşluğu     : 11.500 − 2.298 = 9.202 kg
    """
    c = ford_fmax_4x2()
    c.besinci_teker_ofset_mm = e_mm
    assert c.kingpin_kapasitesi_kg() == pytest.approx(beklenen_kapasite, abs=1.0)


def test_6b_e_900_tam_yuku_engelliyor():
    """e = 900 mm'de yük ≈ 25.225 kg ile sınırlanır (tam yük 25.757).

    Tam yükte dorse üzerindeki ağırlık 25.757 + 6.335 = 32.092 kg. Grup
    en çok 24.000 kg alabildiği için kingpin en az 8.092 kg almak zorunda.
    e = 900 mm'de çekici yalnız 7.560 kg kaldırabiliyor → tam yük geçersiz.
    """
    cekici = ford_fmax_4x2()
    dorse = schmitz_scs_24l()
    es = eslesme_hesapla(cekici, dorse)
    tam_yuk = es.faydali_yuk_kg                  # 25.757
    grup_siniri = es.dingil_sinirlari.dingil_grubu_kg   # 24.000

    gereken_kingpin = (tam_yuk + dorse.bos_agirlik_kg) - grup_siniri
    assert gereken_kingpin == pytest.approx(8_092.0)

    # e = 600 → mümkün
    assert cekici.kingpin_kapasitesi_kg() > gereken_kingpin

    # e = 900 → mümkün değil, sınır ≈ 25.225 kg
    cekici.besinci_teker_ofset_mm = 900.0
    kapasite = cekici.kingpin_kapasitesi_kg()
    assert kapasite < gereken_kingpin
    azami_yuk = kapasite + grup_siniri - dorse.bos_agirlik_kg
    assert azami_yuk == pytest.approx(25_225.0, abs=1.0)


def test_6c_e_varsayim_olarak_isaretli():
    c = ford_fmax_4x2()
    assert "besinci_teker_ofset_mm" in c.varsayim_alanlari
    assert "VARSAYIM" in c.varsayim_alanlari["besinci_teker_ofset_mm"]


# ═════════════════════════════════════════════════════════════════════════════
# TEST 7 — U_V ile U_W ayrışması
# ═════════════════════════════════════════════════════════════════════════════

def test_7a_agir_kucuk_yuk_agirlikta_doluyor():
    """Yoğun yük: ağırlık dolar, hacim boş kalır (Mackie & Harding 1982)."""
    a = AracDoluluk(etiket="ağır", gercek_hacim=10.0, arac_hacim=91.2,
                    yuk_kg=24_000.0, faydali_yuk_kg=25_757.0)
    assert a.u_v == pytest.approx(0.1096, abs=0.001)
    assert a.u_w == pytest.approx(0.9318, abs=0.001)
    assert a.u_w > a.u_v


def test_7b_hafif_hacimli_yuk_hacimde_doluyor():
    a = AracDoluluk(etiket="hafif", gercek_hacim=85.0, arac_hacim=91.2,
                    yuk_kg=3_000.0, faydali_yuk_kg=25_757.0)
    assert a.u_v == pytest.approx(0.9320, abs=0.001)
    assert a.u_w == pytest.approx(0.1165, abs=0.001)
    assert a.u_v > a.u_w


def test_7c_toplam_oran_arac_ortalamasindan_ayrisiyor():
    """Heterojen filoda U_V toplam oranı ile araç ortalaması farklıdır."""
    plan = PlanDoluluk(araclar=[
        AracDoluluk(etiket="büyük", gercek_hacim=80.0, arac_hacim=91.2,
                    yuk_kg=20_000.0, faydali_yuk_kg=25_757.0,
                    bos_agirlik_kg=14_243.0),
        AracDoluluk(etiket="küçük", gercek_hacim=10.0, arac_hacim=40.0,
                    yuk_kg=2_000.0, faydali_yuk_kg=12_000.0,
                    bos_agirlik_kg=9_000.0),
    ])
    toplam = plan.u_v                     # 90 / 131,2
    ortalama = plan.u_v_ortalama          # (0,877 + 0,250) / 2
    assert toplam == pytest.approx(90.0 / 131.2, abs=0.001)
    assert ortalama == pytest.approx((80 / 91.2 + 10 / 40) / 2, abs=0.001)
    assert abs(toplam - ortalama) > 0.05, "ayrışma görünür olmalı"

    assert plan.u_v_en_dusuk == pytest.approx(0.25, abs=0.001)
    assert plan.arac_sayisi == 2
    # Toplam boş ağırlık YALNIZ raporlanır (K1'in 2. ölçütü karara bağlı değil)
    assert plan.toplam_bos_agirlik_kg == pytest.approx(23_243.0)


def test_7d_sifir_payda_none_donuyor():
    a = AracDoluluk(gercek_hacim=5.0, arac_hacim=0.0,
                    yuk_kg=100.0, faydali_yuk_kg=0.0)
    assert a.u_v is None
    assert a.u_w is None
    assert PlanDoluluk(araclar=[]).u_v is None


# ═════════════════════════════════════════════════════════════════════════════
# TEST 8 — Schmitz föy değerleri ve tutarlılık kontrolleri
# ═════════════════════════════════════════════════════════════════════════════

def test_8a_kingpin_olculeri_ic_eksene_cevriliyor():
    """F kararı: c = kingpin_on_kenar − on_duvar_kalinligi."""
    d = schmitz_scs_24l()
    assert d.kingpin_on_kenar_mesafe_mm == 1_690.0
    assert d.c_mm == 1_690.0                      # duvar kalınlığı 0

    d.on_duvar_kalinligi_mm = 40.0
    assert d.c_mm == 1_650.0


def test_8b_c_arti_d_yuk_alani_icinde():
    d = schmitz_scs_24l()
    assert d.c_mm + d.d_mm == 9_390.0
    assert d.c_mm + d.d_mm < d.ic_uzunluk_mm
    assert d.tutarlilik_uyarilari() == []


def test_8c_grup_yuk_alani_disinda_uyari():
    d = schmitz_scs_24l()
    d.kingpin_dingil_grubu_mesafe_mm = 13_000.0   # 1.690 + 13.000 > 13.620
    uyarilar = d.tutarlilik_uyarilari()
    assert any("yük alanının dışında" in u for u in uyarilar)


def test_8d_duvar_kalinligi_kingpinden_buyukse_uyari():
    d = schmitz_scs_24l()
    d.on_duvar_kalinligi_mm = 2_000.0             # c negatif çıkar
    assert any("ön duvarın önünde" in u for u in d.tutarlilik_uyarilari())


def test_8e_bos_dorse_payi_varsayimi():
    """Föyde boş dingil yükleri yoksa ağırlık merkezi ortada varsayılır."""
    d = schmitz_scs_24l()
    kingpin, grup, kaynak, uyarilar = d.bos_agirlik_payi()
    assert kaynak == "varsayım"
    assert uyarilar and "VARSAYIM" in uyarilar[0]
    assert kingpin + grup == pytest.approx(6_335.0)
    # cg = 13.620/2 = 6.810 → grup = 6.335 × (6.810−1.690)/7.700 ≈ 4.212
    assert grup == pytest.approx(4_212.1, abs=1.0)
    assert kingpin == pytest.approx(2_122.9, abs=1.0)


def test_8f_elle_girilen_pay_varsayimi_kaldiriyor():
    d = schmitz_scs_24l()
    d.bos_kingpin_payi_kg = 2_300.0
    d.bos_dingil_grubu_payi_kg = 4_035.0
    d.bos_payi_kaynagi = "föy"
    kingpin, grup, kaynak, uyarilar = d.bos_agirlik_payi()
    assert kaynak == "föy"
    assert uyarilar == []
    assert kingpin == 2_300.0 and grup == 4_035.0


# ═════════════════════════════════════════════════════════════════════════════
# Dingil izleyici — artımlı hesap ve kipler
# ═════════════════════════════════════════════════════════════════════════════

def test_izleyici_bos_araci_gecerli_buluyor():
    es = eslesme_hesapla(ford_fmax_4x2(), schmitz_scs_24l())
    assert es.dingil_kontrol_edilebilir
    sonuc = DingilIzleyici(es).sonuc()
    assert sonuc.gecerli, [str(i) for i in sonuc.ihlaller]
    # Boş araç: ön 5.610 + kingpin payı, tahrik 2.298 + kingpin payı
    assert sonuc.yukler.toplam_kg == pytest.approx(7_908.0 + 6_335.0)


def test_izleyici_artimli_toplam_tek_seferlikle_ayni():
    """Artımlı toplam ile tek seferlik rapor aynı sonucu vermeli."""
    es = eslesme_hesapla(ford_fmax_4x2(), schmitz_scs_24l())
    yukler = [(1_200.0, 2_000.0), (900.0, 5_500.0), (1_500.0, 9_000.0)]

    izleyici = DingilIzleyici(es, kip=KIP_YALNIZCA_RAPOR)
    for w, cg in yukler:
        izleyici.ekle(w, cg)
    a = izleyici.sonuc().yukler
    b = arac_dingil_raporu(es, yukler).yukler

    assert a.kingpin_kg == pytest.approx(b.kingpin_kg)
    assert a.dingil_grubu_kg == pytest.approx(b.dingil_grubu_kg)
    assert a.on_dingil_kg == pytest.approx(b.on_dingil_kg)
    assert a.toplam_kg == pytest.approx(b.toplam_kg)


def test_izleyici_one_yiginca_on_dingili_asiyor():
    """Yük öne yığıldığında toplam sınırın altındayken dingil aşılabilir.

    Yükleme Yönetmeliği md. 6(1)(b)'nin kodda somutlaşması.
    """
    es = eslesme_hesapla(ford_fmax_4x2(), schmitz_scs_24l())
    izleyici = DingilIzleyici(es, kip=KIP_HER_YERLESTIRME)

    # 10 t'lik yükü dorsenin en önüne koy → kingpin payı çok büyük
    uygun, ihlal_kg, ihlaller = izleyici.aday_uygun_mu(10_000.0, cg_mm=200.0)
    assert not uygun
    assert ihlal_kg > 0
    adlar = {i.ad for i in ihlaller}
    assert adlar & {"ön dingil", "tahrik dingili", "kingpin"}
    # Toplam sınır AŞILMADI — ihlal yalnız dingil kaynaklı
    assert "toplam" not in adlar

    # aday_uygun_mu YAN ETKİSİZDİR (motor her aday konum için çağırıyor);
    # sayacı çağıran taraf parça düzeyinde artırır.
    assert izleyici.red_sayisi == 0
    izleyici.kaydet_red()
    assert izleyici.red_sayisi == 1


def test_izleyici_yalnizca_rapor_kipi_reddetmiyor():
    es = eslesme_hesapla(ford_fmax_4x2(), schmitz_scs_24l())
    izleyici = DingilIzleyici(es, kip=KIP_YALNIZCA_RAPOR)
    uygun, ihlal_kg, ihlaller = izleyici.aday_uygun_mu(10_000.0, cg_mm=200.0)
    assert uygun, "yalnızca rapor kipinde reddedilmez"
    assert ihlaller, "ama ihlal bildirilir"
    izleyici.kaydet_ara_durum()
    assert izleyici.ara_durum_reti == 1
    assert izleyici.red_sayisi == 0


def test_izleyici_ihlal_kg_toplami_katsayisiz():
    """İhlal ölçüsü = aşılan kg'ların toplamı; ceza katsayısı yok."""
    es = eslesme_hesapla(ford_fmax_4x2(), schmitz_scs_24l())
    izleyici = DingilIzleyici(es, kip=KIP_YALNIZCA_RAPOR)
    izleyici.ekle(20_000.0, cg_mm=500.0)
    sonuc = izleyici.sonuc()
    assert not sonuc.gecerli
    assert sonuc.ihlal_kg == pytest.approx(
        sum(i.asim_kg for i in sonuc.ihlaller))


# ═════════════════════════════════════════════════════════════════════════════
# Çekici eşleştirme (C kararı)
# ═════════════════════════════════════════════════════════════════════════════

def test_eslestirme_en_yuksek_faydali_yuku_seciyor():
    hafif = ford_fmax_4x2()
    hafif.cekici_id, hafif.plaka = "C-HAFIF", "34 AAA 111"
    hafif.bos_agirlik_kg = 7_000.0            # daha hafif → daha çok faydalı yük

    agir = ford_fmax_4x2()
    agir.cekici_id, agir.plaka = "C-AGIR", "34 BBB 222"
    agir.bos_agirlik_kg = 8_500.0

    secilen, es = cekici_ata(schmitz_scs_24l(), [agir, hafif])
    assert secilen is hafif
    assert es.faydali_yuk_kg == pytest.approx(40_000 - 7_000 - 6_335)


def test_eslestirme_esitlikte_dingil_payi_belirliyor():
    """Faydalı yük eşitse dingil payı geniş olan kazanır."""
    dar = ford_fmax_4x2()
    dar.cekici_id, dar.plaka = "C-DAR", "34 CCC 333"
    dar.besinci_teker_ofset_mm = 900.0        # kapasite 7.560

    genis = ford_fmax_4x2()
    genis.cekici_id, genis.plaka = "C-GENIS", "34 DDD 444"
    genis.besinci_teker_ofset_mm = 600.0      # kapasite 11.042

    secilen, _ = cekici_ata(schmitz_scs_24l(), [dar, genis])
    assert secilen is genis


def test_eslestirme_bos_cekici_yoksa_none():
    secilen, es = cekici_ata(schmitz_scs_24l(), [])
    assert secilen is None and es is None


def test_eslestirme_tekrarlanabilir():
    """Her şey eşitse liste sırası belirler → aynı girdi aynı sonuç."""
    a, b = ford_fmax_4x2(), ford_fmax_4x2()
    a.plaka, b.plaka = "34 AAA 111", "34 BBB 222"
    for _ in range(3):
        secilen, _ = cekici_ata(schmitz_scs_24l(), [a, b])
        assert secilen is a


# ═════════════════════════════════════════════════════════════════════════════
# Göç (H kararı)
# ═════════════════════════════════════════════════════════════════════════════

def test_goc_eski_kapasite_aynen_korunuyor():
    """Eski araç kapasitesi KTY tablosuyla KIRPILMAMALI.

    Benchmark'ta (thpack) kapasite bilerek çok yüksek veriliyor; KTY
    uygulanırsa 18 t'ye kırpılır ve eski sonuçlar bozulurdu.
    """
    dorse, cekici = eski_aractan_donustur(
        "BENCH", genislik_cm=233, uzunluk_cm=587, yukseklik_cm=220,
        kapasite_kg=9_999_999.0)
    es = eslesme_hesapla(cekici, dorse)
    assert es.faydali_yuk_kg == pytest.approx(9_999_999.0)


def test_goc_olculer_mm_ye_cevriliyor():
    dorse, _ = eski_aractan_donustur(
        "Büyük-1", genislik_cm=240, uzunluk_cm=600, yukseklik_cm=270,
        kapasite_kg=8_000.0)
    assert (dorse.ic_genislik_mm, dorse.ic_uzunluk_mm, dorse.ic_yukseklik_mm) \
        == (2_400.0, 6_000.0, 2_700.0)


def test_goc_dingil_kontrolu_sessizce_atlanmiyor():
    """H şartı: uyarı görünür olmalı."""
    dorse, cekici = eski_aractan_donustur(
        "Orta-1", 180, 420, 220, 7_000.0)
    es = eslesme_hesapla(cekici, dorse)
    assert not es.dingil_kontrol_edilebilir
    assert any("çekici tanımsız" in u for u in es.uyarilar)
    assert any("dingil kontrolü yapılamadı" in u for u in es.uyarilar)

    sonuc = DingilIzleyici(es).sonuc()
    assert not sonuc.kontrol_edildi
    assert not sonuc.gecerli, "kontrol yapılamadıysa 'geçerli' denmez"
    assert any("çekici tanımsız" in u for u in sonuc.uyarilar)


def test_goc_edilmis_arac_yerlestirmeyi_engellemiyor():
    """Dingil verisi yoksa aday konumlar reddedilmez (eski davranış)."""
    dorse, cekici = eski_aractan_donustur("X", 240, 600, 270, 8_000.0)
    izleyici = DingilIzleyici(eslesme_hesapla(cekici, dorse))
    uygun, ihlal_kg, _ = izleyici.aday_uygun_mu(5_000.0, cg_mm=100.0)
    assert uygun and ihlal_kg == 0.0


# ═════════════════════════════════════════════════════════════════════════════
# Eksik veri davranışı
# ═════════════════════════════════════════════════════════════════════════════

def test_eksik_dingil_verisi_raporlaniyor():
    cekici = ford_fmax_4x2()
    cekici.dingil_mesafesi_mm = None
    es = eslesme_hesapla(cekici, schmitz_scs_24l())
    assert not es.dingil_kontrol_edilebilir
    assert "dingil_mesafesi_mm" in es.eksik_alanlar
    assert any("eksik veri" in u for u in es.uyarilar)
    # Kütle kapasitesi yine hesaplanır
    assert es.faydali_yuk_kg == pytest.approx(25_757.0)


def test_eksik_teknik_sinirlar_uyari_veriyor():
    cekici = ford_fmax_4x2()
    cekici.teknik_gcw_kg = None
    dorse = schmitz_scs_24l()
    dorse.teknik_azami_kg = None
    es = eslesme_hesapla(cekici, dorse)
    assert any("teknik GCW girilmedi" in u for u in es.uyarilar)
    assert any("teknik azami" in u for u in es.uyarilar)
    assert es.faydali_yuk_kg == pytest.approx(25_757.0)


def test_kingpin_kapasitesi_eksik_veride_none():
    cekici = ford_fmax_4x2()
    cekici.bos_on_dingil_kg = None
    assert cekici.kingpin_kapasitesi_kg() is None


def test_tahrik_siniri_kty_ile_kirpilir():
    """Föy değeri KTY'den büyükse KTY bağlar (min(yasal, teknik))."""
    cekici = ford_fmax_4x2()
    cekici.tahrik_dingil_izin_kg = 13_000.0
    assert cekici.tahrikli_dingil_siniri_kg == 11_500.0


def test_on_dingil_siniri_foy_ile_kirpilir():
    """Ford föyü 7.500 kg → KTY'nin 10 t'sinden küçük, föy bağlar."""
    assert ford_fmax_4x2().on_dingil_siniri_kg == 7_500.0
