# -*- coding: utf-8 -*-
"""
Filo Excel şablonu ve içe/dışa aktarma testleri
================================================
    python -X utf8 -m pytest test_filo_excel.py -q
"""

from __future__ import annotations

import io

import pytest

import filo_excel as fx
from filo_modeli import eslesme_hesapla
from ornek_filo import ford_fmax_4x2, schmitz_scs_24l


def _kitap(baytlar: bytes):
    import pandas as pd
    return pd.read_excel(io.BytesIO(baytlar), sheet_name=None)


def _excel_yaz(cekici_satirlari, dorse_satirlari) -> bytes:
    """Elle satır listesinden şablon biçiminde Excel üretir."""
    import pandas as pd
    tampon = io.BytesIO()
    with pd.ExcelWriter(tampon, engine="openpyxl") as w:
        pd.DataFrame(cekici_satirlari,
                     columns=[s.baslik for s in fx.SUTUNLAR_CEKICI]
                     ).to_excel(w, sheet_name=fx.SAYFA_CEKICI, index=False)
        pd.DataFrame(dorse_satirlari,
                     columns=[s.baslik for s in fx.SUTUNLAR_DORSE]
                     ).to_excel(w, sheet_name=fx.SAYFA_DORSE, index=False)
    return tampon.getvalue()


def _cekici_satiri(**kw):
    satir = {s.baslik: None for s in fx.SUTUNLAR_CEKICI}
    satir.update({
        "Plaka": "34 TEST 001",
        "Marka / model": "Test Çekici",
        "Boş ağırlık (kg)": 7_500,
        "Dingil sayısı": 2,
        "Beşinci teker ofseti e (mm)": 600,
    })
    satir.update(kw)
    return satir


def _dorse_satiri(**kw):
    satir = {s.baslik: None for s in fx.SUTUNLAR_DORSE}
    satir.update({
        "Plaka": "34 TEST 002",
        "Tip": "tenteli",
        "İç uzunluk (mm)": 13_600,
        "İç genişlik (mm)": 2_480,
        "İç yükseklik (mm)": 2_700,
        "Boş ağırlık (kg)": 6_300,
        "Dingil sayısı": 3,
    })
    satir.update(kw)
    return satir


# ═════════════════════════════════════════════════════════════════════════════
# Şablon
# ═════════════════════════════════════════════════════════════════════════════

def test_sablon_uretiliyor():
    assert len(fx.sablon_uret()) > 1_000


def test_sablon_sayfalari():
    k = _kitap(fx.sablon_uret())
    assert fx.SAYFA_CEKICI in k
    assert fx.SAYFA_DORSE in k
    assert fx.SAYFA_ORNEK in k
    assert fx.SAYFA_ACIKLAMA in k


def test_sablon_veri_satirlari_bos():
    """Kullanıcıya BOŞ sunulmalı — örnek ayrı sayfada."""
    k = _kitap(fx.sablon_uret())
    assert k[fx.SAYFA_CEKICI].empty
    assert k[fx.SAYFA_DORSE].empty


def test_sablon_basliklari_sutun_tanimlariyla_ayni():
    k = _kitap(fx.sablon_uret())
    assert list(k[fx.SAYFA_CEKICI].columns) == \
        [s.baslik for s in fx.SUTUNLAR_CEKICI]
    assert list(k[fx.SAYFA_DORSE].columns) == \
        [s.baslik for s in fx.SUTUNLAR_DORSE]


def test_aciklama_sayfasi_her_sutunu_anlatiyor():
    k = _kitap(fx.sablon_uret())
    metin = k[fx.SAYFA_ACIKLAMA].astype(str).to_string()
    for s in list(fx.SUTUNLAR_CEKICI) + list(fx.SUTUNLAR_DORSE):
        assert s.baslik in metin, f"açıklaması yok: {s.baslik}"
    assert "tahmini değer yazmayın" in metin


def test_sablon_ornek_sayfasi_okunmuyor():
    """Örnek sayfası veri olarak alınmamalı."""
    ck, dr, hatalar, _ = fx.oku(fx.sablon_uret())
    assert ck == [] and dr == []
    assert hatalar == []


def test_sablonda_zorunlu_alanlar_isaretli():
    zorunlu_ck = {s.baslik for s in fx.SUTUNLAR_CEKICI if s.zorunlu}
    assert zorunlu_ck == {"Plaka", "Boş ağırlık (kg)", "Dingil sayısı",
                          "Beşinci teker ofseti e (mm)"}
    zorunlu_dr = {s.baslik for s in fx.SUTUNLAR_DORSE if s.zorunlu}
    assert "İç uzunluk (mm)" in zorunlu_dr and "Tip" in zorunlu_dr


# ═════════════════════════════════════════════════════════════════════════════
# Okuma
# ═════════════════════════════════════════════════════════════════════════════

def test_basit_okuma():
    ck, dr, hatalar, _ = fx.oku(_excel_yaz([_cekici_satiri()],
                                           [_dorse_satiri()]))
    assert hatalar == []
    assert len(ck) == 1 and len(dr) == 1
    assert ck[0].plaka == "34 TEST 001"
    assert ck[0].bos_agirlik_kg == 7_500
    assert dr[0].ic_uzunluk_mm == 13_600
    assert dr[0].dorse_id == dr[0].plaka


def test_bos_hucre_none_kaliyor():
    """Tahmini değer YAZILMAZ — boş alan bilinmiyor demektir."""
    ck, _, _, _ = fx.oku(_excel_yaz([_cekici_satiri()], []))
    c = ck[0]
    assert c.teknik_gcw_kg is None
    assert c.bos_on_dingil_kg is None
    assert c.dingil_mesafesi_mm is None


def test_zorunlu_alan_eksikse_satir_atlaniyor():
    ck, _, hatalar, _ = fx.oku(_excel_yaz(
        [_cekici_satiri(**{"Boş ağırlık (kg)": None})], []))
    assert ck == []
    assert any("zorunlu" in h for h in hatalar)


def test_hatali_satir_digerlerini_engellemiyor():
    ck, _, hatalar, _ = fx.oku(_excel_yaz(
        [_cekici_satiri(**{"Plaka": None}),
         _cekici_satiri(**{"Plaka": "34 TEST 009"})], []))
    assert [c.plaka for c in ck] == ["34 TEST 009"]
    assert hatalar


def test_sayi_olmayan_deger_hata_veriyor():
    _, _, hatalar, _ = fx.oku(_excel_yaz(
        [_cekici_satiri(**{"Boş ağırlık (kg)": "abc"})], []))
    assert any("sayı olmalı" in h for h in hatalar)


def test_bos_satirlar_atlaniyor():
    bos = {s.baslik: None for s in fx.SUTUNLAR_CEKICI}
    ck, _, hatalar, _ = fx.oku(_excel_yaz([bos, _cekici_satiri(), bos], []))
    assert len(ck) == 1 and hatalar == []


@pytest.mark.parametrize("deger, beklenen", [
    ("E", True), ("e", True), ("Evet", True), (1, True), ("X", True),
    ("H", False), ("Hayır", False), (0, False),
])
def test_evet_hayir_okuma(deger, beklenen):
    _, dr, hatalar, _ = fx.oku(_excel_yaz(
        [], [_dorse_satiri(**{"40 ft ISO konteyner": deger})]))
    assert hatalar == []
    assert dr[0].iso_40ft_konteyner is beklenen


def test_gecersiz_evet_hayir_hata():
    _, _, hatalar, _ = fx.oku(_excel_yaz(
        [], [_dorse_satiri(**{"40 ft ISO konteyner": "belki"})]))
    assert any("E/H" in h for h in hatalar)


def test_dosya_ici_plaka_cakismasi():
    ck, dr, hatalar, _ = fx.oku(_excel_yaz(
        [_cekici_satiri(**{"Plaka": "AYNI"})],
        [_dorse_satiri(**{"Plaka": "AYNI"})]))
    assert any("birden fazla" in h for h in hatalar)
    assert ck == [] and dr == []


def test_eksik_dingil_verisi_uyari_veriyor():
    _, _, _, uyarilar = fx.oku(_excel_yaz([_cekici_satiri()], []))
    assert any("dingil kontrolü yapılamayacak" in u for u in uyarilar)


def test_bilinmeyen_dorse_tipi_uyari_ama_kaydediliyor():
    _, dr, hatalar, uyarilar = fx.oku(_excel_yaz(
        [], [_dorse_satiri(**{"Tip": "açık kasa"})]))
    assert hatalar == []
    assert len(dr) == 1 and dr[0].tip == "açık kasa"
    assert any("bilinen tiplerden değil" in u for u in uyarilar)


def test_yanlis_sayfa_adlari_hata():
    import pandas as pd
    t = io.BytesIO()
    with pd.ExcelWriter(t, engine="openpyxl") as w:
        pd.DataFrame({"a": [1]}).to_excel(w, sheet_name="Sheet1", index=False)
    _, _, hatalar, _ = fx.oku(t.getvalue())
    assert any("bulunamadı" in h for h in hatalar)


def test_bozuk_dosya_hata_veriyor():
    _, _, hatalar, _ = fx.oku(b"bu bir excel degil")
    assert hatalar and "okunamadı" in hatalar[0]


def test_on_duvar_kalinligi_bos_sifir_oluyor():
    _, dr, _, _ = fx.oku(_excel_yaz([], [_dorse_satiri()]))
    assert dr[0].on_duvar_kalinligi_mm == 0.0


# ═════════════════════════════════════════════════════════════════════════════
# Dışa aktarma ve gidiş-dönüş
# ═════════════════════════════════════════════════════════════════════════════

def test_disa_aktar_okunabiliyor():
    baytlar = fx.disa_aktar([ford_fmax_4x2()], [schmitz_scs_24l()])
    ck, dr, hatalar, _ = fx.oku(baytlar)
    assert hatalar == []
    assert ck[0].plaka == "54 ABC 123"
    assert dr[0].plaka == "54 XYZ 456"


def test_gidis_donus_degerleri_koruyor():
    """Dışa aktar → geri oku: hesaplar aynı kalmalı."""
    ck, dr, _, _ = fx.oku(fx.disa_aktar([ford_fmax_4x2()],
                                        [schmitz_scs_24l()]))
    es = eslesme_hesapla(ck[0], dr[0])
    assert es.yasal_toplam_kg == 40_000
    assert es.faydali_yuk_kg == pytest.approx(25_757.0)
    assert es.dingil_kontrol_edilebilir
    assert dr[0].ic_hacim_m3 == pytest.approx(91.20, abs=0.01)


def test_gidis_donus_kaynak_alanlarini_koruyor():
    c = ford_fmax_4x2()
    c.kaynak = "Ford Trucks F-MAX Euro 6E teknik föyü"
    c.dogrulama_durumu = "değerler föyden okundu; föy PDF'i arşivde yok"
    ck, _, _, _ = fx.oku(fx.disa_aktar([c], []))
    assert ck[0].kaynak == c.kaynak
    assert ck[0].dogrulama_durumu == c.dogrulama_durumu


def test_bos_filo_disa_aktarilabiliyor():
    ck, dr, hatalar, _ = fx.oku(fx.disa_aktar([], []))
    assert ck == [] and dr == [] and hatalar == []
