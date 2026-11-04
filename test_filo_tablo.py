# -*- coding: utf-8 -*-
"""
Filo tablosunda doğrudan düzenleme testleri
===========================================
    python -X utf8 -m pytest test_filo_tablo.py -q

Kabul ölçütü (Sude, 21 Ekim 2026):
  "zaten tabloda alan veriyi değiştiremiyorum" → tablodaki hücre
  değiştirilip kaydedilebilmeli, hesaplanan sütunlar korunmalı, hatalı
  satır kaydedilmemeli.

Buradaki testler arayüzü değil, arayüzün dayandığı SAF mantığı ölçer:
değişiklik bulma, tür çevirimi, doğrulama ve Lift-Top kuralı.
"""

from __future__ import annotations

import dataclasses

import pandas as pd
import pytest

from filo_modeli import Cekici, Dorse
from filo_sayfasi import (_ayni_mi, _cekici_dogrula, _dorse_dogrula,
                          _dorse_listesi, _dorse_tavan_kurali, _hucre_cevir,
                          _tablo_farklari, _DORSE_TIPLERI)


# ═════════════════════════════════════════════════════════════════════════════
# Yardımcılar
# ═════════════════════════════════════════════════════════════════════════════

def _dorse(plaka="34 AAA 001", **ek):
    varsayilan = dict(dorse_id=plaka, plaka=plaka, tip="tenteli",
                      ic_uzunluk_mm=13_620.0, ic_genislik_mm=2_480.0,
                      ic_yukseklik_mm=2_700.0, bos_agirlik_kg=6_300.0,
                      dingil_sayisi=3)
    varsayilan.update(ek)
    return Dorse(**varsayilan)


def _cekici(plaka="34 CCC 001", **ek):
    varsayilan = dict(cekici_id=plaka, plaka=plaka, bos_agirlik_kg=7_800.0,
                      dingil_sayisi=2)
    varsayilan.update(ek)
    return Cekici(**varsayilan)


# Tablodaki birkaç sütunu temsil eden küçük bir eşleme
_SUTUNLAR = {
    "Tip": ("tip", "metin"),
    "Z · yükseklik (mm)": ("ic_yukseklik_mm", "ondalik"),
    "Z max (Lift-Top)": ("yukseklik_max_mm", "ondalik_bos"),
    "Dingil": ("dingil_sayisi", "tam"),
    "40 ft": ("iso_40ft_konteyner", "kutu"),
}


def _satirlar():
    return [
        {"Plaka": "34 AAA 001", "Tip": "tenteli",
         "Z · yükseklik (mm)": 2_700.0, "Z max (Lift-Top)": None,
         "Dingil": 3, "40 ft": False, "İç hacim (m³)": 91.2},
        {"Plaka": "34 BBB 002", "Tip": "mega",
         "Z · yükseklik (mm)": 3_000.0, "Z max (Lift-Top)": None,
         "Dingil": 3, "40 ft": False, "İç hacim (m³)": 101.4},
    ]


# ═════════════════════════════════════════════════════════════════════════════
# Hücre karşılaştırma ve tür çevirimi
# ═════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("a,b", [
    (None, None), (float("nan"), None), (None, float("nan")),
    (2700, 2700.0), ("tenteli", "tenteli"), (True, True),
])
def test_ayni_sayilan_degerler(a, b):
    assert _ayni_mi(a, b)


@pytest.mark.parametrize("a,b", [
    (None, 0.0), (2700.0, 2800.0), ("tenteli", "mega"), (True, False),
])
def test_farkli_sayilan_degerler(a, b):
    assert not _ayni_mi(a, b)


def test_bos_hucre_turune_gore_cevriliyor():
    assert _hucre_cevir(None, "metin") == ""
    assert _hucre_cevir(None, "tam") == 0
    assert _hucre_cevir(None, "ondalik") == 0.0
    assert _hucre_cevir(None, "ondalik_bos") is None
    assert _hucre_cevir(None, "kutu") is False


def test_bos_birakilabilen_sayida_sifir_da_bos_sayilir():
    """Z max'a 0 yazmak 'tavan sabit' demektir, '0 mm tavan' değil."""
    assert _hucre_cevir(0, "ondalik_bos") is None
    assert _hucre_cevir(2_850, "ondalik_bos") == 2_850.0


def test_metin_hucresinin_bosluklari_kirpiliyor():
    assert _hucre_cevir("  mega  ", "metin") == "mega"


# ═════════════════════════════════════════════════════════════════════════════
# Değişiklik bulma
# ═════════════════════════════════════════════════════════════════════════════

def test_degisiklik_yoksa_bos_doner():
    satirlar = _satirlar()
    assert _tablo_farklari(satirlar, pd.DataFrame(satirlar), _SUTUNLAR) == {}


def test_tek_hucre_degisikligi_bulunuyor():
    satirlar = _satirlar()
    df = pd.DataFrame(satirlar)
    df.at[0, "Z max (Lift-Top)"] = 2_850.0
    farklar = _tablo_farklari(satirlar, df, _SUTUNLAR)
    assert farklar == {"34 AAA 001": {"yukseklik_max_mm": 2_850.0}}


def test_hesaplanan_sutun_degisikligi_yok_sayiliyor():
    """İç hacim kilitli; yine de değişmiş görünse bile kayda yazılmaz."""
    satirlar = _satirlar()
    df = pd.DataFrame(satirlar)
    df.at[0, "İç hacim (m³)"] = 999.0
    assert _tablo_farklari(satirlar, df, _SUTUNLAR) == {}


def test_siralanmis_tabloda_degisiklik_dogru_araca_gidiyor():
    """KABUL: kullanıcı tabloyu sıralarsa satır numarası kayar.

    Eşleştirme plakadan yapıldığı için değişiklik yine doğru araca yazılmalı.
    """
    satirlar = _satirlar()
    df = pd.DataFrame(satirlar).iloc[::-1].reset_index(drop=True)
    assert df.at[0, "Plaka"] == "34 BBB 002"      # sıra tersine döndü
    df.at[0, "Dingil"] = 2                        # BBB'nin dingili değişti
    farklar = _tablo_farklari(satirlar, df, _SUTUNLAR)
    assert farklar == {"34 BBB 002": {"dingil_sayisi": 2}}


def test_ayni_anda_birden_cok_satir_ve_sutun():
    satirlar = _satirlar()
    df = pd.DataFrame(satirlar)
    df.at[0, "Tip"] = "mega"
    df.at[0, "40 ft"] = True
    df.at[1, "Z · yükseklik (mm)"] = 2_950.0
    farklar = _tablo_farklari(satirlar, df, _SUTUNLAR)
    assert farklar == {
        "34 AAA 001": {"tip": "mega", "iso_40ft_konteyner": True},
        "34 BBB 002": {"ic_yukseklik_mm": 2_950.0},
    }


def test_tabloda_olmayan_plaka_atlaniyor():
    satirlar = _satirlar()
    df = pd.DataFrame(satirlar)
    df.at[0, "Plaka"] = "99 ZZZ 999"       # olmayan kayıt
    df.at[0, "Dingil"] = 2
    assert _tablo_farklari(satirlar, df, _SUTUNLAR) == {}


# ═════════════════════════════════════════════════════════════════════════════
# Doğrulama — hatalı satır kaydedilmemeli
# ═════════════════════════════════════════════════════════════════════════════

def test_gecerli_kayitlar_dogrulamayi_geciyor():
    assert _dorse_dogrula(_dorse()) is None
    assert _cekici_dogrula(_cekici()) is None


@pytest.mark.parametrize("alan,deger", [
    ("ic_genislik_mm", 0.0),
    ("ic_uzunluk_mm", 0.0),
    ("ic_yukseklik_mm", 0.0),
    ("bos_agirlik_kg", 0.0),
    ("dingil_sayisi", 0),
    ("dingil_sayisi", 5),
    ("tip", "bilinmeyen"),
    ("plaka", "   "),
])
def test_dorse_hatali_deger_reddediliyor(alan, deger):
    assert _dorse_dogrula(dataclasses.replace(_dorse(), **{alan: deger}))


def test_z_max_z_den_kucukse_reddediliyor():
    hata = _dorse_dogrula(_dorse(yukseklik_max_mm=2_600.0))
    assert hata and "Z max" in hata


def test_z_max_bossa_sorun_degil():
    assert _dorse_dogrula(_dorse(yukseklik_max_mm=None)) is None


@pytest.mark.parametrize("alan,deger", [
    ("bos_agirlik_kg", 0.0),
    ("dingil_sayisi", 0),
    ("dingil_sayisi", 6),
    ("plaka", ""),
])
def test_cekici_hatali_deger_reddediliyor(alan, deger):
    assert _cekici_dogrula(dataclasses.replace(_cekici(), **{alan: deger}))


# ═════════════════════════════════════════════════════════════════════════════
# Lift-Top kuralı: Z max girilince tavan kendiliğinden açılır
# ═════════════════════════════════════════════════════════════════════════════

def test_z_max_girilince_lift_top_aciliyor():
    d = _dorse_tavan_kurali(_dorse(yukseklik_max_mm=2_850.0))
    assert d.ayarlanabilir_tavan is True
    assert d.tavan_payi_mm == 150.0


def test_z_max_bosaltilinca_lift_top_kapaniyor():
    acik = _dorse(ayarlanabilir_tavan=True, yukseklik_max_mm=2_850.0)
    kapali = _dorse_tavan_kurali(dataclasses.replace(
        acik, yukseklik_max_mm=None))
    assert kapali.ayarlanabilir_tavan is False
    assert kapali.tavan_payi_mm == 0.0


def test_z_max_z_ye_esitse_lift_top_acilmiyor():
    """Pay sıfırsa yükseltme fiilen yok — tablo kendi içinde çelişmesin."""
    d = _dorse_tavan_kurali(_dorse(yukseklik_max_mm=2_700.0))
    assert d.ayarlanabilir_tavan is False


# ═════════════════════════════════════════════════════════════════════════════
# Tablo sütunları ile kayıt alanları tutarlı mı?
# ═════════════════════════════════════════════════════════════════════════════

def test_dorse_tipleri_tek_yerden_geliyor():
    assert _DORSE_TIPLERI == ["tenteli", "frigorifik", "kapalı kasa", "mega"]
    for tip in _DORSE_TIPLERI:
        assert _dorse_dogrula(_dorse(tip=tip)) is None


def test_duzenlenebilir_sutunlar_gercek_alanlara_bakiyor():
    """Sütun eşlemesindeki her alan dataclass'ta gerçekten var olmalı."""
    import inspect
    kaynak = inspect.getsource(_dorse_listesi)
    dorse_alanlari = {f.name for f in dataclasses.fields(Dorse)}
    for alan in ("tip", "ic_genislik_mm", "ic_uzunluk_mm", "ic_yukseklik_mm",
                 "yukseklik_max_mm", "bos_agirlik_kg", "dingil_sayisi",
                 "iso_40ft_konteyner", "kaynak"):
        assert alan in dorse_alanlari
        assert alan in kaynak, f"{alan} dorse tablosunda eşlenmemiş"
