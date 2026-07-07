# -*- coding: utf-8 -*-
"""
Algorithm Recommender — Akıllı Algoritma Seçim Rehberi
========================================================
Kullanıcı hangi algoritmayı seçeceğini bilmiyor olabilir. Bu modül
problem karakteristiklerine göre 3 öneri döndürür: hızlı/dengeli/en iyi.

Heuristic-based scoring — tam Bayesian seçim için bayesian_optimizer kullanılır.
Bu modül O(1) hızlı öneri için "rule-of-thumb" sağlar.

References:
    Wolpert & Macready (1997). "No Free Lunch Theorems for Optimization"
    — Hiçbir algoritma evrensel olarak en iyi değildir; problem
    karakteristiği seçimi belirler.
"""

from typing import List, Dict, Tuple
from dataclasses import dataclass


@dataclass
class ProblemProfile:
    """Problem karakteristiği."""
    n_pieces: int               # Toplam parça (quantity dahil)
    n_unique_types: int         # Farklı parça tipi
    n_trucks: int               # Farklı araç tipi
    has_fragile: bool           # Kırılgan parça var mı
    has_priority: bool          # Priority kısıtı var mı
    has_cylinder: bool          # Silindir parça var mı
    weight_heterogeneity: float # 0-1, ağırlık dağılım çeşitliliği

    @property
    def complexity_score(self) -> float:
        """0-100 arası problem karmaşıklık skoru."""
        base = min(100, self.n_pieces / 10.0 * 10)   # 0-100 parça → 0-100
        if self.has_fragile: base += 5
        if self.has_priority: base += 8
        if self.has_cylinder: base += 4
        base += self.weight_heterogeneity * 10
        if self.n_unique_types > 10: base += 5
        return min(100, base)

    @property
    def size_tier(self) -> str:
        """small / medium / large / xlarge"""
        if self.n_pieces <= 20:   return "small"
        if self.n_pieces <= 100:  return "medium"
        if self.n_pieces <= 300:  return "large"
        return "xlarge"


@dataclass
class AlgorithmRecommendation:
    """Tek bir algoritma önerisi."""
    algo_key: str            # ALGORITHMS dict'inde kullanılan anahtar
    label: str               # Görüntülenen ad
    icon: str                # Emoji
    tier: str                # "fast" | "balanced" | "best"
    reason: str              # Türkçe açıklama
    estimated_time_sec: float
    expected_util_pct: Tuple[float, float]   # min-max beklenen doluluk


def profile_problem(
    pieces: List,
    trucks: List,
) -> ProblemProfile:
    """Piece3D/Truck3D listelerinden problem profili çıkar."""
    n_pieces = sum(getattr(p, "quantity", 1) for p in pieces)
    n_unique = len(pieces)
    n_trucks = len(trucks)
    has_fragile = any(getattr(p, "is_fragile", False) for p in pieces)
    has_priority = any(getattr(p, "priority", None) is not None for p in pieces)
    has_cylinder = any(getattr(p, "shape", "box") == "cylinder" for p in pieces)

    # Ağırlık çeşitliliği
    weights = [getattr(p, "weight", 0) for p in pieces if getattr(p, "weight", 0) > 0]
    if len(weights) > 1:
        avg = sum(weights) / len(weights)
        if avg > 0:
            variance = sum((w - avg) ** 2 for w in weights) / len(weights)
            heterogeneity = min(1.0, (variance ** 0.5) / avg)
        else:
            heterogeneity = 0.0
    else:
        heterogeneity = 0.0

    return ProblemProfile(
        n_pieces=n_pieces,
        n_unique_types=n_unique,
        n_trucks=n_trucks,
        has_fragile=has_fragile,
        has_priority=has_priority,
        has_cylinder=has_cylinder,
        weight_heterogeneity=heterogeneity,
    )


# ─── ÖNERİ MOTORU ────────────────────────────────────────────────────────────

def recommend_algorithms(profile: ProblemProfile) -> List[AlgorithmRecommendation]:
    """
    Problem profiline göre 3 öneri döndür:
        1. fast      — En hızlı, makul sonuç
        2. balanced  — Dengeli hız/kalite (varsayılan öneri)
        3. best      — En iyi sonuç, daha uzun süre

    Kurallar:
        - Küçük problem (≤20 parça): FFD yeter (deterministik + hızlı)
        - Orta (≤100): Greedy/FFD hızlı, GA dengeli, Bayesian en iyi
        - Büyük (≤300): FFD hızlı, Tabu/SA dengeli, Island GA en iyi
        - Çok büyük (>300): Sadece Greedy/FFD pratik; meta-heuristic uyarı verir

        - Kırılgan + öncelik var → meta-heuristic'lere ek puan (kısıtları öğrenir)
        - Heterojen ağırlık → Bayesian iyileşir
        - Tek tip parça → Greedy yeterli
    """
    tier = profile.size_tier
    has_constraints = profile.has_fragile or profile.has_priority

    recs: List[AlgorithmRecommendation] = []

    # ── FAST katmanı ────────────────────────────────────────────────────
    if tier in ("small", "medium"):
        recs.append(AlgorithmRecommendation(
            algo_key="ffd_ep_cp",
            label="FFD",
            icon="📦",
            tier="fast",
            reason="Hızlı ve deterministik. Küçük/orta problemlerde tutarlı sonuç.",
            estimated_time_sec=0.5 if tier == "small" else 2.0,
            expected_util_pct=(70.0, 85.0),
        ))
    else:  # large/xlarge
        recs.append(AlgorithmRecommendation(
            algo_key="ffd_ep_cp",
            label="FFD",
            icon="📦",
            tier="fast",
            reason="Büyük problemlerde tek pratik hızlı seçenek. ~10 saniye.",
            estimated_time_sec=10.0 if tier == "large" else 30.0,
            expected_util_pct=(65.0, 80.0),
        ))

    # ── BALANCED katmanı ────────────────────────────────────────────────
    if tier == "small":
        # Küçük problemde fancy alg'a gerek yok, Layer Building önerelim
        recs.append(AlgorithmRecommendation(
            algo_key="layer_building",
            label="Layer Building",
            icon="🧱",
            tier="balanced",
            reason="Operatör için yükleme sırası net (duvar duvar). Küçük problemde ideal.",
            estimated_time_sec=0.8,
            expected_util_pct=(72.0, 86.0),
        ))
    elif tier == "medium":
        if has_constraints:
            recs.append(AlgorithmRecommendation(
                algo_key="genetic",
                label="Genetic Algorithm",
                icon="🧬",
                tier="balanced",
                reason="Kırılgan+öncelik gibi kısıtları öğrenir. Orta problemde dengeli.",
                estimated_time_sec=8.0,
                expected_util_pct=(78.0, 90.0),
            ))
        else:
            recs.append(AlgorithmRecommendation(
                algo_key="greedy_ep_cp",
                label="Greedy",
                icon="⚡",
                tier="balanced",
                reason="Kısıtsız problemde hızlı + iyi sonuç. Karmaşıklık gerekmez.",
                estimated_time_sec=2.0,
                expected_util_pct=(75.0, 87.0),
            ))
    else:  # large/xlarge
        recs.append(AlgorithmRecommendation(
            algo_key="tabu",
            label="Tabu Search",
            icon="🔍",
            tier="balanced",
            reason="Büyük problemde sistematik komşuluk arama. Lokal optimumlardan kaçar.",
            estimated_time_sec=30.0,
            expected_util_pct=(80.0, 90.0),
        ))

    # ── BEST katmanı ────────────────────────────────────────────────────
    if tier == "small":
        recs.append(AlgorithmRecommendation(
            algo_key="genetic",
            label="Genetic Algorithm",
            icon="🧬",
            tier="best",
            reason="Küçük problemde 5 saniyede mükemmel sonuç.",
            estimated_time_sec=5.0,
            expected_util_pct=(82.0, 95.0),
        ))
    elif tier == "medium":
        recs.append(AlgorithmRecommendation(
            algo_key="bayesian",
            label="Bayesian Optimization",
            icon="🔬",
            tier="best",
            reason=("Hiperparametre otomasyonu — sizin için en iyi yapılandırmayı bulur. "
                    "Heterojen yüklerde fark yaratır."),
            estimated_time_sec=60.0,
            expected_util_pct=(85.0, 95.0),
        ))
    elif tier == "large":
        recs.append(AlgorithmRecommendation(
            algo_key="island_ga",
            label="Island GA",
            icon="🏝️",
            tier="best",
            reason="Çoklu populasyon ile büyük problemde en iyi sonuç. ~2 dakika.",
            estimated_time_sec=120.0,
            expected_util_pct=(83.0, 93.0),
        ))
    else:  # xlarge
        # Çok büyük problemde meta-heuristic riskli olabilir
        recs.append(AlgorithmRecommendation(
            algo_key="ffd_ep_cp",
            label="FFD (xlarge için)",
            icon="📦",
            tier="best",
            reason=("300+ parçada meta-heuristic'ler 10+ dakika sürebilir. "
                    "FFD pratik olarak en iyi seçim."),
            estimated_time_sec=30.0,
            expected_util_pct=(70.0, 82.0),
        ))

    return recs


def recommend_top_algo(profile: ProblemProfile) -> str:
    """Tek varsayılan öneri (balanced tier)."""
    recs = recommend_algorithms(profile)
    for r in recs:
        if r.tier == "balanced":
            return r.algo_key
    return recs[0].algo_key if recs else "ffd_ep_cp"


def format_problem_summary(profile: ProblemProfile) -> str:
    """UI için tek satır özet."""
    parts = [
        f"📦 {profile.n_pieces} parça ({profile.n_unique_types} tip)",
        f"🚛 {profile.n_trucks} araç",
    ]
    flags = []
    if profile.has_priority: flags.append("öncelik")
    if profile.has_fragile: flags.append("kırılgan")
    if profile.has_cylinder: flags.append("silindir")
    if flags:
        parts.append("⚠️ " + ", ".join(flags))
    parts.append(f"📊 Karmaşıklık: %{profile.complexity_score:.0f}")
    return "  ·  ".join(parts)
