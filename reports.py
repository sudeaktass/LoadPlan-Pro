# -*- coding: utf-8 -*-
"""
Reports — PDF & Excel Dışa Aktarım
====================================
PDF  : ReportLab ile şirket logolu, tam detaylı rapor
Excel: openpyxl ile çok sayfalı, formüllü çalışma kitabı

Her ikisi de bellek içi (BytesIO) üretilir → Streamlit download_button ile sunulur.
"""

from __future__ import annotations
import io
from datetime import datetime
from typing import Any, Dict, List, Optional

# ─── ReportLab ───────────────────────────────────────────────────────────────
from reportlab.lib.pagesizes  import A4
from reportlab.lib.units       import cm
from reportlab.lib             import colors
from reportlab.lib.styles      import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus        import (
    SimpleDocTemplate, Table, TableStyle, Paragraph,
    Spacer, HRFlowable
)
from reportlab.pdfbase         import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# ─── Türkçe karakter desteği için Unicode TTF font kaydı ─────────────────────
# Öncelik sırası: Arial (Windows), DejaVu (Linux/macOS), Helvetica (fallback)
import os as _os

_FONT_CANDIDATES = [
    # Windows
    ("C:/Windows/Fonts/arial.ttf",    "C:/Windows/Fonts/arialbd.ttf"),
    ("C:/Windows/Fonts/calibri.ttf",  "C:/Windows/Fonts/calibrib.ttf"),
    ("C:/Windows/Fonts/segoeui.ttf",  "C:/Windows/Fonts/segoeuib.ttf"),
    ("C:/Windows/Fonts/tahoma.ttf",   "C:/Windows/Fonts/tahomabd.ttf"),
    # Linux
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
     "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    # macOS
    ("/Library/Fonts/Arial.ttf",      "/Library/Fonts/Arial Bold.ttf"),
    ("/System/Library/Fonts/Helvetica.ttc", None),
]

_TR_FONT      = "Helvetica"       # varsayılan (Türkçe desteği yok ama en azından çalışır)
_TR_FONT_BOLD = "Helvetica-Bold"
_TR_FONTS_OK  = False

for _reg, _bold in _FONT_CANDIDATES:
    try:
        if _os.path.isfile(_reg):
            pdfmetrics.registerFont(TTFont("TRFont",     _reg))
            if _bold and _os.path.isfile(_bold):
                pdfmetrics.registerFont(TTFont("TRFont-Bold", _bold))
                pdfmetrics.registerFontFamily(
                    "TRFont",
                    normal="TRFont",
                    bold="TRFont-Bold",
                    italic="TRFont",
                    boldItalic="TRFont-Bold",
                )
            _TR_FONT      = "TRFont"
            _TR_FONT_BOLD = "TRFont-Bold" if (_bold and _os.path.isfile(_bold)) else "TRFont"
            _TR_FONTS_OK  = True
            break
    except Exception:
        continue

# ─── openpyxl ────────────────────────────────────────────────────────────────
import openpyxl
from openpyxl.styles import (
    Font, PatternFill, Alignment, Border, Side
)
from openpyxl.chart import BarChart, Reference
from openpyxl.utils import get_column_letter


# ============================================================================
# RENK PALETİ (kurumsal)
# ============================================================================
BRAND_BLUE    = colors.HexColor("#1565C0")
BRAND_ACCENT  = colors.HexColor("#2196F3")
BRAND_DARK    = colors.HexColor("#0D1117")
BRAND_LIGHT   = colors.HexColor("#E3F2FD")
BRAND_GRAY    = colors.HexColor("#546E7A")
TEXT_DARK     = colors.HexColor("#1A237E")
SUCCESS_GREEN = colors.HexColor("#2E7D32")
WARN_ORANGE   = colors.HexColor("#E65100")

XLSX_BLUE     = "1565C0"
XLSX_HEADER   = "0D47A1"
XLSX_SUBHDR   = "E3F2FD"
XLSX_ACCENT   = "BBDEFB"


# ============================================================================
# PDF RAPORU
# ============================================================================


def _yuzde(deger, basamak: int = 1) -> str:
    """Oranı yüzde metnine çevirir; bilinmiyorsa "—" (sıfır DEĞİL).

    Doluluk ölçüleri app_3d.results_dict_from içinde `doluluk.py`
    tarafından hesaplanır; burada formül YOKTUR, yalnız biçimlendirme.
    """
    if deger is None:
        return "—"
    return f"%{deger:.{basamak}f}"


def generate_pdf_report(
    project_name:   str,
    company_name:   str,
    trucks:         List[dict],
    pieces:         List[dict],
    results:        Dict[str, Any],    # {algo_name: {utilization, truck_count, placed, ...}}
    best_algo:      str,
    params:         dict,
    created_by:     str = "",
    logo_path:      Optional[str] = None,
) -> bytes:
    """
    Tam sayfalı PDF optimizasyon raporu üretir.
    Döndürür: PDF bytes (doğrudan download_button'a verilebilir).
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=1.8*cm, rightMargin=1.8*cm,
        topMargin=2*cm,    bottomMargin=2*cm,
        title=f"LoadPlan Pro — {project_name}",
        author=company_name,
    )

    styles = getSampleStyleSheet()
    # ─── Özel stiller — Türkçe destekli font ─────────────────────────────────
    h1 = ParagraphStyle("H1", parent=styles["Heading1"],
                         fontName=_TR_FONT_BOLD,
                         fontSize=18, textColor=BRAND_BLUE,
                         spaceAfter=6, spaceBefore=6)
    h2 = ParagraphStyle("H2", parent=styles["Heading2"],
                         fontName=_TR_FONT_BOLD,
                         fontSize=13, textColor=BRAND_BLUE,
                         spaceAfter=4, spaceBefore=10)
    body = ParagraphStyle("Body", parent=styles["Normal"],
                           fontName=_TR_FONT,
                           fontSize=9, leading=14)
    caption = ParagraphStyle("Cap", parent=styles["Normal"],
                              fontName=_TR_FONT,
                              fontSize=8, textColor=BRAND_GRAY)

    elements = []
    W = doc.width

    # ── KAPAK ────────────────────────────────────────────────────────────────
    elements.append(Spacer(1, 1.5*cm))
    elements.append(Paragraph(f"🚛 {company_name}", h2))
    elements.append(HRFlowable(width=W, thickness=2, color=BRAND_BLUE))
    elements.append(Spacer(1, 0.4*cm))
    elements.append(Paragraph("Araç Yükleme Optimizasyon Raporu", h1))
    elements.append(Paragraph(f"<b>Proje:</b> {project_name}", body))
    elements.append(Paragraph(
        f"<b>Tarih:</b> {datetime.now().strftime('%d.%m.%Y %H:%M')}  |  "
        f"<b>Hazırlayan:</b> {created_by or '—'}  |  "
        f"<b>En İyi Algoritma:</b> {best_algo}",
        body
    ))
    elements.append(Spacer(1, 0.5*cm))

    # ── ÖZET METRİKLER ───────────────────────────────────────────────────────
    best = results.get(best_algo, {})
    elements.append(Paragraph("1. Yönetici Özeti", h2))
    elements.append(HRFlowable(width=W, thickness=0.5, color=BRAND_ACCENT))
    elements.append(Spacer(1, 0.2*cm))

    summary_data = [
        ["Metrik", "Değer"],
        ["Kullanılan Araç Sayısı",      str(best.get("truck_count", "—"))],
        ["Yerleştirilen Palet",          f"{best.get('placed', '—')} / {best.get('total_req', '—')}"],
        ["Hacim Doluluğu  U_G",          _yuzde(best.get("utilization"))],
        ["Hacim Doluluğu  U_BB (dış kutu)", _yuzde(best.get("u_bb"))],
        ["Ağırlık Doluluğu  U_W",        _yuzde(best.get("u_w"))],
        ["Bağlayıcı Ölçü",               best.get("baglayici") or "—"],
        ["Yük Kütlesi (palet darası dâhil)",
         f"{best.get('yuk_kg', 0):,.0f} kg"],
        ["Faydalı Yük",
         (f"{best['faydali_yuk_kg']:,.0f} kg"
          if best.get("faydali_yuk_kg") else "—")],
        ["Toplam Yük Ağırlığı",          f"{best.get('total_weight', 0):,.0f} kg"],
        ["Fire Hacmi",                   f"{best.get('waste_cm3', 0)/1e6:.3f} m³"],
        ["Optimizasyon Süresi",          f"{best.get('execution_time', 0):.2f} sn"],
    ]
    summary_table = Table(summary_data, colWidths=[W*0.55, W*0.45])
    summary_table.setStyle(TableStyle([
        ("BACKGROUND",   (0, 0), (-1, 0),  BRAND_BLUE),
        ("TEXTCOLOR",    (0, 0), (-1, 0),  colors.white),
        ("FONTNAME",     (0, 0), (-1, 0),  _TR_FONT_BOLD),
        ("FONTNAME",     (0, 1), (-1, -1), _TR_FONT),
        ("FONTSIZE",     (0, 0), (-1, 0),  9),
        ("ALIGN",        (0, 0), (-1, -1), "CENTER"),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [colors.white, BRAND_LIGHT]),
        ("FONTSIZE",     (0, 1), (-1, -1), 9),
        ("GRID",         (0, 0), (-1, -1), 0.5, BRAND_GRAY),
        ("TOPPADDING",   (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 5),
    ]))
    elements.append(summary_table)
    elements.append(Spacer(1, 0.6*cm))

    # ── ALGORİTMA KARŞILAŞTIRMA ───────────────────────────────────────────────
    if len(results) > 1:
        elements.append(Paragraph("2. Algoritma Karşılaştırması", h2))
        elements.append(HRFlowable(width=W, thickness=0.5, color=BRAND_ACCENT))
        elements.append(Spacer(1, 0.2*cm))

        cmp_data = [["Algoritma", "Kamyon", "Yerleşen", "U_G", "U_W",
                     "Bağlayıcı", "Süre (sn)"]]
        for algo, r in sorted(results.items(), key=lambda x: -x[1].get("utilization", 0)):
            is_best = (algo == best_algo)
            row = [
                f"★ {algo}" if is_best else algo,
                str(r.get("truck_count", "—")),
                f"{r.get('placed', '—')}/{r.get('total_req', '—')}",
                _yuzde(r.get("utilization")),
                _yuzde(r.get("u_w")),
                r.get("baglayici") or "—",
                f"{r.get('execution_time', 0):.2f}",
            ]
            cmp_data.append(row)

        col_w = [W * f for f in (0.26, 0.10, 0.15, 0.12, 0.12, 0.13, 0.12)]
        cmp_table = Table(cmp_data, colWidths=col_w)
        style = [
            ("BACKGROUND",    (0, 0), (-1, 0),  BRAND_BLUE),
            ("TEXTCOLOR",     (0, 0), (-1, 0),  colors.white),
            ("FONTNAME",      (0, 0), (-1, 0),  _TR_FONT_BOLD),
            ("FONTNAME",      (0, 1), (-1, -1), _TR_FONT),
            ("FONTSIZE",      (0, 0), (-1, -1), 8.5),
            ("ALIGN",         (1, 0), (-1, -1), "CENTER"),
            ("ALIGN",         (0, 0), (0, -1),  "LEFT"),
            ("ROWBACKGROUNDS",(0, 1), (-1, -1), [colors.white, BRAND_LIGHT]),
            ("GRID",          (0, 0), (-1, -1), 0.5, BRAND_GRAY),
            ("TOPPADDING",    (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]
        # En iyi satırı vurgula
        for i, algo in enumerate(sorted(results, key=lambda x: -results[x].get("utilization", 0))):
            if algo == best_algo:
                style.append(("BACKGROUND", (0, i+1), (-1, i+1), BRAND_LIGHT))
                style.append(("FONTNAME",   (0, i+1), (-1, i+1), _TR_FONT_BOLD))
                style.append(("TEXTCOLOR",  (0, i+1), (-1, i+1), TEXT_DARK))
        cmp_table.setStyle(TableStyle(style))
        elements.append(cmp_table)
        elements.append(Spacer(1, 0.6*cm))

    # ── ARAÇ BAŞINA DOLULUK (R-a) ─────────────────────────────────────────────
    # Satırlar doluluk.arac_satirlari() ile üretildi; burada formül YOK.
    _arac_sat = best.get("arac_satirlari") or []
    if _arac_sat:
        elements.append(Paragraph("3. Araç Başına Doluluk", h2))
        elements.append(HRFlowable(width=W, thickness=0.5, color=BRAND_ACCENT))
        elements.append(Spacer(1, 0.2*cm))
        _basliklar = ["Araç", "Parça", "U_G", "U_BB", "U_W", "Bağlayıcı",
                      "Yük (kg)", "Faydalı yük (kg)"]
        _dol_data = [_basliklar]
        for _r in _arac_sat:
            _dol_data.append([
                str(_r["Araç"]), str(_r["Parça"]), _r["U_G (hacim)"],
                _r["U_BB (dış kutu)"], _r["U_W (ağırlık)"], _r["Bağlayıcı"],
                f"{_r['Yük (kg)']:,.0f}" if isinstance(_r["Yük (kg)"], (int, float))
                else str(_r["Yük (kg)"]),
                (f"{_r['Faydalı yük (kg)']:,.0f}"
                 if isinstance(_r["Faydalı yük (kg)"], (int, float))
                 else str(_r["Faydalı yük (kg)"])),
            ])
        _dol_table = Table(_dol_data,
                           colWidths=[W * f for f in
                                      (0.24, 0.08, 0.10, 0.10, 0.10, 0.12,
                                       0.13, 0.13)])
        _dol_table.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, 0),  BRAND_BLUE),
            ("TEXTCOLOR",     (0, 0), (-1, 0),  colors.white),
            ("FONTNAME",      (0, 0), (-1, 0),  _TR_FONT_BOLD),
            ("FONTNAME",      (0, 1), (-1, -1), _TR_FONT),
            ("FONTSIZE",      (0, 0), (-1, -1), 8),
            ("ALIGN",         (1, 0), (-1, -1), "CENTER"),
            ("ALIGN",         (0, 0), (0, -1),  "LEFT"),
            ("ROWBACKGROUNDS",(0, 1), (-1, -1), [colors.white, BRAND_LIGHT]),
            ("GRID",          (0, 0), (-1, -1), 0.5, BRAND_GRAY),
            ("TOPPADDING",    (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        elements.append(_dol_table)
        elements.append(Spacer(1, 0.25*cm))
        elements.append(Paragraph(
            "Hacim doluluğu gerçek parça hacmiyle, ağırlık doluluğu faydalı "
            "yüke göre hesaplanır. Yük kütlesine palet darası dâhildir. "
            "Filo toplamı, araç oranlarının ortalaması değil, toplamların "
            "oranıdır.", caption))
        elements.append(Spacer(1, 0.6*cm))

    # ── ARAÇ FİLOSU ───────────────────────────────────────────────────────────
    elements.append(Paragraph("4. Araç Filosu", h2))
    elements.append(HRFlowable(width=W, thickness=0.5, color=BRAND_ACCENT))
    elements.append(Spacer(1, 0.2*cm))
    truck_data = [["ID", "G (cm)", "U (cm)", "Y (cm)", "Kapasite (kg)", "Adet"]]
    for t in trucks:
        truck_data.append([
            t.get("ID", "—"),
            str(t.get("Genişlik (cm)", "—")),
            str(t.get("Uzunluk (cm)", "—")),
            str(t.get("Yükseklik (cm)", "—")),
            f"{t.get('Kapasite (kg)', 0):,.0f}",
            str(t.get("Adet", 1)),
        ])
    t_table = Table(truck_data)
    t_table.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0),  BRAND_BLUE),
        ("TEXTCOLOR",     (0, 0), (-1, 0),  colors.white),
        ("FONTNAME",      (0, 0), (-1, 0),  _TR_FONT_BOLD),
        ("FONTNAME",      (0, 1), (-1, -1), _TR_FONT),
        ("FONTSIZE",      (0, 0), (-1, -1), 8.5),
        ("ALIGN",         (1, 0), (-1, -1), "CENTER"),
        ("ALIGN",         (0, 0), (0, -1),  "LEFT"),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [colors.white, BRAND_LIGHT]),
        ("GRID",          (0, 0), (-1, -1), 0.5, BRAND_GRAY),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    elements.append(t_table)
    elements.append(Spacer(1, 0.6*cm))

    # ── PALET LİSTESİ ─────────────────────────────────────────────────────────
    elements.append(Paragraph("5. Palet / Yük Listesi", h2))
    elements.append(HRFlowable(width=W, thickness=0.5, color=BRAND_ACCENT))
    elements.append(Spacer(1, 0.2*cm))

    piece_data = [["ID", "Şekil", "G×U×Y (cm)", "Ağırlık (kg)", "Adet", "Müşteri"]]
    for p in pieces:
        piece_data.append([
            p.get("ID", "—"),
            p.get("Şekil", "Dikdörtgen"),
            f"{p.get('Genişlik (cm)', '?')}×{p.get('Uzunluk (cm)', '?')}×{p.get('Yükseklik (cm)', '?')}",
            f"{p.get('Ağırlık (kg)', 0):,.1f}",
            str(p.get("Adet", 1)),
            p.get("Müşteri", "—") or "—",
        ])
    p_table = Table(piece_data)
    p_table.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0),  BRAND_BLUE),
        ("TEXTCOLOR",     (0, 0), (-1, 0),  colors.white),
        ("FONTNAME",      (0, 0), (-1, 0),  _TR_FONT_BOLD),
        ("FONTNAME",      (0, 1), (-1, -1), _TR_FONT),
        ("FONTSIZE",      (0, 0), (-1, -1), 8),
        ("ALIGN",         (3, 0), (-1, -1), "CENTER"),
        ("ALIGN",         (0, 0), (2, -1),  "LEFT"),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [colors.white, BRAND_LIGHT]),
        ("GRID",          (0, 0), (-1, -1), 0.5, BRAND_GRAY),
        ("TOPPADDING",    (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    elements.append(p_table)
    elements.append(Spacer(1, 1*cm))

    # ── FOOTER ────────────────────────────────────────────────────────────────
    elements.append(HRFlowable(width=W, thickness=1, color=BRAND_BLUE))
    elements.append(Spacer(1, 0.2*cm))
    elements.append(Paragraph(
        f"LoadPlan Pro — {company_name}  |  "
        f"Oluşturulma: {datetime.now().strftime('%d.%m.%Y %H:%M')}  |  "
        "Akademik referanslar: Crainic (2008), Lodi (2002), George (1980)",
        caption
    ))

    doc.build(elements)
    return buf.getvalue()


# ============================================================================
# EXCEL YARDIMCILARI — stil + yükleme talimatı sayfası (yeniden kullanılabilir)
# ============================================================================

def _xl_styles():
    """Ortak Excel stil seti."""
    return {
        "hdr_fill":   PatternFill("solid", fgColor=XLSX_HEADER),
        "sub_fill":   PatternFill("solid", fgColor=XLSX_SUBHDR),
        "accent_fill":PatternFill("solid", fgColor=XLSX_ACCENT),
        "white_fill": PatternFill("solid", fgColor="FFFFFF"),
        "hdr_font":   Font(bold=True, color="FFFFFF", size=10),
        "norm_font":  Font(size=9),
        "center":     Alignment(horizontal="center", vertical="center", wrap_text=True),
        "border":     Border(left=Side(style="thin"), right=Side(style="thin"),
                             top=Side(style="thin"),  bottom=Side(style="thin")),
    }


def _safe_sheet_name(name: str, used: set) -> str:
    """Excel sayfa adı: yasak karakterler temizlenir, 31 karakter, benzersiz."""
    clean = "".join(c for c in name if c not in "\\/*?:[]").strip() or "Sayfa"
    clean = clean[:28]
    final, i = clean, 2
    while final in used:
        final = f"{clean}~{i}"[:31]
        i += 1
    used.add(final)
    return final


def _add_loading_sheet(wb, sheet_title: str, project_name: str,
                       plan, trucks: List[dict], piece_info: dict) -> None:
    """
    'Yükleme Talimatı' sayfası — TEK plan için. Hem tekli rapor hem de
    genel (tüm algoritmalar) raporu bu fonksiyonu kullanır; sıralama
    mantığı tek yerde yaşar.
    """
    S = _xl_styles()

    def style_header(cell):
        cell.fill = S["hdr_fill"]; cell.font = S["hdr_font"]
        cell.alignment = S["center"]; cell.border = S["border"]

    def style_row(cell, even=True):
        cell.fill = S["sub_fill"] if even else S["white_fill"]
        cell.font = S["norm_font"]; cell.alignment = S["center"]
        cell.border = S["border"]

    ws_lt = wb.create_sheet(sheet_title)

    ws_lt["A1"] = f"Yükleme Talimatı — {project_name}"
    ws_lt["A1"].font = Font(bold=True, size=13, color=XLSX_HEADER)
    ws_lt.merge_cells("A1:H1")
    ws_lt["A1"].alignment = Alignment(horizontal="left", vertical="center")
    ws_lt.row_dimensions[1].height = 22

    _algo_lbl = getattr(plan, "algorithm", "")
    ws_lt["A2"] = (
        f"Algoritma: {_algo_lbl}  |  "
        "📋 Yükleme sırası: Kapıdan en uzak (kabin tarafı, Y=0) satırın alt "
        "katmanı yerleştirilir → hemen üstündeki katman eklenir → bir sıra "
        "kapıya doğru ilerlenir → tekrar. "
        "Sıra No 1 = kabin tarafına ilk yerleşen ürün | Son Sıra = kapıya en yakın ürün."
    )
    ws_lt["A2"].font = Font(italic=True, size=9, color="546E7A")
    ws_lt.merge_cells("A2:H2")
    ws_lt.row_dimensions[2].height = 16

    non_empty_bins = [(i, b) for i, b in enumerate(plan.bins) if b]
    truck_assignments = getattr(plan, "truck_assignments", {}) or {}
    trucks_by_id_lt = {t.get("ID", ""): t for t in trucks}

    ws_lt["A3"] = "Araç Yükleme Sırası:"
    ws_lt["A3"].font = Font(bold=True, size=10, color=XLSX_HEADER)
    ws_lt.row_dimensions[3].height = 16

    order_parts = [
        f"Araç {i + 1}  ({truck_assignments.get(i, f'V{i+1}')})"
        for i, _ in non_empty_bins
    ]
    ws_lt["A4"] = "  →  ".join(order_parts)
    ws_lt["A4"].font = Font(size=9)
    ws_lt.merge_cells("A4:H4")
    ws_lt.row_dimensions[4].height = 16

    lt_headers = [
        "Sıra No", "Palet ID", "Boyut G×U×Y (cm)",
        "Ağırlık (kg)", "Konum (X, Y, Z)", "Müşteri",
        "Öncelik", "Dikkat Notları",
    ]
    lt_col_widths = [10, 18, 20, 13, 18, 18, 10, 24]
    frag_fill  = PatternFill("solid", fgColor="FFF9C4")
    truck_hdr_fill = PatternFill("solid", fgColor="0D47A1")

    def _gp(pl, attr, default=0):
        if hasattr(pl, attr):
            return getattr(pl, attr)
        if hasattr(pl, "get"):
            return pl.get(attr, default)
        return default

    current_row = 6

    for bin_idx, bin_placements in non_empty_bins:
        truck_id   = truck_assignments.get(bin_idx, f"V{bin_idx + 1}")
        truck_dict = trucks_by_id_lt.get(truck_id, {})
        tw = truck_dict.get("Genişlik (cm)", 0)
        tl = truck_dict.get("Uzunluk (cm)", 0)
        th = truck_dict.get("Yükseklik (cm)", 0)

        truck_label = (
            f"  ARAÇ {bin_idx + 1}:  {truck_id}  "
            f"({tw}×{tl}×{th} cm)  —  {len(bin_placements)} parça"
        )
        cell_th = ws_lt.cell(current_row, 1, truck_label)
        cell_th.font = Font(bold=True, size=11, color="FFFFFF")
        cell_th.fill = truck_hdr_fill
        cell_th.alignment = Alignment(horizontal="left", vertical="center")
        cell_th.border = S["border"]
        ws_lt.merge_cells(start_row=current_row, start_column=1,
                          end_row=current_row, end_column=len(lt_headers))
        ws_lt.row_dimensions[current_row].height = 22
        current_row += 1

        for c, h in enumerate(lt_headers, 1):
            style_header(ws_lt.cell(current_row, c, h))
        ws_lt.row_dimensions[current_row].height = 18
        current_row += 1

        # Yükleme sırası: kabin tarafı (Y=0) önce → kapıya ilerle (LIFO)
        sorted_placements = sorted(
            bin_placements,
            key=lambda pl: (_gp(pl, "y", 0), _gp(pl, "z", 0), _gp(pl, "x", 0)),
        )

        for seq, pl in enumerate(sorted_placements, 1):
            pid = _gp(pl, "piece_id", "—") or "—"
            px, py, pz = _gp(pl, "x", 0), _gp(pl, "y", 0), _gp(pl, "z", 0)
            pw, pln, pht = _gp(pl, "width", 0), _gp(pl, "length", 0), _gp(pl, "height", 0)

            pinfo    = (piece_info or {}).get(pid, {})
            weight   = pinfo.get("weight", 0) or 0
            customer = pinfo.get("customer", "") or pinfo.get("Müşteri", "") or ""
            priority = pinfo.get("priority", "") or ""
            fragile  = bool(pinfo.get("is_fragile") or pinfo.get("fragile"))
            no_top   = bool(pinfo.get("no_top_load")
                            or pinfo.get("üstüne_yük_konmasın"))

            notes = []
            if fragile:
                notes.append("⚠ Kırılgan")
            if no_top:
                notes.append("🚫 Üstüne Yük Koyma")
            if str(priority) == "1":
                notes.append("🚪 Kapıya Yakın")
            note_str = " · ".join(notes) if notes else ""

            row_vals = [
                seq, pid, f"{pw}×{pln}×{pht}", round(float(weight), 1),
                f"({px}, {py}, {pz})", str(customer),
                str(priority) if priority else "", note_str,
            ]
            even = seq % 2 == 0
            for c, v in enumerate(row_vals, 1):
                cell = ws_lt.cell(current_row, c, v)
                style_row(cell, even)
                if fragile:
                    cell.fill = frag_fill
            current_row += 1

        current_row += 1

    for col, w in enumerate(lt_col_widths, 1):
        ws_lt.column_dimensions[get_column_letter(col)].width = w


# ============================================================================
# EXCEL RAPORU
# ============================================================================

def generate_excel_report(
    project_name:  str,
    company_name:  str,
    trucks:        List[dict],
    pieces:        List[dict],
    results:       Dict[str, Any],
    best_algo:     str,
    load_rules_df=None,   # pd.DataFrame — Yük Listesi & Yerleştirme Kuralları
    best_plan=None,       # CuttingPlan3D — Yükleme Talimatı sayfası için
    piece_info=None,      # {piece_id: {"weight", "is_fragile", "priority", "customer"}}
) -> bytes:
    """
    Çok sayfalı Excel çalışma kitabı üretir:
    · Özet             — KPI tablosu + bar chart
    · Kamyonlar        — filo detayı
    · Yük Listesi      — load_rules (tüm kurallarla) veya eski paletler
    · Karşılaştırma    — algoritma metrikleri
    · Yükleme Talimatı — araç ve ürün yükleme sırası (best_plan varsa)
    """
    wb = openpyxl.Workbook()

    # ── Stil kütüphanesi ──────────────────────────────────────────────────────
    hdr_fill   = PatternFill("solid", fgColor=XLSX_HEADER)
    sub_fill   = PatternFill("solid", fgColor=XLSX_SUBHDR)
    accent_fill= PatternFill("solid", fgColor=XLSX_ACCENT)
    white_fill = PatternFill("solid", fgColor="FFFFFF")
    hdr_font   = Font(bold=True, color="FFFFFF", size=10)
    norm_font  = Font(size=9)
    center_aln = Alignment(horizontal="center", vertical="center", wrap_text=True)
    thin_border = Border(
        left=Side(style="thin"),  right=Side(style="thin"),
        top=Side(style="thin"),   bottom=Side(style="thin"),
    )

    def style_header(cell, col_span=1):
        cell.fill = hdr_fill; cell.font = hdr_font
        cell.alignment = center_aln; cell.border = thin_border

    def style_row(cell, even=True):
        cell.fill = sub_fill if even else white_fill
        cell.font = norm_font; cell.alignment = center_aln
        cell.border = thin_border

    def set_col_widths(ws, widths):
        for col, w in enumerate(widths, 1):
            ws.column_dimensions[get_column_letter(col)].width = w

    # ========================================================================
    # Sayfa 1: Özet
    # ========================================================================
    ws_sum = wb.active
    ws_sum.title = "Özet"

    ws_sum["A1"] = f"LoadPlan Pro — {company_name}"
    ws_sum["A1"].font = Font(bold=True, size=14, color=XLSX_HEADER)
    ws_sum["A2"] = f"Proje: {project_name}"
    ws_sum["A2"].font = Font(bold=True, size=11)
    ws_sum["A3"] = (f"Tarih: {datetime.now().strftime('%d.%m.%Y %H:%M')} | "
                    f"Rapor Algoritması: {best_algo}")
    ws_sum["A3"].font = Font(italic=True, size=9, color="546E7A")

    best = results.get(best_algo, {})
    kpi_rows = [
        ("Metrik", "Değer"),
        ("Kullanılan Araç", best.get("truck_count", "—")),
        ("Yerleştirilen Palet", f"{best.get('placed', '—')} / {best.get('total_req', '—')}"),
        ("Hacim Doluluğu U_G", _yuzde(best.get("utilization"))),
        ("Hacim Doluluğu U_BB", _yuzde(best.get("u_bb"))),
        ("Ağırlık Doluluğu U_W", _yuzde(best.get("u_w"))),
        ("Bağlayıcı Ölçü", best.get("baglayici") or "—"),
        ("Yük Kütlesi (kg, palet darası dâhil)",
         round(best.get("yuk_kg", 0), 1)),
        ("Faydalı Yük (kg)", (round(best["faydali_yuk_kg"], 1)
                              if best.get("faydali_yuk_kg") else "—")),
        ("Toplam Ağırlık (kg)", round(best.get("total_weight", 0), 1)),
        ("Fire (m³)", round(best.get("waste_cm3", 0) / 1e6, 3)),
        ("Süre (sn)", round(best.get("execution_time", 0), 2)),
    ]
    start_row = 5
    for i, (k, v) in enumerate(kpi_rows):
        r = start_row + i
        ws_sum.cell(r, 1, k)
        ws_sum.cell(r, 2, v)
        for c in [ws_sum.cell(r, 1), ws_sum.cell(r, 2)]:
            if i == 0:
                style_header(c)
            else:
                style_row(c, i % 2 == 0)

    set_col_widths(ws_sum, [32, 20])

    # ========================================================================
    # Sayfa 2: Kamyonlar
    # ========================================================================
    ws_tr = wb.create_sheet("Kamyonlar")
    tr_headers = ["ID", "Genişlik (cm)", "Uzunluk (cm)", "Yükseklik (cm)",
                  "Kapasite (kg)", "Adet", "Hacim (m³)"]
    for c, h in enumerate(tr_headers, 1):
        cell = ws_tr.cell(1, c, h)
        style_header(cell)

    for i, t in enumerate(trucks, 2):
        vol = (t.get("Genişlik (cm)", 0) * t.get("Uzunluk (cm)", 0) *
               t.get("Yükseklik (cm)", 0)) / 1e6
        row_vals = [
            t.get("ID", "—"), t.get("Genişlik (cm)", 0), t.get("Uzunluk (cm)", 0),
            t.get("Yükseklik (cm)", 0), t.get("Kapasite (kg)", 0),
            t.get("Adet", 1), round(vol, 3)
        ]
        for c, v in enumerate(row_vals, 1):
            cell = ws_tr.cell(i, c, v)
            style_row(cell, i % 2 == 0)
    set_col_widths(ws_tr, [14, 14, 14, 14, 14, 8, 12])

    # ========================================================================
    # Sayfa 3: Yük Listesi (load_rules varsa tam kurallarla, yoksa eski paletler)
    # ========================================================================
    ws_pl = wb.create_sheet("Yük Listesi")

    _use_lr = load_rules_df is not None and not load_rules_df.empty

    if _use_lr:
        pl_headers = [
            "Kaynak", "ID", "Şekil",
            "G(cm)", "U(cm)", "Y(cm)",
            "Adet", "Ağırlık(kg)", "Müşteri",
            "Altına yük konmasın", "Üstüne yük konmasın",
            "Rotasyon", "Min. Aralık(cm)", "Öncelik",
        ]
        for c, h in enumerate(pl_headers, 1):
            style_header(ws_pl.cell(1, c, h))

        def _bool(val):
            if val is True or str(val).strip().lower() in ("true", "evet", "1"):
                return "Evet"
            return "Hayır"

        for i, (_, row) in enumerate(load_rules_df.iterrows(), 2):
            row_vals = [
                str(row.get("Kaynak", "Manuel") or "Manuel"),
                str(row.get("ID", "—") or "—"),
                str(row.get("Şekil", "Dikdörtgen") or "Dikdörtgen"),
                round(float(row.get("G(cm)", 0) or 0), 1),
                round(float(row.get("U(cm)", 0) or 0), 1),
                round(float(row.get("Y(cm)", 0) or 0), 1),
                int(row.get("Adet", 1) or 1),
                round(float(row.get("Ağırlık(kg)", 0) or 0), 1),
                str(row.get("Müşteri", "") or ""),
                _bool(row.get("Altına yerleştirilemez", False)),
                _bool(row.get("Üstüne yerleştirilemez", False)),
                _bool(row.get("Rotasyon", True)),
                int(row.get("Min. Aralık (cm)", 0) or 0),
                str(row.get("Öncelik", "") or ""),
            ]
            for c, v in enumerate(row_vals, 1):
                cell = ws_pl.cell(i, c, v)
                style_row(cell, i % 2 == 0)
        set_col_widths(ws_pl, [10, 12, 14, 9, 9, 9, 7, 12, 16, 18, 18, 10, 14, 10])
    else:
        # Geriye dönük uyumluluk: eski df_pallets verisi
        pl_headers = ["ID", "Şekil", "Genişlik(cm)", "Uzunluk(cm)", "Yükseklik(cm)",
                      "Ağırlık(kg)", "Adet", "Müşteri"]
        for c, h in enumerate(pl_headers, 1):
            style_header(ws_pl.cell(1, c, h))
        for i, p in enumerate(pieces, 2):
            row_vals = [
                p.get("ID", "—"), p.get("Şekil", "Dikdörtgen"),
                p.get("Genişlik (cm)", 0), p.get("Uzunluk (cm)", 0),
                p.get("Yükseklik (cm)", 0), p.get("Ağırlık (kg)", 0),
                p.get("Adet", 1), p.get("Müşteri", "") or "",
            ]
            for c, v in enumerate(row_vals, 1):
                style_row(ws_pl.cell(i, c, v), i % 2 == 0)
        set_col_widths(ws_pl, [14, 14, 14, 14, 14, 14, 8, 16])

    # ========================================================================
    # Sayfa 4: Karşılaştırma
    # ========================================================================
    # ── Araç başına doluluk (R-a) ───────────────────────────────────────
    _arac_sat = results.get(best_algo, {}).get("arac_satirlari") or []
    if _arac_sat:
        ws_dol = wb.create_sheet("Araç Doluluk")
        _dh = ["Araç", "Parça", "U_G (hacim)", "U_BB (dış kutu)",
               "U_W (ağırlık)", "Bağlayıcı", "Yük (kg)", "Faydalı yük (kg)"]
        for c, h in enumerate(_dh, 1):
            style_header(ws_dol.cell(1, c, h))
        for i, _r in enumerate(_arac_sat, 2):
            for c, h in enumerate(_dh, 1):
                ws_dol.cell(i, c, _r[h])
        ws_dol.cell(len(_arac_sat) + 3, 1,
                    "Hacim doluluğu gerçek parça hacmiyle, ağırlık doluluğu "
                    "faydalı yüke göre hesaplanır. Yük kütlesine palet "
                    "darası dâhildir.")
        for col, w in zip("ABCDEFGH", (26, 8, 13, 16, 14, 12, 12, 16)):
            ws_dol.column_dimensions[col].width = w

    ws_cmp = wb.create_sheet("Karşılaştırma")
    cmp_headers = ["Algoritma", "Kamyon", "Yerleşen", "Toplam",
                   "U_G hacim (%)", "U_BB dış kutu (%)", "U_W ağırlık (%)",
                   "Bağlayıcı", "Fire (m³)", "Süre (sn)"]
    for c, h in enumerate(cmp_headers, 1):
        style_header(ws_cmp.cell(1, c, h))

    for i, (algo, r) in enumerate(
            sorted(results.items(), key=lambda x: -x[1].get("utilization", 0)), 2):
        row_vals = [
            algo,
            r.get("truck_count", "—"),
            r.get("placed", "—"),
            r.get("total_req", "—"),
            round(r.get("utilization", 0), 1),
            (round(r["u_bb"], 1) if r.get("u_bb") is not None else "—"),
            (round(r["u_w"], 1) if r.get("u_w") is not None else "—"),
            r.get("baglayici") or "—",
            round(r.get("waste_cm3", 0) / 1e6, 3),
            round(r.get("execution_time", 0), 2),
        ]
        for c, v in enumerate(row_vals, 1):
            cell = ws_cmp.cell(i, c, v)
            if algo == best_algo:
                cell.fill = accent_fill
                cell.font = Font(bold=True, size=9)
            else:
                style_row(cell, i % 2 == 0)
            cell.alignment = center_aln
            cell.border = thin_border

    # Bar chart — doluluk karşılaştırması
    if len(results) > 1:
        chart = BarChart()
        chart.type = "col"
        chart.title = "Doluluk Oranı Karşılaştırması (%)"
        chart.y_axis.title = "Doluluk (%)"
        chart.x_axis.title = "Algoritma"
        chart.style = 10
        chart.width = 16
        chart.height = 10
        data = Reference(ws_cmp, min_col=5, max_col=5,
                         min_row=1, max_row=len(results)+1)
        cats = Reference(ws_cmp, min_col=1, min_row=2, max_row=len(results)+1)
        chart.add_data(data, titles_from_data=True)
        chart.set_categories(cats)
        ws_cmp.add_chart(chart, "I2")

    set_col_widths(ws_cmp, [22, 10, 10, 10, 14, 12, 12])

    # ========================================================================
    # Sayfa 5: Yükleme Talimatı (seçilen plan) — ortak yardımcı kullanır
    # ========================================================================
    if best_plan is not None and hasattr(best_plan, "bins") and best_plan.bins:
        _add_loading_sheet(wb, "Yükleme Talimatı", project_name,
                           best_plan, trucks, piece_info or {})

    # ── Buffer'a yaz ──────────────────────────────────────────────────────────
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ============================================================================
# GENEL RAPOR — koşulan TÜM algoritmalar tek çalışma kitabında
# ============================================================================

def generate_comparison_excel(
    project_name:  str,
    company_name:  str,
    trucks:        List[dict],
    pieces:        List[dict],
    results:       Dict[str, Any],      # {algo: {utilization, placed, ...}}
    best_algo:     str,
    plans_by_algo: Dict[str, Any],      # {algo: CuttingPlan3D}
    piece_info=None,
) -> bytes:
    """
    GENEL BİLGİLENDİRME RAPORU: o koşuda çalıştırılan bütün algoritmalar.

    · "Genel Özet"      — karşılaştırma tablosu (en iyi ★) + doluluk grafiği
    · Her algoritma için ayrı "Yükleme Talimatı" sayfası (plan detayı)
    """
    wb = openpyxl.Workbook()
    S = _xl_styles()

    def style_header(cell):
        cell.fill = S["hdr_fill"]; cell.font = S["hdr_font"]
        cell.alignment = S["center"]; cell.border = S["border"]

    def style_row(cell, even=True, highlight=False):
        cell.fill = S["accent_fill"] if highlight else (
            S["sub_fill"] if even else S["white_fill"])
        cell.font = Font(bold=True, size=9) if highlight else S["norm_font"]
        cell.alignment = S["center"]; cell.border = S["border"]

    # ── Sayfa 1: Genel Özet ──────────────────────────────────────────────
    ws = wb.active
    ws.title = "Genel Özet"
    ws["A1"] = f"LoadPlan Pro — Genel Karşılaştırma Raporu"
    ws["A1"].font = Font(bold=True, size=14, color=XLSX_HEADER)
    ws["A2"] = f"{company_name}  |  Proje: {project_name}"
    ws["A2"].font = Font(bold=True, size=11)
    ws["A3"] = (f"Tarih: {datetime.now().strftime('%d.%m.%Y %H:%M')}  |  "
                f"Koşulan algoritma: {len(results)}  |  En iyi: ★ {best_algo}")
    ws["A3"].font = Font(italic=True, size=9, color="546E7A")

    headers = ["Algoritma", "Kamyon", "Yerleşen", "Toplam",
               "Doluluk (%)", "Fire (m³)", "Süre (sn)"]
    for c, h in enumerate(headers, 1):
        style_header(ws.cell(5, c, h))

    _sorted = sorted(results.items(),
                     key=lambda x: (-x[1].get("placed", 0),
                                    x[1].get("truck_count", 0),
                                    -x[1].get("utilization", 0)))
    for i, (algo, r) in enumerate(_sorted, 6):
        is_best = (algo == best_algo)
        row_vals = [
            ("★ " if is_best else "") + algo,
            r.get("truck_count", "—"),
            r.get("placed", "—"),
            r.get("total_req", "—"),
            round(r.get("utilization", 0), 1),
            round(r.get("waste_cm3", 0) / 1e6, 3),
            round(r.get("execution_time", 0), 2),
        ]
        for c, v in enumerate(row_vals, 1):
            style_row(ws.cell(i, c, v), i % 2 == 0, highlight=is_best)

    if len(results) > 1:
        chart = BarChart()
        chart.type = "col"
        chart.title = "Doluluk Oranı Karşılaştırması (%)"
        chart.y_axis.title = "Doluluk (%)"
        chart.style = 10
        chart.width = 16
        chart.height = 9
        data = Reference(ws, min_col=5, max_col=5,
                         min_row=5, max_row=5 + len(results))
        cats = Reference(ws, min_col=1, min_row=6, max_row=5 + len(results))
        chart.add_data(data, titles_from_data=True)
        chart.set_categories(cats)
        ws.add_chart(chart, f"A{8 + len(results)}")

    for col, w in enumerate([26, 10, 10, 10, 13, 11, 11], 1):
        ws.column_dimensions[get_column_letter(col)].width = w

    # ── Her algoritma için yükleme talimatı sayfası ──────────────────────
    _used_names: set = set()
    for algo, plan in plans_by_algo.items():
        if plan is None or not getattr(plan, "bins", None):
            continue
        sheet = _safe_sheet_name(("★ " if algo == best_algo else "") + algo,
                                 _used_names)
        _add_loading_sheet(wb, sheet, project_name, plan, trucks,
                           piece_info or {})

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ============================================================================
# R5 FIX — SÜRÜCÜ YÜKLEME TALİMATI PDF (Sıra No + QR Kod)
# ============================================================================

def _make_qr_image(data: str, size_cm: float = 1.2) -> "Optional[object]":
    """
    Verilen metni QR koda çevir, ReportLab Image objesi olarak döndür.
    qrcode kütüphanesi yoksa None döner.
    """
    try:
        import qrcode
        from reportlab.platypus import Image
        from reportlab.lib.units import cm as _cm
    except ImportError:
        return None
    qr = qrcode.QRCode(
        version=1, error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=8, border=1,
    )
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return Image(buf, width=size_cm * _cm, height=size_cm * _cm)


def _compute_loading_order(placements: List[dict]) -> List[int]:
    """
    Yükleme sırası (fiziksel satır-katman mantığı).

    EKSEN KONVANSİYONU: Kapı Y = maks (uzunluk) tarafındadır; priority=1
    bölgesi (y >= 0.70·L) "kapıya en yakın"dır. Yükleme kapıdan yapıldığı
    için ilk ürün kapıdan EN UZAK noktaya (kabin tarafı, Y=0) yerleşir:
      1) Y artan   — kabin tarafından başla (kapıdan uzak = önce yükle)
      2) Z artan   — o satırın alt katmanı önce, üst katmanı hemen ardından
      3) X artan   — aynı Y+Z seviyesinde soldan sağa (tiebreaker)

    Sonuç: kabin tarafı alt katman → üst katman → bir sıra kapıya doğru →
           … → kapıya en yakın (öncelikli) ürün EN SON yüklenir (LIFO).

    Returns:
        placements listesinin her elemanı için sıra numarası (1-based) listesi
    """
    indexed = list(enumerate(placements))
    indexed.sort(key=lambda ix: (
         ix[1].get("y", 0),    # kabin tarafı önce (kapıdan uzak)
         ix[1].get("z", 0),    # alt katman önce
         ix[1].get("x", 0),    # soldan sağa tiebreaker
    ))
    # Sıra numarası map'i: orig_index → load_order (1-based)
    order_map = {}
    for load_order, (orig_index, _) in enumerate(indexed, start=1):
        order_map[orig_index] = load_order
    return [order_map[i] for i in range(len(placements))]


def generate_loading_sheet_pdf(
    project_name: str,
    company_name: str,
    bins_data: List[Dict[str, Any]],     # [{truck_id, truck_dims, placements: [...]}]
    piece_info: Dict[str, dict],         # piece_id → {name, weight, fragile, priority, ...}
    include_qr: bool = True,
    qr_prefix: str = "LP",                # QR data prefix (LP-{project_id}-{piece_id}-{bin})
) -> bytes:
    """
    Sürücü için yükleme talimatı PDF'i — her araç için ayrı sayfa.

    Args:
        project_name : Proje adı (başlıkta)
        company_name : Şirket adı (başlıkta)
        bins_data    : Her bin için
                       { "truck_id": str, "truck_dims": (w,l,h),
                         "placements": [{"piece_id": str, "x": int, "y": int,
                                         "z": int, "width": int, "length": int,
                                         "height": int, ...}, ...] }
        piece_info   : piece_id → meta (name, weight, fragile, priority)
        include_qr   : QR kod ekle (qrcode kütüphanesi gerekli)
        qr_prefix    : QR içeriğinde kullanılan ön ek

    Returns:
        PDF bytes
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=1.5*cm, rightMargin=1.5*cm,
        topMargin=1.8*cm,  bottomMargin=1.8*cm,
        title=f"Yükleme Talimatı — {project_name}",
        author=company_name,
    )

    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("LH1", parent=styles["Heading1"],
                         fontName=_TR_FONT_BOLD,
                         fontSize=16, textColor=BRAND_BLUE,
                         spaceAfter=4, spaceBefore=4)
    h2 = ParagraphStyle("LH2", parent=styles["Heading2"],
                         fontName=_TR_FONT_BOLD,
                         fontSize=12, textColor=BRAND_BLUE,
                         spaceAfter=2, spaceBefore=6)
    body = ParagraphStyle("LBody", parent=styles["Normal"],
                           fontName=_TR_FONT,
                           fontSize=9, leading=12)
    caption = ParagraphStyle("LCap", parent=styles["Normal"],
                              fontName=_TR_FONT,
                              fontSize=7, textColor=BRAND_GRAY)

    elements: List = []
    W = 17.5 * cm

    # ── BAŞLIK ──────────────────────────────────────────────────────────
    elements.append(Paragraph(
        f"🚛 Sürücü Yükleme Talimatı — {project_name}", h1
    ))
    elements.append(HRFlowable(width=W, thickness=1.5, color=BRAND_BLUE))
    elements.append(Paragraph(
        f"<b>{company_name}</b>  |  "
        f"Oluşturulma: {datetime.now().strftime('%d.%m.%Y %H:%M')}  |  "
        f"Toplam araç: {len(bins_data)}",
        caption
    ))
    elements.append(Spacer(1, 0.4*cm))

    # ── YÜKLEME TALİMATI (Önemli Notlar) ────────────────────────────────
    elements.append(Paragraph(
        "📋 <b>Önemli:</b> Parçalar belirtilen sıra ile yüklenmelidir. "
        "1 numaralı parça aracın <b>kapıdan en uzak (kabin) tarafına</b>, "
        "son numara <b>kapıya en yakın</b> yerleşir. "
        "Kırılgan ve ağır parçalar ayrıca işaretlenmiştir.",
        body
    ))
    elements.append(Spacer(1, 0.3*cm))

    # ── HER ARAÇ İÇİN AYRI BÖLÜM ─────────────────────────────────────────
    for bin_idx, bin_data in enumerate(bins_data):
        truck_id = bin_data.get("truck_id", f"V{bin_idx+1}")
        placements = bin_data.get("placements", [])
        truck_dims = bin_data.get("truck_dims", (0, 0, 0))

        if not placements:
            continue

        # Yeni sayfa (ilk araç hariç)
        if bin_idx > 0:
            from reportlab.platypus import PageBreak
            elements.append(PageBreak())

        # Araç başlığı
        elements.append(Paragraph(
            f"🚛 Araç {bin_idx + 1}: <b>{truck_id}</b>  "
            f"({truck_dims[0]}×{truck_dims[1]}×{truck_dims[2]} cm)",
            h2
        ))
        elements.append(Paragraph(
            f"<b>Toplam parça:</b> {len(placements)}  |  "
            f"<b>Yükleme sırası:</b> Numara küçükten büyüğe",
            body
        ))
        elements.append(Spacer(1, 0.2*cm))

        # Yükleme sırasını hesapla
        load_order = _compute_loading_order(placements)

        # Tablo başlığı
        if include_qr:
            header = ["Sıra", "QR", "Parça ID", "Konum (X,Y,Z)", "Boyut (G×U×Y)",
                      "Ağırlık", "Dikkat"]
            col_widths = [1.2*cm, 1.5*cm, 3*cm, 3.2*cm, 3*cm, 1.6*cm, 3.5*cm]
        else:
            header = ["Sıra", "Parça ID", "Konum (X,Y,Z)", "Boyut (G×U×Y)",
                      "Ağırlık", "Dikkat"]
            col_widths = [1.2*cm, 3.5*cm, 3.5*cm, 3.5*cm, 1.8*cm, 3.5*cm]

        table_rows = [header]

        # Placements'ı load_order'a göre sırala
        sorted_items = sorted(
            zip(load_order, placements),
            key=lambda pair: pair[0]
        )

        for order_no, pl in sorted_items:
            pid = pl.get("piece_id", "—")
            piece_meta = piece_info.get(pid, {})

            # Dikkat notu
            notes = []
            if piece_meta.get("is_fragile") or piece_meta.get("fragile"):
                notes.append("⚠ Kırılgan")
            # Excel sayfasıyla tutarlı: priority int VEYA string gelebilir
            if str(piece_meta.get("priority", "")).strip() == "1":
                notes.append("🚪 Öncelik — kapıya yakın, EN SON yükle")
            weight = piece_meta.get("weight", 0)
            if weight >= 200:
                notes.append(f"🏋 {weight:.0f} kg")
            note_str = " · ".join(notes) if notes else "—"

            pos_str = f"({pl.get('x', 0)}, {pl.get('y', 0)}, {pl.get('z', 0)})"
            dim_str = f"{pl.get('width', 0)}×{pl.get('length', 0)}×{pl.get('height', 0)}"
            wgt_str = f"{weight:.0f} kg" if weight else "—"

            if include_qr:
                qr_data = f"{qr_prefix}|{truck_id}|{pid}|{pl.get('x',0)},{pl.get('y',0)},{pl.get('z',0)}"
                qr_img = _make_qr_image(qr_data, size_cm=1.2)
                row = [str(order_no), qr_img if qr_img else "—",
                       pid, pos_str, dim_str, wgt_str, note_str]
            else:
                row = [str(order_no), pid, pos_str, dim_str, wgt_str, note_str]
            table_rows.append(row)

        # Tablo
        t = Table(table_rows, colWidths=col_widths)
        t.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, 0),  BRAND_BLUE),
            ("TEXTCOLOR",     (0, 0), (-1, 0),  colors.white),
            ("FONTNAME",      (0, 0), (-1, 0),  _TR_FONT_BOLD),
            ("FONTNAME",      (0, 1), (-1, -1), _TR_FONT),
            ("FONTSIZE",      (0, 0), (-1, 0),  8),
            ("FONTSIZE",      (0, 1), (-1, -1), 8),
            ("ALIGN",         (0, 0), (0, -1),  "CENTER"),   # Sıra ortalı
            ("ALIGN",         (1, 0), (1, -1),  "CENTER"),   # QR ortalı
            ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
            ("ROWBACKGROUNDS",(0, 1), (-1, -1), [colors.white, BRAND_LIGHT]),
            ("GRID",          (0, 0), (-1, -1), 0.5, BRAND_GRAY),
            ("TOPPADDING",    (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        elements.append(t)
        elements.append(Spacer(1, 0.3*cm))

        # Sayfa altı uyarı
        elements.append(Paragraph(
            "📌 X = sol-sağ, Y = kabinden (0) kapıya doğru artar, Z = alt-üst. "
            "Tüm ölçüler cm cinsinden.",
            caption
        ))

    # ── GENEL SAYFA SONU ─────────────────────────────────────────────────
    elements.append(Spacer(1, 0.5*cm))
    elements.append(HRFlowable(width=W, thickness=1, color=BRAND_BLUE))
    elements.append(Paragraph(
        f"LoadPlan Pro — {company_name}  |  "
        f"Sürücü Talimat Belgesi  |  "
        f"{datetime.now().strftime('%d.%m.%Y %H:%M')}",
        caption
    ))

    doc.build(elements)
    return buf.getvalue()


def build_bins_data_from_plan(plan, trucks: list) -> List[Dict[str, Any]]:
    """
    Algoritma çıktısı CuttingPlan3D'den generate_loading_sheet_pdf için
    bins_data oluştur.

    Args:
        plan   : CuttingPlan3D
        trucks : Truck3D listesi

    Returns:
        [{ "truck_id": str, "truck_dims": (w,l,h), "placements": [...] }]
    """
    trucks_by_id = {t.id: t for t in trucks}
    bins_data: List[Dict[str, Any]] = []
    for bin_idx, bin_placements in enumerate(plan.bins or []):
        if not bin_placements:
            continue
        truck_id = (plan.truck_assignments or {}).get(bin_idx, f"V{bin_idx+1}")
        truck = trucks_by_id.get(truck_id)
        truck_dims = (truck.width, truck.length, truck.height) if truck else (0, 0, 0)
        bins_data.append({
            "truck_id": truck_id,
            "truck_dims": truck_dims,
            "placements": [
                {
                    "piece_id": pl.piece_id,
                    "x": pl.x, "y": pl.y, "z": pl.z,
                    "width": pl.width, "length": pl.length, "height": pl.height,
                    "rotation": pl.rotation,
                }
                for pl in bin_placements
            ],
        })
    return bins_data
