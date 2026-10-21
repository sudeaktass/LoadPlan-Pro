# -*- coding: utf-8 -*-
"""
Aktif filo seçimi — kalıcı
===========================
`st.session_state` sayfa yenilenince sıfırlanıyor; kullanıcı 🚚 Filo
sayfasından bir filo seçtiğinde bu seçimin kalıcı olması gerekiyor.
Seçim veritabanındaki `ayarlar` tablosunda saklanır.

Kural:
  * Veritabanında aktif çekici VE dorse kaydı varsa, varsayılan olarak
    HEPSİ kullanılır (K4: kullanıcının filosu zaten bir TAVANDIR).
  * Kullanıcı 🚚 Filo sayfasından bir alt küme seçebilir.
  * "Eski araç tablosunu kullan" tercihi de kalıcıdır.
"""

from __future__ import annotations

from typing import List, Tuple

import database as db_mod

ANAHTAR_CEKICI = "filo_secili_cekiciler"
ANAHTAR_DORSE = "filo_secili_dorseler"
ANAHTAR_ESKI_TABLO = "filo_eski_tablo_kullan"


def eski_tablo_mu() -> bool:
    return bool(db_mod.ayar_oku(ANAHTAR_ESKI_TABLO, False))


def eski_tablo_ayarla(deger: bool) -> None:
    db_mod.ayar_yaz(ANAHTAR_ESKI_TABLO, bool(deger))


def secimi_kaydet(cekici_plakalari: List[str],
                  dorse_plakalari: List[str]) -> None:
    db_mod.ayar_yaz(ANAHTAR_CEKICI, list(cekici_plakalari))
    db_mod.ayar_yaz(ANAHTAR_DORSE, list(dorse_plakalari))
    eski_tablo_ayarla(False)


def aktif_filo() -> Tuple[List, List]:
    """
    Optimizasyonda kullanılacak çekici ve dorse listeleri.

    Boş liste döndürmek "eski araç tablosunu kullan" demektir.
    """
    if eski_tablo_mu():
        return [], []

    from filo_sayfasi import _cekici_kayitlari, _dorse_kayitlari
    cekiciler = _cekici_kayitlari()
    dorseler = _dorse_kayitlari()
    if not cekiciler or not dorseler:
        return [], []

    sec_ck = db_mod.ayar_oku(ANAHTAR_CEKICI, None)
    sec_dr = db_mod.ayar_oku(ANAHTAR_DORSE, None)

    # Hiç seçim yapılmamışsa TÜM kayıtlı filo kullanılır (K4: tavan).
    if sec_ck is not None:
        cekiciler = [c for c in cekiciler if c.plaka in sec_ck]
    if sec_dr is not None:
        dorseler = [d for d in dorseler if d.plaka in sec_dr]

    if not cekiciler or not dorseler:
        return [], []
    return cekiciler, dorseler
