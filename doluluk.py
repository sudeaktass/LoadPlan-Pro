# -*- coding: utf-8 -*-
"""
Doluluk ölçüleri — hacim (U_V) ve ağırlık (U_W) kullanımı (karar R-a)
=====================================================================
U_V : Σ gerçek parça hacmi ÷ Σ kullanılan dorselerin iç hacmi
      Bu, uygulamadaki mevcut U_G tanımıyla AYNIDIR (4 Eylül kararı) ve
      DEĞİŞTİRİLMEMİŞTİR. Silindirler için gerçek hacim (πr²h) kullanılır.
U_W : Σ yük kütlesi ÷ Σ faydalı yük

ÖNEMLİ — hacim tanımının tek kaynağı:
  Parça hacmi hesaplanırken `core_3d.piece_used_volume` kullanılmalıdır.
  O fonksiyonun kopyası bu dosyada TANIMLANMADI (core_3d.py'deki uyarı
  gereği). Bu modül hacimleri hazır sayı olarak alır.

BEKLEYEN KARARLAR (bu modülde bilerek uygulanmadı):
  * S10 — U_V'nin paydası föydeki mm hacmi mi, motorun kullandığı cm
    hacmi mi? Çağıran taraf hangisini verirse o kullanılır.
  * S11 — "bağlayıcı ölçü" (U_V ile U_W'den hangisi) tanımı. Karar
    verilene kadar seçim yapılmıyor; ikisi de ayrı ayrı raporlanıyor.

Birim kuralı: hacimler aynı birimde olmalı (hepsi m³ ya da hepsi mm³);
bu modül birim dönüştürmez.

Literatür: araç başına doluluk raporlaması Cai ve ark. 2026, Paquay ve
ark. 2018, Hao ve ark. 2026'da böyle; toplam oran ile araç ortalaması
heterojen filoda ayrışır. Ağırlık ↔ hacim ayrışması: Mackie & Harding
(1982), ITS Leeds WP160.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence


# ─────────────────────────────────────────────────────────────────────────────
# Araç başına
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class AracDoluluk:
    """Tek bir aracın (çekici + dorse) doluluk ölçüleri."""
    etiket: str = ""
    gercek_hacim: float = 0.0          # Σ piece_used_volume
    dis_kutu_hacim: float = 0.0        # Σ bounding-box hacmi (U_BB payı)
    arac_hacim: float = 0.0            # dorsenin iç hacmi (payda — bkz. S10)
    yuk_kg: float = 0.0
    faydali_yuk_kg: float = 0.0
    bos_agirlik_kg: float = 0.0        # çekici + dorse boş ağırlığı

    @property
    def u_v(self) -> Optional[float]:
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
        """Ağırlık doluluğu [0, 1]. Faydalı yük sıfırsa None."""
        if self.faydali_yuk_kg <= 0:
            return None
        return self.yuk_kg / self.faydali_yuk_kg


# ─────────────────────────────────────────────────────────────────────────────
# Plan düzeyi
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class PlanDoluluk:
    """Bütün planın doluluk raporu."""
    araclar: List[AracDoluluk] = field(default_factory=list)

    # ── Toplam oranlar (ana ölçüler) ────────────────────────────────────
    @property
    def u_v(self) -> Optional[float]:
        """U_V — toplam oran. Mevcut U_G tanımıyla aynı."""
        pay = sum(a.gercek_hacim for a in self.araclar)
        payda = sum(a.arac_hacim for a in self.araclar)
        return pay / payda if payda > 0 else None

    @property
    def u_bb(self) -> Optional[float]:
        pay = sum(a.dis_kutu_hacim for a in self.araclar)
        payda = sum(a.arac_hacim for a in self.araclar)
        return pay / payda if payda > 0 else None

    @property
    def u_w(self) -> Optional[float]:
        """U_W — toplam ağırlık kullanımı."""
        pay = sum(a.yuk_kg for a in self.araclar)
        payda = sum(a.faydali_yuk_kg for a in self.araclar)
        return pay / payda if payda > 0 else None

    # ── Araç başına ek ölçüler ──────────────────────────────────────────
    @property
    def u_v_ortalama(self) -> Optional[float]:
        """Araç başına hacim doluluğunun ORTALAMASI.

        Heterojen filoda toplam orandan ayrışır (örnek: %60,0 ↔ %65,3) —
        bu yüzden ikisi birlikte raporlanıyor.
        """
        return _ortalama([a.u_v for a in self.araclar])

    @property
    def u_v_en_dusuk(self) -> Optional[float]:
        return _en_dusuk([a.u_v for a in self.araclar])

    @property
    def u_w_ortalama(self) -> Optional[float]:
        return _ortalama([a.u_w for a in self.araclar])

    @property
    def u_w_en_dusuk(self) -> Optional[float]:
        return _en_dusuk([a.u_w for a in self.araclar])

    # ── K1'in 2. ölçütü tartışması için: yalnız HESAPLANIR ──────────────
    @property
    def toplam_bos_agirlik_kg(self) -> float:
        """Taşınan ölü ağırlık (çekici + dorse boş ağırlıkları toplamı).

        ⚠ YALNIZCA RAPORLANIR. K1'in 2. ölçütü (toplam araç hacmi mi,
        toplam boş ağırlık mı) henüz karara bağlanmadı; bu değer hiçbir
        sıralamada kullanılmıyor.
        """
        return sum(a.bos_agirlik_kg for a in self.araclar)

    @property
    def arac_sayisi(self) -> int:
        """Kullanılan çekici (sefer) sayısı — K1'in 1. ölçütü."""
        return len(self.araclar)


def _ortalama(degerler: Sequence[Optional[float]]) -> Optional[float]:
    gecerli = [d for d in degerler if d is not None]
    return sum(gecerli) / len(gecerli) if gecerli else None


def _en_dusuk(degerler: Sequence[Optional[float]]) -> Optional[float]:
    gecerli = [d for d in degerler if d is not None]
    return min(gecerli) if gecerli else None


def toplam_bos_agirlik(plan_doluluk: PlanDoluluk) -> float:
    """Ayrı fonksiyon olarak da erişilebilir (plan Bölüm 9)."""
    return plan_doluluk.toplam_bos_agirlik_kg
