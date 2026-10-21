# -*- coding: utf-8 -*-
"""
Örnek filo — gerçek araç föylerinden alınmış referans kayıtlar
===============================================================
Bu dosyadaki değerler testlerde ve arayüzdeki "örnek filo" düğmesinde
kullanılır. Her değerin kaynağı `kaynak_notlari`'nda; föyde OLMAYAN ve
tarafımızca varsayılan her değer `varsayim_alanlari`'nda "VARSAYIM"
etiketiyle işaretli.

Kaynak: FILO_VERI_MODELI_REHBERI.md Bölüm 3.1 (Ford Trucks F-MAX Euro 6E
föyü, Schmitz Cargobull SCS 24/L föyü).
"""

from __future__ import annotations

from filo_modeli import Cekici, Dorse

FOY_FORD = "Ford Trucks F-MAX Euro 6E föyü"
FOY_SCHMITZ = "Schmitz Cargobull SCS 24/L föyü"


def ford_fmax_4x2() -> Cekici:
    """Ford F-MAX 4x2 çekici.

    Boş ağırlık 7.908 kg = ön dingil 5.610 + arka (tahrik) 2.298.
    Teknik GCW 44.000 kg, ancak 5 dingilli kombinasyonda yasal toplam
    40.000 kg bağlar (KTY md.128) → min(yasal, teknik).
    """
    return Cekici(
        cekici_id="C-001",
        plaka="54 ABC 123",
        marka_model="Ford F-MAX 4x2",
        bos_agirlik_kg=7_908.0,
        dingil_sayisi=2,
        # ⚠ VARSAYIM: beşinci teker ofseti (e) üretici föyünde YOK.
        # Bu değer sonucu doğrudan etkiliyor: e = 600 mm'de tam yük
        # geçerli, e = 900 mm'de ön dingil aşılıyor ve yük ≈ 25.225 kg
        # ile sınırlanıyor (bkz. test_e_duyarliligi).
        besinci_teker_ofset_mm=600.0,
        bos_on_dingil_kg=5_610.0,
        bos_arka_dingil_kg=2_298.0,
        on_dingil_izin_kg=7_500.0,
        tahrik_dingil_izin_kg=11_500.0,
        dingil_mesafesi_mm=3_600.0,
        teknik_gcw_kg=44_000.0,
        varsayim_alanlari={
            "besinci_teker_ofset_mm":
                "VARSAYIM: üretici föyünde yok, 600 mm kabul edildi. "
                "Araç üzerinde ölçülerek doğrulanmalıdır; dingil "
                "kontrolünün sonucunu doğrudan etkiler.",
        },
        kaynak_notlari={
            "bos_agirlik_kg": FOY_FORD,
            "bos_on_dingil_kg": FOY_FORD,
            "bos_arka_dingil_kg": FOY_FORD,
            "on_dingil_izin_kg": FOY_FORD + " (yasal ön dingil sınırı)",
            "tahrik_dingil_izin_kg": FOY_FORD + " + KTY md.128",
            "dingil_mesafesi_mm": FOY_FORD,
            "teknik_gcw_kg": FOY_FORD + " (GCW)",
        },
    )


def schmitz_scs_24l() -> Dorse:
    """Schmitz Cargobull SCS 24/L tenteli dorse.

    İç ölçü 13.620 × 2.480 × 2.700 mm ≈ 91,2 m³ (hesaplanır).
    Boş ağırlık 6.335 kg (±%3). 3 dingil, aralık 1.310 mm → KTY'de 24 t
    sınıfı. Kingpin izni 15.000 kg, teknik azami 39.000 kg.

    Kingpin ölçüleri (F kararı): föydeki değerler DIŞ ön kenardan.
      "king pin, position 1690 mm, acc. to SAE" → kingpin_on_kenar
      "wheelbase 7700 mm"                      → kingpin → dingil grubu
    Ölçü referansının yorumu bizim; bkz. kaynak_notlari.
    """
    return Dorse(
        dorse_id="D-001",
        plaka="54 XYZ 456",
        tip="tenteli",
        ic_uzunluk_mm=13_620.0,
        ic_genislik_mm=2_480.0,
        ic_yukseklik_mm=2_700.0,
        bos_agirlik_kg=6_335.0,
        dingil_sayisi=3,
        dingil_araligi_mm=1_310.0,
        dingil_grubu_izin_kg=24_000.0,
        kingpin_izin_kg=15_000.0,
        kingpin_on_kenar_mesafe_mm=1_690.0,
        on_duvar_kalinligi_mm=0.0,
        kingpin_dingil_grubu_mesafe_mm=7_700.0,
        teknik_azami_kg=39_000.0,
        iso_40ft_konteyner=False,
        kaynak_notlari={
            "ic_uzunluk_mm": FOY_SCHMITZ,
            "ic_genislik_mm": FOY_SCHMITZ,
            "ic_yukseklik_mm": FOY_SCHMITZ,
            "bos_agirlik_kg": FOY_SCHMITZ + " (±%3)",
            "dingil_araligi_mm": FOY_SCHMITZ,
            "dingil_grubu_izin_kg": FOY_SCHMITZ,
            "kingpin_izin_kg": FOY_SCHMITZ,
            "teknik_azami_kg": FOY_SCHMITZ,
            "kingpin_on_kenar_mesafe_mm":
                FOY_SCHMITZ + "; ölçü referansının yorumu bizim "
                "(kingpin: ön dış kenardan)",
            "kingpin_dingil_grubu_mesafe_mm":
                FOY_SCHMITZ + " ('wheelbase 7700 mm'); ölçü referansının "
                "yorumu bizim (kingpin → dingil grubu ortası)",
            "on_duvar_kalinligi_mm":
                "Föyde yok; 0 mm kabul edildi (isteğe bağlı alan). "
                "Girilirse c = kingpin_on_kenar − kalınlık olur.",
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# Pollaris ve ark. (2016) referans aracı — testlerde karşılaştırma için
# ─────────────────────────────────────────────────────────────────────────────

POLLARIS_2016 = {
    "kaynak": ("Pollaris ve ark. (2016), EURO J. Transp. Logist., "
               "Belçikalı lojistik firması verisi"),
    "yasal_toplam_t": 44.0,       # konteyner taşımacılığı
    "bos_cekici_t": 6.82,         # 4,88 ön + 1,97 tahrik (föydeki yuvarlama)
    "bos_cekici_on_t": 4.88,
    "bos_cekici_tahrik_t": 1.97,
    "konteyner_dara_t": 3.0,      # 2 t kaplinde, 1 t dorse dingillerinde
    "konteyner_dara_kingpin_t": 2.0,
    "konteyner_dara_grup_t": 1.0,
    "bos_dorse_t": 2.0,
    "faydali_yuk_t": 32.2,        # 44 − 6,82 − 3 − 2
    "kaplin_sinir_t": 13.6,       # yük sınırı: 13,6 − 2 = 11,6 t
    "tridem_sinir_t": 24.0,       # yük sınırı: 24 − 2 − 1 = 21 t
    "c_mm": 1_000.0,              # dorse önünden kingpine
    "d_mm": 5_500.0,              # kingpin → dorse orta dingili
    "kingpin_tahrik_payi": 0.80,  # makaledeki araç için sabit %80/%20
    "kingpin_on_payi": 0.20,
}
