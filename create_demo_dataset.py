from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side, PatternFill
from openpyxl.utils import get_column_letter

OUTPUT = r"C:\Users\Sude\Downloads\loadplan_fixed_v24 (1) (1)\loadplan_fixed_v24\enterprise_backup_20260410\demo_dataset.xlsx"

HEADER_FONT = Font(name="Arial", bold=True, color="FFFFFFFF")
HEADER_FILL = PatternFill("solid", fgColor="FF1F3864")
HEADER_ALIGN = Alignment(horizontal="center", vertical="center")

FILL_WHITE = PatternFill("solid", fgColor="FFFFFFFF")
FILL_BLUE  = PatternFill("solid", fgColor="FFEBF3FB")

DATA_FONT = Font(name="Arial")
DATA_ALIGN = Alignment(horizontal="center", vertical="center")

THIN = Side(style="thin")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)


def style_header(cell):
    cell.font = HEADER_FONT
    cell.fill = HEADER_FILL
    cell.alignment = HEADER_ALIGN
    cell.border = BORDER


def style_data(cell, row_idx):
    cell.font = DATA_FONT
    cell.fill = FILL_WHITE if row_idx % 2 == 1 else FILL_BLUE
    cell.alignment = DATA_ALIGN
    cell.border = BORDER


def autofit(ws, min_width=14):
    for col_cells in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col_cells[0].column)
        for cell in col_cells:
            try:
                val = str(cell.value) if cell.value is not None else ""
                max_len = max(max_len, len(val))
            except Exception:
                pass
        ws.column_dimensions[col_letter].width = max(max_len + 2, min_width)


wb = Workbook()

# ── Sheet 1: Araçlar ───────────────────────────────────────────────────────────
ws1 = wb.active
ws1.title = "Araçlar"
ws1.sheet_properties.tabColor = "FF2F75B6"

arac_headers = ["ID", "Genişlik (cm)", "Uzunluk (cm)", "Yükseklik (cm)", "Kapasite (kg)", "Adet"]
ws1.append(arac_headers)
ws1.row_dimensions[1].height = 22
for cell in ws1[1]:
    style_header(cell)

arac_data = [
    ["Tır-1",    240, 600, 200, 20000, 2],
    ["Tır-2",    240, 420, 200, 13000, 1],
    ["Kamyon-1", 220, 260, 180,  5000, 1],
]
for row_idx, row in enumerate(arac_data, start=1):
    ws1.append(row)
    excel_row = row_idx + 1
    ws1.row_dimensions[excel_row].height = 18
    for cell in ws1[excel_row]:
        style_data(cell, row_idx)

autofit(ws1)
ws1.freeze_panes = "A2"

# ── Sheet 2: Yükler ────────────────────────────────────────────────────────────
ws2 = wb.create_sheet("Yükler")
ws2.sheet_properties.tabColor = "FF375623"

yuk_headers = [
    "ID", "Genişlik (cm)", "Uzunluk (cm)", "Yükseklik (cm)",
    "Ağırlık (kg)", "Adet", "Müşteri",
    "Altına yerleştirilemez", "Üstüne yerleştirilemez",
    "Rotasyon", "Min. Aralık (cm)", "Öncelik"
]
ws2.append(yuk_headers)
ws2.row_dimensions[1].height = 22
for cell in ws2[1]:
    style_header(cell)

yuk_data = [
    ["Euro-Palet-A",   80,  120, 100,  450,  6, "Müşteri-A", False, False, True,  0, None],
    ["Euro-Palet-B",   80,  120,  80,  380,  4, "Müşteri-A", False, False, True,  0, None],
    ["Koli-Büyük",     60,   80,  60,  120,  8, "Müşteri-B", False, False, True,  0, None],
    ["Koli-Orta",      40,   60,  40,   55, 10, "Müşteri-B", False, False, True,  0, None],
    ["Koli-Küçük",     30,   40,  30,   20, 12, "Müşteri-C", False, False, True,  0, None],
    ["Makine-A",      120,  180, 140, 2800,  1, "Müşteri-D", True,  False, False, 0, None],
    ["Makine-B",      100,  150, 120, 1950,  1, "Müşteri-D", True,  False, False, 0, None],
    ["Cam-Kasa",       80,  100, 120,  340,  2, "Müşteri-E", False, True,  False, 5,    1],
    ["Elektronik",     60,   80,  70,   95,  5, "Müşteri-E", False, True,  True,  0,    1],
    ["Mobilya-A",      90,  200, 100,  680,  2, "Müşteri-F", False, False, True,  0, None],
    ["Mobilya-B",      70,  160,  80,  420,  2, "Müşteri-F", False, False, True,  0, None],
    ["Metal-Parça",    80,  140,  60,  890,  3, "Müşteri-G", False, False, True,  0, None],
    ["Tekstil-Balya", 100,  120,  90,  210,  4, "Müşteri-G", False, False, True,  0, None],
    ["İçecek-Koli",    40,   60,  50,  180, 15, "Müşteri-H", False, False, True,  0,    2],
    ["Gıda-Koli",      50,   70,  60,  140, 10, "Müşteri-H", False, False, True,  0,    2],
    ["Kimyasal-Varil", 58,   58,  90,  220,  4, "Müşteri-I", True,  False, False, 5, None],
    ["Ağır-Ekipman",  140,  200, 160, 4200,  1, "Müşteri-J", True,  False, False, 0, None],
    ["Plastik-Kasa",   60,   80,  50,   75,  8, "Müşteri-J", False, False, True,  0, None],
    ["Kağıt-Top",     100,  100, 120,  310,  3, "Müşteri-K", False, False, True,  0, None],
    ["Demir-Profil",   10,  600,   8,  480,  2, "Müşteri-K", False, False, False, 0, None],
]

for row_idx, row in enumerate(yuk_data, start=1):
    ws2.append(row)
    excel_row = row_idx + 1
    ws2.row_dimensions[excel_row].height = 18
    for cell in ws2[excel_row]:
        style_data(cell, row_idx)

autofit(ws2)
ws2.freeze_panes = "A2"

wb.save(OUTPUT)
print(f"Saved: {OUTPUT}")
