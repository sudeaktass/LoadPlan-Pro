# -*- coding: utf-8 -*-
"""
DOLULUK METRİKLERİ — Resmî Tanımlar
====================================
Bir yerleşim planı için farklı doluluk oranlarını AYRI AYRI hesaplar.
Hiçbiri diğerinin yerine kullanılmamalıdır; her sonuç hangi metriğin
kullanıldığı belirtilerek raporlanmalıdır.

Danışman raporu Bölüm 3.3: "Bu oranlardan biri diğerinin yerine
kullanılmamalıdır. Payda 'kullanılan araçlar' mı, 'mevcut tüm filo' mu
açıkça belirtilmelidir."

TANIMLAR
--------
U_BB     : Σ(yerleşen parçaların bounding-box hacmi) / Σ(KULLANILAN araç hacmi)
           Şekilden bağımsız; silindiri kapladığı kutu ile sayar.

U_G      : Σ(yerleşen parçaların gerçek geometrik hacmi) / Σ(KULLANILAN araç hacmi)
           Silindir için π·r²·h. Uygulamanın ana "Doluluk" göstergesi budur.

U_Fleet  : Σ(yerleşen parçaların gerçek hacmi) / Σ(MEVCUT TÜM filo hacmi × adet)
           Kullanılmayan araçlar da paydaya girer; filo planlama göstergesidir.

T_V      : Σ(tüm parçaların gerçek hacmi) / Σ(tüm filo hacmi)   — hacim sıkılığı
T_W      : Σ(tüm parçaların ağırlığı) / Σ(tüm filo kapasitesi)  — ağırlık sıkılığı

U_BB ile U_G arasındaki fark, ALGORİTMİK bir boşluk değildir; yalnızca
geometri temsilinden doğar. Yalnız kutulardan oluşan bir örnekte ikisi
birbirine eşittir.
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from core_3d import piece_used_volume  # noqa: E402  (tek resmî hacim tanımı)


def _kullanilan_arac_hacmi(plan, trucks):
    """Yalnızca içinde parça bulunan araçların toplam hacmi."""
    atama = plan.truck_assignments or {}
    toplam = 0.0
    for b_idx, yerlesimler in enumerate(plan.bins):
        if not yerlesimler:
            continue
        tid = atama.get(b_idx)
        truck = next((t for t in trucks if t.id == tid), None) or trucks[0]
        toplam += truck.get_volume()
    return toplam


def _filo_hacmi(trucks):
    """Mevcut tüm filonun hacmi (adet çarpanı dahil)."""
    return sum(t.get_volume() * t.available for t in trucks)


def hesapla(plan, pieces, trucks):
    """
    Bir plan için tüm doluluk metriklerini birlikte döndürür.

    Dönen sözlükteki her anahtar, yukarıdaki TANIMLAR bölümünde açıklanan
    metriğe karşılık gelir. Yüzde cinsindendir (0-100).
    """
    pinfo = {p.id: p for p in pieces}

    sum_bbox = 0.0        # yerleşen parçaların bounding-box hacmi
    sum_gercek = 0.0      # yerleşen parçaların gerçek hacmi
    yerlesen = 0

    for yerlesimler in plan.bins:
        for pl in yerlesimler:
            pc = pinfo.get(pl.piece_id)
            if pc is None:
                continue
            yerlesen += 1
            sum_bbox += pc.get_bounding_volume()
            sum_gercek += piece_used_volume(pl, pinfo)

    kullanilan = _kullanilan_arac_hacmi(plan, trucks)
    filo = _filo_hacmi(trucks)

    toplam_adet = sum(p.quantity for p in pieces)
    tum_gercek = sum(p.get_actual_volume() * p.quantity for p in pieces)
    tum_agirlik = sum(p.weight * p.quantity for p in pieces)
    filo_kapasite = sum(t.capacity * t.available for t in trucks)

    def oran(pay, payda):
        return (pay / payda * 100.0) if payda else 0.0

    return {
        "U_BB": round(oran(sum_bbox, kullanilan), 4),
        "U_G": round(oran(sum_gercek, kullanilan), 4),
        "U_Fleet": round(oran(sum_gercek, filo), 4),
        "T_V": round(tum_gercek / filo, 4) if filo else 0.0,
        "T_W": round(tum_agirlik / filo_kapasite, 4) if filo_kapasite else 0.0,
        "kullanilan_arac": sum(1 for b in plan.bins if b),
        "yerlesen_parca": yerlesen,
        "toplam_parca": toplam_adet,
        "yerlesen_oran": round(yerlesen / toplam_adet, 4) if toplam_adet else 0.0,
        "kullanilan_arac_hacmi_cm3": kullanilan,
        "filo_hacmi_cm3": filo,
    }


def gecerlilik_kontrolu(m):
    """
    Metriklerin mantıklı olup olmadığını kontrol eder.
    U_BB her zaman U_G'ye eşit veya ondan büyük olmalıdır (bounding-box
    gerçek hacmi kapsar). Aksi durum kod hatasına işaret eder.
    """
    uyarilar = []
    if m["U_BB"] + 1e-6 < m["U_G"]:
        uyarilar.append(f"U_BB ({m['U_BB']}) < U_G ({m['U_G']}) — beklenmedik")
    if m["U_G"] > 100.0 + 1e-6:
        uyarilar.append(f"U_G %100'ü aşıyor ({m['U_G']})")
    if m["U_Fleet"] > m["U_G"] + 1e-6:
        uyarilar.append("U_Fleet, U_G'den büyük — payda hatası olabilir")
    return uyarilar
