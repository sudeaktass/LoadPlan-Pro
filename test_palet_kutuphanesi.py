# -*- coding: utf-8 -*-
"""
Standart palet kütüphanesi testleri
====================================
    python -X utf8 -m pytest test_palet_kutuphanesi.py -q

Kabul ölçütleri:
  * Hazır EUR paleti seçilince alanlar kütüphanedeki değerlerle doluyor.
  * ISO paletlerinde yükseklik ve ağırlık BOŞ geliyor (None) ve
    kullanıcıdan isteniyor — tahmini değer yazılmıyor.
  * Özel ölçüyle palet eklemek eskisi gibi çalışıyor (load_rules yolu).
"""

from __future__ import annotations

import pandas as pd
import pytest

import palet_kutuphanesi as pk


# ═════════════════════════════════════════════════════════════════════════════
# Kayıtlar
# ═════════════════════════════════════════════════════════════════════════════

def test_kutuphane_yalniz_belirtilen_kayitlari_iceriyor():
    """Başka araç/palet UYDURULMAMIŞ olmalı."""
    kodlar = {p.kod for p in pk.tum_paletler()}
    assert kodlar == {
        "EUR",
        "ISO-1200x1000", "ISO-1219x1016", "ISO-1165x1165",
        "ISO-1067x1067", "ISO-1100x1100",
    }


def test_eur_degerleri():
    p = pk.palet_bul("EUR")
    assert (p.uzunluk_mm, p.genislik_mm, p.yukseklik_mm) == (1200, 800, 144)
    assert p.bos_agirlik_kg == 25.0
    assert p.dinamik_yuk_kg == 1500.0
    assert p.statik_yuk_kg == 4000.0
    assert p.kaynak == "UIC 435-2 / EPAL (EUR paleti)"
    assert "EPAL resmî föyünden teyit edilecek" in p.dogrulama_durumu
    assert p.eksik_alanlar == []


@pytest.mark.parametrize("kod, uzunluk, genislik", [
    ("ISO-1200x1000", 1200, 1000),
    ("ISO-1219x1016", 1219, 1016),
    ("ISO-1165x1165", 1165, 1165),
    ("ISO-1067x1067", 1067, 1067),
    ("ISO-1100x1100", 1100, 1100),
])
def test_iso_taban_olculeri(kod, uzunluk, genislik):
    p = pk.palet_bul(kod)
    assert (p.uzunluk_mm, p.genislik_mm) == (uzunluk, genislik)
    assert p.kaynak == "ISO 6780:2003"
    assert "standart metni paralı" in p.dogrulama_durumu


@pytest.mark.parametrize("kod", [
    "ISO-1200x1000", "ISO-1219x1016", "ISO-1165x1165",
    "ISO-1067x1067", "ISO-1100x1100"])
def test_iso_bilinmeyen_alanlar_none(kod):
    """Tahmini değer yazılmamalı — bilinmeyen alan None."""
    p = pk.palet_bul(kod)
    assert p.yukseklik_mm is None
    assert p.bos_agirlik_kg is None
    assert p.dinamik_yuk_kg is None
    assert p.statik_yuk_kg is None
    assert set(p.eksik_alanlar) == {
        "yukseklik_mm", "bos_agirlik_kg", "dinamik_yuk_kg", "statik_yuk_kg"}


def test_bilinmeyen_kod_none_donuyor():
    assert pk.palet_bul("YOK") is None


# ═════════════════════════════════════════════════════════════════════════════
# mm → cm (karar S-C: aşağı yuvarlama)
# ═════════════════════════════════════════════════════════════════════════════

def test_eur_olcusu_tam_cm():
    assert pk.olculer_cm(pk.palet_bul("EUR")) == (80, 120)


def test_iso_48x40_asagi_yuvarlaniyor():
    """1219 × 1016 mm → 121 × 101 cm (122 × 102 DEĞİL).

    En yakına yuvarlansaydı palet gerçeğinden ~4 mm büyük görünür ve
    araca sığmayan bir plan üretilebilirdi.
    """
    g, u = pk.olculer_cm(pk.palet_bul("ISO-1219x1016"))
    assert (g, u) == (101, 121)


def test_hicbir_palet_gercekten_buyuk_gorunmuyor():
    for p in pk.tum_paletler():
        g_cm, u_cm = pk.olculer_cm(p)
        assert g_cm * 10 <= p.genislik_mm
        assert u_cm * 10 <= p.uzunluk_mm


# ═════════════════════════════════════════════════════════════════════════════
# Palet darasının otomatik eklenmesi (karar S-A)
# ═════════════════════════════════════════════════════════════════════════════

def test_eur_yukseklik_darasi_ekleniyor():
    toplam, aciklama, uyarilar = pk.toplam_yukseklik_cm(
        pk.palet_bul("EUR"), 125.0)
    assert toplam == pytest.approx(139.4)      # 125 + 14,4
    assert "125.0 (yük)" in aciklama and "14.4 (palet)" in aciklama
    assert uyarilar == []


def test_eur_agirlik_darasi_ekleniyor():
    toplam, aciklama, uyarilar = pk.toplam_agirlik_kg(
        pk.palet_bul("EUR"), 225.0)
    assert toplam == pytest.approx(250.0)      # 225 + 25
    assert "225.0 (yük)" in aciklama and "25.0 (palet)" in aciklama
    assert uyarilar == []


def test_iso_dara_eklenmiyor_ve_uyariyor():
    """Palet ölçüsü bilinmiyorsa TAHMİN YAPILMAZ, uyarı verilir."""
    p = pk.palet_bul("ISO-1200x1000")
    toplam_y, _, uy_y = pk.toplam_yukseklik_cm(p, 125.0)
    toplam_kg, _, uy_kg = pk.toplam_agirlik_kg(p, 225.0)
    assert toplam_y == pytest.approx(125.0)
    assert toplam_kg == pytest.approx(225.0)
    assert uy_y and "eklenemedi" in uy_y[0]
    assert uy_kg and "eklenemedi" in uy_kg[0]


def test_sifir_yuk_bos_paleti_veriyor():
    """Yük 0 girilirse sonuç boş paletin kendisidir."""
    p = pk.palet_bul("EUR")
    assert pk.toplam_yukseklik_cm(p, 0.0)[0] == pytest.approx(14.4)
    assert pk.toplam_agirlik_kg(p, 0.0)[0] == pytest.approx(25.0)


# ═════════════════════════════════════════════════════════════════════════════
# İstif limiti (karar S-B)
# ═════════════════════════════════════════════════════════════════════════════

def test_eur_istif_limiti_dinamik_yuk():
    """Dinamik yük seçilir — istiflemede palet hareket hâlinde taşır."""
    assert pk.istif_limiti_kg(pk.palet_bul("EUR")) == 1500.0


def test_iso_istif_limiti_none():
    assert pk.istif_limiti_kg(pk.palet_bul("ISO-1100x1100")) is None


# ═════════════════════════════════════════════════════════════════════════════
# load_rules hücresi → Piece3D.max_stack_weight
# ═════════════════════════════════════════════════════════════════════════════
# NOT: build_pieces_from_load_rules app_3d.py (Streamlit betiği) içinde
# olduğu için doğrudan import edilemiyor. Bu yüzden hücre okuma mantığı
# palet_kutuphanesi.istif_limiti_oku'ya taşındı ve burada test ediliyor;
# uçtan uca doğrulama test_algoritma_uygunlugu.py ve dogrula_cozum.py ile
# yapılıyor.

@pytest.mark.parametrize("deger, beklenen", [
    (1500.0, 1500.0),
    (1500, 1500.0),
    ("1500", 1500.0),
    (None, None),
    ("", None),
    ("nan", None),
    (float("nan"), None),
    (0, None),
    (-5, None),
    ("abc", None),
    (True, None),
])
def test_istif_limiti_okuma(deger, beklenen):
    assert pk.istif_limiti_oku(deger) == beklenen


def test_bos_hucre_varsayilani_bozmuyor():
    """Boş hücre → Piece3D'nin kendi varsayılanı (1000 kg) kalır."""
    from core_3d import Piece3D
    assert pk.istif_limiti_oku(None) is None
    assert Piece3D(id="x", width=1, length=1, height=1,
                   quantity=1).max_stack_weight == 1000.0


def test_eur_limiti_varsayilandan_buyuk():
    """EUR paleti seçilince istif limiti gerçekten değişiyor."""
    assert pk.istif_limiti_oku(pk.istif_limiti_kg(pk.palet_bul("EUR"))) == 1500.0


def test_load_rules_satiri_sutunsuz_da_okunabiliyor():
    """Eski kayıtlarda sütun yok — .get() None döndürmeli."""
    satir = _load_rules_satiri().drop(columns=["İstif limiti (kg)"])
    assert pk.istif_limiti_oku(
        satir.iloc[0].get("İstif limiti (kg)", None)) is None


def _load_rules_satiri(**kw):
    """Yük Listesi'nin bir satırı (sütun adları app_3d ile aynı)."""
    satir = {
        "Kaynak": "Manuel", "ID": "EUR-1", "Şekil": "Dikdörtgen",
        "G(cm)": 80.0, "U(cm)": 120.0, "Y(cm)": 139.4,
        "Adet": 6, "Ağırlık(kg)": 250.0, "Müşteri": "",
        "Altına yerleştirilemez": False, "Üstüne yerleştirilemez": False,
        "Rotasyon": True, "Min. Aralık (cm)": 0, "Öncelik": None,
        "İstif limiti (kg)": None,
    }
    satir.update(kw)
    return pd.DataFrame([satir])


def test_hazir_palet_satiri_yuk_listesi_sutunlariyla_uyumlu():
    """Eklenen satır, mevcut Yük Listesi sütunlarını birebir karşılıyor."""
    p = pk.palet_bul("EUR")
    g_cm, u_cm = pk.olculer_cm(p)
    toplam_y = pk.toplam_yukseklik_cm(p, 125.0)[0]
    toplam_kg = pk.toplam_agirlik_kg(p, 225.0)[0]
    satir = _load_rules_satiri(**{"G(cm)": g_cm, "U(cm)": u_cm,
                                  "Y(cm)": round(toplam_y, 1),
                                  "Ağırlık(kg)": round(toplam_kg, 1),
                                  "İstif limiti (kg)": pk.istif_limiti_kg(p)})
    r = satir.iloc[0]
    assert (r["G(cm)"], r["U(cm)"]) == (80, 120)
    assert r["Y(cm)"] == pytest.approx(139.4)
    assert r["Ağırlık(kg)"] == pytest.approx(250.0)
    assert pk.istif_limiti_oku(r["İstif limiti (kg)"]) == 1500.0
