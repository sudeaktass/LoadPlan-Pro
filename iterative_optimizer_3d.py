# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║          3D BIN PACKING — ITERATİF OPTİMİZER & HİBRİT ARAMA MOTORU        ║
╚══════════════════════════════════════════════════════════════════════════════╝

Kullanım:
    from iterative_optimizer_3d import IterativeSearch, HybridPipeline

    # 1) En iyi parametre kombinasyonunu bul
    best = IterativeSearch(pieces, trucks).run()

    # 2) Hibrit pipeline çalıştır (Greedy → SA rafine)
    plan = HybridPipeline(pieces, trucks).run()
"""

import itertools
import time
import random
import math
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Callable, Any, Tuple

# ── Projenizin modülleri ─────────────────────────────────────────────────────
from core_3d import Piece3D, Truck3D, CuttingPlan3D
from ffd_3d import ffd_3d_optimization
from greedy_3d import greedy_3d_optimization
from layer_building_3d import layer_building_3d_optimization
from genetic_3d import genetic_3d_optimization
from tabu_search_3d import tabu_search_3d_optimization
from simulated_annealing_3d import simulated_annealing_3d_optimization
from monte_carlo_3d import monte_carlo_3d_optimization


# ═══════════════════════════════════════════════════════════════════════════════
# BÖLÜM 1 — PARAMETRE UZAYLARI
# Her algoritma için denenecek değer aralıkları burada merkezi olarak tanımlı.
# Deneme süresini kısaltmak için küçültebilinir; daha hassas tarama için genişletilir.
# ═══════════════════════════════════════════════════════════════════════════════

PARAM_SPACES: Dict[str, Dict[str, List[Any]]] = {

    "Genetic": {
        "population_size": [30, 50, 80, 120],   # Nesil başına birey sayısı
        "generations":     [50, 100, 200],        # Toplam nesil
        "crossover_rate":  [0.7, 0.8, 0.9],       # OX1 çaprazlama oranı
        "mutation_rate":   [0.1, 0.2, 0.3],        # Swap/Rotasyon mutasyon oranı
    },

    "SimulatedAnnealing": {
        # FIX-A: initial_temp kaldırıldı — simulated_annealing_3d.py
        # artık _calibrate_initial_temp() ile otomatik hesaplıyor.
        # Elle verilirse auto-kalibrasyon devre dışı kalır; bu nedenle
        # PARAM_SPACES taramasında manuel değer tutulmuyor.
        "cooling_rate":  [0.990, 0.995, 0.999],  # Soğuma çarpanı α
        "max_time":      [20.0, 40.0, 60.0],      # Maksimum süre (saniye)
        "min_temp":      [0.1, 1.0],               # Dur sıcaklığı
        "engine":        ["EP"],                    # Yerleştirme motoru
    },

    "TabuSearch": {
        "max_iterations": [200, 500, 1000],    # Tabu iterasyon limiti
        "tabu_tenure":    [5, 10, 20],          # Tabu listesi uzunluğu
        "max_time":       [20.0, 40.0],          # Zaman limiti
        "engine":         ["EP"],
    },

    "MonteCarlo": {
        "iterations": [200, 500, 1000, 2000],   # Rastgele deneme sayısı
    },

    "LayerBuilding": {
        # Layer Building deterministik — parametre taraması yerine
        # rotasyon & sıralama stratejisi test edilir
        "sort_by": ["volume_desc", "height_desc", "weight_desc"],
    },

    # FFD & Greedy deterministik; hibrit pipeline başlangıcı olarak kullanılır
    "FFD":    {},
    "Greedy": {},

    # FIX-M3: Island GA büyük problemler için
    "IslandGA": {
        "n_islands":        [3, 4, 5],
        "island_population": [15, 25],
        "generations":      [50, 80],
    },
}


# ═══════════════════════════════════════════════════════════════════════════════
# BÖLÜM 2 — SONUÇ KAYIT YAPISI
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class SearchResult:
    algorithm:   str
    params:      Dict[str, Any]
    utilization: float          # Hacimsel doluluk oranı (%)
    execution_time: float       # Algoritmanın çalışma süresi (s)
    plan:        CuttingPlan3D
    rank:        int = 0

    def __str__(self) -> str:
        return (
            f"[{self.rank:>3}] {self.algorithm:<22} | "
            f"Util: {self.utilization:6.2f}% | "
            f"Süre: {self.execution_time:5.1f}s | "
            f"Params: {self.params}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# BÖLÜM 3 — YARDIMCİ FONKSIYONLAR
# ═══════════════════════════════════════════════════════════════════════════════

def _run_algorithm(
    name:   str,
    params: Dict[str, Any],
    pieces: List[Piece3D],
    trucks: List[Truck3D],
    seed_plan: Optional[CuttingPlan3D] = None,
) -> Tuple[CuttingPlan3D, float]:
    """
    Verilen algoritma + parametrelerle bir çalıştırma yapar.
    Süreyi ölçer, (plan, elapsed) döndürür.
    """
    t0 = time.time()

    if name == "FFD":
        # FIX-B: FFD/Greedy yapıcı algoritmalar — seed_plan anlamlı değil.
        # Çağıran taraf seed beklediğini düşünse de geçmiyordu; açıkça belgeleniyor.
        plan = ffd_3d_optimization(pieces, trucks)

    elif name == "Greedy":
        plan = greedy_3d_optimization(pieces, trucks)

    elif name == "LayerBuilding":
        sort_key = params.get("sort_by", "volume_desc")
        sorted_pieces = _sort_pieces(pieces, sort_key)
        plan = layer_building_3d_optimization(sorted_pieces, trucks)

    elif name == "MonteCarlo":
        plan = monte_carlo_3d_optimization(
            pieces, trucks,
            iterations=params.get("iterations", 500),
            initial_solution=seed_plan,
        )

    elif name == "Genetic":
        plan = genetic_3d_optimization(
            pieces, trucks,
            population_size=params.get("population_size", 50),
            generations=params.get("generations", 100),
            crossover_rate=params.get("crossover_rate", 0.8),
            mutation_rate=params.get("mutation_rate", 0.2),
            initial_solution=seed_plan,
        )

    elif name == "SimulatedAnnealing":
        # FIX-B: initial_temp varsayılanı None → auto-kalibrasyon devreye girer.
        # params içinde "initial_temp" yoksa (PARAM_SPACES'ten kaldırıldı),
        # simulated_annealing_3d._calibrate_initial_temp() çalışır.
        plan = simulated_annealing_3d_optimization(
            pieces, trucks,
            initial_solution=seed_plan,
            max_time=params.get("max_time", 30.0),
            initial_temp=params.get("initial_temp", None),   # None → auto
            cooling_rate=params.get("cooling_rate", 0.995),
            min_temp=params.get("min_temp", 1.0),
            engine=params.get("engine", "EP"),
        )

    elif name == "TabuSearch":
        plan = tabu_search_3d_optimization(
            pieces, trucks,
            initial_solution=seed_plan,
            max_iterations=params.get("max_iterations", 500),
            tabu_tenure=params.get("tabu_tenure", 10),
            max_time=params.get("max_time", 30.0),
            engine=params.get("engine", "EP"),
        )

    elif name == "IslandGA":
        # FIX-M3: Island GA iterative_optimizer entegrasyonu
        from island_genetic_3d import island_model_ga_3d
        total_q = sum(p.quantity for p in pieces)
        plan = island_model_ga_3d(
            pieces, trucks,
            n_islands=params.get("n_islands", 4),
            island_population=params.get("island_population", 20),
            generations=params.get("generations", 60),
            initial_solution=seed_plan,
        ) if total_q >= 12 else (seed_plan or ffd_3d_optimization(pieces, trucks))

    else:
        raise ValueError(f"Bilinmeyen algoritma: {name}")

    elapsed = time.time() - t0

    # ── Yerleştirme garantisi — hiçbir ürün eksik kalmamalı ──────────────────
    try:
        from fallback_strategy import get_unplaced_pieces, rescue_placement
        from placement_guarantee import guarantee_all_placed, force_place_remaining
        _unplaced = get_unplaced_pieces(pieces, plan)
        if _unplaced:
            # Kademe A: rescue (tam filo ile)
            try:
                plan = rescue_placement(pieces, plan, trucks)
                _unplaced = get_unplaced_pieces(pieces, plan)
            except Exception:
                pass
            # Kademe B: boyut-garantili overflow
            if _unplaced:
                plan, _, _ = guarantee_all_placed(pieces, plan, trucks)
                _unplaced = get_unplaced_pieces(pieces, plan)
            # Kademe C: EP bypass force-placement
            if _unplaced:
                plan = force_place_remaining(pieces, plan, trucks)
    except Exception:
        pass   # garanti modulu yoksa sessizce gec

    return plan, elapsed


def _sort_pieces(pieces: List[Piece3D], strategy: str) -> List[Piece3D]:
    """Layer Building için farklı palet sıralama stratejileri."""
    p = list(pieces)
    if strategy == "volume_desc":
        p.sort(key=lambda x: x.width * x.length * x.height, reverse=True)
    elif strategy == "height_desc":
        p.sort(key=lambda x: x.height, reverse=True)
    elif strategy == "weight_desc":
        p.sort(key=lambda x: getattr(x, "weight", 0), reverse=True)
    return p


def _param_combinations(space: Dict[str, List[Any]]) -> List[Dict[str, Any]]:
    """Kartezyen çarpım → tüm parametre kombinasyon listesi."""
    if not space:
        return [{}]
    keys   = list(space.keys())
    values = list(space.values())
    return [dict(zip(keys, combo)) for combo in itertools.product(*values)]


# ═══════════════════════════════════════════════════════════════════════════════
# BÖLÜM 4 — İTERATİF ARAMA MOTORU
# ═══════════════════════════════════════════════════════════════════════════════

class IterativeSearch:
    """
    Arama Motoru — Tüm algoritma × parametre kombinasyonlarını tarar.

    Örnek:
        searcher = IterativeSearch(
            pieces, trucks,
            algorithms=["Genetic", "SimulatedAnnealing"],
            time_budget=300,        # Toplam maks 300 saniye
            top_k=5,                # En iyi 5 sonucu sakla
            seed_with_ffd=True,     # FFD çözümünü başlangıç noktası yap
            verbose=True,
        )
        best = searcher.run()
        searcher.print_report()
    """

    def __init__(
        self,
        pieces:         List[Piece3D],
        trucks:         List[Truck3D],
        algorithms:     Optional[List[str]] = None,
        param_spaces:   Optional[Dict[str, Dict]] = None,
        time_budget:    float = 300.0,     # saniye — toplam bütçe
        top_k:          int   = 5,
        seed_with_ffd:  bool  = True,      # FFD seed her metasezgisel'e verilir
        verbose:        bool  = True,
        on_result:      Optional[Callable[[SearchResult], None]] = None,
    ):
        self.pieces       = pieces
        self.trucks       = trucks
        self.algorithms   = algorithms or list(PARAM_SPACES.keys())
        self.param_spaces = param_spaces or PARAM_SPACES
        self.time_budget  = time_budget
        self.top_k        = top_k
        self.seed_with_ffd = seed_with_ffd
        self.verbose      = verbose
        self.on_result    = on_result   # Streamlit progress callback için

        self.results:    List[SearchResult] = []
        self._ffd_seed:  Optional[CuttingPlan3D] = None
        self._start_time = 0.0

    # ── Genel akış ──────────────────────────────────────────────────────────

    def run(self) -> SearchResult:
        """
        Tüm taramayı çalıştırır, en iyi SearchResult'u döndürür.
        """
        self._start_time = time.time()
        self.results.clear()

        # FFD seed hazırla
        if self.seed_with_ffd:
            self._log("🔧 FFD seed hazırlanıyor…")
            self._ffd_seed, _ = _run_algorithm("FFD", {}, self.pieces, self.trucks)
            self._log(f"   FFD seed → %{self._ffd_seed.utilization:.2f}")

        # Her algoritma × parametre kombinasyonu
        total_combos = sum(
            len(_param_combinations(self.param_spaces.get(alg, {})))
            for alg in self.algorithms
        )
        self._log(f"\n🔍 Toplam {total_combos} kombinasyon taranacak "
                  f"(bütçe: {self.time_budget:.0f}s)\n")

        combo_no  = 0
        timed_out = False   # FIX-C: flag değişkeni — for-else-break yerine

        for alg in self.algorithms:
            if timed_out:
                break   # Zaman bitti: dış döngüyü temiz kır

            space  = self.param_spaces.get(alg, {})
            combos = _param_combinations(space)

            for params in combos:
                # Zaman bütçesi kontrolü
                elapsed_total = time.time() - self._start_time
                if elapsed_total >= self.time_budget:
                    self._log(f"⏰ Zaman bütçesi doldu ({elapsed_total:.0f}s). Duruyorum.")
                    timed_out = True
                    break   # Yalnızca iç döngüyü kırar; dış döngü flag ile durur

                combo_no += 1
                seed = self._ffd_seed if self.seed_with_ffd else None

                try:
                    plan, t = _run_algorithm(alg, params, self.pieces, self.trucks, seed)
                    result = SearchResult(
                        algorithm=alg,
                        params=params,
                        utilization=plan.utilization,
                        execution_time=t,
                        plan=plan,
                    )
                    self.results.append(result)

                    if self.on_result:
                        self.on_result(result)

                    self._log(
                        f"  [{combo_no:>4}/{total_combos}] "
                        f"{alg:<22} {params} → %{plan.utilization:.2f}  ({t:.1f}s)"
                    )

                except Exception as e:
                    self._log(f"  ⚠️  {alg} {params} → HATA: {e}")

        # Sırala
        self.results.sort(key=lambda r: r.utilization, reverse=True)
        for i, r in enumerate(self.results):
            r.rank = i + 1

        return self.results[0] if self.results else None

    # ── Raporlama ───────────────────────────────────────────────────────────

    def print_report(self, top_k: Optional[int] = None) -> None:
        k = top_k or self.top_k
        print("\n" + "═" * 78)
        print(f"  🏆  ARAMA SONUÇLARI — EN İYİ {k} KOMBİNASYON")
        print("═" * 78)
        for r in self.results[:k]:
            print(r)
        print("═" * 78)
        if self.results:
            best = self.results[0]
            print(f"\n✅ EN İYİ → {best.algorithm} | %{best.utilization:.2f}")
            print(f"   Parametreler: {best.params}")
            print(f"   Toplam süre : {time.time() - self._start_time:.1f}s")

    def top_results(self, k: Optional[int] = None) -> List[SearchResult]:
        return self.results[:k or self.top_k]

    def _log(self, msg: str) -> None:
        if self.verbose:
            print(msg)


# ═══════════════════════════════════════════════════════════════════════════════
# BÖLÜM 5 — HİBRİT PIPELINE
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class PipelineStage:
    """
    Pipeline'daki tek bir aşama.

    algorithm : çalıştırılacak algoritma adı
    params    : sabit parametreler (boş → varsayılan)
    use_prev_as_seed : True → önceki aşamanın planını seed al
    """
    algorithm:          str
    params:             Dict[str, Any] = field(default_factory=dict)
    use_prev_as_seed:   bool = True
    label:              str  = ""

    def __post_init__(self):
        if not self.label:
            self.label = self.algorithm


class HybridPipeline:
    """
    Birden fazla algoritmayı sırayla (pipeline) çalıştırır;
    her aşama bir öncekinin çıktısını seed olarak kullanır.

    Yerleşik pipeline'lar:
        HybridPipeline.greedy_sa()          Greedy → Simulated Annealing
        HybridPipeline.ffd_genetic()        FFD    → Genetic Algorithm
        HybridPipeline.full_chain()         FFD → Greedy → GA → SA → Tabu

    Özel pipeline:
        stages = [
            PipelineStage("FFD"),
            PipelineStage("Genetic", {"population_size": 80, "generations": 150}),
            PipelineStage("SimulatedAnnealing", {"max_time": 60, "cooling_rate": 0.999}),
        ]
        plan = HybridPipeline(pieces, trucks, stages=stages).run()
    """

    def __init__(
        self,
        pieces: List[Piece3D],
        trucks: List[Truck3D],
        stages: Optional[List[PipelineStage]] = None,
        verbose: bool = True,
    ):
        self.pieces  = pieces
        self.trucks  = trucks
        self.stages  = stages or self._default_stages()
        self.verbose = verbose
        self.history: List[Tuple[str, float, float]] = []   # (label, util, time)

    # ── Fabrika metotları ────────────────────────────────────────────────────

    @classmethod
    def greedy_sa(cls, pieces, trucks, sa_time=40.0, cooling=0.997, **kwargs):
        """Greedy → Simulated Annealing  (hızlı ve güçlü)"""
        # FIX-K1: "initial_temp": 1000.0 kaldırıldı.
        # params sözlüğünde initial_temp olmayınca _run_algorithm
        # params.get("initial_temp", None) = None döndürür ve
        # _calibrate_initial_temp() otomatik devreye girer.
        stages = [
            PipelineStage("Greedy", label="1. Greedy"),
            PipelineStage("SimulatedAnnealing",
                          {"max_time": sa_time, "cooling_rate": cooling},
                          label="2. SA Rafine"),
        ]
        return cls(pieces, trucks, stages=stages, **kwargs)

    @classmethod
    def ffd_genetic(cls, pieces, trucks, pop=80, gen=150, **kwargs):
        """FFD → Genetic Algorithm"""
        stages = [
            PipelineStage("FFD", label="1. FFD Seed"),
            PipelineStage("Genetic",
                          {"population_size": pop, "generations": gen,
                           "crossover_rate": 0.85, "mutation_rate": 0.2},
                          label="2. Genetic Optimizer"),
        ]
        return cls(pieces, trucks, stages=stages, **kwargs)

    @classmethod
    def ffd_tabu(cls, pieces, trucks, tabu_iter=600, tabu_tenure=12, max_time=45, **kwargs):
        """FFD → Tabu Search"""
        stages = [
            PipelineStage("FFD", label="1. FFD Seed"),
            PipelineStage("TabuSearch",
                          {"max_iterations": tabu_iter, "tabu_tenure": tabu_tenure,
                           "max_time": max_time},
                          label="2. Tabu Rafine"),
        ]
        return cls(pieces, trucks, stages=stages, **kwargs)

    @classmethod
    def full_chain(cls, pieces, trucks, **kwargs):
        """
        Tam zincir:
          FFD → Greedy → Genetic → Simulated Annealing → Tabu Search
        Her aşama bir öncekini aşamazsa kendi çıktısını saklarken
        bir sonrakine seed olarak en iyi planı iletir.
        """
        stages = [
            PipelineStage("FFD",    label="1. FFD"),
            PipelineStage("Greedy", label="2. Greedy"),
            PipelineStage("Genetic",
                          {"population_size": 60, "generations": 100},
                          label="3. Genetic"),
            # FIX-M3: Island GA eklendi — Genetic'ten daha iyi çeşitlilik
            PipelineStage("IslandGA",
                          {"n_islands": 4, "island_population": 20, "generations": 60},
                          label="4. Island GA"),
            PipelineStage("SimulatedAnnealing",
                          {"max_time": 40.0, "cooling_rate": 0.996},
                          label="5. SA"),
            PipelineStage("TabuSearch",
                          {"max_iterations": 400, "max_time": 30.0},
                          label="6. Tabu"),
        ]
        return cls(pieces, trucks, stages=stages, **kwargs)

    # ── Çalıştırıcı ─────────────────────────────────────────────────────────

    def run(self) -> CuttingPlan3D:
        """
        Pipeline'ı çalıştırır.
        Her aşama bir öncekini geçerse yeni en iyi plan güncellenir.
        Sonuç: tüm aşamalar arasından en yüksek utilization'lı plan.
        """
        best_plan: Optional[CuttingPlan3D] = None
        best_util = -1.0
        prev_plan: Optional[CuttingPlan3D] = None

        self._log("\n" + "═" * 60)
        self._log("  🔗  HİBRİT PİPELİNE BAŞLIYOR")
        self._log("═" * 60)

        for stage in self.stages:
            # FIX-D: Seed olarak her zaman best_plan verilir (prev_plan değil).
            # Önceki aşama kötüleşirse (örn. SA yerel optimuma düşerse),
            # sonraki algoritma kötü bir noktadan değil en iyi noktadan başlar.
            # Yapıcı algoritmalar (FFD/Greedy) seed kullanmaz — güvenli.
            seed = best_plan if stage.use_prev_as_seed else None
            self._log(f"\n▶  {stage.label}  {stage.params or ''}")

            try:
                plan, elapsed = _run_algorithm(
                    stage.algorithm, stage.params,
                    self.pieces, self.trucks, seed
                )
                self.history.append((stage.label, plan.utilization, elapsed))
                self._log(f"   → %{plan.utilization:.2f}  ({elapsed:.1f}s)")

                if plan.utilization >= best_util:
                    best_util = plan.utilization
                    best_plan = plan
                    self._log(f"   ⭐ Yeni en iyi: %{best_util:.2f}")

            except Exception as e:
                self._log(f"   ⚠️  HATA: {e}")
                # Hata olursa best_plan değişmeden kalır, sonraki aşamaya verilir

        self._log("\n" + "═" * 60)
        self._log(f"  ✅  PIPELINE TAMAMLANDI — En iyi: %{best_util:.2f}")
        self._log("═" * 60 + "\n")
        return best_plan

    def print_history(self) -> None:
        print("\n📈 Pipeline Aşama Geçmişi:")
        for label, util, elapsed in self.history:
            bar = "█" * int(util / 2)
            print(f"  {label:<28} %{util:6.2f}  {bar}  ({elapsed:.1f}s)")

    def _log(self, msg: str) -> None:
        if self.verbose:
            print(msg)

    def _default_stages(self) -> List[PipelineStage]:
        return HybridPipeline.greedy_sa.__func__(
            HybridPipeline, self.pieces, self.trucks
        ).stages


# ═══════════════════════════════════════════════════════════════════════════════
# BÖLÜM 6 — AKILLI PARAMETRE ADAPTASYONU (Bayesian-benzeri basit sürüm)
# ═══════════════════════════════════════════════════════════════════════════════

class AdaptiveSearch:
    """
    Basit adaptif arama: ilk turda geniş tarama, sonrasında en iyi
    bölgeyi yakınlaştırarak daraltır (zoom-in stratejisi).

    Tam Bayesian Optimizasyon'a gerek kalmadan pratik iyileştirme sağlar.

    Örnek:
        adaptive = AdaptiveSearch(pieces, trucks, algorithm="SimulatedAnnealing")
        best = adaptive.run(rounds=3)
    """

    def __init__(
        self,
        pieces:    List[Piece3D],
        trucks:    List[Truck3D],
        algorithm: str = "SimulatedAnnealing",
        rounds:    int = 3,
        samples_per_round: int = 10,
        verbose:   bool = True,
        seed_with_ffd: bool = True,
    ):
        self.pieces    = pieces
        self.trucks    = trucks
        self.algorithm = algorithm
        self.rounds    = rounds
        self.samples   = samples_per_round
        self.verbose   = verbose
        self.seed_with_ffd = seed_with_ffd
        self._ffd_seed: Optional[CuttingPlan3D] = None

    def run(self) -> SearchResult:
        if self.seed_with_ffd:
            self._ffd_seed, _ = _run_algorithm("FFD", {}, self.pieces, self.trucks)

        space = dict(PARAM_SPACES.get(self.algorithm, {}))
        best_result: Optional[SearchResult] = None

        for rnd in range(1, self.rounds + 1):
            self._log(f"\n── Tur {rnd}/{self.rounds} — {self.algorithm} ──")
            self._log(f"   Uzay: {space}")

            # Bu turdaki örnekleri rastgele çek
            candidates = self._sample(space, self.samples)
            round_results = []

            for params in candidates:
                try:
                    plan, t = _run_algorithm(
                        self.algorithm, params,
                        self.pieces, self.trucks, self._ffd_seed
                    )
                    r = SearchResult(self.algorithm, params, plan.utilization, t, plan)
                    round_results.append(r)
                    self._log(f"   {params} → %{plan.utilization:.2f}")
                except Exception as e:
                    self._log(f"   ⚠️ {params} → {e}")

            if not round_results:
                break

            round_results.sort(key=lambda r: r.utilization, reverse=True)
            top = round_results[0]

            if best_result is None or top.utilization > best_result.utilization:
                best_result = top

            # Parametreleri en iyi etrafında daralt (zoom-in)
            space = self._zoom(space, top.params)
            self._log(f"   ⭐ Tur {rnd} en iyi: %{top.utilization:.2f}")

        self._log(f"\n✅ AdaptiveSearch bitti → %{best_result.utilization:.2f}")
        return best_result

    def _sample(self, space: Dict, n: int) -> List[Dict]:
        """Uzaydan n rastgele örnek."""
        all_combos = _param_combinations(space)
        if len(all_combos) <= n:
            return all_combos
        return random.sample(all_combos, n)

    def _zoom(self, space: Dict, best_params: Dict) -> Dict:
        """
        Sayısal parametreleri en iyi değerin ±%30 bandında daralt.
        Kategorik parametreler sabitlenir.

        FIX-E: Orijinal kod filtre sonucu tek değer kalınca [best_val]
        döndürüyordu — bu parametreyi sonraki turda dondurur, arama
        uzayı erken kapanır. Yeni kod:
          1. Komşu değerleri de filtreye dahil et (en az 2 değer garantisi).
          2. Hâlâ tek değer kalırsa orijinal uzayı koru (daraltma atlanır).
        """
        new_space = {}
        for key, values in space.items():
            best_val = best_params.get(key)
            if best_val is None:
                new_space[key] = values
                continue

            if isinstance(best_val, (int, float)) and len(values) > 1:
                sorted_vals = sorted(values)
                lo_gl = min(sorted_vals)
                hi_gl = max(sorted_vals)
                span  = (hi_gl - lo_gl) * 0.3
                new_lo = best_val - span
                new_hi = best_val + span

                filtered = [v for v in sorted_vals if new_lo <= v <= new_hi]

                if len(filtered) >= 2:
                    new_space[key] = filtered
                elif len(filtered) == 1:
                    # En yakın komşuyu da ekle — en az 2 değer garantisi
                    idx = sorted_vals.index(filtered[0])
                    candidates = list(filtered)
                    if idx > 0:
                        candidates.append(sorted_vals[idx - 1])
                    if idx < len(sorted_vals) - 1:
                        candidates.append(sorted_vals[idx + 1])
                    new_space[key] = sorted(set(candidates))
                else:
                    # Hiç değer kalmadı → orijinal uzayı koru
                    new_space[key] = sorted_vals
            else:
                # Kategorik → en iyi değeri sabitle
                new_space[key] = [best_val]

        return new_space

    def _log(self, msg: str) -> None:
        if self.verbose:
            print(msg)


# ═══════════════════════════════════════════════════════════════════════════════
# BÖLÜM 7 — KULLANIM ÖRNEKLERİ
# ═══════════════════════════════════════════════════════════════════════════════

def demo(pieces: List[Piece3D], trucks: List[Truck3D]) -> None:
    """
    Tüm stratejilerin örnek kullanımı.
    Gerçek veriyle çağrın: demo(my_pieces, my_trucks)
    """

    # ── A) Tam Parametre Taraması ────────────────────────────────────────────
    print("\n" + "="*60)
    print("A) TAM PARAMETRE TARAMASI (IterativeSearch)")
    print("="*60)

    searcher = IterativeSearch(
        pieces, trucks,
        algorithms=["Genetic", "SimulatedAnnealing", "TabuSearch", "MonteCarlo"],
        time_budget=180,       # 3 dakika bütçe
        top_k=5,
        seed_with_ffd=True,
        verbose=True,
    )
    best = searcher.run()
    searcher.print_report()

    # ── B) Hızlı Hibrit (Greedy → SA) ───────────────────────────────────────
    print("\n" + "="*60)
    print("B) HİBRİT: Greedy → Simulated Annealing")
    print("="*60)

    pipeline = HybridPipeline.greedy_sa(
        pieces, trucks,
        sa_time=50.0,
        cooling=0.998,
    )
    plan_b = pipeline.run()
    pipeline.print_history()

    # ── C) Tam Zincir ────────────────────────────────────────────────────────
    print("\n" + "="*60)
    print("C) TAM ZİNCİR: FFD → Greedy → GA → SA → Tabu")
    print("="*60)

    chain = HybridPipeline.full_chain(pieces, trucks)
    plan_c = chain.run()
    chain.print_history()

    # ── D) Adaptif Arama (SA için) ───────────────────────────────────────────
    print("\n" + "="*60)
    print("D) ADAPTİF ARAMA (Simulated Annealing)")
    print("="*60)

    adaptive = AdaptiveSearch(
        pieces, trucks,
        algorithm="SimulatedAnnealing",
        rounds=3,
        samples_per_round=8,
    )
    best_sa = adaptive.run()
    print(f"\n→ Adaptif SA sonucu: %{best_sa.utilization:.2f}")
    print(f"  Parametreler: {best_sa.params}")

    # ── Karşılaştırma özeti ──────────────────────────────────────────────────
    print("\n" + "="*60)
    print("📊 STRATEJI KARŞILAŞTIRMASI")
    print("="*60)
    scores = {
        "A) Tam Tarama (en iyi)": best.utilization if best else 0,
        "B) Greedy→SA":           plan_b.utilization if plan_b else 0,
        "C) Tam Zincir":          plan_c.utilization if plan_c else 0,
        "D) Adaptif SA":          best_sa.utilization if best_sa else 0,
    }
    for label, util in sorted(scores.items(), key=lambda x: -x[1]):
        bar = "█" * int(util / 2)
        print(f"  {label:<30} %{util:6.2f}  {bar}")


# ═══════════════════════════════════════════════════════════════════════════════
# BÖLÜM 8 — STREAMLIT ENTEGRASYONU (app_3d.py için hazır snippet)
# ═══════════════════════════════════════════════════════════════════════════════
#
# app_3d.py'ye şu bloğu ekleyin:
#
#   from iterative_optimizer_3d import IterativeSearch, HybridPipeline
#
#   if st.button("🔍 Otomatik Optimize Et"):
#       progress = st.progress(0)
#       status   = st.empty()
#       results_placeholder = st.empty()
#
#       collected = []
#       def on_result(r):
#           collected.append(r)
#           collected.sort(key=lambda x: -x.utilization)
#           status.write(f"Son: {r.algorithm} → %{r.utilization:.2f}")
#           results_placeholder.dataframe(
#               [{"Algoritma": x.algorithm,
#                 "Doluluk %": round(x.utilization, 2),
#                 "Params": str(x.params)} for x in collected[:10]]
#           )
#
#       searcher = IterativeSearch(
#           st.session_state.pieces,
#           st.session_state.trucks,
#           algorithms=["Genetic","SimulatedAnnealing","TabuSearch"],
#           time_budget=120,
#           on_result=on_result,
#       )
#       best = searcher.run()
#       st.success(f"✅ En iyi: {best.algorithm} → %{best.utilization:.2f}")
#       st.session_state.cutting_plan = best.plan
#
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # Hızlı fonksiyonel test — gerçek veri olmadan temel import kontrolü
    print("✅ iterative_optimizer_3d.py başarıyla yüklendi.")
    print("   Kullanım: demo(my_pieces, my_trucks)")
    print("   veya  : HybridPipeline.greedy_sa(pieces, trucks).run()")
