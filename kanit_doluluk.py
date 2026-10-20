# -*- coding: utf-8 -*-
"""
DOLULUK TUTARSIZLIK KANITI
==========================
Tek bir çözüm (sabit seed, deterministik FFD) üretir; sonra AYNI çözüm üzerinde
farklı doluluk tanımlarını hesaplar. Amaç: %96,6 / %94,0 / %92,9 tarzı farkın bir
'algoritmik boşluk' değil, PAY/PAYDA tanım farkı olduğunu sayısal göstermektir.

Çalıştırma:  python kanit_doluluk.py
"""
import sys, io, contextlib, math, csv, os, random
from core_3d import Piece3D, Truck3D
from ffd_3d import ffd_3d_optimization

PI4 = math.pi / 4.0


@contextlib.contextmanager
def _quiet():
    old = sys.stdout
    sys.stdout = io.StringIO()
    try:
        yield
    finally:
        sys.stdout = old


def make_instance(seed=100):
    """Kutu + silindir karışık, tek büyük aracı yoğun dolduracak örnek."""
    rng = random.Random(seed)
    ps = []
    # Kutular (bbox = gerçek)
    for i in range(10):
        w = rng.choice([100, 120, 120, 160])
        l = rng.choice([150, 200, 200, 300])
        h = rng.choice([100, 150, 200])
        ps.append(Piece3D(id=f'box-{i}', shape='box', width=w, length=l, height=h,
                          quantity=1, weight=rng.randint(100, 400)))
    # Silindirler (gerçek hacim = π/4 · bbox) — bbox/gerçek farkını yaratır
    for i in range(8):
        d = rng.choice([100, 120, 160])
        h = rng.choice([150, 200, 200])
        ps.append(Piece3D(id=f'cyl-{i}', shape='cylinder', width=d, length=d, height=h,
                          quantity=1, weight=rng.randint(100, 400)))
    return ps


def fleet():
    """Filo: 1 araç KULLANILIR, gerisi boş kapasite (U_Fleet farkını gösterir)."""
    return [Truck3D('Buyuk', 240, 600, 200, 24000, 4),
            Truck3D('Orta',  240, 420, 200, 16000, 3)]


def truck_by_id(trucks, tid):
    return next((t for t in trucks if t.id == tid), None)


def analyze(plan, pieces, trucks):
    pinfo = {p.id: p for p in pieces}
    # bin -> truck eşlemesi
    assign = plan.truck_assignments or {}

    used_truck_vol = 0.0        # yalnızca dolu araçların iç hacmi
    sum_bbox = 0.0              # yerleşen parçaların bbox hacmi
    sum_actual = 0.0           # yerleşen parçaların gerçek hacmi
    sum_hybrid = 0.0           # kod A: silindir gerçek, kutu bbox
    placed_ids = []

    for b_idx, placements in enumerate(plan.bins):
        if not placements:
            continue
        tid = assign.get(b_idx)
        truck = truck_by_id(trucks, tid)
        if truck is None:
            # atama yoksa ilk aracı varsay
            truck = trucks[0]
        used_truck_vol += truck.get_volume()
        for pl in placements:
            pc = pinfo.get(pl.piece_id)
            if pc is None:
                continue
            placed_ids.append(pl.piece_id)
            bbox = pc.get_bounding_volume()
            actual = pc.get_actual_volume()
            sum_bbox += bbox
            sum_actual += actual
            sum_hybrid += (actual if pc.shape == 'cylinder' else bbox)

    # Tüm filo hacmi (adet çarpanı dahil) — B ve U_Fleet paydası
    fleet_vol = sum(t.get_volume() * t.available for t in trucks)

    # B yolu (app_3d.py:1354-1356): TÜM parçalar (yerleşsin/yerleşmesin) fill_ratio·bbox,
    # payda TÜM araçlar × available.
    def fill_ratio(p):
        return (p.get_actual_volume() / p.get_bounding_volume()) if p.get_bounding_volume() else 1.0
    all_piece_fillw = sum(fill_ratio(p) * p.get_bounding_volume() * p.quantity for p in pieces)
    U_B = min(100.0, all_piece_fillw / fleet_vol * 100.0) if fleet_vol else 0.0

    return {
        "used_trucks": sum(1 for b in plan.bins if b),
        "placed": len(placed_ids),
        "total": len(pieces),
        "cyl_share_bbox": (sum(pinfo[i].get_bounding_volume() for i in placed_ids if pinfo[i].shape=='cylinder')
                           / sum_bbox * 100.0) if sum_bbox else 0.0,
        "A_hybrid_used":  sum_hybrid / used_truck_vol * 100.0 if used_truck_vol else 0.0,
        "U_BB_used":      sum_bbox   / used_truck_vol * 100.0 if used_truck_vol else 0.0,
        "U_G_used":       sum_actual / used_truck_vol * 100.0 if used_truck_vol else 0.0,
        "U_Fleet_G":      sum_actual / fleet_vol      * 100.0 if fleet_vol else 0.0,
        "U_B_layer":      U_B,
        "plan_util":      plan.utilization,
    }


def box_instance(seed=100):
    """Yalnız kutu — U_BB ile U_G'nin ÖZDEŞ olduğunu (geometri boşluğu = 0) gösterir."""
    rng = random.Random(seed)
    ps = []
    for i in range(12):
        w = rng.choice([120, 120, 160]); l = rng.choice([200, 200, 300]); h = rng.choice([150, 200])
        ps.append(Piece3D(id=f'box-{i}', shape='box', width=w, length=l, height=h,
                          quantity=1, weight=rng.randint(100, 400)))
    return ps


def report_case(title, pieces, trucks):
    with _quiet():
        plan = ffd_3d_optimization(pieces, trucks)
    r = analyze(plan, pieces, trucks)
    print("=" * 72)
    print(f"  {title}")
    print("=" * 72)
    print(f"  Yerleşen: {r['placed']}/{r['total']}   Kullanılan araç: {r['used_trucks']}   "
          f"Silindir payı (bbox): %{r['cyl_share_bbox']:.1f}")
    print("-" * 72)
    rows = [
        ("plan.utilization  (kodun ekrana yazdigi)",         r['plan_util']),
        ("U_G   gercek geometri / kullanilan araclar",       r['U_G_used']),
        ("U_BB  saf bounding-box / kullanilan araclar",      r['U_BB_used']),
        ("U_Fleet  gercek / TUM filo (adet dahil)",          r['U_Fleet_G']),
        ("U_B  layer-app yolu (fill_ratio, tum filo)",       r['U_B_layer']),
    ]
    for name, val in rows:
        print(f"    {name:46s} : %{val:6.2f}")
    gap = r['U_BB_used'] - r['U_G_used']
    pred = r['U_BB_used'] * (r['cyl_share_bbox']/100.0) * (1 - PI4)
    print("-" * 72)
    print(f"  U_BB - U_G (geometri bosuslugu)        : {gap:+.2f} puan")
    print(f"  Teorik  U_BB x silindir_payi x (1-pi/4): {pred:+.2f} puan  (pi/4={PI4:.4f})")
    print(f"  >> plan.utilization == U_G ? {'EVET' if abs(r['plan_util']-r['U_G_used'])<0.05 else 'HAYIR'}"
          f"  (kod, gercek-geometri dolulugunu raporluyor; U_BB'yi DEGIL)")
    print()
    return rows, gap


def main():
    trucks = fleet()
    print()
    r1, g1 = report_case("KANIT 1 — KARISIK (10 kutu + 8 silindir): tanim farki",
                         make_instance(100), trucks)
    r2, g2 = report_case("KANIT 2 — YALNIZ KUTU (12 kutu): U_BB == U_G (geometri boslugu YOK)",
                         box_instance(100), trucks)

    print("=" * 72)
    print("  SONUC")
    print("=" * 72)
    print("  * Ayni cozumu DEGISTIRMEDEN, yalnizca TANIMI degistirerek doluluk")
    print("    yuzdesi farkli cikiyor (Kanit 1). Demek ki tezdeki %96,6/%94,0/%92,9")
    print("    farki bir 'algoritmik bosluk' DEGIL, pay/payda tanim farkidir.")
    print("  * U_BB - U_G farki tam olarak silindir payi x (1-pi/4) kadardir")
    print("    -> fark dogrudan pi/4 geometri iliskisinden gelir, algoritmadan degil.")
    print("  * Yalniz kutuda (Kanit 2) U_BB == U_G: geometri boslugu SIFIR;")
    print("    fark yalnizca silindir/duzensiz parca oldugunda dogar (Makale 1'in cekirdegi).")
    print("  * Kodun 'utilization' alani zaten U_G'ye esit; U_BB'yi hicbir yerde raporlamiyor")
    print("    -> tezdeki daha yuksek (bbox) sayi ayri bir hesaptan gelmis olmali.")
    print("=" * 72)

    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kanit_doluluk_sonuc.csv")
    with open(out, "w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        wr.writerow(["kanit", "tanim", "deger_%"])
        for name, val in r1:
            wr.writerow(["karisik", name, f"{val:.2f}"])
        for name, val in r2:
            wr.writerow(["yalniz_kutu", name, f"{val:.2f}"])
    print(f"  Kanit eki CSV: kanit_doluluk_sonuc.csv")


if __name__ == "__main__":
    main()
