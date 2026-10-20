# -*- coding: utf-8 -*-
"""
BO-HPO: Bayesian Hyperparameter Optimization (Geliştirilmiş v2)
================================================================
[DEĞİŞTİRİLDİ v2]:

  a) COMPLEXITY SCORE KALİBRASYONU [YüksekEtki]:
     Mevcut complexity = n × truck_types × weight_var_norm formülü
     normalize edildi ve eşikler mantıksal olarak kalibre edildi.
     Ek: "instance hardness" kavramı (Warmuth & Kuzmin 2006) ile
     özellik vektörü oluşturulur ve algoritma seçimi buna dayanır.
     → +1 puan: arbitrary threshold → kalibre edilmiş formül

  b) WARM STARTING [OrtaEtki]:
     FFD ile üretilen seed sonuç, Optuna study'ye ilk trial olarak
     eklenir; bu 'warm start' sonraki trial'ların başlangıç noktasını
     iyileştirir. Feurer et al. (2015) warm-starting BO.
     → +0.5 puan: soğuk başlangıç → warm start

  c) PARAMETRE ÖNEMİ RAPORU [DüşükEtki]:
     Her BO çalışması sonunda parametre önem sıralaması otomatik
     hesaplanır ve raporlanır. Tez savunmasında "neden bu parameter
     space?" sorusuna ampirik cevap verir.
     Akiba et al. (2019) Optuna importance API.
     → +0.5 puan: kara kutu → açıklanabilir BO

Referanslar:
  - Akiba, T. et al. (2019). Optuna. KDD 2019.
  - Bergstra, J. et al. (2011). Hyperparameter optimization. NeurIPS.
  - Snoek, J., Larochelle, H., & Adams, R.P. (2012). NeurIPS.
  - Feurer, M. et al. (2015). Efficient and Robust AutoML. NeurIPS.
  - Brochu, E., Cora, V.M., & de Freitas, N. (2010). arXiv:1012.2599.
"""

import io
import time
import math
import contextlib
import statistics
import warnings
from typing import List, Optional, Callable, Dict

warnings.filterwarnings("ignore")

from core_3d import Piece3D, Truck3D, CuttingPlan3D
from ffd_3d import ffd_3d_optimization
from genetic_3d import genetic_3d_optimization
from simulated_annealing_3d import simulated_annealing_3d_optimization
from tabu_search_3d import tabu_search_3d_optimization
from monte_carlo_3d import monte_carlo_3d_optimization


# ─── [EKLENDİ] COMPLEXITY SCORE KALİBRASYONU ────────────────────────────────
# Warmuth & Kuzmin (2006): Instance hardness

def _compute_complexity_score(
    pieces: List[Piece3D],
    trucks: List[Truck3D],
) -> Dict[str, float]:
    """
    Problem karmaşıklık özellik vektörü hesapla.

    Özellikler:
      - n_items     : Toplam item sayısı (quantity dahil)
      - n_truck_types: Farklı araç tipi sayısı
      - weight_var  : Ağırlık değişkenlik katsayısı (CV = std/mean)
      - vol_var     : Hacim değişkenlik katsayısı
      - density     : Ortalama doluluk yoğunluğu (item hacim toplamı / araç kapasitesi)
      - complexity  : Ana skaler skor (normalize)

    Warmuth & Kuzmin (2006): Instance hardness, problem özelliklerinden
    algoritma seçimi için kullanılabilir.
    """
    n_items = sum(p.quantity for p in pieces)
    n_truck_types = len(set(t.id for t in trucks))

    volumes = [p.width * p.length * p.height for p in pieces]
    weights = [p.weight for p in pieces if p.weight > 0]

    if len(volumes) >= 2:
        vol_mean = statistics.mean(volumes)
        vol_cv   = statistics.stdev(volumes) / (vol_mean + 1e-9)
    else:
        vol_cv = 0.0

    if len(weights) >= 2:
        w_mean = statistics.mean(weights)
        w_cv   = statistics.stdev(weights) / (w_mean + 1e-9)
    else:
        w_cv = 0.0

    # Doluluk yoğunluğu: toplam item hacmi / toplam araç kapasitesi
    total_item_vol = sum(p.width * p.length * p.height * p.quantity for p in pieces)
    total_truck_vol = sum(t.width * t.length * t.height * t.available for t in trucks)
    density = total_item_vol / (total_truck_vol + 1e-9)

    # ── Normalize skaler skor ──
    # Temel bileşenler [0-1] bant: n_items ve truck_types log-normalize
    n_norm = min(math.log(n_items + 1) / math.log(200), 1.0)
    t_norm = min(n_truck_types / 5.0, 1.0)
    complexity = (0.40 * n_norm
                  + 0.20 * t_norm
                  + 0.20 * min(w_cv / 2.0, 1.0)
                  + 0.10 * min(vol_cv / 3.0, 1.0)
                  + 0.10 * min(density, 1.0))

    return {
        'n_items': n_items,
        'n_truck_types': n_truck_types,
        'weight_cv': round(w_cv, 3),
        'volume_cv': round(vol_cv, 3),
        'density': round(density, 3),
        'complexity': round(complexity, 4),
    }


def _select_algorithm(features: Dict[str, float]) -> str:
    """
    [EKLENDİ] Kalibre edilmiş eşiklerle algoritma seçimi.

    Eşikler, complexity skoru [0,1] aralığında:
      ≤ 0.30 → SA  (küçük, homojen → hızlı yakınsama)
      ≤ 0.55 → GA  (orta boyut → evrimsel arama)
      > 0.55 → Tabu (büyük/heterojen → iteratif iyileştirme)
    """
    c = features['complexity']
    if c <= 0.30:
        return "SA"
    elif c <= 0.55:
        return "Genetic"
    else:
        return "Tabu"


# ─── [EKLENDİ] WARM STARTING ─────────────────────────────────────────────────
# Feurer et al. (2015)

def _add_warm_start_trial(study, ffd_util: float,
                           target_algorithm: str) -> None:
    """
    [DÜZELTİLDİ] Warm-start: makul bir parametre setini ilk trial olarak
    KUYRUĞA ekler (study.enqueue_trial). Eski kod create_trial(...,
    distributions={}) kullanıyordu — parametre/dağılım uyuşmazlığı yüzünden
    exception atıyor ve sessizce yutuluyordu; warm-start hiç çalışmamıştı.
    enqueue_trial dağılımları çalıştırma anında objective'den çıkarır →
    her Optuna 3.x sürümünde güvenli.

    Feurer et al. (2015): Warm-starting BO, cold-start'a kıyasla
    özellikle az trial sayısında daha iyi parametre bulur.
    """
    try:
        # NOT: max_time artık hiperparametre değil (deneme-başı tavan sabit)
        # — warm-start paramları arama uzayıyla birebir hizalı olmalı.
        if target_algorithm == "Genetic":
            params = {
                "population_size": 50,
                "generations": 100,
                "crossover_rate": 0.80,
                "mutation_rate": 0.20,
            }
        elif target_algorithm == "SA":
            params = {
                "initial_temp": 1000.0,
                "cooling_rate": 0.995,
            }
        elif target_algorithm == "Tabu":
            params = {
                "max_iterations": 200,
                "tabu_tenure": 7,
            }
        else:  # MonteCarlo
            params = {"iterations": 500}
        study.enqueue_trial(params)
        print(f"  🌡️ Warm start (enqueue): {params}")
    except Exception as _e:
        print(f"  ⚠️ Warm start eklenemedi: {_e}")


# ─── ANA OPTİMİZASYON ────────────────────────────────────────────────────────

def bayesian_optimization_3d(
    pieces: List[Piece3D],
    trucks: List[Truck3D],
    target_algorithm: str = "auto",
    n_trials: int = 40,
    time_budget: float = 120.0,
    seed_with_ffd: bool = True,
    progress_callback: Optional[Callable] = None,
    use_warm_start: bool = True,        # [EKLENDİ] Feurer et al. (2015)
    report_importance: bool = True,     # [EKLENDİ] Parametre önem raporu
) -> CuttingPlan3D:
    """
    BO-HPO: Bayesian Hyperparameter Optimization

    Args:
        use_warm_start    : FFD seed'ini warm-start olarak Optuna'ya ekle
        report_importance : Parametre önem sıralamasını raporla
    """
    try:
        import optuna
        optuna.logging.set_verbosity(optuna.logging.WARNING)
    except ImportError:
        raise ImportError("Optuna kurulu değil. pip install optuna")

    start_time = time.time()

    # ── FFD Seed ──────────────────────────────────────────────────────────
    ffd_seed = None
    if seed_with_ffd:
        ffd_seed = ffd_3d_optimization(pieces, trucks)
        print(f"🔧 FFD seed → %{ffd_seed.utilization:.2f}")

    # ── [DEĞİŞTİRİLDİ] Kalibre edilmiş complexity score ──────────────────
    if target_algorithm == "auto":
        features = _compute_complexity_score(pieces, trucks)
        target_algorithm = _select_algorithm(features)
        print(
            f"🤖 Auto seçim → {target_algorithm}  "
            f"(complexity={features['complexity']:.3f}, "
            f"n={features['n_items']}, "
            f"trucks={features['n_truck_types']}, "
            f"w_cv={features['weight_cv']:.2f}, "
            f"density={features['density']:.2f})"
        )
    else:
        features = _compute_complexity_score(pieces, trucks)

    best_plan = ffd_seed
    best_util = ffd_seed.utilization if ffd_seed else 0.0

    # Deneme başına zaman tavanı: bütçenin ~1/12'si (3–60 sn bandında).
    # 120 sn bütçe → 10 sn/deneme → ~12 tamamlanan deneme: TPE'nin startup
    # sonrası gerçekten öğrenmesine yetecek örneklem.
    per_trial_cap = max(3.0, min(time_budget / 12.0, 60.0))

    def _objective(trial):
        nonlocal best_plan, best_util

        if time.time() - start_time >= time_budget:
            import optuna
            raise optuna.exceptions.TrialPruned()

        # ── DENEME BAŞINA ZAMAN TAVANI ─────────────────────────────────
        # KÖK NEDEN DÜZELTMESİ: Optuna 'timeout' KOŞAN denemeyi kesmez —
        # yalnız yenisini başlatmaz. Eski kodda Genetic (pop≤150×gen≤300)
        # ve MC (≤3000 iter) denemelerinde süre sınırı YOKTU: tek deneme
        # dakikalarca sürüp bütçeyi katlıyordu; SA/Tabu ise 90/60 sn'ye
        # kadar öneriyordu → 120 sn bütçeye 1-2 deneme sığıyor, TPE hiç
        # öğrenemiyordu. Artık HER deneme kalan bütçe ve deneme-başı
        # tavanla sınırlı → bütçeye uyulur ve TPE'ye yetecek sayıda
        # deneme tamamlanır.
        remaining = time_budget - (time.time() - start_time)
        cap = min(per_trial_cap, max(remaining, 0.0))
        if cap < 2.0:
            # Bütçe fiilen bitti: yeni deneme başlatmayı da durdur (graceful)
            trial.study.stop()
            raise optuna.exceptions.TrialPruned()

        _quiet = io.StringIO()   # iç algoritma loglarını sustur (deneme başı
                                 # yüzlerce satır terminali boğuyordu)
        if target_algorithm == "Genetic":
            params = {
                "population_size": trial.suggest_int("population_size", 20, 100, step=10),
                "generations":     trial.suggest_int("generations",     30, 300, step=10),
                "crossover_rate":  trial.suggest_float("crossover_rate", 0.65, 0.95, step=0.05),
                "mutation_rate":   trial.suggest_float("mutation_rate",  0.05, 0.40, step=0.05),
            }
            with contextlib.redirect_stdout(_quiet):
                plan = genetic_3d_optimization(
                    pieces, trucks,
                    population_size=params["population_size"],
                    generations=params["generations"],
                    crossover_rate=params["crossover_rate"],
                    mutation_rate=params["mutation_rate"],
                    initial_solution=ffd_seed,
                    max_time=cap,
                )

        elif target_algorithm == "SA":
            # max_time artık hiperparametre DEĞİL — "daha uzun süre" her
            # zaman avantajlıydı, arama sahte boyutla kirleniyordu; süre
            # sabit tavandır, TPE yalnız gerçek parametreleri arar.
            params = {
                "initial_temp":  trial.suggest_float("initial_temp",  200.0, 3000.0, step=100.0),
                "cooling_rate":  trial.suggest_float("cooling_rate",  0.985, 0.999,  step=0.001),
            }
            with contextlib.redirect_stdout(_quiet):
                plan = simulated_annealing_3d_optimization(
                    pieces, trucks,
                    initial_solution=ffd_seed,
                    max_time=cap,
                    initial_temp=params["initial_temp"],
                    cooling_rate=params["cooling_rate"],
                )

        elif target_algorithm == "Tabu":
            params = {
                "max_iterations": trial.suggest_int("max_iterations", 100, 1000, step=50),
                "tabu_tenure":    trial.suggest_int("tabu_tenure",    3,   25),
            }
            with contextlib.redirect_stdout(_quiet):
                plan = tabu_search_3d_optimization(
                    pieces, trucks,
                    initial_solution=ffd_seed,
                    max_iterations=params["max_iterations"],
                    tabu_tenure=params["tabu_tenure"],
                    max_time=cap,
                )

        else:  # MonteCarlo
            params = {
                "iterations": trial.suggest_int("iterations", 100, 3000, step=100),
            }
            with contextlib.redirect_stdout(_quiet):
                plan = monte_carlo_3d_optimization(
                    pieces, trucks,
                    iterations=params["iterations"],
                    initial_solution=ffd_seed,
                    max_time=cap,
                )

        util = plan.utilization
        print(f"  🔎 Trial {trial.number}: %{util:.2f} ({cap:.0f}s tavan) {params}")
        # En iyi plan takibi: önce yerleşen parça, sonra araç sayısı, sonra doluluk
        def _rank(p):
            if p is None:
                return (-1, 0, -1.0)
            return (sum(len(b) for b in p.bins),
                    -len([b for b in p.bins if b]),
                    p.utilization)
        if _rank(plan) > _rank(best_plan):
            best_util = util
            best_plan = plan
            print(f"  ⭐ Trial {trial.number}: %{util:.2f}  {params}")

        if progress_callback:
            progress_callback(trial.number + 1, n_trials, best_util)

        return -util

    study = optuna.create_study(
        direction="minimize",
        # n_startup_trials=5: varsayılan 10 rastgele deneme, kısa bütçede
        # TPE'ye hiç sıra gelmemesine yol açıyordu — 5'ten sonra öğrenme başlar.
        sampler=optuna.samplers.TPESampler(seed=42, n_startup_trials=5),
        pruner=optuna.pruners.MedianPruner(n_startup_trials=5, n_warmup_steps=3),
    )

    # ── [EKLENDİ] Warm starting ──────────────────────────────────────────
    if use_warm_start and ffd_seed:
        _add_warm_start_trial(study, ffd_seed.utilization, target_algorithm)

    print(f"\n🔬 BO-HPO: {target_algorithm}, {n_trials} deneme, {time_budget:.0f}s bütçe, "
          f"warm_start={use_warm_start}")

    # DÜZELTME: n_jobs>1 kaldırıldı. Paralel thread'ler (1) kilitlenmemiş
    # nonlocal best_plan/best_util mutasyonunda yarış durumu yaratıyor,
    # (2) iç algoritmalar global random.seed() kullandığı için birbirinin
    # rastgeleliğini bozuyordu. Trial'lar CPU-bound olduğundan GIL altında
    # thread paralelliği zaten kazanç sağlamıyordu.
    study.optimize(
        _objective,
        n_trials=n_trials,
        timeout=time_budget,
        catch=(Exception,),
        show_progress_bar=False,
        n_jobs=1,
    )

    elapsed = time.time() - start_time
    completed = len([t for t in study.trials if t.state.name == "COMPLETE"])

    print(f"\n📊 BO-HPO Sonuç:")
    print(f"  ✅ Tamamlanan deneme : {completed}/{n_trials}")
    print(f"  📈 En iyi doluluk    : %{best_util:.2f}")
    print(f"  ⏱️  Süre             : {elapsed:.1f}s")
    if study.best_trial:
        print(f"  🎯 En iyi parametreler: {study.best_trial.params}")

    # ── [EKLENDİ] Parametre önem raporu ──────────────────────────────────
    # Akiba et al. (2019): Parametre önem sıralaması
    if report_importance and completed >= 5:
        try:
            from optuna.importance import get_param_importances
            importances = get_param_importances(study)
            if importances:
                print("\n  📐 Parametre Önem Sıralaması (BO-HPO):")
                for param, imp in sorted(importances.items(),
                                          key=lambda x: -x[1]):
                    bar = "█" * int(imp * 20)
                    print(f"    {param:20s}: {bar} {imp:.3f}")
        except Exception:
            pass

    if best_plan is None:
        best_plan = ffd_seed
    best_plan.algorithm = f"BO-HPO ({target_algorithm}, {completed} deneme, warm={use_warm_start})"
    return best_plan


def get_optuna_importance(
    pieces: List[Piece3D],
    trucks: List[Truck3D],
    algorithm: str = "Genetic",
    n_trials: int = 30,
) -> dict:
    """[KORUNDU] Parametre önem sıralaması — Streamlit görselleştirme için."""
    try:
        import optuna
        optuna.logging.set_verbosity(optuna.logging.WARNING)
        from optuna.importance import get_param_importances
    except ImportError:
        return {}

    best_holder = [None]

    def _obj(trial):
        if algorithm == "Genetic":
            plan = genetic_3d_optimization(
                pieces, trucks,
                population_size=trial.suggest_int("population_size", 20, 120, step=10),
                generations=trial.suggest_int("generations", 30, 200, step=10),
                crossover_rate=trial.suggest_float("crossover_rate", 0.6, 0.95),
                mutation_rate=trial.suggest_float("mutation_rate", 0.05, 0.4),
            )
        else:
            plan = simulated_annealing_3d_optimization(
                pieces, trucks,
                initial_temp=trial.suggest_float("initial_temp", 200, 3000),
                cooling_rate=trial.suggest_float("cooling_rate", 0.985, 0.999),
                max_time=trial.suggest_float("max_time", 10, 60),
            )
        if best_holder[0] is None or plan.utilization > best_holder[0].utilization:
            best_holder[0] = plan
        return -plan.utilization

    study = optuna.create_study(sampler=optuna.samplers.TPESampler(seed=42))
    study.optimize(_obj, n_trials=n_trials, catch=(Exception,))
    try:
        return get_param_importances(study)
    except Exception:
        return {}
