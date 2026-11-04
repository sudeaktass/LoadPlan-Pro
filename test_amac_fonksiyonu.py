# -*- coding: utf-8 -*-
"""
Ortak amaç fonksiyonu testleri (3. adım)
========================================
    python -X utf8 -m pytest test_amac_fonksiyonu.py -q

Kabul ölçütleri:
  K1-1) Araç sayısı HER ZAMAN yener: daha az araçlı bir çözüm, dengesi
        ya da doluluğu daha kötü olsa bile kazanmalı.
  Deb ) Geçerli çözüm geçersizi HER ZAMAN yener.
  F   ) Araç sayısı eşitken Falkenauer terimi yol göstermeli (düz
        manzara olmamalı).
"""

from __future__ import annotations

import amac_fonksiyonu as af
import core_3d
from core_3d import Piece3D, Placement3D, Truck3D


def _t(tid, en=248, boy=1362, yuk=270, kap=25_000):
    return Truck3D(tid, en, boy, yuk, kap, 4)


def _p(pid, en=100, boy=100, yuk=100, kg=100.0, prio=None):
    return Piece3D(id=pid, width=en, length=boy, height=yuk,
                   quantity=1, weight=kg, priority=prio)


def _y(pid, x=0, y=0, z=0, en=100, boy=100, yuk=100):
    return Placement3D(x, y, z, en, boy, yuk, pid, (0, 0, 0), 0)


def _amac(bins, atama, trucks, parcalar, yerlesmeyen=0, tasma=0):
    return af.amac(bins, atama, trucks, {p.id: p for p in parcalar},
                   yerlesmeyen, tasma)[0]


# ═════════════════════════════════════════════════════════════════════════════
# Falkenauer terimi
# ═════════════════════════════════════════════════════════════════════════════

def test_falkenauer_dolu_araci_odullendiriyor():
    assert af.falkenauer_terimi([0.9]) > af.falkenauer_terimi([0.5])


def test_falkenauer_ayni_toplamda_yogun_dolulugu_tercih_ediyor():
    """k>1 olduğu için 'iyi dolmuş birkaç araç' > 'eşit dağılmış araçlar'."""
    assert af.falkenauer_terimi([1.0, 0.2]) > af.falkenauer_terimi([0.6, 0.6])


def test_falkenauer_bos_liste():
    assert af.falkenauer_terimi([]) == 0.0


def test_falkenauer_araligi():
    assert af.falkenauer_terimi([0.0, 0.0]) == 0.0
    assert af.falkenauer_terimi([1.0, 1.0]) == 1.0


def test_falkenauer_homojen_kutuda_az_arac_kazanir():
    """Falkenauer'in k<=2 kanıtı: aynı yük, daha az kutu daha iyi."""
    assert af.falkenauer_terimi([0.90]) > af.falkenauer_terimi([0.45, 0.45])


def test_falkenauer_heterojen_filoda_GARANTI_VERMIYOR():
    """KANITLANAN SINIR — bu yüzden araç sayısı ayrı bir düzeydir.

    Falkenauer tüm kutuların aynı kapasitede olduğunu varsayar. Heterojen
    filoda iki küçük araç, bir büyük araçtan yüksek skor alabiliyor.
    """
    bir_buyuk = af.falkenauer_terimi([100 / 1000])          # u = 0,10
    iki_kucuk = af.falkenauer_terimi([50 / 55, 50 / 55])    # u = 0,91
    assert iki_kucuk > bir_buyuk, "karşı örnek artık geçerli değil mi?"


# ═════════════════════════════════════════════════════════════════════════════
# KABUL K1-1: araç sayısı her zaman yener
# ═════════════════════════════════════════════════════════════════════════════

def test_az_arac_kotu_dolulukla_bile_kazanir():
    """Heterojen filodaki karşı örneğin amaç fonksiyonunda ÇÖZÜLDÜĞÜ test."""
    buyuk = _t("BUYUK", en=1000, boy=1000, yuk=1000)
    k1, k2 = _t("K1", en=100, boy=100, yuk=550), _t("K2", en=100, boy=100, yuk=550)
    parcalar = [_p("a"), _p("b")]

    tek = _amac([[_y("a"), _y("b", y=100)]], {0: "BUYUK"}, [buyuk], parcalar)
    cift = _amac([[_y("a")], [_y("b")]], {0: "K1", 1: "K2"}, [k1, k2], parcalar)
    assert tek < cift, "tek araç, doluluğu çok düşük olsa bile kazanmalı"


def test_bir_arac_farki_alt_duzeylerin_tamamindan_pahali():
    """Hiyerarşi KESİN: araç ağırlığı, altındaki iki düzeyin toplamından büyük."""
    assert abs(sum(af.AGIRLIKLAR.values()) - 1.0) < 1e-9   # sürekli ≤ 1,0
    assert af.AGIRLIK_COG_TOL > 1.0                        # CoG tol > sürekli
    assert af.AGIRLIK_ARAC > af.AGIRLIK_COG_TOL + 1.0      # araç > ikisi


def test_denge_ugruna_fazladan_arac_acilmiyor():
    """Eski formülün açığı: CoG cezası fazladan aracın bedelini ödüyordu."""
    t1, t2 = _t("T1"), _t("T2")
    parcalar = [_p(f"p{i}", kg=1000.0) for i in range(4)]

    # Tek araç, hepsi önde kümelenmiş → CoG berbat
    kotu_denge = _amac([[_y(f"p{i}", y=i * 100) for i in range(4)]],
                       {0: "T1"}, [t1, t2], parcalar)
    # İki araç, ikisi de dengeli → CoG mükemmele yakın
    iyi_denge = _amac([[_y("p0", y=500), _y("p1", y=600)],
                       [_y("p2", y=500), _y("p3", y=600)]],
                      {0: "T1", 1: "T2"}, [t1, t2], parcalar)
    assert kotu_denge < iyi_denge


# ═════════════════════════════════════════════════════════════════════════════
# KABUL Deb: geçerli > geçersiz
# ═════════════════════════════════════════════════════════════════════════════

def test_yerlesmeyen_parca_her_seyi_yener():
    t1, t2, t3 = _t("T1"), _t("T2"), _t("T3")
    parcalar = [_p("a"), _p("b")]
    hepsi_yerlesti_cok_arac = _amac(
        [[_y("a")], [_y("b")], []], {0: "T1", 1: "T2", 2: "T3"},
        [t1, t2, t3], parcalar, yerlesmeyen=0)
    tek_arac_ama_dusen_var = _amac(
        [[_y("a")]], {0: "T1"}, [t1, t2, t3], parcalar, yerlesmeyen=1)
    assert hepsi_yerlesti_cok_arac < tek_arac_ama_dusen_var


def test_daha_az_ihlal_daha_iyi():
    """Deb (iii): iki geçersizden ihlali küçük olan seçilir."""
    t1 = _t("T1")
    parcalar = [_p("a")]
    bir = _amac([[_y("a")]], {0: "T1"}, [t1], parcalar, yerlesmeyen=1)
    iki = _amac([[_y("a")]], {0: "T1"}, [t1], parcalar, yerlesmeyen=2)
    assert bir < iki


def test_tasma_araci_da_gecersizlik():
    t1 = _t("T1")
    parcalar = [_p("a")]
    temiz = _amac([[_y("a")]], {0: "T1"}, [t1], parcalar)
    tasmali = _amac([[_y("a")]], {0: "T1"}, [t1], parcalar, tasma=1)
    assert temiz < tasmali


# ═════════════════════════════════════════════════════════════════════════════
# Araç sayısı eşitken: doluluk, öncelik, CoG
# ═════════════════════════════════════════════════════════════════════════════

def test_esit_aracta_yuksek_doluluk_kazanir():
    kucuk = _t("K", en=120, boy=240, yuk=120)
    buyuk = _t("B", en=248, boy=1362, yuk=270)
    parcalar = [_p("a"), _p("b")]
    yerlesim = [_y("a"), _y("b", y=100)]
    dolu = _amac([yerlesim], {0: "K"}, [kucuk, buyuk], parcalar)
    bos = _amac([yerlesim], {0: "B"}, [kucuk, buyuk], parcalar)
    assert dolu < bos


def test_oncelik_ihlali_cezalandiriliyor_ama_parca_dusurmekten_ucuz():
    """Yumuşak öncelik: yanlış yere koymak, hiç yüklememekten iyidir."""
    t1 = _t("T1")
    parcalar = [_p("a", prio=1)]
    yanlis_yer = _amac([[_y("a", y=0)]], {0: "T1"}, [t1], parcalar)      # kapıdan uzak
    dogru_yer = _amac([[_y("a", y=1200)]], {0: "T1"}, [t1], parcalar)    # kapıya yakın
    hic_yok = _amac([[]], {0: "T1"}, [t1], parcalar, yerlesmeyen=1)
    assert dogru_yer < yanlis_yer < hic_yok


def test_onceliksiz_yukte_oncelik_terimi_sifir():
    t1 = _t("T1")
    parcalar = [_p("a")]
    bilgi = {p.id: p for p in parcalar}
    assert af._oncelik_normalize([[_y("a")]], bilgi, [t1], {0: "T1"}) == 0.0


def test_cog_sapmasi_cezalandiriliyor():
    t1 = _t("T1")
    parcalar = [_p("a", kg=1000.0), _p("b", kg=1000.0)]
    hedef = int(1362 * 0.40)
    ortada = _amac([[_y("a", x=74, y=hedef - 100), _y("b", x=74, y=hedef)]],
                   {0: "T1"}, [t1], parcalar)
    kosede = _amac([[_y("a", x=0, y=0), _y("b", x=0, y=100)]],
                   {0: "T1"}, [t1], parcalar)
    assert ortada < kosede


# ═════════════════════════════════════════════════════════════════════════════
# KABUL: ağırlık merkezi STANDARTLARIN DIŞINA çıkmamalı
# ═════════════════════════════════════════════════════════════════════════════

def _dengeli_ve_dengesiz():
    """Aynı iki parça: biri tolerans içinde, biri dışında yerleşmiş."""
    hedef = int(1362 * 0.40)
    dengeli = [_y("a", x=74, y=hedef - 100), _y("b", x=74, y=hedef)]
    dengesiz = [_y("a", x=0, y=0), _y("b", x=0, y=100)]
    return dengeli, dengesiz


def test_tolerans_disi_arac_sayiliyor():
    t1 = _t("T1")
    parcalar = [_p("a", kg=1000.0), _p("b", kg=1000.0)]
    bilgi = {p.id: p for p in parcalar}
    dengeli, dengesiz = _dengeli_ve_dengesiz()
    assert af.cog_tolerans_ihlali([dengesiz], bilgi, [t1], {0: "T1"}) == (1, 1)
    assert af.cog_tolerans_ihlali([dengeli], bilgi, [t1], {0: "T1"})[0] == 0


def test_tolerans_disina_doluluk_ugruna_cikilmiyor():
    """KABUL: standart dışı denge, daha iyi doluluk ile satın alınamaz.

    Dar araç → yüksek doluluk ama ağırlık merkezi tolerans dışı.
    Geniş araç → düşük doluluk ama denge standart içinde.
    Araç sayısı eşit olduğu için tolerans kazanmalı.
    """
    dar = _t("DAR", en=100, boy=1362, yuk=120)        # küçük hacim → dolu
    genis = _t("GENIS", en=248, boy=1362, yuk=270)    # büyük hacim → boş
    parcalar = [_p("a", kg=1000.0), _p("b", kg=1000.0)]
    dengeli, dengesiz = _dengeli_ve_dengesiz()

    # Önce kurgunun gerçekten istediğimiz gibi olduğunu doğrula
    bilgi = {p.id: p for p in parcalar}
    assert af.cog_tolerans_ihlali([dengesiz], bilgi, [dar], {0: "DAR"})[0] == 1
    assert af.cog_tolerans_ihlali([dengeli], bilgi, [genis],
                                  {0: "GENIS"})[0] == 0

    tolerans_disi_dolu = _amac([dengesiz], {0: "DAR"}, [dar, genis], parcalar)
    tolerans_ici_bos = _amac([dengeli], {0: "GENIS"}, [dar, genis], parcalar)
    assert tolerans_ici_bos < tolerans_disi_dolu


def test_tolerans_icin_fazladan_arac_acilmiyor():
    """Ama dengeyi düzeltmek için sefer sayısı ARTMAZ — K1 üstte kalır."""
    t1, t2 = _t("T1"), _t("T2")
    parcalar = [_p("a", kg=1000.0), _p("b", kg=1000.0)]
    tek_ama_dengesiz = _amac([[_y("a", x=0, y=0), _y("b", x=0, y=100)]],
                             {0: "T1"}, [t1, t2], parcalar)
    hedef = int(1362 * 0.40)
    iki_ama_dengeli = _amac([[_y("a", x=74, y=hedef)],
                             [_y("b", x=74, y=hedef)]],
                            {0: "T1", 1: "T2"}, [t1, t2], parcalar)
    assert tek_ama_dengesiz < iki_ama_dengeli


def test_dingil_ihlali_tolerans_ihlalinden_agir():
    """Yasal sınır (dingil), tavsiye niteliğindeki toleransı yener."""
    assert af.AGIRLIK_ARAC > af.AGIRLIK_COG_TOL


def test_dokum_tolerans_bilgisini_veriyor():
    t1 = _t("T1")
    parcalar = [_p("a", kg=1000.0), _p("b", kg=1000.0)]
    bilgi = {p.id: p for p in parcalar}
    d = af.dokum([[_y("a", x=0, y=0), _y("b", x=0, y=100)]],
                 {0: "T1"}, [t1], bilgi)
    assert d["cog_tolerans_disi_arac"] == 1.0
    assert d["cog_tolerans_disi_oran"] == 1.0


# ═════════════════════════════════════════════════════════════════════════════
# Arayüz uyumu ve dökümle tutarlılık
# ═════════════════════════════════════════════════════════════════════════════

def test_eski_arayuz_korunuyor():
    """packing_objective aynı imzayı ve (uygunluk, doluluk%) döndürmeli."""
    t1 = _t("T1")
    parcalar = [_p("a")]
    uygunluk, doluluk = core_3d.packing_objective(
        [[_y("a")]], {0: "T1"}, [t1], {p.id: p for p in parcalar})
    assert isinstance(uygunluk, float) and 0.0 <= doluluk <= 100.0


def test_eski_amac_hala_cagrilabiliyor():
    """Önce/sonra deneyi için eski formül duruyor olmalı."""
    t1 = _t("T1")
    parcalar = [_p("a")]
    eski = core_3d._eski_packing_objective(
        [[_y("a")]], {0: "T1"}, [t1], {p.id: p for p in parcalar})
    assert len(eski) == 2


def test_dokum_uygunlukla_tutarli():
    t1 = _t("T1")
    parcalar = [_p("a"), _p("b")]
    bilgi = {p.id: p for p in parcalar}
    bins, atama = [[_y("a"), _y("b", y=100)]], {0: "T1"}
    d = af.dokum(bins, atama, [t1], bilgi)
    u, _ = af.amac(bins, atama, [t1], bilgi)
    assert abs(d["uygunluk"] - u) < 1e-9
    assert d["arac_sayisi"] == 1.0


def test_bos_plan_patlamiyor():
    assert af.amac([], {}, [], {})[0] >= 0.0
    assert af.amac([[]], {0: "T1"}, [_t("T1")], {})[1] == 0.0


def test_bos_arac_sayilmiyor():
    """Hiç yük almamış araç 'kullanılan araç' değildir (doluluk.py kuralı)."""
    t1, t2 = _t("T1"), _t("T2")
    parcalar = [_p("a")]
    bilgi = {p.id: p for p in parcalar}
    assert af.dokum([[_y("a")], []], {0: "T1", 1: "T2"},
                    [t1, t2], bilgi)["arac_sayisi"] == 1.0


def test_dingil_verisi_yoksa_ihlal_sayilmiyor():
    """Veri eksikse tahmin yürütülmez — araç geçersiz sayılmaz."""
    t1 = _t("T1")                       # eslesme yok
    parcalar = [_p("a", kg=50_000.0)]   # abartı ağır
    assert af.dingil_ihlali([[_y("a")]], {p.id: p for p in parcalar},
                            [t1], {0: "T1"}) == 0
