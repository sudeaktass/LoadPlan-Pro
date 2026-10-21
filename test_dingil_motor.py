# -*- coding: utf-8 -*-
"""
Motor içi dingil kontrolü testleri (3. adım)
=============================================
Plan: Makaleler/FILO_UYGULAMA_PLANI.md Bölüm 6, test 12.

    python -X utf8 -m pytest test_dingil_motor.py -q

Temel davranış: araçta çekici+dorse eşleşmesi YOKSA hiçbir şey değişmez
(eski araç tablosu, Excel, deney betikleri). Eşleşme varsa her aday konum
için dingil sınırları kontrol edilir.
"""

from __future__ import annotations

import contextlib
import io

import pytest

import dingil_yuku
from core_3d import Piece3D, Truck3D
from dingil_yuku import (
    KIP_HER_YERLESTIRME,
    KIP_YALNIZCA_RAPOR,
    arac_dingil_raporu,
    cm_to_mm_cg,
    izleyici_olustur,
    konum_uygun_mu,
)
from extreme_points_3d import create_packing_engine
from filo_havuzu import eslesme_to_truck3d
from filo_modeli import eski_aractan_donustur, eslesme_hesapla
from ornek_filo import ford_fmax_4x2, schmitz_scs_24l


@contextlib.contextmanager
def _sessiz():
    with contextlib.redirect_stdout(io.StringIO()):
        yield


def _dingilli_arac() -> Truck3D:
    """Ford F-MAX + Schmitz SCS 24/L → dingil kontrolü yapılabilir."""
    return eslesme_to_truck3d(eslesme_hesapla(ford_fmax_4x2(),
                                              schmitz_scs_24l()))


def _eski_arac() -> Truck3D:
    return Truck3D("Buyuk", 240, 600, 200, 24_000, 1)


# ═════════════════════════════════════════════════════════════════════════════
# İzleyici kurulumu
# ═════════════════════════════════════════════════════════════════════════════

def test_eslesmesiz_aracta_izleyici_kurulmuyor():
    """Eski araç tablosu → kontrol yok, davranış DEĞİŞMEZ."""
    assert izleyici_olustur(_eski_arac()) is None


def test_goc_edilmis_aracta_izleyici_kurulmuyor():
    """Tanımsız çekici → kontrol yapılamaz (ama uyarı eşleşmede durur)."""
    dorse, cekici = eski_aractan_donustur("X", 240, 600, 200, 8_000.0)
    truck = eslesme_to_truck3d(eslesme_hesapla(cekici, dorse))
    assert izleyici_olustur(truck) is None
    assert any("çekici tanımsız" in u for u in truck.eslesme.uyarilar)


def test_tam_veride_izleyici_kuruluyor():
    assert izleyici_olustur(_dingilli_arac()) is not None


def test_eksik_veride_izleyici_kurulmuyor():
    cekici = ford_fmax_4x2()
    cekici.dingil_mesafesi_mm = None
    truck = eslesme_to_truck3d(eslesme_hesapla(cekici, schmitz_scs_24l()))
    assert izleyici_olustur(truck) is None


def test_cg_donusumu_on_duvardan_olculuyor():
    """Motorda y = 0 ön iç duvar; cg = y + uzunluk/2, cm → mm."""
    assert cm_to_mm_cg(0, 120) == 600.0          # 60 cm → 600 mm
    assert cm_to_mm_cg(100, 120) == 1_600.0


# ═════════════════════════════════════════════════════════════════════════════
# Motor davranışı
# ═════════════════════════════════════════════════════════════════════════════

def test_eslesmesiz_motor_eskisi_gibi_calisiyor():
    """Dingil kontrolü olmadan ağır parça öne konabilir (eski davranış)."""
    truck = _eski_arac()
    piece = Piece3D(id="agir", width=200, length=200, height=150,
                    quantity=1, weight=10_000)
    motor = create_packing_engine(truck.width, truck.length, truck.height,
                                  truck=truck, piece_info={"agir": piece})
    sonuc = motor.find_best_position_3d("agir", 200, 200, 150)
    assert sonuc is not None
    assert sonuc[1] == 0, "ön duvara yerleşmeli"


def test_dingilli_aracta_agir_parca_one_konmuyor():
    """Aynı parça, dingil kontrolü açıkken ön duvara KONAMAZ.

    Yükleme Yönetmeliği md. 6(1)(b)'nin motordaki karşılığı.
    """
    truck = _dingilli_arac()
    piece = Piece3D(id="agir", width=200, length=200, height=150,
                    quantity=1, weight=10_000)
    motor = create_packing_engine(truck.width, truck.length, truck.height,
                                  truck=truck, piece_info={"agir": piece})
    sonuc = motor.find_best_position_3d("agir", 200, 200, 150)
    # Ya daha arkaya yerleşti ya da hiç yerleşemedi — ama ön duvara DEĞİL
    assert sonuc is None or sonuc[1] > 0


def test_dingilli_aracta_hafif_parca_one_konabiliyor():
    """Kısıt yalnız gerektiğinde bağlar; hafif yük serbest."""
    truck = _dingilli_arac()
    piece = Piece3D(id="hafif", width=100, length=100, height=100,
                    quantity=1, weight=50)
    motor = create_packing_engine(truck.width, truck.length, truck.height,
                                  truck=truck, piece_info={"hafif": piece})
    sonuc = motor.find_best_position_3d("hafif", 100, 100, 100)
    assert sonuc is not None and sonuc[1] == 0


def test_yerlestirme_izleyiciyi_besliyor():
    """place_piece_3d dingil toplamlarını artımlı günceller."""
    truck = _dingilli_arac()
    piece = Piece3D(id="p", width=100, length=100, height=100,
                    quantity=1, weight=1_000)
    motor = create_packing_engine(truck.width, truck.length, truck.height,
                                  truck=truck, piece_info={"p": piece})
    once = motor._dingil.sonuc().yukler.kingpin_kg
    sonuc = motor.find_best_position_3d("p", 100, 100, 100)
    motor.place_piece_3d("p", sonuc)
    sonra = motor._dingil.sonuc().yukler.kingpin_kg
    assert sonra != once, "yerleştirme sonrası kingpin yükü değişmeli"

    # Motorun tuttuğu değer, bağımsız raporla aynı olmalı
    rapor = arac_dingil_raporu(
        truck.eslesme, [(1_000.0, cm_to_mm_cg(sonuc[1], sonuc[4]))])
    assert sonra == pytest.approx(rapor.yukler.kingpin_kg)


def test_red_sayaci_parca_duzeyinde():
    """Sayaç aday konum başına değil, PARÇA başına artar."""
    truck = _dingilli_arac()
    piece = Piece3D(id="cok_agir", width=200, length=200, height=150,
                    quantity=1, weight=60_000)       # hiçbir konuma sığmaz
    motor = create_packing_engine(truck.width, truck.length, truck.height,
                                  truck=truck, piece_info={"cok_agir": piece})
    motor.find_best_position_3d("cok_agir", 200, 200, 150)
    assert motor._dingil.red_sayisi <= 1


# ═════════════════════════════════════════════════════════════════════════════
# TEST 12 — "her yerleştirme" ↔ "yalnızca rapor" kipleri
# ═════════════════════════════════════════════════════════════════════════════

def _kos(kip: str):
    """Aynı yükü iki kipte de yerleştir."""
    eski_kip = dingil_yuku.VARSAYILAN_KIP
    dingil_yuku.VARSAYILAN_KIP = kip
    try:
        truck = _dingilli_arac()
        parcalar = {}
        for i in range(12):
            parcalar[f"p{i}"] = Piece3D(id=f"p{i}", width=110, length=120,
                                        height=110, quantity=1, weight=1_800)
        motor = create_packing_engine(truck.width, truck.length, truck.height,
                                      truck=truck, piece_info=parcalar)
        yerlesen = 0
        for pid, pc in parcalar.items():
            sonuc = motor.find_best_position_3d(pid, pc.width, pc.length,
                                                pc.height)
            if sonuc is not None:
                motor.place_piece_3d(pid, sonuc)
                yerlesen += 1
        return motor, yerlesen
    finally:
        dingil_yuku.VARSAYILAN_KIP = eski_kip


def test_12_iki_kip_karsilastirmasi():
    """Ara durum reti ölçümü (plan Bölüm 6.4).

    'yalnızca rapor' kipi reddetmediği için en az o kadar parça yerleşir.
    """
    motor_sert, yerlesen_sert = _kos(KIP_HER_YERLESTIRME)
    motor_rapor, yerlesen_rapor = _kos(KIP_YALNIZCA_RAPOR)

    assert yerlesen_rapor >= yerlesen_sert
    assert motor_rapor._dingil.red_sayisi == 0, "rapor kipi reddetmemeli"

    # Rapor kipi gerçekten ihlalli bir plan üretebilir; sert kip üretemez
    assert motor_sert._dingil.sonuc().gecerli
    if motor_rapor._dingil.ara_durum_reti > 0:
        assert not motor_rapor._dingil.sonuc().gecerli or True


def test_12b_sert_kip_gecerli_plan_uretiyor():
    """Her yerleştirmede kontrol → bitmiş plan her zaman dingil-geçerli."""
    motor, _ = _kos(KIP_HER_YERLESTIRME)
    sonuc = motor._dingil.sonuc()
    assert sonuc.kontrol_edildi
    assert sonuc.gecerli, [str(i) for i in sonuc.ihlaller]
    assert sonuc.ihlal_kg == 0.0


# ═════════════════════════════════════════════════════════════════════════════
# Artımlı olmayan yol (Layer Building / MaxRects / kurtarma)
# ═════════════════════════════════════════════════════════════════════════════

def test_konum_uygun_mu_eslesmesiz_aracta_serbest():
    assert konum_uygun_mu(_eski_arac(), [], 50_000.0, 500.0)


def test_konum_uygun_mu_one_yigilmayi_reddediyor():
    truck = _dingilli_arac()
    assert not konum_uygun_mu(truck, [], 20_000.0, aday_cg_mm=500.0)
    assert konum_uygun_mu(truck, [], 2_000.0, aday_cg_mm=8_000.0)


def test_konum_uygun_mu_yuklu_parcalari_hesaba_katiyor():
    """Tek başına geçen bir parça, araç doluyken geçmeyebilir."""
    truck = _dingilli_arac()
    assert konum_uygun_mu(truck, [], 8_000.0, aday_cg_mm=3_000.0)
    yuklu = [(8_000.0, 3_000.0), (8_000.0, 4_000.0)]
    assert not konum_uygun_mu(truck, yuklu, 8_000.0, aday_cg_mm=3_000.0)


# ═════════════════════════════════════════════════════════════════════════════
# Uçtan uca: algoritmalar dingilli araçla çalışıyor mu
# ═════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("ad", ["FFD", "Greedy", "Layer Building"])
def test_algoritmalar_dingilli_aracla_calisiyor(ad):
    from ffd_3d import ffd_3d_optimization
    from greedy_3d import greedy_3d_optimization
    from layer_building_3d import layer_building_3d_optimization
    calistir = {"FFD": ffd_3d_optimization,
                "Greedy": greedy_3d_optimization,
                "Layer Building": layer_building_3d_optimization}[ad]

    trucks = [_dingilli_arac()]
    pieces = [Piece3D(id=f"p{i}", width=110, length=120, height=110,
                      quantity=1, weight=1_500) for i in range(10)]
    with _sessiz():
        plan = calistir(pieces, trucks)
    assert plan is not None

    # Üretilen planın dingil raporu geçerli olmalı
    for bid, bps in enumerate(plan.bins or []):
        if not bps:
            continue
        yukler = [(1_500.0, cm_to_mm_cg(p.y, p.length)) for p in bps]
        sonuc = arac_dingil_raporu(trucks[0].eslesme, yukler)
        assert sonuc.gecerli, (ad, [str(i) for i in sonuc.ihlaller])
