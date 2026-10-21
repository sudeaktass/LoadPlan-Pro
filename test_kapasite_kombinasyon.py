# -*- coding: utf-8 -*-
"""
Kombinasyon → Truck3D ve kütle kapasitesi testleri (adım 2b)
=============================================================
    python -X utf8 -m pytest test_kapasite_kombinasyon.py -q

Kabul ölçütü:
  Toplamı 25.757 kg'ı aşan yük, TEK bir Ford F-MAX + Schmitz SCS 24/L
  aracına yerleştirilmiyor — ve bu, ALGORITHMS'teki BÜTÜN algoritma
  anahtarlarında gösteriliyor.

Önemli: algoritma fonksiyonları DOĞRUDAN çağrılır (app_3d.run_algo
üzerinden değil). Böylece kurtarma adımları (rescue_placement,
guarantee_all_placed, force_place_remaining) devreye girmez — onlar
bilerek kapsam dışıdır ve `force_place_remaining` zaten kapasitesi
99.999 kg olan sahte bir "OVERFLOW" aracı açar.
"""

from __future__ import annotations

import contextlib
import io

import pytest

from core_3d import Piece3D, Truck3D
from filo_havuzu import eslesme_to_truck3d
from filo_modeli import eslesme_hesapla
from ornek_filo import ford_fmax_4x2, schmitz_scs_24l

FAYDALI_YUK = 25_757.0      # Ford F-MAX 4x2 + Schmitz SCS 24/L
TOL = 1e-6


@contextlib.contextmanager
def _sessiz():
    with contextlib.redirect_stdout(io.StringIO()):
        yield


def _arac() -> Truck3D:
    """Tek bir Ford + Schmitz kombinasyonu."""
    return eslesme_to_truck3d(eslesme_hesapla(ford_fmax_4x2(),
                                              schmitz_scs_24l()))


def _asiri_yuk():
    """30 × 1.200 kg = 36.000 kg → faydalı yükü 10.243 kg aşıyor."""
    return [Piece3D(id=f"p{i}", width=110, length=120, height=110,
                    quantity=1, weight=1_200.0) for i in range(30)]


def _bin_agirliklari(plan, pieces):
    bilgi = {p.id: p for p in pieces}
    agirliklar = []
    for b in (plan.bins or []):
        if not b:
            continue
        agirliklar.append(sum(bilgi[p.piece_id].weight for p in b
                              if p.piece_id in bilgi))
    return agirliklar


# ─────────────────────────────────────────────────────────────────────────────
# Kombinasyon → Truck3D (istenen değişiklik 1)
# ─────────────────────────────────────────────────────────────────────────────

def test_ic_olculer_dorseden_geliyor():
    t = _arac()
    d = schmitz_scs_24l()
    assert (t.width, t.length, t.height) == (248, 1_362, 270)
    assert t.width * 10 <= d.ic_genislik_mm      # aşağı yuvarlama
    assert t.length * 10 <= d.ic_uzunluk_mm
    assert t.height * 10 <= d.ic_yukseklik_mm


def test_kapasite_faydali_yuke_esit():
    assert _arac().capacity == pytest.approx(FAYDALI_YUK)


def test_truck3d_cekici_ve_dorse_kimligini_tasiyor():
    """Rapor ve izlenebilirlik için ikisi de erişilebilir olmalı."""
    t = _arac()
    assert t.eslesme is not None
    assert t.eslesme.cekici.plaka == "54 ABC 123"
    assert t.eslesme.dorse.plaka == "54 XYZ 456"
    assert t.id == "54 XYZ 456"                  # yük alanı dorsedir
    assert t.eslesme.etiket == "54 ABC 123 + 54 XYZ 456"
    assert t.available == 1                      # her kombinasyon bir sefer


def test_eski_arac_girisi_bozulmadi():
    """Eşleşmesiz Truck3D aynen çalışmalı (eski tek kayıtlı giriş)."""
    t = Truck3D("Buyuk", 240, 600, 200, 24_000, 2)
    assert t.eslesme is None
    assert t.capacity == 24_000 and t.get_volume() == 240 * 600 * 200


# ─────────────────────────────────────────────────────────────────────────────
# Kütle kapasitesi — BÜTÜN algoritma anahtarları
# ─────────────────────────────────────────────────────────────────────────────

def _calistiricilar():
    """ALGORITHMS'teki 10 anahtarın karşılığı.

    nfp_nested KAPSAM DIŞI: ayrı bir motor (run_nfp) kullanıyor ve kütle
    kapasitesini hiç kontrol etmiyor — bilinen boşluk, ayrı ele alınacak.
    """
    from ffd_3d import ffd_3d_optimization
    from greedy_3d import greedy_3d_optimization
    from layer_building_3d import layer_building_3d_optimization
    from tabu_search_3d import tabu_search_3d_optimization
    from simulated_annealing_3d import simulated_annealing_3d_optimization
    from genetic_3d import genetic_3d_optimization
    from monte_carlo_3d import monte_carlo_3d_optimization

    calistir = {
        "ffd_ep": lambda p, t: ffd_3d_optimization(p, t),
        "greedy_ep": lambda p, t: greedy_3d_optimization(p, t),
        "layer_building": lambda p, t: layer_building_3d_optimization(p, t),
        "tabu_search": lambda p, t: tabu_search_3d_optimization(
            p, t, max_time=2.0, seed=1001),
        "sa_hybrid": lambda p, t: simulated_annealing_3d_optimization(
            p, t, max_time=2.0, seed=1001),
        "genetic": lambda p, t: genetic_3d_optimization(
            p, t, population_size=10, generations=5, max_time=2.0, seed=1001),
        "monte_carlo": lambda p, t: monte_carlo_3d_optimization(
            p, t, iterations=20, max_time=2.0, seed=1001),
    }

    # ── Dondurulmuş varyantlar (karar A) — yine de kapasiteye uymalı ──
    try:
        from island_genetic_3d import island_model_ga_3d
        calistir["island_ga"] = lambda p, t: island_model_ga_3d(
            p, t, n_islands=2, island_population=6, generations=5,
            max_time=2.0, seed=1001)
    except Exception:                                    # noqa: BLE001
        pass
    try:
        from multistart_sa_3d import multistart_sa_3d
        calistir["multistart_sa"] = lambda p, t: multistart_sa_3d(
            p, t, n_starts=2, time_budget=3.0, seed=1001)
    except Exception:                                    # noqa: BLE001
        pass
    try:
        from bayesian_optimizer_3d import bayesian_optimization_3d
        calistir["bayesian"] = lambda p, t: bayesian_optimization_3d(
            p, t, target_algorithm="ffd", n_trials=2, time_budget=5.0,
            seed_with_ffd=True)
    except Exception:                                    # noqa: BLE001
        pass
    return calistir


ANAHTARLAR = sorted(_calistiricilar().keys())


def test_butun_anahtarlar_kapsandi():
    """ALGORITHMS'teki anahtarların hepsi test ediliyor mu?"""
    beklenen = {"ffd_ep", "greedy_ep", "layer_building", "tabu_search",
                "sa_hybrid", "monte_carlo", "genetic",
                "island_ga", "multistart_sa", "bayesian"}
    eksik = beklenen - set(ANAHTARLAR)
    assert not eksik, f"çalıştırılamayan anahtarlar: {sorted(eksik)}"


@pytest.mark.parametrize("anahtar", ANAHTARLAR)
def test_kapasite_asilmiyor(anahtar):
    """KABUL ÖLÇÜTÜ: hiçbir araç 25.757 kg'ı aşmıyor."""
    trucks = [_arac()]
    pieces = _asiri_yuk()
    with _sessiz():
        plan = _calistiricilar()[anahtar](pieces, trucks)

    agirliklar = _bin_agirliklari(plan, pieces)
    assert agirliklar, f"{anahtar}: hiç araç kullanılmadı"
    for i, w in enumerate(agirliklar):
        assert w <= FAYDALI_YUK + TOL, (
            f"{anahtar}: bin{i} {w:,.0f} kg > faydalı yük "
            f"{FAYDALI_YUK:,.0f} kg")


@pytest.mark.parametrize("anahtar", ANAHTARLAR)
def test_asan_yuk_disarida_kaliyor(anahtar):
    """36.000 kg tek araca sığamaz → bir kısmı yerleşmemeli."""
    trucks = [_arac()]
    pieces = _asiri_yuk()
    with _sessiz():
        plan = _calistiricilar()[anahtar](pieces, trucks)

    yerlesen = sum(len(b) for b in (plan.bins or []) if b)
    assert yerlesen < len(pieces), (
        f"{anahtar}: {len(pieces)} parçanın hepsi tek araca yerleşmiş — "
        f"kapasite kontrolü çalışmıyor")


def test_kapasiteye_sigan_yuk_tamamen_yerlesebiliyor():
    """Kontrol fazla kısıtlayıcı olmamalı: sığan yük yerleşmeli.

    Hafif ve az sayıda parça → ne kütle ne dingil bağlar.
    """
    from ffd_3d import ffd_3d_optimization
    trucks = [_arac()]
    pieces = [Piece3D(id=f"h{i}", width=110, length=120, height=110,
                      quantity=1, weight=50.0) for i in range(10)]
    with _sessiz():
        plan = ffd_3d_optimization(pieces, trucks)
    assert sum(len(b) for b in (plan.bins or []) if b) == len(pieces)
    assert not plan.unfitted_pieces


# ─────────────────────────────────────────────────────────────────────────────
# Bağımsız doğrulayıcı kütleyi denetliyor mu
# ─────────────────────────────────────────────────────────────────────────────

def test_dogrulayici_asiri_yuku_yakaliyor():
    """dogrula_cozum.py elle kurulmuş aşırı yüklü bir planı reddetmeli."""
    from core_3d import CuttingPlan3D, Placement3D
    from dogrula_cozum import validate_plan

    truck = _arac()
    pieces = {f"a{i}": Piece3D(id=f"a{i}", width=110, length=120, height=110,
                               quantity=1, weight=9_000.0) for i in range(3)}
    yerlesimler = [Placement3D(0, i * 120, 0, 110, 120, 110, f"a{i}",
                               (0, 0, 0), 0) for i in range(3)]
    plan = CuttingPlan3D(bins=[yerlesimler], total_waste=0, utilization=0.0,
                         execution_time=0.0, algorithm="test",
                         truck_assignments={0: truck.id})

    rapor = validate_plan(plan, pieces, [truck])
    assert rapor.overweight, "27.000 kg > 25.757 kg yakalanmalıydı"
    assert not rapor.feasible


# ─────────────────────────────────────────────────────────────────────────────
# NFP yolu — kütle kapasitesi (21 Ekim 2026'da eklendi)
# ─────────────────────────────────────────────────────────────────────────────
# NFP ayrı bir motor (nfp_engine) kullandığı için ortak EP motorundaki
# ağırlık kontrolünü görmüyordu. Kural `filo_havuzu.kapasiteye_gore_suz`
# fonksiyonuna alındı; `app_3d.run_nfp` onu çağırıyor. run_nfp Streamlit
# betiğinin içinde olduğu için burada ortak fonksiyon test ediliyor.

def test_kapasiteye_gore_suz_asani_atliyor():
    from filo_havuzu import kapasiteye_gore_suz
    secilen, toplam = kapasiteye_gore_suz([1_000, 1_000, 1_000], 2_500)
    assert secilen == [0, 1]
    assert toplam == pytest.approx(2_000)


def test_kapasiteye_gore_suz_agir_parcayi_atlayip_devam_ediyor():
    """Ağır bir parça yüzünden arkasındaki hafifler boşuna elenmemeli."""
    from filo_havuzu import kapasiteye_gore_suz
    secilen, toplam = kapasiteye_gore_suz([1_000, 9_000, 500], 2_000)
    assert secilen == [0, 2]
    assert toplam == pytest.approx(1_500)


def test_kapasiteye_gore_suz_tam_sinir_kabul():
    from filo_havuzu import kapasiteye_gore_suz
    secilen, toplam = kapasiteye_gore_suz([FAYDALI_YUK], FAYDALI_YUK)
    assert secilen == [0] and toplam == pytest.approx(FAYDALI_YUK)


def test_kapasiteye_gore_suz_hicbiri_sigmazsa_bos():
    from filo_havuzu import kapasiteye_gore_suz
    secilen, toplam = kapasiteye_gore_suz([30_000, 40_000], FAYDALI_YUK)
    assert secilen == [] and toplam == 0.0


def test_nfp_kurali_ep_motoruyla_ayni():
    """Aynı girdi için NFP süzgeci ile EP motoru aynı sonucu vermeli."""
    from filo_havuzu import kapasiteye_gore_suz
    agirliklar = [1_200.0] * 30
    secilen, toplam = kapasiteye_gore_suz(agirliklar, FAYDALI_YUK)
    # 25.757 / 1.200 = 21,46 → 21 parça
    assert len(secilen) == 21
    assert toplam == pytest.approx(25_200.0)
    assert toplam <= FAYDALI_YUK
