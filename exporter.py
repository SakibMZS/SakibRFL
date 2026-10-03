"""
exporter.py  -  Excel exports.

Every export carries its data-quality status:
  * summary tables : footer line + a 'Data Quality' sheet
  * master ledger  : a 'Data Quality' sheet (no footer, so the data block stays clean for re-use)
Master ledger rows are written contiguously (no blank rows), at full precision, with real date cells.
"""
import io
from datetime import datetime

import openpyxl
import pandas as pd
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

_HDR_FILL = PatternFill(start_color="FFFF00", end_color="FFFF00", fill_type="solid")
_HDR_FONT = Font(name="Calibri", size=11, bold=True, color="000000")
_DATA_FONT = Font(name="Calibri", size=11, color="000000")
_TOT_FONT = Font(name="Calibri", size=11, bold=True, color="FF0000")
_THIN = Side(border_style="thin", color="BFBFBF")
_CELL_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)
_TOT_BORDER = Border(left=_THIN, right=_THIN, top=Side(border_style="thin", color="000000"), bottom=Side(border_style="double", color="000000"))
_RED = Font(name="Calibri", size=11, bold=True, color="C00000")
_GREEN = Font(name="Calibri", size=11, bold=True, color="2E7D32")
_BLUE_HDR = PatternFill(start_color="DDEBF7", end_color="DDEBF7", fill_type="solid")


def quality_pack(health, floor_label="ALL FLOORS"):
    """Condenses the health report into what the Excel exports need."""
    if not health:
        return None
    ri = health["row_issues"]
    open_ri = ri[(ri["Status"] == "Open") & ri["Severity"].isin(["Error", "Warning"])] if not ri.empty else ri
    fi = health["file_issues"]
    fi_act = fi[fi["Severity"].isin(["Error", "Warning"])] if not fi.empty else fi
    return {
        "counts": health["counts"],
        "period": health["period"]["label"] if health.get("period") else "",
        "generated": datetime.now().strftime("%d-%m-%Y %H:%M"),
        "floor": floor_label,
        "open_rows": open_ri,
        "file_issues": fi_act,
        "coverage": health["coverage"],
        "recon": health["recon"],
    }


def _write_df(ws, df, start_row=1, header_fill=None):
    for j, name in enumerate(df.columns, 1):
        c = ws.cell(row=start_row, column=j, value=str(name))
        c.font = _HDR_FONT
        c.fill = header_fill or _BLUE_HDR
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = _CELL_BORDER
    for i, row in enumerate(df.itertuples(index=False), start_row + 1):
        for j, v in enumerate(row, 1):
            if isinstance(v, float) and pd.isna(v):
                v = None
            if hasattr(v, "item"):
                v = v.item()
            c = ws.cell(row=i, column=j, value=v)
            c.font = _DATA_FONT
            c.border = _CELL_BORDER
    return start_row + len(df) + 1


def _autowidth(ws, cap=70, minimum=10):
    for col in ws.columns:
        longest = max((len(str(c.value)) for c in col if c.value is not None), default=0)
        ws.column_dimensions[get_column_letter(col[0].column)].width = min(max(longest + 3, minimum), cap)


def write_quality_sheet(wb, q):
    ws = wb.create_sheet("Data Quality")
    c = q["counts"]
    ws["A1"] = f"Data Quality - {q['period']} ({q['floor']})"
    ws["A1"].font = Font(name="Calibri", size=14, bold=True)
    ws["A2"] = f"Generated: {q['generated']}"
    status = "NO open data issues" if c["open"] == 0 else f"{c['errors']} error(s) and {c['warnings']} warning(s) are still open - figures may be affected"
    ws["A3"] = status
    ws["A3"].font = _GREEN if c["open"] == 0 else _RED
    ws["A4"] = f"Reviewed (accepted) items: {c['reviewed']}"
    r = 6

    def block(title, df):
        nonlocal r
        ws.cell(row=r, column=1, value=title).font = Font(name="Calibri", size=12, bold=True)
        r += 1
        if df is None or df.empty:
            ws.cell(row=r, column=1, value="None").font = _DATA_FONT
            r += 2
            return
        r = _write_df(ws, df.reset_index(drop=True), start_row=r) + 1

    fi = q["file_issues"]
    block("Day / sheet level problems", fi[["Severity", "Category", "Floor", "Date", "Detail"]] if not fi.empty else fi)
    rc = q["recon"]
    block("Reconciliation: sheet pieces vs report pieces",
          rc[["Floor", "Date", "Sheet", "Sheet Good", "Parsed Good", "Lost in parsing", "Excluded by you", "Edited by you", "Final Good", "Check"]] if not rc.empty else rc)
    orows = q["open_rows"]
    block("Open row-level issues",
          orows[["Severity", "Category", "Floor", "Date", "Sheet", "Src Row", "Machine", "Order", "Item", "Detail"]] if not orows.empty else orows)
    _autowidth(ws)
    return ws


def _footer(ws, last_row, ncols, q):
    if not q:
        return
    row = last_row + 2
    c = q["counts"]
    ws.cell(row=row, column=1, value=f"Period: {q['period']}  |  View: {q['floor']}  |  Generated: {q['generated']}").font = Font(name="Calibri", size=10, italic=True)
    msg = "No open data issues." if c["open"] == 0 else (
        f"WARNING: exported with {c['errors']} open error(s) and {c['warnings']} open warning(s) - see the 'Data Quality' sheet.")
    cell = ws.cell(row=row + 1, column=1, value=msg)
    cell.font = _GREEN if c["open"] == 0 else _RED


def convert_df_to_excel_bytes(df, quality=None):
    """Summary-table export (values arrive pre-formatted from clean_and_format_dataframe)."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Report"
    for j, name in enumerate(df.columns, 1):
        c = ws.cell(row=1, column=j, value=name)
        c.fill, c.font, c.border = _HDR_FILL, _HDR_FONT, _CELL_BORDER
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    df = df.reset_index(drop=True)
    for i, row in df.iterrows():
        r = i + 2
        is_total = any("sub total" in str(v).lower() for v in row.values)
        for j, (col, val) in enumerate(row.items(), 1):
            cell = ws.cell(row=r, column=j)
            lc = str(col).lower()
            cell.font = _TOT_FONT if is_total else _DATA_FONT
            cell.border = _TOT_BORDER if is_total else _CELL_BORDER
            s = str(val).strip()
            if isinstance(val, (int, float)) and not isinstance(val, bool) and pd.notna(val):
                cell.value = val
                cell.number_format = "#,##0" if any(k in lc for k in ["qty", "pcs", "good", "due", "demand", "produced", "bad", "rej"]) else "#,##0.00"
                cell.alignment = Alignment(horizontal="right", vertical="center")
                continue
            plain = s.replace(",", "").replace("%", "")
            try:
                num = float(plain)
                if "%" in s:
                    cell.value, cell.number_format = num / 100.0, "0.00%"
                elif plain.lstrip("-").isdigit() and not (len(plain) > 1 and plain.startswith("0")):
                    cell.value, cell.number_format = int(plain), "#,##0"
                else:
                    cell.value, cell.number_format = num, "#,##0.00"
                cell.alignment = Alignment(horizontal="right", vertical="center")
            except ValueError:
                cell.value = None if s in ("nan", "None") else s
                centered = is_total or lc in ["acc code", "status", "date", "mc sl"]
                cell.alignment = Alignment(horizontal="center" if centered else "left", vertical="center")
    _autowidth(ws, cap=60, minimum=12)
    _footer(ws, len(df) + 1, len(df.columns), quality)
    if quality:
        write_quality_sheet(wb, quality)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


MASTER_COLUMNS = ["Date", "MC SL", "Order Name", "Acc Code", "Item Name", "Unit Wt", "Color", "Cavity", "CT",
                  "STD Cap/Shift", "A Total", "A Good", "B Total", "B Good", "T-Good", "T-Bad"]


def master_frame(df_curr):
    """Rows with production, in floor-block order (FF then GF), by date then sheet order."""
    d = df_curr[df_curr["T-Good"] > 0].copy()
    d = d.sort_values(["Floor", "DateObj", "Src Row"], kind="stable").reset_index(drop=True)
    return d


def build_master_workbook(df_curr, quality=None):
    d = master_frame(df_curr)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Details"
    for j, name in enumerate(MASTER_COLUMNS, 1):
        c = ws.cell(row=1, column=j, value=name)
        c.fill, c.font, c.border = _HDR_FILL, _HDR_FONT, _CELL_BORDER
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.freeze_panes = "A2"

    ints = {"A Total", "A Good", "B Total", "B Good", "T-Good", "T-Bad"}
    cols = {name: ("DateObj" if name == "Date" else name) for name in MASTER_COLUMNS}
    for j, name in enumerate(MASTER_COLUMNS, 1):
        series = d[cols[name]]
        for i, v in enumerate(series.tolist(), 2):
            cell = ws.cell(row=i, column=j)
            cell.font, cell.border = _DATA_FONT, _CELL_BORDER
            if name == "Date":
                cell.value = v.to_pydatetime() if hasattr(v, "to_pydatetime") else v
                cell.number_format = "dd-mm-yyyy"
                cell.alignment = Alignment(horizontal="center")
            elif name == "Acc Code":
                sv = str(v)
                cell.value = int(sv) if sv.isdigit() else sv
                cell.alignment = Alignment(horizontal="center")
            elif name in ("MC SL", "Order Name", "Item Name", "Color"):
                cell.value = v
            else:
                cell.value = None if (isinstance(v, float) and pd.isna(v)) else float(v)
                if name in ints:
                    cell.number_format = "#,##0"
                elif name == "STD Cap/Shift":
                    cell.number_format = "#,##0.00"
                else:
                    cell.number_format = "General"  # full precision (Unit Wt, CT, Cavity)
    _autowidth(ws, cap=55, minimum=10)
    if quality:
        write_quality_sheet(wb, quality)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue(), len(d)
