# -*- coding: utf-8 -*-
"""
Bin başına önbellek testleri
============================
    python -X utf8 -m pytest test_bin_onbellegi.py -q

`evaluate_solution` her aday için BÜTÜN binleri baştan paketliyordu; oysa
bir komşuluk hamlesi genellikle TEK bini değiştirir. Bir bin'in
paketlemesi yalnız (atandığı araç, o bin'in sıralı parça listesi)
ikilisine bağlıdır — binler arası bağımlılık yoktur.

Bu testlerin ASIL İŞİ: önbelleğin YAKLAŞIKLAMA DEĞİL, birebir aynı
sonucu verdiğini kanıtlamak. Çakışma, destek, ağırlık, CoG ve filo
kısıtları motorda hesaplanmaya devam eder.
"""

from __future__ import annotations

import contextlib
import inspect
import io
import random

import pytest

from core_3d import Piece3D, Truck3D
from tabu_search_3d import TSSolution, evaluate_solution


def _araclar(adet=4, en=240, boy=600, yuk=200, kap=30_000):
    t = Truck3D("T1", en, boy, yuk, kap, 6)
    t.available = adet
    return [t]


def _parcalar(n=24, seed=0):
    rnd = random.Random(seed)
    olcu = [(40, 60, 50), (120, 200, 150), (60, 80, 70), (100, 160, 120),
            (50, 70, 60)]
    out = []
    for i in range(n):
        w, l, h = olcu[rnd.randrange(len(olcu))]
        out.append(Piece3D(id=f"p{i}", width=w, length=l, height=h,
                           quantity=1, weight=rnd.randint(80, 400)))
    return out


def _rastgele_cozum(n, n_bin, rnd):
    ba = [rnd.randrange(n_bin) for _ in range(n)]
    po = {}
    for i, b in enumerate(ba):
        po.setdefault(b, []).append(i)
    return TSSolution(bin_assignments=ba, piece_orders=po)


def _iz(plan):
    return [(bi, pl.piece_id, pl.x, pl.y, pl.z, pl.width, pl.length,
             pl.height, pl.bin_id)
            for bi, b in enumerate(plan.bins) for pl in b]


def _degerlendir(sol, parcalar, araclar, onbellek):
    bilgi = {p.id: p for p in parcalar}
    with contextlib.redirect_stdout(io.StringIO()):
        return evaluate_solution(sol, list(parcalar), araclar, bilgi, "EP",
                                 bin_cache=onbellek)


# ═════════════════════════════════════════════════════════════════════════════
# KABUL: önbellekli ve önbelleksiz sonuçlar BİREBİR aynı olmalı
# ═════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("seed", [1, 2, 3])
def test_onbellek_sonucu_degistirmiyor(seed):
    rnd = random.Random(seed)
    parcalar = _parcalar(24, seed)
    araclar = _araclar(4)
    onbellek = {}
    for _ in range(6):
        sol = _rastgele_cozum(len(parcalar), rnd.randint(2, 4), rnd)
        f1, u1, b1, p1 = _degerlendir(sol, parcalar, araclar, None)
        f2, u2, b2, p2 = _degerlendir(sol, parcalar, araclar, onbellek)
        assert (f1, u1, b1) == (f2, u2, b2)
        assert _iz(p1) == _iz(p2)


def test_ayni_cozum_ikinci_cagrida_da_ayni():
    """Önbellek dolduktan sonra da sonuç değişmemeli."""
    parcalar = _parcalar(20, 11)
    araclar = _araclar(3)
    rnd = random.Random(11)
    sol = _rastgele_cozum(len(parcalar), 3, rnd)
    onbellek = {}
    ilk = _degerlendir(sol, parcalar, araclar, onbellek)
    ikinci = _degerlendir(sol, parcalar, araclar, onbellek)
    assert ilk[:3] == ikinci[:3]
    assert _iz(ilk[3]) == _iz(ikinci[3])


def test_yerlesmeyen_sayisi_onbellekte_de_dogru():
    """Düşen parça sayısı bin başına saklanıp doğru toplanmalı."""
    # Kasten küçük araç → çok parça düşsün
    t = Truck3D("K", 100, 100, 100, 1_000, 2)
    t.available = 2
    parcalar = _parcalar(14, 5)
    rnd = random.Random(5)
    sol = _rastgele_cozum(len(parcalar), 2, rnd)
    f1, u1, b1, p1 = _degerlendir(sol, parcalar, [t], None)
    f2, u2, b2, p2 = _degerlendir(sol, parcalar, [t], {})
    assert f1 == f2
    yerlesen1 = sum(len(b) for b in p1.bins)
    yerlesen2 = sum(len(b) for b in p2.bins)
    assert yerlesen1 == yerlesen2


def test_bin_id_etiketi_duzeltiliyor():
    """Önbellekten gelen yerleşimlerin bin_id'si yeni sıraya göre olmalı."""
    parcalar = _parcalar(12, 3)
    araclar = _araclar(3)
    onbellek = {}
    a = TSSolution(bin_assignments=[0] * 6 + [1] * 6,
                   piece_orders={0: list(range(6)), 1: list(range(6, 12))})
    _degerlendir(a, parcalar, araclar, onbellek)
    # Aynı iki grup, ama bin numaraları takas edilmiş
    b = TSSolution(bin_assignments=[1] * 6 + [0] * 6,
                   piece_orders={1: list(range(6)), 0: list(range(6, 12))})
    _, _, _, plan = _degerlendir(b, parcalar, araclar, onbellek)
    for bi, yerlesimler in enumerate(plan.bins):
        for pl in yerlesimler:
            assert pl.bin_id == bi, "bin_id etiketi düzeltilmedi"


def test_onbellek_gercekten_isabet_ediyor():
    """Tek bini değişen komşuda diğer binler önbellekten gelmeli."""
    parcalar = _parcalar(18, 9)
    araclar = _araclar(3)
    onbellek = {}
    a = TSSolution(bin_assignments=[0] * 6 + [1] * 6 + [2] * 6,
                   piece_orders={0: list(range(6)), 1: list(range(6, 12)),
                                 2: list(range(12, 18))})
    _degerlendir(a, parcalar, araclar, onbellek)
    ilk_boyut = len(onbellek)
    assert ilk_boyut == 3, f"3 bin beklenirken {ilk_boyut} kayıt"

    # Yalnız 2. bin'in sırası değişsin
    b = a.copy()
    b.piece_orders[2] = list(reversed(b.piece_orders[2]))
    _degerlendir(b, parcalar, araclar, onbellek)
    assert len(onbellek) == ilk_boyut + 1, \
        "değişmeyen binler yeniden paketlenmiş olmalı değil"


# ═════════════════════════════════════════════════════════════════════════════
# Arayüz ve güvenlik
# ═════════════════════════════════════════════════════════════════════════════

def test_onbellek_varsayilan_kapali():
    """`bin_cache=None` → eski davranış; dış arayüz korunuyor."""
    par = inspect.signature(evaluate_solution).parameters
    assert "bin_cache" in par
    assert par["bin_cache"].default is None


def test_onbellek_kosuya_ozel():
    """Tabu ve SA her koşuda YENİ bir önbellek kurmalı (sızma olmasın)."""
    import simulated_annealing_3d as sa
    import tabu_search_3d as ts

    ts_kaynak = inspect.getsource(ts.tabu_search_3d_optimization)
    sa_kaynak = inspect.getsource(sa.simulated_annealing_3d_optimization)
    # Her koşu KENDİ önbelleğini kurar — modül düzeyinde paylaşılan
    # (dolayısıyla farklı filo/parça arasında sızabilecek) bir nesne yok.
    assert "_bin_cache = BinOnbellegi()" in ts_kaynak
    assert "_bin_cache = BinOnbellegi()" in sa_kaynak
    assert "BinOnbellegi()" not in inspect.getsource(ts).split(
        "def tabu_search_3d_optimization")[0].replace(
        "class BinOnbellegi(dict):", ""), "modül düzeyinde paylaşılan önbellek"


def test_farkli_arac_farkli_anahtar():
    """Aynı parça sırası ama farklı araç → önbellek karıştırmamalı."""
    parcalar = _parcalar(8, 2)
    kucuk = Truck3D("KUCUK", 120, 200, 120, 10_000, 4)
    kucuk.available = 2
    buyuk = Truck3D("BUYUK", 240, 600, 200, 30_000, 6)
    buyuk.available = 2
    sol = TSSolution(bin_assignments=[0] * 8,
                     piece_orders={0: list(range(8))})
    onbellek = {}
    f_k = _degerlendir(sol, parcalar, [kucuk], onbellek)[0]
    f_b = _degerlendir(sol, parcalar, [buyuk], onbellek)[0]
    assert f_k != f_b, "farklı araçlar aynı önbellek kaydını kullanmış"
    assert len(onbellek) == 2


def test_lift_top_yuksekligi_anahtarda():
    """Tavan yükseltilirse önbellek kaydı AYRI olmalı."""
    parcalar = _parcalar(6, 4)
    t = Truck3D("T1", 240, 600, 200, 30_000, 6)
    t.available = 2
    sol = TSSolution(bin_assignments=[0] * 6,
                     piece_orders={0: list(range(6))})
    onbellek = {}
    _degerlendir(sol, parcalar, [t], onbellek)
    t.height = 280                      # Lift-Top ile yükseltilmiş hâl
    _degerlendir(sol, parcalar, [t], onbellek)
    assert len(onbellek) == 2, "aktif yükseklik anahtarda değil"


# ═════════════════════════════════════════════════════════════════════════════
# Büyük ölçek: bütçe aday döngüsünün İÇİNDE de denetlenmeli
# ═════════════════════════════════════════════════════════════════════════════

def test_butce_aday_dongusunun_icinde_denetleniyor():
    """Tek bir yineleme bütçeyi tek başına aşmamalı.

    Bütçe eskiden yalnız YİNELEMELER ARASINDA bakılıyordu; 365+ parçalık
    örneklerde bir yinelemenin aday listesi (8 aday × tam yeniden
    paketleme) bütçeyi tek başına aşabiliyordu.
    """
    import tabu_search_3d as ts
    kaynak = inspect.getsource(ts.tabu_search_3d_optimization)
    bas = kaynak.index("for neighbor, move, tabu_flag in neighbors:")
    blok = kaynak[bas:bas + 1200]
    assert "deadline=_son_tarih" in blok, "adaya son-tarih geçilmiyor"
    assert "if _sonuc is None" in blok, "iptal sinyali ele alınmıyor"


def test_kismi_degerlendirme_aday_sayilmiyor():
    """KABUL: süre dolduğunda YARIM sonuç geçerli aday olamaz.

    `evaluate_solution` kısmi plan döndürmez; None döner ve çağıran
    elindeki en iyi TAMAMLANMIŞ planı korur.
    """
    import time

    parcalar = _parcalar(40, 77)
    araclar = _araclar(4)
    bilgi = {p.id: p for p in parcalar}
    rnd = random.Random(77)
    sol = _rastgele_cozum(len(parcalar), 4, rnd)
    with contextlib.redirect_stdout(io.StringIO()):
        sonuc = evaluate_solution(sol, list(parcalar), araclar, bilgi, "EP",
                                  deadline=time.time() - 1.0)   # çoktan doldu
    assert sonuc is None, "süre dolmuşken kısmi sonuç döndürüldü"


def test_son_tarihsiz_cagri_eskisi_gibi():
    """`deadline=None` → hiçbir denetim yapılmaz (geriye uyum)."""
    par = inspect.signature(evaluate_solution).parameters
    assert "deadline" in par and par["deadline"].default is None
    parcalar = _parcalar(10, 3)
    araclar = _araclar(2)
    sonuc = _degerlendir(_rastgele_cozum(10, 2, random.Random(3)),
                         parcalar, araclar, None)
    assert sonuc is not None and len(sonuc) == 4


def test_iptal_edilen_degerlendirme_onbellege_yazilmiyor():
    """Yarım kalan paketleme önbelleğe GİRMEMELİ."""
    import time

    parcalar = _parcalar(30, 55)
    araclar = _araclar(3)
    bilgi = {p.id: p for p in parcalar}
    onbellek = {}
    sol = _rastgele_cozum(len(parcalar), 3, random.Random(55))
    with contextlib.redirect_stdout(io.StringIO()):
        evaluate_solution(sol, list(parcalar), araclar, bilgi, "EP",
                          bin_cache=onbellek, deadline=time.time() - 1.0)
    assert onbellek == {}, "iptal edilen değerlendirme önbelleğe yazıldı"


def test_isabet_sayaci_calisiyor():
    from tabu_search_3d import BinOnbellegi

    parcalar = _parcalar(18, 8)
    araclar = _araclar(3)
    onbellek = BinOnbellegi()
    sol = TSSolution(bin_assignments=[0] * 6 + [1] * 6 + [2] * 6,
                     piece_orders={0: list(range(6)), 1: list(range(6, 12)),
                                   2: list(range(12, 18))})
    _degerlendir(sol, parcalar, araclar, onbellek)
    assert onbellek.iska == 3 and onbellek.isabet == 0
    _degerlendir(sol, parcalar, araclar, onbellek)     # tamamı isabet
    assert onbellek.isabet == 3
    assert 0.0 < onbellek.isabet_orani <= 1.0


def test_buyuk_orneklerde_butce_makul_asiliyor():
    """Davranışsal: 200 parçalık örnekte 5 sn bütçe çok aşılmamalı."""
    import time

    from tabu_search_3d import tabu_search_3d_optimization

    parcalar = _parcalar(200, 21)
    araclar = _araclar(6)
    butce = 5.0
    bas = time.time()
    with contextlib.redirect_stdout(io.StringIO()):
        plan = tabu_search_3d_optimization(
            parcalar, araclar, max_time=butce, seed=13)
    gecen = time.time() - bas
    assert plan is not None and any(plan.bins)
    assert gecen <= butce * 4.0, f"{butce} sn bütçede {gecen:.1f} sn sürdü"


def test_buyuk_orneklerde_plan_gecerli():
    """Önbellek büyük örnekte plan geçerliliğini bozmamalı."""
    from tabu_search_3d import tabu_search_3d_optimization

    parcalar = _parcalar(120, 31)
    araclar = _araclar(5)
    with contextlib.redirect_stdout(io.StringIO()):
        plan = tabu_search_3d_optimization(
            parcalar, araclar, max_time=4.0, seed=17)
    atama = plan.truck_assignments or {}
    kimlikler = {t.id for t in araclar}
    görülen = set()
    for bid, yerlesimler in enumerate(plan.bins):
        if not yerlesimler:
            continue
        assert atama.get(bid) in kimlikler, f"bin {bid} atanmamış"
        for pl in yerlesimler:
            assert pl.bin_id == bid
            assert (pl.piece_id, pl.x, pl.y, pl.z) not in görülen, \
                "aynı konumda yinelenen yerleşim"
            görülen.add((pl.piece_id, pl.x, pl.y, pl.z))
