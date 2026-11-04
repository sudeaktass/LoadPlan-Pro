# -*- coding: utf-8 -*-
"""
Ağırlık dağılımı ölçüm testleri (1. adım)
=========================================
    python -X utf8 -m pytest test_agirlik_dagilimi.py -q

Bu modül YALNIZCA ÖLÇER. Testler de ölçünün doğruluğunu sınar;
hiçbir algoritmanın davranışı burada denenmez.

Kabul ölçütü (Sude, 22 Ekim 2026):
  "tırın ön tarafında kümelenmiş bir grup oluştu" durumu sayıyla
  görülebilmeli — hem ağırlık merkezinin kaç cm önde olduğu, hem de
  yükün bir yerde ne kadar yığıldığı (yoğunlaşma).
"""

from __future__ import annotations

import agirlik_dagilimi as ad
from core_3d import COG_FRONT_BIAS, CuttingPlan3D, Piece3D, Placement3D, Truck3D


# ═════════════════════════════════════════════════════════════════════════════
# Kurgu yardımcıları
# ═════════════════════════════════════════════════════════════════════════════

def _truck(boy=1362, en=248, yuk=270, kapasite=25_000):
    return Truck3D("T1", en, boy, yuk, kapasite, 4)


def _parca(pid, agirlik, boy=100, en=100, yuk=100):
    return Piece3D(id=pid, width=en, length=boy, height=yuk,
                   quantity=1, weight=agirlik)


def _yerlesim(pid, y, boy=100, x=0, z=0, en=100, yuk=100):
    return Placement3D(x, y, z, en, boy, yuk, pid, (0, 0, 0), 0)


def _plan(yerlesimler, truck_id="T1"):
    return CuttingPlan3D(bins=[yerlesimler], total_waste=0, utilization=0,
                         execution_time=0.0, algorithm="test",
                         truck_assignments={0: truck_id})


def _rapor(yerlesimler, parcalar, truck=None):
    t = truck or _truck()
    return ad.plan_agirlik_dagilimi(_plan(yerlesimler), parcalar, [t])


# ═════════════════════════════════════════════════════════════════════════════
# Metre dağılımı — ağırlık parçanın boyuna yayılır
# ═════════════════════════════════════════════════════════════════════════════

def test_tek_metreye_sigan_parca_tek_dilime_yazilir():
    parcalar = [_parca("p", 300.0)]
    bilgi = {p.id: p for p in parcalar}
    dilimler = ad.metre_dagilimi([_yerlesim("p", y=0, boy=100)], bilgi, 500)
    assert dilimler[0] == 300.0
    assert sum(dilimler[1:]) == 0.0


def test_iki_metreye_yayilan_parca_ikiye_bolunur():
    """150 cm'lik parça 50 cm'den başlıyorsa: 1. metreye 50, 2.'ye 100 cm."""
    parcalar = [_parca("p", 300.0, boy=150)]
    bilgi = {p.id: p for p in parcalar}
    dilimler = ad.metre_dagilimi([_yerlesim("p", y=50, boy=150)], bilgi, 500)
    assert abs(dilimler[0] - 100.0) < 1e-6      # 300 × 50/150
    assert abs(dilimler[1] - 200.0) < 1e-6      # 300 × 100/150
    assert sum(dilimler[2:]) == 0.0


def test_agirlik_toplami_korunur():
    parcalar = [_parca(f"p{i}", 250.0, boy=120) for i in range(5)]
    bilgi = {p.id: p for p in parcalar}
    yerlesimler = [_yerlesim(f"p{i}", y=i * 120, boy=120) for i in range(5)]
    dilimler = ad.metre_dagilimi(yerlesimler, bilgi, 1362)
    assert abs(sum(dilimler) - 5 * 250.0) < 1e-6


def test_dilim_sayisi_arac_boyuna_gore():
    assert len(ad.metre_dagilimi([], {}, 1362)) == 14     # 13,62 m → 14 dilim
    assert len(ad.metre_dagilimi([], {}, 500)) == 5
    assert ad.metre_dagilimi([], {}, 0) == []


# ═════════════════════════════════════════════════════════════════════════════
# Bölüm bulma — 2. adımın ön koşulu
# ═════════════════════════════════════════════════════════════════════════════

def test_bitisik_parcalar_ayri_bolum():
    """Tam bitişik parçalar AYRI bölümdür — aralarında temiz kesim var.

    Duvar-inşa (George & Robinson) yerleşiminde duvarlar birbirine
    yaslıdır ama yine de takas edilebilir; Davies & Bischoff'un
    "kesişmeyen bölümler" tanımı tam olarak budur.
    """
    y = [_yerlesim("a", 0, 100), _yerlesim("b", 100, 100),
         _yerlesim("c", 200, 100)]
    assert ad.bolumleri_bul(y) == [(0.0, 100.0), (100.0, 200.0),
                                   (200.0, 300.0)]


def test_bosluklu_parcalar_ayri_bolum():
    y = [_yerlesim("a", 0, 100), _yerlesim("b", 300, 100),
         _yerlesim("c", 700, 100)]
    bolumler = ad.bolumleri_bul(y)
    assert bolumler == [(0.0, 100.0), (300.0, 400.0), (700.0, 800.0)]


def test_ortusen_parcalar_birlesir():
    """Y'de örtüşen parçalar aynı bölüme girer — kesim düzlemi yok."""
    y = [_yerlesim("a", 0, 150), _yerlesim("b", 100, 150)]
    assert ad.bolumleri_bul(y) == [(0.0, 250.0)]


def test_bos_yerlesim_bolum_yok():
    assert ad.bolumleri_bul([]) == []


def test_tek_bolumde_dengeleme_yapilamaz():
    """KABUL: blok takası en az iki ayrık bölüm ister.

    Y'de örtüşen parçalar tek bölüm yapar; kesilebilecek bir düzlem
    olmadığı için takas edilecek bir şey de yoktur.
    """
    parcalar = [_parca("a", 500.0, boy=150), _parca("b", 500.0, boy=150)]
    rapor = _rapor([_yerlesim("a", 0, boy=150),
                    _yerlesim("b", 100, boy=150)], parcalar)
    arac = rapor.araclar[0]
    assert arac.bolum_sayisi == 1
    assert arac.dengelenebilir_mi is False
    assert rapor.dengelenebilir_arac_sayisi == 0


def test_iki_bolumde_dengeleme_yapilabilir():
    parcalar = [_parca("a", 500.0), _parca("b", 500.0)]
    rapor = _rapor([_yerlesim("a", 0), _yerlesim("b", 400)], parcalar)
    assert rapor.araclar[0].dengelenebilir_mi is True
    assert rapor.dengelenebilir_arac_sayisi == 1


# ═════════════════════════════════════════════════════════════════════════════
# Sapma ölçüleri
# ═════════════════════════════════════════════════════════════════════════════

def test_hedef_noktalar_dogru_hesaplaniyor():
    rapor = _rapor([_yerlesim("a", 0)], [_parca("a", 100.0)])
    arac = rapor.araclar[0]
    assert abs(arac.hedef_y_cm - 1362 * COG_FRONT_BIAS) < 1e-6   # ön %40
    assert abs(arac.orta_y_cm - 681.0) < 1e-6                    # tam orta
    assert abs(arac.hedef_x_cm - 124.0) < 1e-6                   # en/2


def test_hedefteki_yuk_sifir_sapma():
    """Ağırlık merkezi tam hedefteyse sapma sıfır olmalı."""
    hedef = 1362 * COG_FRONT_BIAS                   # 544,8 cm
    rapor = _rapor([_yerlesim("a", y=hedef - 50, boy=100, x=74)],
                   [_parca("a", 1_000.0)])
    arac = rapor.araclar[0]
    assert arac.sapma_y_cm < 1e-6
    assert arac.sapma_x_cm < 1e-6
    assert arac.one_mi_arkaya_mi == "tam hedefte"


def test_onde_kumelenme_sapma_olarak_gorunuyor():
    """KABUL: Sude'nin tarif ettiği durum — her şey önde.

    Beş parça aracın ilk 5 metresinde; ağırlık merkezi hedefin ÇOK
    önünde çıkmalı ve yön 'önde' demelidir.
    """
    parcalar = [_parca(f"p{i}", 1_000.0) for i in range(5)]
    yerlesimler = [_yerlesim(f"p{i}", y=i * 100) for i in range(5)]
    arac = _rapor(yerlesimler, parcalar).araclar[0]
    assert abs(arac.cog_y_cm - 250.0) < 1e-6         # 0..500 ortası
    assert arac.one_mi_arkaya_mi == "önde"
    assert arac.sapma_y_cm > 290                     # 544,8 − 250 ≈ 295
    assert abs(arac.sapma_orta_y_cm - 431.0) < 1.0   # 681 − 250


def test_arkada_kumelenme_yonu_dogru():
    parcalar = [_parca(f"p{i}", 1_000.0) for i in range(3)]
    yerlesimler = [_yerlesim(f"p{i}", y=1000 + i * 100) for i in range(3)]
    assert _rapor(yerlesimler, parcalar).araclar[0].one_mi_arkaya_mi == "arkada"


def test_yanal_sapma_olculuyor():
    """Hepsi sola yaslıysa yanal sapma ortaya çıkmalı."""
    arac = _rapor([_yerlesim("a", 0, x=0, en=100)],
                  [_parca("a", 500.0)]).araclar[0]
    assert abs(arac.sapma_x_cm - 74.0) < 1e-6        # |50 − 124|


def test_cog_yuksekligi_ve_orani():
    arac = _rapor([_yerlesim("a", 0, z=0, yuk=100)],
                  [_parca("a", 500.0)]).araclar[0]
    assert abs(arac.cog_z_cm - 50.0) < 1e-6
    assert abs(arac.cog_z_orani - 50.0 / 270.0) < 1e-6


# ═════════════════════════════════════════════════════════════════════════════
# Yoğunlaşma — kümelenmenin tek sayılık ölçüsü
# ═════════════════════════════════════════════════════════════════════════════

def test_duzgun_dagilimda_yogunlasma_bire_yakin():
    """Aracın her metresine eşit yük → yoğunlaşma ≈ 1,0."""
    t = _truck(boy=1000)
    parcalar = [_parca(f"p{i}", 100.0) for i in range(10)]
    yerlesimler = [_yerlesim(f"p{i}", y=i * 100) for i in range(10)]
    arac = _rapor(yerlesimler, parcalar, t).araclar[0]
    assert abs(arac.yogunlasma - 1.0) < 1e-6


def test_kumelenmede_yogunlasma_buyuyor():
    """Bütün yük tek metrede → yoğunlaşma = metre sayısı."""
    t = _truck(boy=1000)
    arac = _rapor([_yerlesim("a", 0)], [_parca("a", 1_000.0)], t).araclar[0]
    assert arac.metre_sayisi == 10
    assert abs(arac.yogunlasma - 10.0) < 1e-6
    assert arac.en_agir_metre_no == 1


def test_en_agir_metre_dogru_bulunuyor():
    t = _truck(boy=500)
    parcalar = [_parca("hafif", 100.0), _parca("agir", 900.0)]
    yerlesimler = [_yerlesim("hafif", y=0), _yerlesim("agir", y=200)]
    arac = _rapor(yerlesimler, parcalar, t).araclar[0]
    assert arac.en_agir_metre_no == 3                # 200-300 cm → 3. metre
    assert abs(arac.en_agir_metre_kg - 900.0) < 1e-6


def test_yuksuz_aracta_olculer_bos():
    """Ağırlığı sıfır olan yük bölme hatası vermemeli."""
    arac = _rapor([_yerlesim("a", 0)], [_parca("a", 0.0)]).araclar[0]
    assert arac.yuk_kg == 0.0
    assert arac.yogunlasma is None
    assert arac.ortalama_metre_kg is None


# ═════════════════════════════════════════════════════════════════════════════
# Plan düzeyi
# ═════════════════════════════════════════════════════════════════════════════

def test_bos_plan_bos_rapor():
    assert ad.plan_agirlik_dagilimi(None, [], []).araclar == []
    assert ad.plan_agirlik_dagilimi(_plan([]), [], [_truck()]).araclar == []


def test_bos_arac_paydaya_girmez():
    """Hiç yük almamış araç 'kullanılan araç' sayılmaz (doluluk.py kuralı)."""
    plan = CuttingPlan3D(bins=[[_yerlesim("a", 0)], []], total_waste=0,
                         utilization=0, execution_time=0.0, algorithm="test",
                         truck_assignments={0: "T1", 1: "T2"})
    t1, t2 = _truck(), _truck()
    t2.id = "T2"
    rapor = ad.plan_agirlik_dagilimi(plan, [_parca("a", 100.0)], [t1, t2])
    assert rapor.arac_sayisi == 1


def test_plan_ozetleri_ortalama_ve_en_kotu():
    t1, t2 = _truck(boy=1000), _truck(boy=1000)
    t2.id = "T2"
    plan = CuttingPlan3D(
        bins=[[_yerlesim("a", 0)], [_yerlesim("b", 400)]],
        total_waste=0, utilization=0, execution_time=0.0, algorithm="test",
        truck_assignments={0: "T1", 1: "T2"})
    parcalar = [_parca("a", 1_000.0), _parca("b", 1_000.0)]
    rapor = ad.plan_agirlik_dagilimi(plan, parcalar, [t1, t2])
    sapmalar = [a.sapma_y_cm for a in rapor.araclar]
    assert abs(rapor.sapma_y_en_kotu_cm - max(sapmalar)) < 1e-6
    assert abs(rapor.sapma_y_ortalama_cm
               - sum(sapmalar) / len(sapmalar)) < 1e-6


def test_bilinmeyen_arac_atlaniyor():
    """truck_assignments'ta olmayan araç rapora girmez, patlamaz."""
    plan = CuttingPlan3D(bins=[[_yerlesim("a", 0)]], total_waste=0,
                         utilization=0, execution_time=0.0, algorithm="test",
                         truck_assignments={0: "YOK"})
    rapor = ad.plan_agirlik_dagilimi(plan, [_parca("a", 100.0)], [_truck()])
    assert rapor.araclar == []


# ═════════════════════════════════════════════════════════════════════════════
# Biçimlendirme — bilinmeyen değer "—" olmalı, sıfır DEĞİL
# ═════════════════════════════════════════════════════════════════════════════

def test_bilinmeyen_deger_tire_gosterilir():
    assert ad.cm(None) == "—"
    assert ad.sayi(None) == "—"
    assert ad.cm(35.4) == "35 cm"
    assert ad.sayi(1.0) == "1.00"


def test_arac_satirlari_tum_sutunlari_veriyor():
    rapor = _rapor([_yerlesim("a", 0)], [_parca("a", 500.0)])
    satir = ad.arac_satirlari(rapor)[0]
    for sutun in ("Araç", "Yük (kg)", "CoG Y (cm)", "Hedeften (cm)", "Yön",
                  "Ortadan (cm)", "Yanal (cm)", "CoG Z (cm)",
                  "En ağır metre", "Yoğunlaşma", "Bölüm"):
        assert sutun in satir
