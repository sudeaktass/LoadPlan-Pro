# -*- coding: utf-8 -*-
"""
Filo için Excel şablonu, içe ve dışa aktarma
=============================================
Optimizasyon sayfasındaki Excel akışının filo karşılığı. Fark: şablon
statik bir dosya DEĞİL, bu modülde ÜRETİLİYOR — böylece `filo_modeli`'ne
yeni bir alan eklendiğinde şablon da kendiliğinden güncel kalır.

Sayfalar:
  "Çekiciler"  — boş, doldurulacak
  "Dorseler"   — boş, doldurulacak
  "Örnek"      — Ford F-MAX + Schmitz SCS 24/L doldurulmuş hâliyle
  "Açıklama"   — her sütunun ne olduğu, birimi, zorunlu mu, nereden bulunur

KURAL: Bilinmeyen değer BOŞ bırakılır (None olur). Hücreye tahmini değer
yazılmaz — veri modelinin "asla tahmin yazma" kuralının Excel karşılığı.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from filo_modeli import Cekici, Dorse

# ─────────────────────────────────────────────────────────────────────────────
# Sütun tanımları — şablon, okuma ve açıklama sayfası hepsi buradan üretilir
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Sutun:
    baslik: str
    alan: str
    tip: str                  # "metin" | "sayi" | "tamsayi" | "evet_hayir"
    zorunlu: bool
    aciklama: str


SAYFA_CEKICI = "Çekiciler"
SAYFA_DORSE = "Dorseler"
SAYFA_ORNEK = "Örnek"
SAYFA_ACIKLAMA = "Açıklama"

SUTUNLAR_CEKICI: Tuple[Sutun, ...] = (
    Sutun("Plaka", "plaka", "metin", True,
          "Benzersiz olmalı. Dorse plakalarıyla da çakışamaz."),
    Sutun("Marka / model", "marka_model", "metin", False,
          "Örnek: Ford F-MAX 4x2"),
    Sutun("Boş ağırlık (kg)", "bos_agirlik_kg", "sayi", True,
          "Çekicinin yüksüz ağırlığı. Föy ya da ruhsat."),
    Sutun("Dingil sayısı", "dingil_sayisi", "tamsayi", True,
          "4x2 → 2 · 6x2 / 6x4 → 3. KTY md.128 toplam ağırlığını belirler."),
    Sutun("Beşinci teker ofseti e (mm)", "besinci_teker_ofset_mm", "sayi", True,
          "Beşinci tekerin TAHRİK DİNGİLİNE yatay uzaklığı. Beşinci teker "
          "dingilin ÖNÜNDE ise pozitif. Araç üzerinde ölçülebilir."),
    Sutun("Boş ön dingil (kg)", "bos_on_dingil_kg", "sayi", False,
          "Dingil kontrolü grubu — ya hepsi doldurulur ya hiçbiri."),
    Sutun("Boş arka (tahrik) dingil (kg)", "bos_arka_dingil_kg", "sayi", False,
          "Dingil kontrolü grubu."),
    Sutun("Ön dingil izni (kg)", "on_dingil_izin_kg", "sayi", False,
          "Föydeki yasal ön dingil sınırı. KTY tahriksiz tek dingil "
          "10.000 kg ile karşılaştırılır, küçüğü bağlar."),
    Sutun("Tahrik dingil izni (kg)", "tahrik_dingil_izin_kg", "sayi", False,
          "KTY tahrikli tek dingil 11.500 kg ile karşılaştırılır."),
    Sutun("Dingil mesafesi WB (mm)", "dingil_mesafesi_mm", "sayi", False,
          "Ön dingil ile tahrik dingili arası."),
    Sutun("Teknik GCW (kg)", "teknik_gcw_kg", "sayi", False,
          "Üreticinin kombinasyon için verdiği sınır. Yasal toplamla "
          "karşılaştırılır, küçüğü bağlar."),
    Sutun("Kaynak", "kaynak", "metin", False,
          "Değerlerin nereden alındığı. Örnek: 'Ford Trucks F-MAX Euro 6E föyü'"),
    Sutun("Doğrulama durumu", "dogrulama_durumu", "metin", False,
          "Örnek: 'değerler föyden okundu; föy PDF'i arşivde yok'"),
)

DORSE_TIPLERI = ("tenteli", "frigorifik", "kapalı kasa", "mega")

SUTUNLAR_DORSE: Tuple[Sutun, ...] = (
    Sutun("Plaka", "plaka", "metin", True,
          "Benzersiz olmalı. Çekici plakalarıyla da çakışamaz."),
    Sutun("Tip", "tip", "metin", True,
          "tenteli / frigorifik / kapalı kasa / mega"),
    Sutun("İç uzunluk (mm)", "ic_uzunluk_mm", "sayi", True,
          "Yük alanının iç ölçüsü. İç hacim bundan HESAPLANIR, girilmez."),
    Sutun("İç genişlik (mm)", "ic_genislik_mm", "sayi", True, "Yük alanı."),
    Sutun("İç yükseklik (mm)", "ic_yukseklik_mm", "sayi", True, "Yük alanı."),
    Sutun("Boş ağırlık (kg)", "bos_agirlik_kg", "sayi", True,
          "Dorsenin yüksüz ağırlığı."),
    Sutun("Dingil sayısı", "dingil_sayisi", "tamsayi", True,
          "Tipik yarı römork 3 dingil."),
    Sutun("Dingil aralığı (mm)", "dingil_araligi_mm", "sayi", False,
          "KTY md.128 grup sınırını belirler. Üç dingilde: ≤1.300 → 21 t · "
          "1.300–1.400 → 24 t · >1.400 → KTY'de değer yok, föy kullanılır."),
    Sutun("Dingil grubu izni (kg)", "dingil_grubu_izin_kg", "sayi", False,
          "Föydeki değer. KTY ile karşılaştırılır, küçüğü bağlar."),
    Sutun("Kingpin izni (kg)", "kingpin_izin_kg", "sayi", False, "Föy."),
    Sutun("Kingpin ön kenar mesafesi (mm)", "kingpin_on_kenar_mesafe_mm",
          "sayi", False,
          "Föydeki gibi DIŞ ön kenardan ölçülür "
          "(ör. 'king pin, position 1690 mm')."),
    Sutun("Ön duvar kalınlığı (mm)", "on_duvar_kalinligi_mm", "sayi", False,
          "Boş bırakılırsa 0. Motorun ekseni iç duvardan başlar: "
          "c = kingpin mesafesi − duvar kalınlığı."),
    Sutun("Kingpin → dingil grubu (mm)", "kingpin_dingil_grubu_mesafe_mm",
          "sayi", False,
          "Föyde genelde 'wheelbase'. Kingpin ile grubun ORTA dingili arası."),
    Sutun("Boş kingpin payı (kg)", "bos_kingpin_payi_kg", "sayi", False,
          "Boş dorsenin ağırlığından kingpine düşen pay. Boşsa ağırlık "
          "merkezi yük alanının ortasında varsayılır."),
    Sutun("Boş dingil grubu payı (kg)", "bos_dingil_grubu_payi_kg", "sayi",
          False, "Boş dorsenin dingil grubuna düşen payı."),
    Sutun("Teknik azami (kg)", "teknik_azami_kg", "sayi", False,
          "Dorsenin üretici sınırı."),
    Sutun("40 ft ISO konteyner", "iso_40ft_konteyner", "evet_hayir", False,
          "E / H. 44 t istisnası YALNIZCA bu 'E' ise VE çekici 3 dingilliyse "
          "uygulanır (KTY md.128)."),
    Sutun("Kaynak", "kaynak", "metin", False,
          "Örnek: 'Schmitz Cargobull SCS 24/L teknik föyü'"),
    Sutun("Doğrulama durumu", "dogrulama_durumu", "metin", False, ""),
)


# ─────────────────────────────────────────────────────────────────────────────
# Hücre okuma
# ─────────────────────────────────────────────────────────────────────────────

def _bos_mu(v: Any) -> bool:
    if v is None:
        return True
    if isinstance(v, str) and not v.strip():
        return True
    if isinstance(v, float) and v != v:          # NaN
        return True
    return False


def _hucre_oku(deger: Any, sutun: Sutun) -> Tuple[Any, Optional[str]]:
    """Bir hücreyi sütun tipine göre çevirir.

    Returns:
        (deger, hata_metni). Boş hücre → (None, None): tahmin YAPILMAZ.
    """
    if _bos_mu(deger):
        return None, None

    if sutun.tip == "metin":
        return str(deger).strip(), None

    if sutun.tip == "evet_hayir":
        m = str(deger).strip().lower()
        if m in ("e", "evet", "1", "true", "x", "var", "yes"):
            return True, None
        if m in ("h", "hayır", "hayir", "0", "false", "", "yok", "no"):
            return False, None
        return None, f"'{sutun.baslik}' için E/H bekleniyordu, '{deger}' geldi."

    try:
        sayi = float(str(deger).replace(".", "").replace(",", ".")
                     if isinstance(deger, str) and "," in str(deger)
                     else deger)
    except (TypeError, ValueError):
        return None, f"'{sutun.baslik}' sayı olmalı, '{deger}' geldi."
    if sayi != sayi:
        return None, None
    if sutun.tip == "tamsayi":
        return int(round(sayi)), None
    return sayi, None


# ─────────────────────────────────────────────────────────────────────────────
# Şablon üretimi
# ─────────────────────────────────────────────────────────────────────────────

def _baslik_yaz(ws, sutunlar: Tuple[Sutun, ...]) -> None:
    from openpyxl.styles import Alignment, Font, PatternFill

    dolgu_zorunlu = PatternFill("solid", fgColor="FFE2B7")
    dolgu_istege = PatternFill("solid", fgColor="E8EEF7")
    for i, s in enumerate(sutunlar, start=1):
        h = ws.cell(row=1, column=i, value=s.baslik)
        h.font = Font(bold=True)
        h.alignment = Alignment(wrap_text=True, vertical="center")
        h.fill = dolgu_zorunlu if s.zorunlu else dolgu_istege
        ws.column_dimensions[h.column_letter].width = max(
            14, min(34, len(s.baslik) + 4))
    ws.row_dimensions[1].height = 34
    ws.freeze_panes = "A2"


def sablon_uret(ornek_dahil: bool = True) -> bytes:
    """Boş filo şablonu üretir (bytes, .xlsx)."""
    from openpyxl import Workbook
    from openpyxl.styles import Font

    wb = Workbook()
    ws_c = wb.active
    ws_c.title = SAYFA_CEKICI
    _baslik_yaz(ws_c, SUTUNLAR_CEKICI)

    ws_d = wb.create_sheet(SAYFA_DORSE)
    _baslik_yaz(ws_d, SUTUNLAR_DORSE)

    if ornek_dahil:
        from ornek_filo import ford_fmax_4x2, schmitz_scs_24l
        ws_o = wb.create_sheet(SAYFA_ORNEK)
        ws_o.cell(row=1, column=1,
                  value="ÖRNEK — bu sayfa OKUNMAZ, yalnız biçimi gösterir"
                  ).font = Font(bold=True)
        satir = 3
        for baslik, sutunlar, kayit in (
                ("Çekici", SUTUNLAR_CEKICI, ford_fmax_4x2()),
                ("Dorse", SUTUNLAR_DORSE, schmitz_scs_24l())):
            ws_o.cell(row=satir, column=1, value=baslik).font = Font(bold=True)
            satir += 1
            for i, s in enumerate(sutunlar, start=1):
                ws_o.cell(row=satir, column=i, value=s.baslik).font = \
                    Font(bold=True, size=9)
                v = getattr(kayit, s.alan, None)
                if s.tip == "evet_hayir":
                    v = "E" if v else "H"
                ws_o.cell(row=satir + 1, column=i, value=v)
            satir += 3
        ws_o.column_dimensions["A"].width = 30

    # ── Açıklama sayfası ────────────────────────────────────────────────
    ws_a = wb.create_sheet(SAYFA_ACIKLAMA)
    ws_a.append(["Sayfa", "Sütun", "Zorunlu", "Tip", "Açıklama"])
    for h in ws_a[1]:
        h.font = Font(bold=True)
    for sayfa, sutunlar in ((SAYFA_CEKICI, SUTUNLAR_CEKICI),
                            (SAYFA_DORSE, SUTUNLAR_DORSE)):
        for s in sutunlar:
            ws_a.append([sayfa, s.baslik, "ZORUNLU" if s.zorunlu else "—",
                         s.tip, s.aciklama])
    ws_a.append([])
    ws_a.append(["KURAL", "Bilinmeyen değeri BOŞ bırakın — tahmini değer "
                          "yazmayın. Boş alan 'bilinmiyor' demektir."])
    ws_a.append(["KURAL", "Dingil kontrolü grubu: ya tamamen doldurun ya da "
                          "tamamen boş bırakın. Eksikse dingil kontrolü "
                          "yapılamaz (araç yine kaydedilir)."])
    ws_a.append(["KURAL", "İç hacim ve faydalı yük HESAPLANIR, girilmez."])
    for w, k in zip(("A", "B", "C", "D", "E"), (14, 32, 10, 10, 90)):
        ws_a.column_dimensions[w].width = k

    tampon = io.BytesIO()
    wb.save(tampon)
    return tampon.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
# Okuma
# ─────────────────────────────────────────────────────────────────────────────

def _satir_oku(satir: Dict[str, Any], sutunlar: Tuple[Sutun, ...],
               sayfa: str, no: int) -> Tuple[Dict[str, Any], List[str]]:
    degerler: Dict[str, Any] = {}
    hatalar: List[str] = []
    for s in sutunlar:
        v, hata = _hucre_oku(satir.get(s.baslik), s)
        if hata:
            hatalar.append(f"{sayfa} satır {no}: {hata}")
            continue
        if v is None and s.zorunlu:
            hatalar.append(f"{sayfa} satır {no}: '{s.baslik}' zorunlu, boş.")
            continue
        if v is not None:
            degerler[s.alan] = v
    return degerler, hatalar


def oku(dosya_baytlari: bytes) -> Tuple[List[Cekici], List[Dorse],
                                        List[str], List[str]]:
    """
    Doldurulmuş şablonu okur.

    Returns:
        (cekiciler, dorseler, hatalar, uyarilar)
        Hatalı satır ATLANIR; diğerleri okunmaya devam eder.
    """
    import pandas as pd

    cekiciler: List[Cekici] = []
    dorseler: List[Dorse] = []
    hatalar: List[str] = []
    uyarilar: List[str] = []

    try:
        kitap = pd.read_excel(io.BytesIO(dosya_baytlari), sheet_name=None)
    except Exception as e:                                   # noqa: BLE001
        return [], [], [f"Excel dosyası okunamadı: {e}"], []

    if SAYFA_CEKICI not in kitap and SAYFA_DORSE not in kitap:
        return [], [], [f"'{SAYFA_CEKICI}' ve '{SAYFA_DORSE}' sayfalarının "
                        f"ikisi de bulunamadı. Şablonu kullanın."], []

    # ── Çekiciler ───────────────────────────────────────────────────────
    if SAYFA_CEKICI in kitap:
        for no, (_, r) in enumerate(kitap[SAYFA_CEKICI].iterrows(), start=2):
            if all(_bos_mu(v) for v in r.values):
                continue
            degerler, satir_hatalari = _satir_oku(
                r.to_dict(), SUTUNLAR_CEKICI, SAYFA_CEKICI, no)
            if satir_hatalari:
                hatalar.extend(satir_hatalari)
                continue
            degerler.setdefault("cekici_id", degerler["plaka"])
            c = Cekici(**degerler)
            eksik = c.eksik_dingil_alanlari()
            if eksik:
                uyarilar.append(
                    f"{c.plaka}: dingil kontrolü yapılamayacak — eksik: "
                    + ", ".join(eksik))
            cekiciler.append(c)

    # ── Dorseler ────────────────────────────────────────────────────────
    if SAYFA_DORSE in kitap:
        for no, (_, r) in enumerate(kitap[SAYFA_DORSE].iterrows(), start=2):
            if all(_bos_mu(v) for v in r.values):
                continue
            degerler, satir_hatalari = _satir_oku(
                r.to_dict(), SUTUNLAR_DORSE, SAYFA_DORSE, no)
            if satir_hatalari:
                hatalar.extend(satir_hatalari)
                continue
            tip = str(degerler.get("tip", "")).strip().lower()
            if tip not in DORSE_TIPLERI:
                uyarilar.append(
                    f"{degerler.get('plaka')}: '{degerler.get('tip')}' "
                    f"bilinen tiplerden değil ({' / '.join(DORSE_TIPLERI)}); "
                    f"aynen kaydedildi.")
            else:
                degerler["tip"] = tip
            degerler.setdefault("dorse_id", degerler["plaka"])
            if degerler.get("on_duvar_kalinligi_mm") is None:
                degerler["on_duvar_kalinligi_mm"] = 0.0
            d = Dorse(**degerler)
            eksik = d.eksik_dingil_alanlari()
            if eksik:
                uyarilar.append(
                    f"{d.plaka}: dingil kontrolü yapılamayacak — eksik: "
                    + ", ".join(eksik))
            uyarilar.extend(f"{d.plaka}: {u}" for u in d.tutarlilik_uyarilari())
            dorseler.append(d)

    # ── Dosya içi plaka çakışması ───────────────────────────────────────
    tum = [c.plaka for c in cekiciler] + [d.plaka for d in dorseler]
    tekrar = {p for p in tum if tum.count(p) > 1}
    for p in sorted(tekrar):
        hatalar.append(f"'{p}' plakası dosyada birden fazla kez geçiyor.")
    if tekrar:
        cekiciler = [c for c in cekiciler if c.plaka not in tekrar]
        dorseler = [d for d in dorseler if d.plaka not in tekrar]

    if not cekiciler and not dorseler and not hatalar:
        uyarilar.append("Dosyada dolu satır bulunamadı.")

    return cekiciler, dorseler, hatalar, uyarilar


# ─────────────────────────────────────────────────────────────────────────────
# Dışa aktarma
# ─────────────────────────────────────────────────────────────────────────────

def disa_aktar(cekiciler: List[Cekici], dorseler: List[Dorse]) -> bytes:
    """Kayıtlı filoyu aynı şablon biçiminde Excel'e yazar."""
    from openpyxl import Workbook

    wb = Workbook()
    ws_c = wb.active
    ws_c.title = SAYFA_CEKICI
    _baslik_yaz(ws_c, SUTUNLAR_CEKICI)
    for c in cekiciler:
        ws_c.append([getattr(c, s.alan, None) for s in SUTUNLAR_CEKICI])

    ws_d = wb.create_sheet(SAYFA_DORSE)
    _baslik_yaz(ws_d, SUTUNLAR_DORSE)
    for d in dorseler:
        satir = []
        for s in SUTUNLAR_DORSE:
            v = getattr(d, s.alan, None)
            satir.append(("E" if v else "H") if s.tip == "evet_hayir" else v)
        ws_d.append(satir)

    tampon = io.BytesIO()
    wb.save(tampon)
    return tampon.getvalue()
