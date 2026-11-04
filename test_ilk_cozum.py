# -*- coding: utf-8 -*-
"""
Başlangıç çözümü testleri (B1)
==============================
    python -X utf8 -m pytest test_ilk_cozum.py -q

Tabu ve SA aynı `_create_initial_solution` fonksiyonunu paylaşır.
22 Ekim 2026'da üç sorunu düzeltildi:
  1. Bütün bin'leri `trucks[0]`'ın hacmine göre kesiyordu (heterojen
     filoda yanlış).
  2. Ağırlığı yok sayıyordu — yoğun yükte aracı önce ağırlık doldurur.
  3. Silindirde dış kutu hacmini kullanıyordu, gerçek hacmi değil.
"""

from __future__ import annotations

import math

from core_3d import Piece3D, Truck3D
from tabu_search_3d import (_acilacak_araclar, _create_initial_solution,
                            ILK_COZUM_DOLULUK_PAYI)


def _t(tid, en, boy, yuk, kap=100_000, adet=1):
    t = Truck3D(tid, en, boy, yuk, kap, 4)
    t.available = adet
    return t


def _p(pid, en=100, boy=100, yuk=100, kg=100.0, sekil="box", prio=None):
    return Piece3D(id=pid, width=en, length=boy, height=yuk, quantity=1,
                   weight=kg, shape=sekil, priority=prio)


def _bin_sayisi(cozum):
    return len(set(cozum.bin_assignments))


# ═════════════════════════════════════════════════════════════════════════════
# Araç dizisi — FiloHavuzu ile aynı sıra
# ═════════════════════════════════════════════════════════════════════════════

def test_arac_dizisi_buyukten_kucuge():
    kucuk = _t("K", 100, 100, 100)
    buyuk = _t("B", 200, 200, 200)
    dizi = _acilacak_araclar([kucuk, buyuk], 5)
    assert [t.id for t in dizi] == ["B", "K"]


def test_arac_dizisi_available_kadar_tekrarliyor():
    t = _t("T", 100, 100, 100, adet=3)
    assert [x.id for x in _acilacak_araclar([t], 10)] == ["T", "T", "T"]


def test_arac_dizisi_max_bins_ile_kirpiliyor():
    t = _t("T", 100, 100, 100, adet=9)
    assert len(_acilacak_araclar([t], 4)) == 4


def test_arac_yoksa_bos_dizi():
    assert _acilacak_araclar([], 5) == []


# ═════════════════════════════════════════════════════════════════════════════
# 1. Heterojen filo — her bin KENDİ aracına göre boyutlanmalı
# ═════════════════════════════════════════════════════════════════════════════

def test_ikinci_bin_kendi_aracinin_hacmine_gore_kesiliyor():
    """KABUL: ilk araç büyük, ikinci araç küçükse 2. bin erken kapanmalı.

    Eski kod ikinci bin'i de BÜYÜK aracın hacmiyle ölçüyordu; küçük
    araca fazla parça yığıyordu.
    """
    buyuk = _t("B", 100, 1000, 100)      # hacim 10.000.000
    kucuk = _t("K", 100, 200, 100, adet=4)   # hacim 2.000.000
    # Her parça 1.000.000 → büyüğe ~9, küçüğe ~1 sığmalı.
    # max_bins bol tutuluyor; yoksa taşan parçaların gidecek yeri kalmaz
    # ve son bin'e yığılırlar (bu ayrı bir davranış).
    parcalar = [_p(f"p{i}") for i in range(12)]
    cozum = _create_initial_solution(parcalar, [buyuk, kucuk], max_bins=5)

    ilk = sum(1 for b in cozum.bin_assignments if b == 0)
    ikinci = sum(1 for b in cozum.bin_assignments if b == 1)
    assert ilk > ikinci, "büyük araca daha çok parça düşmeliydi"
    assert ikinci <= 2, f"küçük araca {ikinci} parça atandı — fazla"


def test_filo_tukenirse_son_arac_referans_aliniyor():
    """max_bins, filodaki araç sayısından fazlaysa son araç sürdürülür."""
    t = _t("T", 100, 200, 100)           # tek araç, hacim 2.000.000
    parcalar = [_p(f"p{i}") for i in range(6)]
    cozum = _create_initial_solution(parcalar, [t], max_bins=6)
    assert _bin_sayisi(cozum) >= 3       # her bin'e ~1 parça


def test_tek_arac_tipinde_davranis_makul():
    t = _t("T", 100, 1000, 100, adet=5)          # hacim 10.000.000
    parcalar = [_p(f"p{i}") for i in range(20)]  # 1.000.000 her biri
    cozum = _create_initial_solution(parcalar, [t], max_bins=5)
    # %95 eşikle araç başına ~9 parça → ~3 bin
    assert 2 <= _bin_sayisi(cozum) <= 4


# ═════════════════════════════════════════════════════════════════════════════
# 2. Ağırlık — hacim yetse bile kapasite dolunca bin kapanmalı
# ═════════════════════════════════════════════════════════════════════════════

def test_agirlik_dolunca_yeni_bin_aciliyor():
    """KABUL: yoğun yükte aracı ağırlık doldurur, hacim değil."""
    # Hacmen çok geniş ama kapasitesi dar araç
    t = _t("T", 1000, 1000, 1000, kap=1_000, adet=5)
    parcalar = [_p(f"p{i}", kg=400.0) for i in range(6)]   # 2 parça = 800 kg
    cozum = _create_initial_solution(parcalar, [t], max_bins=5)
    assert _bin_sayisi(cozum) >= 3, "ağırlık sınırı yok sayılıyor"


def test_agirlik_bilinmiyorsa_hacme_gore_bolunuyor():
    """capacity yoksa tahmin yürütülmez, eski davranışa düşülür."""
    t = _t("T", 100, 1000, 100, kap=0, adet=5)
    parcalar = [_p(f"p{i}", kg=9_999.0) for i in range(4)]
    cozum = _create_initial_solution(parcalar, [t], max_bins=5)
    assert _bin_sayisi(cozum) == 1       # hacim yetiyor → tek bin


def test_hacim_ve_agirlik_birlikte_hangisi_once_dolarsa():
    dar_kapasite = _t("A", 1000, 1000, 1000, kap=500, adet=4)
    bol_kapasite = _t("B", 100, 300, 100, kap=100_000, adet=4)
    parcalar = [_p(f"p{i}", kg=300.0) for i in range(4)]
    a = _bin_sayisi(_create_initial_solution(parcalar, [dar_kapasite], 4))
    b = _bin_sayisi(_create_initial_solution(parcalar, [bol_kapasite], 4))
    assert a >= 2        # ağırlık bağlıyor
    assert b >= 2        # hacim bağlıyor


# ═════════════════════════════════════════════════════════════════════════════
# 3. Silindir — gerçek hacim kullanılmalı
# ═════════════════════════════════════════════════════════════════════════════

def test_silindir_gercek_hacimle_sayiliyor():
    """πr²h, dış kutudan ~%21 küçüktür; ilk çözüm bunu görmeli."""
    silindir = _p("s", en=100, boy=100, yuk=100, sekil="cylinder")
    assert silindir.get_actual_volume() == math.pi * 50 ** 2 * 100
    assert silindir.get_actual_volume() < silindir.get_bounding_volume()


def test_silindirler_kutulardan_daha_cok_sigiyor():
    """Aynı dış ölçüde silindir, gerçek hacmi küçük olduğu için
    aynı bin'e daha çok sığar."""
    t = _t("T", 100, 1000, 100, adet=5)     # 10.000.000
    kutular = [_p(f"k{i}") for i in range(12)]
    silindirler = [_p(f"s{i}", sekil="cylinder") for i in range(12)]
    bk = _bin_sayisi(_create_initial_solution(kutular, [t], 5))
    bs = _bin_sayisi(_create_initial_solution(silindirler, [t], 5))
    assert bs <= bk


# ═════════════════════════════════════════════════════════════════════════════
# Korunması gerekenler
# ═════════════════════════════════════════════════════════════════════════════

def test_her_parca_tam_bir_bine_atanmis():
    t = _t("T", 100, 500, 100, adet=5)
    parcalar = [_p(f"p{i}") for i in range(11)]
    cozum = _create_initial_solution(parcalar, [t], max_bins=5)
    assert len(cozum.bin_assignments) == 11
    toplam = sum(len(v) for v in cozum.piece_orders.values())
    assert toplam == 11
    assert sorted(i for v in cozum.piece_orders.values() for i in v) == \
        list(range(11))


def test_max_bins_asilmiyor():
    t = _t("T", 100, 100, 100, adet=99)
    parcalar = [_p(f"p{i}") for i in range(30)]
    cozum = _create_initial_solution(parcalar, [t], max_bins=3)
    assert max(cozum.bin_assignments) <= 2


def test_oncelikli_parca_sona_biraklilyor():
    """priority=1 (kapıya yakın) sıralamada en sonda olmalı."""
    t = _t("T", 1000, 1000, 1000, adet=3)
    parcalar = [_p("oncelikli", prio=1), _p("normal1"), _p("normal2")]
    cozum = _create_initial_solution(parcalar, [t], max_bins=3)
    sira = cozum.piece_orders[0]
    assert sira[-1] == 0, "öncelikli parça en sona yerleşmeliydi"


def test_bos_parca_listesi():
    t = _t("T", 100, 100, 100)
    cozum = _create_initial_solution([], [t], max_bins=3)
    assert cozum.bin_assignments == []


def test_doluluk_payi_makul():
    assert 0.5 < ILK_COZUM_DOLULUK_PAYI <= 1.0
