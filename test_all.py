# -*- coding: utf-8 -*-
"""
Test — Tüm algoritmalar doğrulama
"""

import sys
import os

# Project path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core_3d import Piece3D, Truck3D

# ============================================================================
# TEST VERİSİ
# ============================================================================

def create_test_data():
    """Gerçekçi test verisi: 15 farklı palet, 2 kamyon tipi"""
    pieces = [
        Piece3D("P1", 120, 80, 100, 3, weight=150.0, customer_id="C1"),
        Piece3D("P2", 100, 100, 80, 2, weight=200.0, customer_id="C1"),
        Piece3D("P3", 80, 60, 60, 4, weight=80.0, customer_id="C2"),
        Piece3D("P4", 120, 100, 120, 2, weight=300.0, customer_id="C2"),
        Piece3D("P5", 60, 40, 40, 5, weight=30.0, customer_id="C3"),
        Piece3D("P6", 100, 80, 100, 2, weight=180.0, customer_id="C3"),
        Piece3D("P7", 80, 80, 80, 3, weight=120.0, customer_id="C1"),
    ]

    trucks = [
        Truck3D("TIR_13m", 240, 1360, 270, 24000, 3),
        Truck3D("KAMYON_7m", 240, 700, 240, 12000, 5),
    ]

    delivery_order = ["C1", "C2", "C3"]  # C1 ilk teslim

    return pieces, trucks, delivery_order


# ============================================================================
# TESTLER
# ============================================================================

def test_greedy():
    print("\n" + "=" * 60)
    print("TEST: Greedy 3D (EP)")
    print("=" * 60)
    from greedy_3d import greedy_3d_optimization
    pieces, trucks, _ = create_test_data()
    result = greedy_3d_optimization(pieces, trucks, engine='EP')
    assert result.utilization > 0, "Greedy: doluluk 0 olamaz"
    assert len(result.bins) > 0, "Greedy: en az 1 bin olmalı"
    placed = sum(len(b) for b in result.bins)
    print(f"  → {placed} palet yerleştirildi, %{result.utilization:.1f}")
    return True


def test_ffd():
    print("\n" + "=" * 60)
    print("TEST: FFD 3D (EP)")
    print("=" * 60)
    from ffd_3d import ffd_3d_optimization
    pieces, trucks, _ = create_test_data()
    result = ffd_3d_optimization(pieces, trucks, engine='EP')
    assert result.utilization > 0, "FFD: doluluk 0 olamaz"
    placed = sum(len(b) for b in result.bins)
    print(f"  → {placed} palet yerleştirildi, %{result.utilization:.1f}")
    return True


def test_layer_building():
    print("\n" + "=" * 60)
    print("TEST: Layer Building 3D")
    print("=" * 60)
    from layer_building_3d import layer_building_3d_optimization
    pieces, trucks, delivery_order = create_test_data()
    result = layer_building_3d_optimization(
        pieces, trucks,
        delivery_order=delivery_order,
        layer_strategy='adaptive'
    )
    assert result.utilization > 0, "LB: doluluk 0 olamaz"
    placed = sum(len(b) for b in result.bins)
    print(f"  → {placed} palet yerleştirildi, %{result.utilization:.1f}")

    # Layer results kontrolü
    if hasattr(result, 'layer_results'):
        for lr in result.layer_results:
            print(f"\n{lr.get_operator_instructions()}")
    return True


def test_tabu_search():
    print("\n" + "=" * 60)
    print("TEST: Tabu Search 3D (5s limit)")
    print("=" * 60)
    from ffd_3d import ffd_3d_optimization
    from tabu_search_3d import tabu_search_3d_optimization
    pieces, trucks, _ = create_test_data()

    # FFD ile başlangıç çözümü
    ffd_result = ffd_3d_optimization(pieces, trucks, engine='EP')

    # Tabu Search ile iyileştir
    ts_result = tabu_search_3d_optimization(
        pieces, trucks,
        initial_solution=ffd_result,
        max_time=5.0,
        max_iterations=50,
        engine='EP'
    )
    placed = sum(len(b) for b in ts_result.bins)
    print(f"  → {placed} palet, %{ts_result.utilization:.1f}")
    print(f"  → FFD: %{ffd_result.utilization:.1f} → TS: %{ts_result.utilization:.1f}")
    return True


def test_simulated_annealing():
    print("\n" + "=" * 60)
    print("TEST: Simulated Annealing 3D (5s limit)")
    print("=" * 60)
    from ffd_3d import ffd_3d_optimization
    from simulated_annealing_3d import simulated_annealing_3d_optimization
    pieces, trucks, _ = create_test_data()

    ffd_result = ffd_3d_optimization(pieces, trucks, engine='EP')

    sa_result = simulated_annealing_3d_optimization(
        pieces, trucks,
        initial_solution=ffd_result,
        max_time=5.0,
        engine='EP'
    )
    placed = sum(len(b) for b in sa_result.bins)
    print(f"  → {placed} palet, %{sa_result.utilization:.1f}")
    return True


def test_comparison():
    print("\n" + "=" * 60)
    print("TEST: Standart Mod Karşılaştırma")
    print("=" * 60)
    from comparison_3d import run_standard_mode
    pieces, trucks, delivery_order = create_test_data()

    comp = run_standard_mode(
        pieces, trucks,
        ts_time=5.0,
        delivery_order=delivery_order
    )
    print(comp.summary)
    print(f"\n🏆 En iyi: {comp.best_algorithm} (%{comp.best_utilization:.1f})")
    return True


# ============================================================================
# MAIN
# ============================================================================

if __name__ == '__main__':
    print("🧪 3D Bin Packing — Tam Sistem Testi")
    print("=" * 60)

    tests = [
        ("Greedy (EP)", test_greedy),
        ("FFD (EP)", test_ffd),
        ("Layer Building", test_layer_building),
        ("Tabu Search", test_tabu_search),
        ("SA", test_simulated_annealing),
        ("Karşılaştırma", test_comparison),
    ]

    passed = 0
    failed = 0
    for name, fn in tests:
        try:
            result = fn()
            if result:
                passed += 1
                print(f"  ✅ {name} BAŞARILI")
        except Exception as e:
            failed += 1
            print(f"  ❌ {name} HATA: {e}")
            import traceback
            traceback.print_exc()

    print(f"\n{'=' * 60}")
    print(f"📊 SONUÇ: {passed}/{len(tests)} test başarılı")
    if failed > 0:
        print(f"⚠️ {failed} test başarısız")
    print("=" * 60)
