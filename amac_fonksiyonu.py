# -*- coding: utf-8 -*-
"""
Ortak amaç fonksiyonu — TEK RESMÎ KAYNAK (3. adım)
===================================================
Beş metasezgisel (Tabu, SA, GA, Island GA, Monte Carlo) aynı hedefi
optimize eder. Yapıcı algoritmalar (FFD, Greedy, Layer Building) açgözlü
olduğu için bu fonksiyonu kullanmaz.

DÜŞÜK = DAHA İYİ.

╔══════════════════════════════════════════════════════════════════════╗
║  uygunluk = CEZA_GECERSIZ·ihlal  +  AGIRLIK_ARAC·N  +  sürekli       ║
╚══════════════════════════════════════════════════════════════════════╝

Üç DÜZEY var ve üstteki alttakini HER ZAMAN yener:

  1) ihlal  (tam sayı)  — Deb (2000) kısıt-baskın kuralı
       yerleşmeyen parça + filo tavanını aşan araç + dingil yükü ihlali.
       Deb'in üç kuralı: (i) iki geçerli çözümden amacı iyi olan,
       (ii) geçerli ile geçersizden geçerli olan, (iii) iki geçersizden
       ihlali küçük olan seçilir. Ceza parametresi gerekmez; burada
       ihlal sayısı doğrudan en üst düzeyde durduğu için aynı sıralama
       elde edilir.

  2) N  (tam sayı)      — K1'in BİRİNCİ ölçütü: araç (sefer) sayısı
       AGIRLIK_ARAC > sürekli terimin üst sınırı (1,0) olduğu için bir
       araç farkı, alttaki bütün ölçütlerin toplamından pahalıdır.
       Yani denge ya da doluluk uğruna fazladan sefer AÇILMAZ.

  3) sürekli ∈ [0, 1]   — araç sayısı EŞİTKEN sıralayan ölçütler
       a) doluluk  : Falkenauer (1996) biçimi,  1 − Σ(uᵢ)^k / N
       b) öncelik  : yumuşak kısıt (Bortfeldt & Gehring 2001)
       c) ağırlık merkezi : yumuşak kısıt (Bortfeldt & Wäscher 2013)

NEDEN BÖYLE — kaynaklar
───────────────────────
Falkenauer (1996), araç sayısını DOĞRUDAN amaç yapmanın "son derece
dostça olmayan bir manzara" ürettiğini, eniyi-altı çözümlerin hepsinin
aynı maliyeti verdiğini ve problemi "samanlıkta iğne"ye çevirdiğini
gösterir. Çözümü: Σ(Fᵢ/C)^k / N biçiminde, k ≤ 2 için özgün amaçla AYNI
eniyilere sahip bir fonksiyon.

⚠ ÖNEMLİ: Falkenauer'in k ≤ 2 kanıtı TÜM KUTULARIN AYNI KAPASİTEDE
olduğunu varsayar. Bizim filomuz heterojendir ve kanıt orada TUTMAZ.
Sayısal karşı örnek (22 Ekim 2026'da ölçüldü, test dosyasında da var):
  yük 100 birim · 1 büyük araç (hacim 1000) → u=0,10 → f = 0,010
                 · 2 küçük araç (hacim  55) → u=0,91 → f = 0,826
Yani Falkenauer terimi TEK BAŞINA bırakılsaydı iki araç açmayı tercih
ederdi. Bu yüzden araç sayısı AYRI ve ÜSTTE bir düzey olarak durur;
Falkenauer terimi yalnızca araç sayısı eşitken yol gösterir — düz
manzara sorunu da böylece çözülür.

Ölçekler ve ağırlıklar
──────────────────────
Marler & Arora (2004): ağırlıklı toplamda ağırlıklar ancak amaçlar
normalize edilmişse anlamlıdır; ölçekleri farklı terimleri doğrudan
toplamak ağırlıkları anlamsızlaştırır. Bu yüzden sürekli düzeydeki üç
terim de [0,1] aralığına çekilir ve ağırlıkları 1'e toplanır.

Bischoff (2006) ağırlıkları tahmin etmez, rastgele aramayla ARAR. Buradaki
varsayılan ağırlıklar başlangıç değeridir; aranarak iyileştirilebilir
(bkz. AGIRLIKLAR).

Osyczka'nın (1984) hiyerarşik yöntemi, bir üst ölçütün %δ kadar
kötüleşmesine izin vererek katı sözlükselin kırılganlığını giderir.
Burada üst iki düzey TAM SAYI olduğu için buna gerek kalmıyor: tam sayı
düzeylerde katı hiyerarşi kurulabiliyor, sürekli düzeyde ise zaten
ağırlıklı toplam kullanılıyor.

Kaynakça
────────
  Falkenauer, E. (1996). A hybrid grouping genetic algorithm for bin
    packing. Journal of Heuristics 2(1), 5-30.
  Deb, K. (2000). An efficient constraint handling method for genetic
    algorithms. Comput. Methods Appl. Mech. Engrg. 186(2-4), 311-338.
  Marler, R.T. & Arora, J.S. (2004). Survey of multi-objective
    optimization methods for engineering. Struct. Multidisc. Optim.
    26(6), 369-395.
  Bischoff, E.E. (2006). Three-dimensional packing of items with limited
    load bearing strength. EJOR 168(3), 952-966.
  Bortfeldt, A. & Gehring, H. (2001). A hybrid genetic algorithm for the
    container loading problem. EJOR 131(1), 143-161.
  Bortfeldt, A. & Wäscher, G. (2013). Constraints in container loading —
    A state-of-the-art review. EJOR 229(1), 1-20.
  Trivella, A. & Pisinger, D. (2016). The load-balanced multi-dimensional
    bin-packing problem. Computers & OR 74, 152-164.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

# ─────────────────────────────────────────────────────────────────────────────
# Ayarlar
# ─────────────────────────────────────────────────────────────────────────────

FALKENAUER_K = 2.0
"""Falkenauer'in k üsteli. k=2 iyi sonuç verir; büyüğü erken yakınsatır."""

AGIRLIK_COG_TOL = 2.0
"""Ağırlık merkezi TOLERANSINI aşan araç oranının bedeli, [0,1] × bu sayı.

Bortfeldt & Wäscher (2013): ağırlık dağılımı yumuşak bir kısıttır, ama
literatürde "ağırlık merkezi belli bir mesafeyi AŞMAMALI" biçiminde
kurulur. Bizde tolerans `core_3d`te tek yerde tanımlı:
  COG_LATERAL_TOL = %10 · COG_LONG_TOL = %15 · COG_VERTICAL_MAX = %60

Bu düzey, sürekli düzeyin (üst sınır 1,0) ÜSTÜNDE durur: yani doluluk
ya da öncelik uğruna tolerans dışına ÇIKILMAZ. Araç sayısının ise
ALTINDADIR: dengeyi düzeltmek için fazladan sefer açılmaz."""

AGIRLIK_ARAC = 10.0
"""Bir araç farkının bedeli. Altındaki iki düzeyin üst sınırı
AGIRLIK_COG_TOL + 1,0 = 3,0 olduğundan 10 > 3 koşulu K1'in birinci
ölçütünü KESİN yapar."""

AGIRLIKLAR = {
    "doluluk":  0.60,   # Falkenauer terimi
    "oncelik":  0.25,   # yumuşak öncelik (boşaltma sırası)
    "cog":      0.15,   # ağırlık merkezi sapması
}
"""Sürekli düzeyin ağırlıkları; toplamı 1,0 olmalıdır (test ediliyor).
Bischoff (2006) bu tür ağırlıkları rastgele aramayla belirliyor — bunlar
başlangıç değeri, ileride aranarak iyileştirilebilir."""

DINGIL_KISITI = True
"""Dingil yükü ihlali geçersizlik sayılsın mı (Deb düzeyi). Verisi
eksik olan araçlarda kontrol yapılamaz; o araçlar ihlal SAYILMAZ."""


# ─────────────────────────────────────────────────────────────────────────────
# Parçalar
# ─────────────────────────────────────────────────────────────────────────────

def _arac_dolulugu(yerlesimler, truck, piece_info) -> float:
    """Tek aracın hacim doluluğu, [0, 1]."""
    from core_3d import piece_used_volume
    payda = float(truck.get_volume())
    if payda <= 0:
        return 0.0
    pay = sum(piece_used_volume(p, piece_info) for p in yerlesimler)
    return max(0.0, min(1.0, pay / payda))


def falkenauer_terimi(doluluklar: Sequence[float],
                      k: float = FALKENAUER_K) -> float:
    """Σ(uᵢ)^k / N — YÜKSEK = daha iyi, [0, 1].

    Falkenauer (1996): araç sayısını tek başına saymak düz bir arama
    uzayı verir; bu biçim iyi dolmuş araçları ödüllendirerek eğim sağlar.
    Burada YALNIZCA araç sayısı eşitken kullanılır (bkz. modül başlığı).
    """
    if not doluluklar:
        return 0.0
    return sum(u ** k for u in doluluklar) / len(doluluklar)


def _oncelik_normalize(bins_list, piece_info, trucks,
                       truck_assignments) -> float:
    """Öncelik bölgesi ihlali oranı, [0, 1].

    Bortfeldt & Gehring (2001) ayrımında bu YUMUŞAK bir kısıttır: amaç
    fonksiyonunda ele alınır. Bizde öncelik "kapıya yakın dursun"
    demektir — bir ürünü hiç yüklememektense yanlış yere koymak yeğdir,
    bu yüzden yerleşmeyen parçanın (geçersizlik düzeyi) ALTINDADIR.
    """
    from priority_utils import PRIORITY_PENALTY, priority_violation_penalty

    oncelikli = 0
    for yerlesimler in bins_list:
        for p in yerlesimler:
            parca = piece_info.get(p.piece_id)
            prio = getattr(parca, "priority", None) if parca else None
            if prio:
                oncelikli += 1
    if oncelikli == 0:
        return 0.0
    ihlal = priority_violation_penalty(
        bins_list, piece_info, trucks, truck_assignments) / PRIORITY_PENALTY
    return max(0.0, min(1.0, ihlal / oncelikli))


def _cog_normalize(bins_list, piece_info, trucks, truck_assignments) -> float:
    """Araç başına CoG sapma skorunun ortalaması, [0, 1].

    Bortfeldt & Wäscher (2013): ağırlık dağılımı kısıtları literatürde
    YUMUŞAK kısıttır. Ölçü `core_3d.cog_penalty_score` — eksen ağırlıkları
    orada tek yerde tanımlıdır.
    """
    from core_3d import cog_penalty_score

    skorlar = []
    for bid, yerlesimler in enumerate(bins_list):
        if not yerlesimler:
            continue
        truck = next((t for t in trucks
                      if t.id == truck_assignments.get(bid)), None)
        if truck is None:
            continue
        skorlar.append(min(1.0, cog_penalty_score(
            yerlesimler, piece_info, truck)))
    return sum(skorlar) / len(skorlar) if skorlar else 0.0


def cog_tolerans_ihlali(bins_list, piece_info, trucks,
                        truck_assignments) -> Tuple[int, int]:
    """Ağırlık merkezi toleransını aşan araç sayısı.

    Tolerans ölçütü `core_3d.check_weight_balance` — üç eksen birden
    (yanal %10, boylamsal %15, dikey %60). Eşikler orada tek yerde
    tanımlı; burada kopyalanmaz.

    Returns:
        (ihlal_eden_arac, yuklu_arac)
    """
    from core_3d import check_weight_balance

    ihlal = 0
    yuklu = 0
    for bid, yerlesimler in enumerate(bins_list):
        if not yerlesimler:
            continue
        truck = next((t for t in trucks
                      if t.id == truck_assignments.get(bid)), None)
        if truck is None:
            continue
        yuklu += 1
        yanal, boylamsal, dikey, _ = check_weight_balance(
            yerlesimler, piece_info, truck)
        if not (yanal and boylamsal and dikey):
            ihlal += 1
    return ihlal, yuklu


def dingil_ihlali(bins_list, piece_info, trucks, truck_assignments) -> int:
    """Dingil yükü sınırını aşan araç sayısı.

    Verisi eksik olan araçta kontrol YAPILAMAZ; tahmin yürütülmez ve
    ihlal sayılmaz (`kontrol_edildi == False`).
    """
    if not DINGIL_KISITI:
        return 0
    try:
        from dingil_yuku import arac_dingil_raporu, cm_to_mm_cg
    except Exception:                      # modül yoksa sessizce atla
        return 0

    sayi = 0
    for bid, yerlesimler in enumerate(bins_list):
        if not yerlesimler:
            continue
        truck = next((t for t in trucks
                      if t.id == truck_assignments.get(bid)), None)
        eslesme = getattr(truck, "eslesme", None) if truck else None
        if eslesme is None:
            continue
        yukler = [((getattr(piece_info.get(p.piece_id), "weight", 0) or 0),
                   cm_to_mm_cg(p.y, p.length)) for p in yerlesimler]
        sonuc = arac_dingil_raporu(eslesme, yukler)
        if sonuc.kontrol_edildi and not sonuc.gecerli:
            sayi += 1
    return sayi


# ─────────────────────────────────────────────────────────────────────────────
# ANA GİRİŞ
# ─────────────────────────────────────────────────────────────────────────────

def amac(bins_list, truck_assignments, trucks, piece_info,
         unplaced: int = 0, overflow_bins: int = 0) -> Tuple[float, float]:
    """Ortak amaç fonksiyonu. DÜŞÜK = DAHA İYİ.

    Returns:
        (uygunluk, doluluk_yuzde) — doluluk yüzde olarak (0-100), eski
        arayüzle aynı; çağıranlar bunu rapora basıyor.
    """
    tid = {t.id: t for t in trucks}

    doluluklar: List[float] = []
    toplam_hacim = 0.0
    dolu_hacim = 0.0
    from core_3d import piece_used_volume
    for bid, yerlesimler in enumerate(bins_list):
        if not yerlesimler:                 # boş araç kullanılmış sayılmaz
            continue
        truck = tid.get(truck_assignments.get(bid))
        if truck is None:
            continue
        doluluklar.append(_arac_dolulugu(yerlesimler, truck, piece_info))
        toplam_hacim += float(truck.get_volume())
        dolu_hacim += sum(piece_used_volume(p, piece_info)
                          for p in yerlesimler)

    n_arac = len(doluluklar)
    doluluk_yuzde = (dolu_hacim / toplam_hacim * 100.0) if toplam_hacim else 0.0

    # ── 3. düzey: sürekli ölçütler, hepsi [0,1] ─────────────────────────
    surekli = (
        AGIRLIKLAR["doluluk"] * (1.0 - falkenauer_terimi(doluluklar))
        + AGIRLIKLAR["oncelik"] * _oncelik_normalize(
            bins_list, piece_info, trucks, truck_assignments)
        + AGIRLIKLAR["cog"] * _cog_normalize(
            bins_list, piece_info, trucks, truck_assignments)
    )

    # ── 2,5. düzey: ağırlık merkezi TOLERANSI ───────────────────────────
    # Standartların dışına çıkmak, doluluk ya da öncelik kazancıyla
    # satın alınamaz; ama bunu düzeltmek için fazladan araç da açılmaz.
    cog_ihlal, cog_yuklu = cog_tolerans_ihlali(
        bins_list, piece_info, trucks, truck_assignments)
    cog_tol_norm = (cog_ihlal / cog_yuklu) if cog_yuklu else 0.0

    # ── 1. düzey: geçersizlik (Deb) ─────────────────────────────────────
    ihlal = (int(unplaced) + int(overflow_bins)
             + dingil_ihlali(bins_list, piece_info, trucks, truck_assignments))

    # Geçersizlik cezası, altındaki HER ŞEYİN toplamından büyük olmalı.
    tavan_arac = max(len(trucks), len(bins_list), n_arac) + 1
    ceza_gecersiz = AGIRLIK_ARAC * tavan_arac + AGIRLIK_COG_TOL + 1.0

    uygunluk = (ceza_gecersiz * ihlal
                + AGIRLIK_ARAC * n_arac
                + AGIRLIK_COG_TOL * cog_tol_norm
                + surekli)
    return uygunluk, doluluk_yuzde


def plan_uygunlugu(plan, trucks, piece_info) -> float:
    """HAZIR bir planın ortak amaç değeri. DÜŞÜK = DAHA İYİ.

    Algoritmalar arama sırasında aday çözümleri `packing_objective` ile
    puanlar; ama ellerindeki HAZIR planları (başlangıç tohumu, çok
    başlangıçlı taramanın aşama sonuçları, karşılaştırma) puanlamak için
    her modül kendi ölçüsünü kullanıyordu:
      * monte_carlo_3d  → `plan.utilization` (yüzde)
      * multistart_sa_3d→ `plan.utilization` (yüzde)
    İkisi de aramanın optimize ettiği değerden FARKLI bir ölçüydü; bu
    yüzden seçimler amaç fonksiyonuyla çelişebiliyordu (örn. doluluğu
    yüksek ama daha ÇOK araç kullanan plan seçilebiliyordu — K1'e aykırı).

    Bu fonksiyon o ölçüyü tek yere topluyor. `core_3d.packing_objective`
    üzerinden gider; böylece YENI_AMAC bayrağı burada da geçerlidir.

    YERLEŞMEYEN PARÇA SAYISI PLANDAN HESAPLANIR, `unfitted_pieces`
    alanından OKUNMAZ. Nedeni ölçümle bulundu (22 Ekim 2026): bu alanı
    yalnız bazı algoritmalar dolduruyor —
      dolduranlar : FFD, Greedy, Layer Building, GA, Island GA
      doldurmayan : Tabu, SA, Monte Carlo, Multi-Start SA
    Alana güvenilirse doldurmayan algoritmaların düşen parçaları SIFIR
    sayılıyor ve amaç skorları haksız yere iyi çıkıyordu (BR7, 110 parça:
    FFD 90/110 → 472,2 · Tabu 84/110 → 12,3 — yani daha AZ parça
    yerleştiren plan daha iyi görünüyordu). Toplam adet ile yerleşen
    arasındaki fark algoritmadan bağımsızdır.

    Plan yoksa/boşsa +sonsuz döner (en kötü).
    """
    from core_3d import packing_objective

    if plan is None or not getattr(plan, "bins", None):
        return float("inf")
    bins_list = list(plan.bins)
    if not any(bins_list):
        return float("inf")

    toplam_adet = sum(int(getattr(p, "quantity", 1) or 1)
                      for p in piece_info.values())
    yerlesen = sum(len(b) for b in bins_list)
    yerlesmeyen = max(0, toplam_adet - yerlesen)

    uygunluk, _ = packing_objective(
        bins_list,
        getattr(plan, "truck_assignments", {}) or {},
        trucks,
        piece_info,
        unplaced=yerlesmeyen,
        overflow_bins=0,
    )
    return uygunluk


def dokum(bins_list, truck_assignments, trucks, piece_info,
          unplaced: int = 0, overflow_bins: int = 0) -> Dict[str, float]:
    """Amaç fonksiyonunun bileşenleri — deney ve hata ayıklama için.

    Amaç değerini DEĞİŞTİRMEZ; yalnızca parçalarını görünür kılar.
    """
    tid = {t.id: t for t in trucks}
    doluluklar = []
    for bid, yerlesimler in enumerate(bins_list):
        if not yerlesimler:
            continue
        truck = tid.get(truck_assignments.get(bid))
        if truck is not None:
            doluluklar.append(_arac_dolulugu(yerlesimler, truck, piece_info))

    uygunluk, doluluk_yuzde = amac(bins_list, truck_assignments, trucks,
                                   piece_info, unplaced, overflow_bins)
    cog_ihlal, cog_yuklu = cog_tolerans_ihlali(
        bins_list, piece_info, trucks, truck_assignments)
    return {
        "uygunluk": uygunluk,
        "arac_sayisi": float(len(doluluklar)),
        "doluluk_yuzde": doluluk_yuzde,
        "cog_tolerans_disi_arac": float(cog_ihlal),
        "cog_tolerans_disi_oran": (cog_ihlal / cog_yuklu) if cog_yuklu else 0.0,
        "falkenauer": falkenauer_terimi(doluluklar),
        "oncelik_norm": _oncelik_normalize(
            bins_list, piece_info, trucks, truck_assignments),
        "cog_norm": _cog_normalize(
            bins_list, piece_info, trucks, truck_assignments),
        "yerlesmeyen": float(unplaced),
        "tasma": float(overflow_bins),
        "dingil_ihlali": float(dingil_ihlali(
            bins_list, piece_info, trucks, truck_assignments)),
    }
