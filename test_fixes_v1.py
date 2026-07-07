# -*- coding: utf-8 -*-
"""
test_fixes_v1.py — Düzeltme Doğrulama Test Paketi
===================================================
Bu script, extreme_points_3d.py ve core_3d.py'deki
3 kritik hatanın düzeltilip düzeltilmediğini doğrular.

Çalıştırma:
    python test_fixes_v1.py

Her test GEÇTI / BAŞARISIZ olarak raporlanır.
Sonunda ESKİ vs YENİ doluluk oranı karşılaştırması gösterilir.
"""

import sys
import os
import time

# Scriptin bulunduğu klasörü path'e ekle — her yerden çalışır
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ─────────────────────────────────────────────────────────────────────────────
# Import
# ─────────────────────────────────────────────────────────────────────────────
try:
    from core_3d import (
        Piece3D, Truck3D, Placement3D, CuttingPlan3D,
        gravity_settle_placements, get_all_rotations_3d,
        check_collision_with_list, check_collision_3d,
    )
    from extreme_points_3d import ExtremePoints3D
    from ffd_3d import ffd_3d_optimization
    from greedy_3d import greedy_3d_optimization
    print("✅ Tüm modüller başarıyla import edildi\n")
except ImportError as e:
    print(f"❌ Import hatası: {e}")
    print("   Bu scripti projenin ana klasöründen çalıştırın.")
    sys.exit(1)

# ─────────────────────────────────────────────────────────────────────────────
# Yardımcı fonksiyonlar
# ─────────────────────────────────────────────────────────────────────────────

PASS = "✅ GEÇTI"
FAIL = "❌ BAŞARISIZ"
results = []

def check(name: str, condition: bool, detail: str = ""):
    status = PASS if condition else FAIL
    msg = f"  {status} — {name}"
    if detail:
        msg += f"\n           {detail}"
    print(msg)
    results.append((name, condition))
    return condition

def section(title: str):
    print(f"\n{'═'*60}")
    print(f"  {title}")
    print(f"{'═'*60}")

def has_collision(placements, piece_info=None):
    """Yerleşim listesinde çakışma var mı?"""
    for i, p1 in enumerate(placements):
        for p2 in placements[i+1:]:
            if check_collision_3d(p1, p2, piece_info):
                return True, (p1.piece_id, p2.piece_id)
    return False, None

def utilization(placements, truck):
    used = sum(p.width * p.length * p.height for p in placements)
    total = truck.width * truck.length * truck.height
    return (used / total * 100) if total > 0 else 0.0


# ─────────────────────────────────────────────────────────────────────────────
# HATA-1 TESTLERİ: EP Dominance Pruning
# ─────────────────────────────────────────────────────────────────────────────
section("HATA-1: EP Dominance Pruning Düzeltmesi")
print("""
  Eski davranış: (0,0,0) EP mevcut olduğunda (100,0,0), (0,200,0) gibi
  noktalar "dominated" sayılıp siliniyordu. Bu, bazı yerleşim fırsatlarını
  yok ediyordu.

  Yeni davranış: Dominance pruning yok. Sadece "sınır dışı" ve "occupied"
  kontrolleri var. EP sayısı MAX_EXTREME_POINTS ile sınırlı.
""")

truck_1 = Truck3D("T_300x600x300", 300, 600, 300, 99999, 5)
pi_1 = {}

ep1 = ExtremePoints3D(300, 600, 300, heuristic='CP', truck=truck_1, piece_info=pi_1)

# İlk kutu: (0,0,0) → (100,100,100) yerleştir
ep1.place_piece_3d("P0", (0, 0, 0, 100, 100, 100, (0, 0, 0)))
eps_after_first = list(ep1.extreme_points)

# Eski kodda (0,0,0) varlığı nedeniyle (100,0,0), (0,100,0), (0,0,100)
# dominant olmayan olarak silinirdi. Yeni kodda bunlar korunmalı.
has_x100 = any(e[0] == 100 for e in eps_after_first)
has_y100 = any(e[1] == 100 for e in eps_after_first)
has_z100 = any(e[2] == 100 for e in eps_after_first)

check("x=100 EP korunuyor (eski kodda silinirdi)", has_x100,
      f"Mevcut EPs: {eps_after_first}")
check("y=100 EP korunuyor", has_y100,
      f"Mevcut EPs: {eps_after_first}")
check("z=100 EP korunuyor", has_z100,
      f"Mevcut EPs: {eps_after_first}")

# İkinci kutu x=100'den başlasın — dominance olsaydı bu hiç denenemezdi
ep1_p = {
    "P0": Piece3D("P0", 100, 100, 100, 1, 10.0),
    "P1": Piece3D("P1", 100, 100, 100, 1, 10.0),
}
ep1b = ExtremePoints3D(300, 600, 300, heuristic='CP', truck=truck_1, piece_info=ep1_p)
ep1b.place_piece_3d("P0", (0, 0, 0, 100, 100, 100, (0, 0, 0)))
res = ep1b.find_best_position_3d("P1", 100, 100, 100, respect_gravity=True)
check("İkinci kutu için geçerli pozisyon bulunuyor", res is not None,
      f"Sonuç: {res}")
if res:
    rx, ry, rz, rw, rl, rh, rrot = res
    # CP heuristic daha fazla temas alanı için üste (z=100) veya yana (x=100)
    # koyabilir — ikisi de geçerli. Sadece çakışmadığını doğrula.
    cand_check = Placement3D(rx, ry, rz, rw, rl, rh, "P1", rrot, 0)
    col_check = check_collision_with_list(cand_check, ep1b.placements, ep1_p)
    check("İkinci kutunun pozisyonu çakışmasız (üst veya yan — ikisi de geçerli)",
          not col_check,
          f"Seçilen pozisyon: ({rx},{ry},{rz}) — {'çakışıyor' if col_check else 'geçerli'}")


# ─────────────────────────────────────────────────────────────────────────────
# HATA-2 TESTLERİ: EP Projeksiyon Aralık Kontrolü
# ─────────────────────────────────────────────────────────────────────────────
section("HATA-2: EP Projeksiyon Aralık Kontrolü")
print("""
  Eski davranış: _project_down_y gibi fonksiyonlar tek nokta (x,z) için
  blok arıyordu. Geniş engelleyici kutular gözden kaçabiliyordu.

  Yeni davranış: Yerleştirilen kutunun boyutlarını kullanarak aralık-aralık
  (interval vs interval) örtüşme kontrolü yapılıyor.
""")

# Senaryo: Geniş bir engel var, projeksiyon onu atlamamalı
# Kamyon: 400 geniş, 600 derin, 300 yüksek
truck_2 = Truck3D("T_400x600x300", 400, 600, 300, 99999, 5)
p_engel = Piece3D("ENGEL", 200, 100, 150, 1, 50.0)
p_test  = Piece3D("TEST",  200, 100, 150, 1, 50.0)
pi_2 = {"ENGEL": p_engel, "TEST": p_test}

ep2 = ExtremePoints3D(400, 600, 300, heuristic='BLF', truck=truck_2, piece_info=pi_2)

# Engel: x=0..200, y=0..100, z=0..150
ep2.place_piece_3d("ENGEL", (0, 0, 0, 200, 100, 150, (0, 0, 0)))

# TEST kutusu: 200x100x150 → EP motorundan pozisyon iste
res2 = ep2.find_best_position_3d("TEST", 200, 100, 150, respect_gravity=True)
check("Engelci kutu varlığında pozisyon bulunabiliyor", res2 is not None,
      f"Sonuç: {res2}")

if res2:
    rx, ry, rz, rw, rl, rh, rrot = res2
    # Çakışma olmamalı
    cand2 = Placement3D(rx, ry, rz, rw, rl, rh, "TEST", rrot, 0)
    collision, pair = has_collision([ep2.placements[0], cand2], pi_2)
    check("Yeni yerleşim engelle çakışmıyor", not collision,
          f"Çakışan çift: {pair}" if collision else f"Pozisyon: ({rx},{ry},{rz})")

# Aralık kontrolü doğruluğu: 2 yanyana kutu ardından 3. yerleşmeli
truck_2b = Truck3D("T_300x600x300", 300, 600, 300, 99999, 5)
pa = Piece3D("A", 100, 200, 100, 1, 10.0)
pb = Piece3D("B", 100, 200, 100, 1, 10.0)
pc = Piece3D("C", 100, 200, 100, 1, 10.0)
pi_2b = {"A": pa, "B": pb, "C": pc}

ep2b = ExtremePoints3D(300, 600, 300, heuristic='CP', truck=truck_2b, piece_info=pi_2b)
ep2b.place_piece_3d("A", (0, 0, 0, 100, 200, 100, (0, 0, 0)))
ep2b.place_piece_3d("B", (100, 0, 0, 100, 200, 100, (0, 0, 0)))
res2b = ep2b.find_best_position_3d("C", 100, 200, 100, respect_gravity=True)
check("Yan yana 2 kutu sonrası 3. kutu yerleşiyor", res2b is not None,
      f"Sonuç: {res2b}")
if res2b:
    check("3. kutunun x=200'de olması bekleniyor", res2b[0] == 200,
          f"Bulunan x={res2b[0]}")


# ─────────────────────────────────────────────────────────────────────────────
# HATA-3 TESTLERİ: Gravity Settle Multi-Pass
# ─────────────────────────────────────────────────────────────────────────────
section("HATA-3: Gravity Settle Multi-Pass Düzeltmesi")
print("""
  Eski davranış: Çakışma düzeltmesi tek geçişte yapılıyordu. Bir parçayı
  yukarı taşımak, onun üzerindeki başka parçayla yeni çakışma yaratabilirdi.

  Yeni davranış: Değişiklik olmayıncaya kadar (yakınsama) tekrarlanır.
  Maksimum N+1 iterasyon — sonsuz döngü riski yok.
""")

# Test-1: Basit zincir çakışma (A→B→C)
p_a = Placement3D(0, 0, 0,   100, 100, 50,  "A", (0,0,0), 0)
p_b = Placement3D(0, 0, 10,  100, 100, 50,  "B", (0,0,0), 0)  # A içinde
p_c = Placement3D(0, 0, 20,  100, 100, 50,  "C", (0,0,0), 0)  # A+B içinde

result3a = gravity_settle_placements([p_a, p_b, p_c])
z_vals = sorted([r.z for r in result3a])
check("Zincir çakışma (A→B→C): z değerleri [0,50,100]",
      z_vals == [0, 50, 100],
      f"Beklenen: [0,50,100], Bulunan: {z_vals}")

collision3a, pair3a = has_collision(result3a)
check("Zincir çakışma sonrası çakışma yok", not collision3a,
      f"Çakışan çift: {pair3a}" if collision3a else "Temiz")

# Test-2: Daha uzun zincir (5 parça)
zincir = [
    Placement3D(0, 0, i * 5, 80, 80, 50, f"P{i}", (0,0,0), 0)
    for i in range(5)
]
result3b = gravity_settle_placements(zincir)
z_expected = [0, 50, 100, 150, 200]
z_found    = sorted([r.z for r in result3b])
check("5 parça zincir düzeltmesi",
      z_found == z_expected,
      f"Beklenen: {z_expected}, Bulunan: {z_found}")

collision3b, pair3b = has_collision(result3b)
check("5 parça zincir sonrası çakışma yok", not collision3b,
      f"Çakışan çift: {pair3b}" if collision3b else "Temiz")

# Test-3: Birden fazla sütun (bağımsız)
col1 = [Placement3D(0,   0, i*5, 50, 50, 50, f"C1P{i}", (0,0,0), 0) for i in range(3)]
col2 = [Placement3D(100, 0, i*5, 50, 50, 50, f"C2P{i}", (0,0,0), 0) for i in range(3)]
result3c = gravity_settle_placements(col1 + col2)
collision3c, pair3c = has_collision(result3c)
check("İki bağımsız sütun sonrası çakışma yok", not collision3c,
      f"Çakışan çift: {pair3c}" if collision3c else "Temiz")


# ─────────────────────────────────────────────────────────────────────────────
# ENTEGRASYON TESTİ: FFD + Greedy gerçek senaryo
# ─────────────────────────────────────────────────────────────────────────────
section("ENTEGRASYON: Gerçek Senaryo — FFD ve Greedy")
print("""
  Gerçek bir yükleme senaryosunda FFD ve Greedy'nin
  düzeltilmiş modüllerle doğru çalışıp çalışmadığını test eder.
  Çakışma, yerleşmeyen parça sayısı ve doluluk oranı raporlanır.
""")

trucks = [
    Truck3D("KAMYON_7m",  240, 700, 260, 8000, 2),
    Truck3D("KAMYON_4m",  220, 400, 240, 4000, 3),
]
pieces = [
    Piece3D("Büyük",    120, 80,  100, 4,  120.0),
    Piece3D("Orta",     80,  60,  80,  6,  60.0),
    Piece3D("Küçük",    60,  40,  60,  8,  25.0),
    Piece3D("İnce",     100, 80,  40,  3,  30.0),
    Piece3D("Kare",     80,  80,  80,  5,  50.0),
]
piece_info_int = {p.id: p for p in pieces}
total_pieces = sum(p.quantity for p in pieces)

# FFD testi
t0 = time.time()
plan_ffd = ffd_3d_optimization(pieces, trucks, engine='EP')
ffd_time = time.time() - t0
ffd_placed = sum(len(b) for b in plan_ffd.bins)
ffd_util = plan_ffd.utilization

check(f"FFD: tüm parçalar yerleşti ({ffd_placed}/{total_pieces})",
      len(plan_ffd.unfitted_pieces or []) == 0,
      f"Yerleşmeyen: {len(plan_ffd.unfitted_pieces or [])}")
check(f"FFD: doluluk oranı > %40", ffd_util > 40,
      f"Oran: %{ffd_util:.1f}")

# FFD çakışma kontrolü
all_placements_ffd = [p for b in plan_ffd.bins for p in b]
col_ffd, pair_ffd = has_collision(all_placements_ffd, piece_info_int)
check("FFD: hiçbir yerleşimde çakışma yok", not col_ffd,
      f"Çakışan çift: {pair_ffd}" if col_ffd else "Temiz")

# FFD zemine basıyor mu?
below_zero_ffd = [p for p in all_placements_ffd if p.z < 0]
check("FFD: hiçbir parça yerden aşağıda değil", len(below_zero_ffd) == 0,
      f"Yerden aşağı: {len(below_zero_ffd)}")

# Greedy testi
t0 = time.time()
plan_gr = greedy_3d_optimization(pieces, trucks, engine='EP')
gr_time = time.time() - t0
gr_placed = sum(len(b) for b in plan_gr.bins)
gr_util = plan_gr.utilization

check(f"Greedy: tüm parçalar yerleşti ({gr_placed}/{total_pieces})",
      len(plan_gr.unfitted_pieces or []) == 0,
      f"Yerleşmeyen: {len(plan_gr.unfitted_pieces or [])}")
check(f"Greedy: doluluk oranı > %40", gr_util > 40,
      f"Oran: %{gr_util:.1f}")

all_placements_gr = [p for b in plan_gr.bins for p in b]
col_gr, pair_gr = has_collision(all_placements_gr, piece_info_int)
check("Greedy: hiçbir yerleşimde çakışma yok", not col_gr,
      f"Çakışan çift: {pair_gr}" if col_gr else "Temiz")


# ─────────────────────────────────────────────────────────────────────────────
# SONUÇ ÖZETİ
# ─────────────────────────────────────────────────────────────────────────────
section("SONUÇ ÖZETİ")

passed = sum(1 for _, ok in results if ok)
failed = sum(1 for _, ok in results if not ok)
total  = len(results)

print(f"\n  Toplam test  : {total}")
print(f"  ✅ Geçti     : {passed}")
print(f"  ❌ Başarısız : {failed}")

if failed == 0:
    print("""
  ════════════════════════════════════════════
  Tüm testler geçti!
  Düzeltilmiş dosyalar doğru çalışıyor.
  Sonraki 3 düzeltmeye geçebilirsiniz.
  ════════════════════════════════════════════""")
else:
    print(f"\n  Başarısız testler:")
    for name, ok in results:
        if not ok:
            print(f"    ✗ {name}")
    print("\n  Lütfen bu hataları bildirin.")

print(f"""
  Performans:
    FFD süresi  : {ffd_time:.3f}s  |  Doluluk: %{ffd_util:.1f}
    Greedy süresi: {gr_time:.3f}s  |  Doluluk: %{gr_util:.1f}
""")
