# -*- coding: utf-8 -*-
"""
Doluluk ölçüleri — TEK RESMÎ KAYNAK (karar R-a)
================================================
Arayüz ve raporlar doluluk formülünü KENDİ HESAPLAMAZ; bu modülü çağırır.
Böylece aynı plan için iki farklı yüzde çıkmaz.

Ölçüler:
  U_G  (ana, hacim)    = Σ gerçek parça hacmi ÷ Σ kullanılan araçların iç hacmi
                         Gerçek hacim `core_3d.piece_used_volume` ile alınır
                         (silindirde πr²h). BU TANIM DEĞİŞMEZ — 4 Eylül kararı.
  U_BB (ikincil, hacim)= Σ parçaların DIŞ KUTU hacmi ÷ Σ iç hacim
  U_W  (ağırlık)       = Σ yük kütlesi ÷ Σ kullanılan araçların faydalı yükü

Bağlayıcı ölçü: U_G ile U_W'den BÜYÜK olanın adı ("Hacim" / "Ağırlık").
Hangisi aracı önce doldurduğunu söyler.

Filo toplamı, araç oranlarının ORTALAMASI DEĞİLDİR; toplamların oranıdır
(Σ pay ÷ Σ payda). Heterojen filoda ikisi ayrışır, bu yüzden ortalama ve
en düşük değer AYRICA raporlanır.

Kurallar:
  * Hiç yük almamış araç "kullanılan araç" sayılmaz, paydaya girmez.
  * Faydalı yük bilinmiyorsa (eski tip araç kaydı) U_W None'dır → arayüzde
    "—" gösterilir. Sıfır gösterilmez, tahmin yapılmaz.
  * Palet darası: hazır palet seçildiğinde paletin boş ağırlığı zaten
    parçanın ağırlığına EKLENİR (bkz. app_3d._palet_render). Ayrı bir alan
    yoktur, bu yüzden `piece.weight` toplandığında dara BİR KEZ sayılır.

Dayanak: Santén & Rogerson 2018 (doluluk = gereken kapasite ÷ mevcut
kapasite; ağırlık ve hacim ayrı ölçülür) · Mackie & Harding 1982 (yoğun
yükte ağırlık, hafif-hacimli yükte hacim önce dolar) · araç başına
raporlama: Cai ve ark. 2026, Paquay ve ark. 2018, Hao ve ark. 2026.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

BAGLAYICI_HACIM = "Hacim"
BAGLAYICI_AGIRLIK = "Ağırlık"

ACIKLAMA_NOTU = ("Hacim doluluğu gerçek parça hacmiyle, ağırlık doluluğu "
                 "faydalı yüke göre hesaplanır.")


# ─────────────────────────────────────────────────────────────────────────────
# Araç başına
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class AracDoluluk:
    """Tek bir aracın (çekici + dorse ya da eski tip araç) doluluk ölçüleri."""
    etiket: str = ""
    gercek_hacim: float = 0.0          # Σ piece_used_volume (silindir: πr²h)
    dis_kutu_hacim: float = 0.0        # Σ bounding-box hacmi
    arac_hacim: float = 0.0            # aracın iç hacmi (payda)
    yuk_kg: float = 0.0                # palet darası DÂHİL
    faydali_yuk_kg: Optional[float] = None   # bilinmiyorsa None
    bos_agirlik_kg: float = 0.0        # çekici + dorse boş ağırlığı
    parca_sayisi: int = 0

    @property
    def u_g(self) -> Optional[float]:
        """Hacim doluluğu [0, 1]. Payda sıfırsa None."""
        if self.arac_hacim <= 0:
            return None
        return self.gercek_hacim / self.arac_hacim

    @property
    def u_bb(self) -> Optional[float]:
        """Dış kutu hacmiyle doluluk (literatürle karşılaştırma için)."""
        if self.arac_hacim <= 0:
            return None
        return self.dis_kutu_hacim / self.arac_hacim

    @property
    def u_w(self) -> Optional[float]:
        """Ağırlık doluluğu [0, 1]. Faydalı yük bilinmiyorsa None."""
        if not self.faydali_yuk_kg or self.faydali_yuk_kg <= 0:
            return None
        return self.yuk_kg / self.faydali_yuk_kg

    @property
    def baglayici(self) -> Optional[str]:
        """Aracı önce hangisi dolduruyor: "Hacim" mi "Ağırlık" mı?

        U_W bilinmiyorsa karşılaştırma yapılamaz → None (arayüzde "—").
        """
        g, w = self.u_g, self.u_w
        if g is None and w is None:
            return None
        if w is None:
            return BAGLAYICI_HACIM
        if g is None:
            return BAGLAYICI_AGIRLIK
        return BAGLAYICI_AGIRLIK if w > g else BAGLAYICI_HACIM


# ─────────────────────────────────────────────────────────────────────────────
# Plan düzeyi
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class PlanDoluluk:
    """Bütün planın doluluk raporu."""
    araclar: List[AracDoluluk] = field(default_factory=list)

    # ── Toplam oranlar: Σ pay ÷ Σ payda (ortalama DEĞİL) ────────────────
    @property
    def u_g(self) -> Optional[float]:
        payda = sum(a.arac_hacim for a in self.araclar)
        if payda <= 0:
            return None
        return sum(a.gercek_hacim for a in self.araclar) / payda

    @property
    def u_bb(self) -> Optional[float]:
        payda = sum(a.arac_hacim for a in self.araclar)
        if payda <= 0:
            return None
        return sum(a.dis_kutu_hacim for a in self.araclar) / payda

    @property
    def u_w(self) -> Optional[float]:
        """Faydalı yükü BİLİNEN araçlar üzerinden toplam oran.

        Bilinmeyen araçlar hem paya hem paydaya girmez; hiçbiri
        bilinmiyorsa None.
        """
        bilinen = [a for a in self.araclar
                   if a.faydali_yuk_kg and a.faydali_yuk_kg > 0]
        if not bilinen:
            return None
        return (sum(a.yuk_kg for a in bilinen)
                / sum(a.faydali_yuk_kg for a in bilinen))

    @property
    def baglayici(self) -> Optional[str]:
        g, w = self.u_g, self.u_w
        if g is None and w is None:
            return None
        if w is None:
            return BAGLAYICI_HACIM
        if g is None:
            return BAGLAYICI_AGIRLIK
        return BAGLAYICI_AGIRLIK if w > g else BAGLAYICI_HACIM

    # ── Araç başına ek ölçüler ──────────────────────────────────────────
    @property
    def u_g_ortalama(self) -> Optional[float]:
        return _ortalama([a.u_g for a in self.araclar])

    @property
    def u_g_en_dusuk(self) -> Optional[float]:
        return _en_dusuk([a.u_g for a in self.araclar])

    @property
    def u_w_ortalama(self) -> Optional[float]:
        return _ortalama([a.u_w for a in self.araclar])

    @property
    def u_w_en_dusuk(self) -> Optional[float]:
        return _en_dusuk([a.u_w for a in self.araclar])

    @property
    def arac_sayisi(self) -> int:
        """Kullanılan araç (sefer) sayısı — K1'in 1. ölçütü."""
        return len(self.araclar)

    @property
    def toplam_yuk_kg(self) -> float:
        return sum(a.yuk_kg for a in self.araclar)

    @property
    def toplam_faydali_yuk_kg(self) -> Optional[float]:
        bilinen = [a.faydali_yuk_kg for a in self.araclar
                   if a.faydali_yuk_kg and a.faydali_yuk_kg > 0]
        return sum(bilinen) if bilinen else None

    # ── K1'in 2. ölçütü tartışması için: yalnız HESAPLANIR ──────────────
    @property
    def toplam_bos_agirlik_kg(self) -> float:
        """Taşınan ölü ağırlık (çekici + dorse boş ağırlıkları).

        ⚠ YALNIZCA RAPORLANIR. K1'in 2. ölçütü (toplam araç hacmi mi,
        toplam boş ağırlık mı) henüz karara bağlanmadı; bu değer hiçbir
        sıralamada kullanılmıyor.
        """
        return sum(a.bos_agirlik_kg for a in self.araclar)


def _ortalama(degerler: Sequence[Optional[float]]) -> Optional[float]:
    gecerli = [d for d in degerler if d is not None]
    return sum(gecerli) / len(gecerli) if gecerli else None


def _en_dusuk(degerler: Sequence[Optional[float]]) -> Optional[float]:
    gecerli = [d for d in degerler if d is not None]
    return min(gecerli) if gecerli else None


def toplam_bos_agirlik(plan_doluluk: PlanDoluluk) -> float:
    """Ayrı fonksiyon olarak da erişilebilir."""
    return plan_doluluk.toplam_bos_agirlik_kg


# ─────────────────────────────────────────────────────────────────────────────
# ANA GİRİŞ — arayüz ve raporlar yalnızca bunu çağırır
# ─────────────────────────────────────────────────────────────────────────────

def plan_doluluk(plan, pieces, trucks) -> PlanDoluluk:
    """
    Bir yerleşim planının bütün doluluk ölçülerini hesaplar.

    Args:
        plan   : CuttingPlan3D (bins + truck_assignments)
        pieces : Piece3D listesi (ağırlık ve şekil buradan okunur)
        trucks : plana atanmış Truck3D listesi

    Returns:
        PlanDoluluk — araç başına ve filo toplamı.

    NOT: Boş araçlar atlanır; paydaya girmezler.
    """
    from core_3d import piece_used_volume

    rapor = PlanDoluluk()
    if plan is None or not getattr(plan, "bins", None) or not trucks:
        return rapor

    piece_info = {p.id: p for p in pieces}
    tid = {t.id: t for t in trucks}
    atama = plan.truck_assignments or {}

    for bid, yerlesimler in enumerate(plan.bins):
        if not yerlesimler:
            continue                      # boş araç kullanılmış sayılmaz
        truck = tid.get(atama.get(bid))
        if truck is None:
            continue

        eslesme = getattr(truck, "eslesme", None)
        etiket = (f"{eslesme.cekici.plaka} + {eslesme.dorse.plaka}"
                  if eslesme is not None else truck.id)
        bos_agirlik = 0.0
        if eslesme is not None:
            bos_agirlik = (float(eslesme.cekici.bos_agirlik_kg or 0.0)
                           + float(eslesme.dorse.bos_agirlik_kg or 0.0))

        # Palet darası parçanın ağırlığına ZATEN dâhil → bir kez sayılır
        yuk_kg = sum(float(getattr(piece_info.get(p.piece_id), "weight", 0)
                           or 0.0) for p in yerlesimler)

        rapor.araclar.append(AracDoluluk(
            etiket=etiket,
            gercek_hacim=sum(piece_used_volume(p, piece_info)
                             for p in yerlesimler),
            dis_kutu_hacim=sum(p.get_volume() for p in yerlesimler),
            arac_hacim=float(truck.get_volume()),
            yuk_kg=yuk_kg,
            faydali_yuk_kg=(float(truck.capacity)
                            if getattr(truck, "capacity", 0) else None),
            bos_agirlik_kg=bos_agirlik,
            parca_sayisi=len(yerlesimler),
        ))

    return rapor


# ─────────────────────────────────────────────────────────────────────────────
# Biçimlendirme — arayüz ve raporlar aynı metni göstersin
# ─────────────────────────────────────────────────────────────────────────────

def yuzde(deger: Optional[float], basamak: int = 1) -> str:
    """Oranı yüzde metnine çevirir. Bilinmiyorsa '—' (sıfır DEĞİL)."""
    if deger is None:
        return "—"
    return f"%{deger * 100:.{basamak}f}"


def arac_satirlari(rapor: PlanDoluluk) -> List[Dict[str, object]]:
    """Araç başına tablo satırları — arayüz ve raporlar ortak kullanır."""
    satirlar: List[Dict[str, object]] = []
    for a in rapor.araclar:
        satirlar.append({
            "Araç": a.etiket,
            "Parça": a.parca_sayisi,
            "U_G (hacim)": yuzde(a.u_g),
            "U_BB (dış kutu)": yuzde(a.u_bb),
            "U_W (ağırlık)": yuzde(a.u_w),
            "Bağlayıcı": a.baglayici or "—",
            "Yük (kg)": round(a.yuk_kg, 1),
            "Faydalı yük (kg)": (round(a.faydali_yuk_kg, 1)
                                 if a.faydali_yuk_kg else "—"),
        })
    return satirlar
