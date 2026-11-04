# -*- coding: utf-8 -*-
"""
Yükleme sırası — TEK RESMÎ KAYNAK
==================================
Operatörün ürünleri hangi sırayla yükleyeceği. Sürücü talimatı (PDF),
Excel "Yükleme Talimatı" sayfası ve 3B görsel AYNI numarayı gösterir;
sıralama mantığı burada tek yerde yaşar.

(Daha önce bu kural iki ayrı yerde kopyalanmıştı: reports.py içinde hem
`_compute_loading_order` hem de Excel sayfasının kendi `sorted(...)`
çağrısı. Aynı plan için iki farklı numara çıkma riski vardı.)

EKSEN KONVANSİYONU
  Kapı Y = maks (uzunluk) tarafındadır. Y = 0 ön duvar, yani KAPIYA EN
  UZAK nokta. Yükleme kapıdan yapıldığı için ilk ürün en dibe gider.

KURAL (öncelik sırasıyla)
  1) Y artan  — kapıdan en uzak sıradan başla
  2) Z artan  — o sıranın alt katmanı önce, üstü hemen ardından
  3) X artan  — aynı Y+Z düzeyinde soldan sağa (eşitlik bozucu)

Sonuç LIFO'dur: 1 numara kapıdan en uzak ürün, son numara kapıya en
yakın (öncelikli) ürün. Boşaltmada ters sırayla çıkar.

NOT — ilerisi için:
  Bu sıralama geometrik ve belirlenimcidir; her adımda parçanın fiilen
  ERİŞİLEBİLİR olduğunu kanıtlamaz. Ramos, Oliveira & Lopes (2016, ITOR
  23:215-238) "fiziksel yerleştirme sırası" algoritması bunu statik denge
  ve yükleme verimliliği kısıtlarıyla birlikte çözer. Oraya geçildiğinde
  DEĞİŞTİRİLECEK TEK YER BURASIDIR.
"""

from __future__ import annotations

from typing import Any, List, Sequence, Tuple

KURAL_METNI = (
    "Yükleme sırası: kapıdan EN UZAK sıranın (ön duvar, Y=0) alt katmanı "
    "önce, sonra üstü, sonra bir sıra kapıya doğru. "
    "1 numara = kapıdan en uzak ürün · son numara = kapıya en yakın ürün."
)


def _al(yerlesim: Any, alan: str, varsayilan: float = 0) -> float:
    """Yerleşim hem dataclass (Placement3D) hem sözlük olabilir."""
    if hasattr(yerlesim, alan):
        return getattr(yerlesim, alan)
    if hasattr(yerlesim, "get"):
        return yerlesim.get(alan, varsayilan)
    return varsayilan


def _anahtar(yerlesim: Any) -> Tuple[float, float, float]:
    return (_al(yerlesim, "y"), _al(yerlesim, "z"), _al(yerlesim, "x"))


def sirali(yerlesimler: Sequence[Any]) -> List[Tuple[int, Any]]:
    """[(sıra_no, yerleşim), ...] — yükleme sırasına göre artan.

    Tabloları doğrudan bu sırayla basmak için.
    """
    return [(no, y) for no, y in
            enumerate(sorted(yerlesimler, key=_anahtar), start=1)]


def sira_numaralari(yerlesimler: Sequence[Any]) -> List[int]:
    """Girdi sırasını koruyarak her yerleşimin sıra numarası (1'den başlar).

    Döndürülen listenin i. elemanı, yerlesimler[i]'nin numarasıdır.
    """
    sirali_indeksler = sorted(range(len(yerlesimler)),
                              key=lambda i: _anahtar(yerlesimler[i]))
    numaralar = [0] * len(yerlesimler)
    for no, i in enumerate(sirali_indeksler, start=1):
        numaralar[i] = no
    return numaralar
