# -*- coding: utf-8 -*-
"""
Yükleme sırası testleri
=======================
    python -X utf8 -m pytest test_yukleme_sirasi.py -q

Kabul ölçütü (Sude, 22 Ekim 2026):
  "ürünlerin her birine kapıya en uzak noktadan başlayarak numaralar
  verilsin, sonra bu numaralar yük yerleşimi görselinde de görünsün"

En kritik test: sürücü talimatı (PDF + Excel) ile 3B görselin AYNI
numarayı göstermesi. Operatör kâğıttaki numarayı görselde arayacak;
iki yerde farklı numara çıkarsa özellik ters teper.
"""

from __future__ import annotations

from core_3d import CuttingPlan3D, Piece3D, Placement3D, Truck3D
from yukleme_sirasi import KURAL_METNI, sira_numaralari, sirali


def _y(pid, x=0, y=0, z=0, en=100, boy=100, yuk=100):
    return Placement3D(x, y, z, en, boy, yuk, pid, (0, 0, 0), 0)


def _d(pid, x=0, y=0, z=0, en=100, boy=100, yuk=100):
    """Raporların kullandığı sözlük biçimi."""
    return {"piece_id": pid, "x": x, "y": y, "z": z,
            "width": en, "length": boy, "height": yuk}


# ═════════════════════════════════════════════════════════════════════════════
# Kural: kapıdan uzak → kapıya doğru, alttan üste, soldan sağa
# ═════════════════════════════════════════════════════════════════════════════

def test_kapidan_uzak_once_numaralanir():
    """Y küçük = ön duvar = kapıdan en uzak = 1 numara."""
    y = [_y("kapiya_yakin", y=900), _y("ortada", y=400), _y("en_dipte", y=0)]
    assert sira_numaralari(y) == [3, 2, 1]
    assert [p.piece_id for _, p in sirali(y)] == [
        "en_dipte", "ortada", "kapiya_yakin"]


def test_ayni_siradaki_alt_katman_once():
    """Aynı Y'de alttaki önce yüklenir."""
    y = [_y("ust", y=0, z=100), _y("alt", y=0, z=0)]
    assert sira_numaralari(y) == [2, 1]


def test_ayni_y_ve_z_de_soldan_saga():
    y = [_y("sag", y=0, z=0, x=200), _y("sol", y=0, z=0, x=0)]
    assert sira_numaralari(y) == [2, 1]


def test_oncelik_sirasi_y_z_x():
    """Y her zaman Z'yi, Z her zaman X'i yener."""
    y = [
        _y("A", y=100, z=0,   x=0),      # Y büyük → en son
        _y("B", y=0,   z=100, x=0),      # Y küçük, Z büyük → ikinci
        _y("C", y=0,   z=0,   x=500),    # Y küçük, Z küçük → birinci
    ]
    assert sira_numaralari(y) == [3, 2, 1]


def test_numaralar_bire_kadar_kesintisiz():
    y = [_y(f"p{i}", y=i * 100) for i in range(7)]
    numaralar = sira_numaralari(y)
    assert sorted(numaralar) == list(range(1, 8))


def test_bos_liste():
    assert sira_numaralari([]) == []
    assert sirali([]) == []


def test_girdi_sirasi_korunuyor():
    """sira_numaralari listeyi YENİDEN SIRALAMAZ, numara döndürür."""
    y = [_y("a", y=500), _y("b", y=0)]
    numaralar = sira_numaralari(y)
    assert numaralar == [2, 1]          # a=2, b=1
    assert y[0].piece_id == "a"         # girdi listesi değişmedi


def test_sirali_artan_dondurur():
    y = [_y("a", y=500), _y("b", y=0)]
    cikti = sirali(y)
    assert [no for no, _ in cikti] == [1, 2]
    assert [p.piece_id for _, p in cikti] == ["b", "a"]


# ═════════════════════════════════════════════════════════════════════════════
# Hem dataclass hem sözlük ile çalışmalı
# ═════════════════════════════════════════════════════════════════════════════

def test_sozluk_ve_dataclass_ayni_sonucu_verir():
    """Raporlar sözlük, görsel dataclass kullanıyor — sonuç aynı olmalı."""
    kurgu = [("a", 0, 900), ("b", 0, 0), ("c", 100, 0)]   # (id, z, y)
    nesneler = [_y(i, y=yy, z=zz) for i, zz, yy in kurgu]
    sozlukler = [_d(i, y=yy, z=zz) for i, zz, yy in kurgu]
    assert sira_numaralari(nesneler) == sira_numaralari(sozlukler)


def test_eksik_alanli_sozluk_patlamiyor():
    """Koordinatı olmayan kayıt 0 sayılır, hata vermez."""
    assert sira_numaralari([{"piece_id": "x"}, _d("y", y=100)]) == [1, 2]


# ═════════════════════════════════════════════════════════════════════════════
# KABUL: rapor ile görsel aynı numarayı göstermeli
# ═════════════════════════════════════════════════════════════════════════════

def _plan_ve_parcalar():
    yerlesimler = [
        _y("P1", x=0,   y=600, z=0),
        _y("P2", x=0,   y=0,   z=0),
        _y("P3", x=0,   y=0,   z=100),
        _y("P4", x=120, y=0,   z=0),
        _y("P5", x=0,   y=300, z=0),
    ]
    parcalar = [Piece3D(id=f"P{i}", width=100, length=100, height=100,
                        quantity=1, weight=100.0) for i in range(1, 6)]
    plan = CuttingPlan3D(bins=[yerlesimler], total_waste=0, utilization=50.0,
                         execution_time=0.0, algorithm="test",
                         truck_assignments={0: "T1"})
    return plan, parcalar, yerlesimler


def test_raporun_hesabi_tek_kaynaktan_geliyor():
    """reports._compute_loading_order artık kendi kuralını tutmuyor."""
    from reports import _compute_loading_order
    sozlukler = [_d("a", y=500), _d("b", y=0), _d("c", y=250)]
    assert _compute_loading_order(sozlukler) == sira_numaralari(sozlukler)


def test_gorseldeki_numara_raporla_ayni():
    """KABUL ÖLÇÜTÜ — kâğıttaki numara ile görseldeki numara aynı olmalı."""
    import plotly_3d
    plan, parcalar, yerlesimler = _plan_ve_parcalar()
    truck = Truck3D("T1", 248, 1362, 270, 25_000, 4)

    fig = plotly_3d.visualize_3d_plan(plan, [truck], parcalar, bin_id=0)
    rozet = next(tr for tr in fig.data
                 if getattr(tr, "name", "") == "🔢 Yükleme sırası")

    beklenen = sira_numaralari(yerlesimler)
    assert list(rozet.text) == [str(n) for n in beklenen]

    # Rapor tarafı da aynı numarayı vermeli
    from reports import _compute_loading_order
    sozlukler = [_d(p.piece_id, x=p.x, y=p.y, z=p.z) for p in yerlesimler]
    assert _compute_loading_order(sozlukler) == beklenen


def test_rozet_urunun_ustune_yaziliyor():
    """Numara ürünün üst yüzünün ortasında durmalı — içinde kaybolmasın."""
    import plotly_3d
    plan, parcalar, yerlesimler = _plan_ve_parcalar()
    truck = Truck3D("T1", 248, 1362, 270, 25_000, 4)
    fig = plotly_3d.visualize_3d_plan(plan, [truck], parcalar, bin_id=0)
    rozet = next(tr for tr in fig.data
                 if getattr(tr, "name", "") == "🔢 Yükleme sırası")
    for i, pl in enumerate(yerlesimler):
        assert rozet.x[i] == pl.x + pl.width / 2
        assert rozet.y[i] == pl.y + pl.length / 2
        assert rozet.z[i] == pl.z + pl.height + 1


def test_rozet_kapatilabiliyor():
    import plotly_3d
    plan, parcalar, _ = _plan_ve_parcalar()
    truck = Truck3D("T1", 248, 1362, 270, 25_000, 4)
    fig = plotly_3d.visualize_3d_plan(plan, [truck], parcalar, bin_id=0,
                                      show_order=False)
    assert not any(getattr(tr, "name", "") == "🔢 Yükleme sırası"
                   for tr in fig.data)


def test_sira_numarasi_hoverda_da_var():
    """Rozet kapalıyken bile ürünün üstüne gelince numara görünsün."""
    import plotly_3d
    plan, parcalar, _ = _plan_ve_parcalar()
    truck = Truck3D("T1", 248, 1362, 270, 25_000, 4)
    fig = plotly_3d.visualize_3d_plan(plan, [truck], parcalar, bin_id=0,
                                      show_order=False)
    hoverlar = " ".join(str(getattr(tr, "hovertemplate", "") or "")
                        for tr in fig.data)
    assert "Yükleme sırası" in hoverlar


def test_excel_talimat_sayfasi_ayni_numarayi_yaziyor():
    """Excel sayfası da tek kaynaktan okumalı — kendi sıralaması kalmadı."""
    from openpyxl import Workbook

    from reports import _add_loading_sheet

    plan, parcalar, yerlesimler = _plan_ve_parcalar()
    wb = Workbook()
    _add_loading_sheet(
        wb, "Yükleme Talimatı", "Test",
        plan,
        [{"ID": "T1", "Genişlik (cm)": 248, "Uzunluk (cm)": 1362,
          "Yükseklik (cm)": 270}],
        {p.id: {"weight": p.weight} for p in parcalar})
    ws = wb["Yükleme Talimatı"]

    # Başlık satırlarından sonra: sıra no (A) + palet ID (B) sütunları
    satirlar = [(ws.cell(r, 1).value, ws.cell(r, 2).value)
                for r in range(1, ws.max_row + 1)
                if isinstance(ws.cell(r, 1).value, int)]
    beklenen = [(no, p.piece_id) for no, p in sirali(yerlesimler)]
    assert satirlar == beklenen


def test_kural_metni_aciklayici():
    assert "kapıdan" in KURAL_METNI.lower()
    assert "1 numara" in KURAL_METNI
