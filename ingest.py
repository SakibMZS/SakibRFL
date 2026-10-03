"""
ingest.py  -  Reads the FF / GF daily production workbooks and NEVER fails silently.

Pipeline
  1. scan_workbook()   : classify every tab (date tab / duplicate variant / inventory-type tab / other)
  2. choose_period()   : month of the latest dated tab, days 1..N are expected
  3. parse_floor()     : read the chosen tab of every day, normalise headers, validate every row,
                         reconcile pieces against the sheet, and return the data + a full audit
  4. build_health()    : merge both floors into one health report (coverage, reconciliation, issues)

Every problem becomes a row in an audit table (Severity = Error / Warning / Info).
Nothing is dropped without a record.  The only things that change numbers are
(a) corrections the user typed in the Data Health screen and (b) rows the user excluded,
and both are shown in the reconciliation table.
"""
import io
import json
import re
from datetime import datetime

import numpy as np
import pandas as pd

from chess import consolidate_chess_family_mold, is_chess_item
from config import EXCEL_SIZES, SORTED_SIZES, get_size_from_position, resolve_machine_info

ERROR, WARN, INFO = "Error", "Warning", "Info"

# ---------------------------------------------------------------------------
# 1. SHEET (TAB) SCANNING
# ---------------------------------------------------------------------------
_DATE_RE = re.compile(r"(?<!\d)(\d{1,2})[-/._\s](\d{1,2})[-/._\s](\d{4}|\d{2})(?!\d)")
_QUARANTINE = ("util", "handover", "inventory", "inv", "pf", "rel", "sheet", "schedule", "need", "pet")


def _scan_names(names):
    out = []
    for pos, name in enumerate(names):
        s = str(name).replace("\xa0", " ").strip()
        rec = {"pos": pos, "name": name, "date": None, "residual": "", "rkey": "", "kind": "non_date", "note": ""}
        m = _DATE_RE.search(s)
        if m:
            d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if y < 100:
                y += 2000
            try:
                if not 2000 <= y <= 2099:
                    raise ValueError("year")
                dt = datetime(y, mo, d)
            except ValueError:
                rec.update(kind="invalid_date", note=f"Tab '{s}' looks like a date but is not a valid calendar date")
            else:
                residual = (s[: m.start()] + " " + s[m.end():]).strip()
                rkey = re.sub(r"[\W_]+", "", residual).lower()
                if rkey == "":
                    kind = "date"
                elif any(k in residual.lower() for k in _QUARANTINE):
                    kind = "quarantined"
                else:
                    kind = "variant"
                rec.update(date=dt, residual=residual, rkey=rkey, kind=kind)
        out.append(rec)
    return out


def scan_workbook(file_bytes):
    xls = pd.ExcelFile(io.BytesIO(file_bytes))
    return _scan_names(xls.sheet_names)


def choose_period(scans):
    """scans: {floor: scan list}.  Period = month of the latest dated tab; days 1..N expected."""
    dates = []
    for sc in scans.values():
        dates += [r["date"] for r in sc if r["kind"] in ("date", "variant")]
    if not dates:
        return None
    latest = max(dates)
    earlier = sorted({d for d in dates if d < latest})
    gap = (latest - earlier[-1]).days if earlier else 0
    return {
        "year": latest.year, "month": latest.month, "last_day": latest.day,
        "latest": latest, "gap_days": gap, "gap_prev": earlier[-1] if earlier else None,
        "label": latest.strftime("%B %Y"),
    }


# ---------------------------------------------------------------------------
# 2. HEADER NORMALISATION
# ---------------------------------------------------------------------------
def _key(h):
    s = str(h).replace("\xa0", " ")
    s = re.sub(r"\s+", " ", s).strip().lower()
    return re.sub(r"[^a-z0-9.]", "", s)


_EXACT = {
    "mcsl": "MC SL", "ordername": "Order Name", "acccode": "Acc Code", "itemname": "Item Name",
    "unitwt": "Unit Wt", "cavity": "Cavity", "ct": "CT", "demand": "Demand",
    "uptoprod": "Up to Prod", "lastdayprod": "Last Day Prod",
    "tcounter": "T Counter", "counter": "Counter", "totalcounterb": "Total Counter B", "counterb": "Counter B",
    "agood": "A Good", "bgood": "B Good", "prodton": "Prod Ton A", "prodtonb": "Prod Ton B",
}
CANON_COLS = [
    "MC SL", "Order Name", "Acc Code", "Item Name", "Unit Wt", "Color", "Cavity", "CT",
    "Demand", "Up to Prod", "Due Prev", "Last Day Prod", "Due Present",
    "A Counter", "A Good", "A Rej", "B Counter", "B Good", "B Rej", "Sheet Ton",
]
REQUIRED = ["MC SL", "Order Name", "Item Name", "Cavity", "CT", "A Good", "B Good"]
OVERRUN_MINOR_LIMIT = 13.0  # derived shift runtime between 12 and this = minor note, above = warning
STRICT_NUM = ["A Good", "B Good", "CT", "Cavity", "Unit Wt"]
SOFT_NUM = ["A Rej", "B Rej", "A Counter", "B Counter"]
LEDGER_NUM = ["Demand", "Up to Prod", "Due Prev", "Due Present", "Last Day Prod"]
_FIELD_OVERRIDE = {"A Good": "a_good", "B Good": "b_good", "CT": "ct", "Cavity": "cavity", "Unit Wt": "unit_wt", "A Rej": "a_rej", "B Rej": "b_rej"}


def _read_sheet(xls, name):
    """Returns (raw_df or None, header_row_index, notes). Finds the header row if it is not row 1."""
    notes = []
    df = pd.read_excel(xls, sheet_name=name)
    hdr = 0
    if "mcsl" not in {_key(c) for c in df.columns}:
        probe = pd.read_excel(xls, sheet_name=name, header=None, nrows=25)
        found = None
        for i in range(len(probe)):
            ks = {_key(v) for v in probe.iloc[i].tolist() if pd.notna(v)}
            if "mcsl" in ks and "ordername" in ks:
                found = i
                break
        if found is None:
            return None, 0, [(ERROR, "Header", f"Tab '{str(name).strip()}': no 'MC SL' / 'Order Name' header row found in the first 25 rows - tab NOT read")]
        df = pd.read_excel(xls, sheet_name=name, header=found)
        hdr = found
        notes.append((INFO, "Header", f"Tab '{str(name).strip()}': header found on Excel row {found + 1}"))
    df = df.copy()
    df["Src Row"] = np.arange(len(df)) + hdr + 2  # Excel row number
    return df, hdr, notes


def _canonicalize(df, sheet):
    """Map raw headers -> canonical names. Returns (canon_df or None, notes)."""
    notes = []
    sname = str(sheet).strip()
    cols = [c for c in df.columns if c != "Src Row"]
    keys = [_key(c) for c in cols]
    colmap, color_cols = {}, []
    for orig, k in zip(cols, keys):
        canon = _EXACT.get(k)
        if canon is None:
            if k.startswith("arejec"):
                canon = "A Rej"
            elif k.startswith("breject"):
                canon = "B Rej"
            elif k.startswith("colo"):  # 'Color' and the corrupted 'Colo+G:AHr'
                color_cols.append(orig)
                continue
        if canon and canon not in colmap:
            colmap[canon] = orig

    # Due columns are matched by POSITION (header text changes day to day):
    #   between 'Up to Prod' and 'Last Day Prod' = previous due ; after 'Last Day Prod' = present due
    up_i = keys.index("uptoprod") if "uptoprod" in keys else None
    ld_i = keys.index("lastdayprod") if "lastdayprod" in keys else None
    due_idx = [i for i, k in enumerate(keys) if "due" in k]
    prev_i = pres_i = None
    if up_i is not None and ld_i is not None:
        between = [i for i in due_idx if up_i < i < ld_i]
        after = [i for i in due_idx if i > ld_i]
        prev_i = between[0] if between else None
        pres_i = after[0] if after else None
    if pres_i is None and due_idx:
        if len(due_idx) >= 2:
            prev_i, pres_i = due_idx[0], due_idx[-1]
        else:
            pres_i = due_idx[0]
        notes.append((WARN, "Header", f"Tab '{sname}': 'Due' columns matched by fallback order, please check"))
    if pres_i is None:
        notes.append((WARN, "Header", f"Tab '{sname}': present-due column not found - due balances unavailable"))
    colmap_due = {"Due Prev": cols[prev_i] if prev_i is not None else None,
                  "Due Present": cols[pres_i] if pres_i is not None else None}

    missing_req = [c for c in REQUIRED if c not in colmap]
    if missing_req:
        shown = ", ".join(str(c).strip() for c in cols[:14])
        notes.append((ERROR, "Header", f"Tab '{sname}': required column(s) {missing_req} not found - tab NOT read. Headers seen: {shown} ..."))
        return None, notes
    miss_rec = [c for c in ["Unit Wt", "Demand", "Up to Prod", "A Rej", "B Rej"] if c not in colmap]
    if "T Counter" not in colmap and "Counter" not in colmap:
        miss_rec.append("A Counter")
    if "Total Counter B" not in colmap and "Counter B" not in colmap:
        miss_rec.append("B Counter")
    if miss_rec:
        notes.append((WARN, "Header", f"Tab '{sname}': column(s) {miss_rec} not found - treated as blank"))

    out = pd.DataFrame(index=df.index)
    out["Src Row"] = df["Src Row"].values
    for c in ["MC SL", "Order Name", "Acc Code", "Item Name", "Unit Wt", "Cavity", "CT", "Demand", "Up to Prod",
              "Last Day Prod", "A Good", "A Rej", "B Good", "B Rej"]:
        out[c] = df[colmap[c]] if c in colmap else np.nan
    for c in ["Due Prev", "Due Present"]:
        out[c] = df[colmap_due[c]] if colmap_due[c] is not None else np.nan
    out["A Counter"] = df[colmap["T Counter"]] if "T Counter" in colmap else (df[colmap["Counter"]] if "Counter" in colmap else np.nan)
    out["B Counter"] = df[colmap["Total Counter B"]] if "Total Counter B" in colmap else (df[colmap["Counter B"]] if "Counter B" in colmap else np.nan)

    col = pd.Series(np.nan, index=df.index, dtype=object)
    for cc in color_cols:
        s = df[cc].astype(object)
        ok = s.notna() & (s.astype(str).str.strip() != "")
        col = col.where(col.notna(), s.where(ok))
    out["Color"] = col

    ta = pd.to_numeric(df[colmap["Prod Ton A"]], errors="coerce").fillna(0) if "Prod Ton A" in colmap else 0.0
    tb = pd.to_numeric(df[colmap["Prod Ton B"]], errors="coerce").fillna(0) if "Prod Ton B" in colmap else 0.0
    out["Sheet Ton"] = ta + tb
    return out, notes


# ---------------------------------------------------------------------------
# 3. CELL CLEANING
# ---------------------------------------------------------------------------
_LEAD = re.compile(r"^\s*(-?\d[\d,]*(?:\.\d+)?)")


def _num_col(series, lead_ok=False):
    """to_numeric that remembers every cell that could not be read. Returns (values, {idx: (text, used)})."""
    s = series
    num = pd.to_numeric(s, errors="coerce").astype("float64")
    bad = s.notna() & num.isna()
    flags = {}
    if bad.any():
        for idx, v in s[bad].items():
            t = str(v).strip()
            if t in ("", "-", "nan", "None", "NaN"):
                continue
            try:
                num.at[idx] = float(t.replace(",", ""))
                continue
            except ValueError:
                pass
            used = None
            if lead_ok:
                m = _LEAD.match(t)
                if m:
                    used = float(m.group(1).replace(",", ""))
                    num.at[idx] = used
            flags[idx] = (t, used)
    return num, flags


def _clean_txt(v):
    if v is None or (not isinstance(v, str) and pd.isna(v)):
        return None
    t = re.sub(r"\s+", " ", str(v).replace("\xa0", " ")).strip()
    return t or None


def _clean_mc(v):
    if v is None or (not isinstance(v, str) and pd.isna(v)):
        return None
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return _clean_txt(v)


def _clean_acc(v):
    if v is None or (not isinstance(v, str) and pd.isna(v)):
        return "-"
    try:
        return str(int(float(v)))
    except (ValueError, TypeError):
        return _clean_txt(v) or "-"


def derive_line_group(floor, mc):
    prefix = str(mc).strip().upper()[:1]
    if prefix in ("A", "B"):
        code = "Line A-B"
    elif prefix in ("C", "D"):
        code = "Line C-D"
    elif prefix in ("E", "F"):
        code = "Line E-F"
    else:
        code = "Line Other"
    return f"{floor} {code}"


def machine_size(resolved_info, text):
    if resolved_info:
        return get_size_from_position(resolved_info["position"])
    t = str(text).upper()
    if "119" in t:
        return "120"
    for sz in SORTED_SIZES:
        if sz in t:
            return sz
    return "Other"


def _size_mismatch(raw, info):
    """Raw text carries a tonnage (e.g. 'A7-120') that differs from the master machine's tonnage."""
    toks = [t for t in re.findall(r"\d{2,3}", str(raw)) if t in EXCEL_SIZES]
    if not toks:
        return False
    return get_size_from_position(info["position"]) not in toks


# ---------------------------------------------------------------------------
# 4. ONE SHEET -> RECORDS + ISSUES
# ---------------------------------------------------------------------------
def _process_sheet(raw, floor, dt, sheet, corr_rows):
    date_str = dt.strftime("%d-%m-%Y")
    sname = str(sheet).strip()
    notes, issues = [], []
    canon, cn = _canonicalize(raw, sheet)
    notes += cn
    if canon is None:
        return None, notes

    # ---- numbers (remember unreadable cells)
    flags = {}
    for f in STRICT_NUM + SOFT_NUM + LEDGER_NUM:
        vals, fl = _num_col(canon[f], lead_ok=(f in LEDGER_NUM))
        canon[f] = vals
        for idx, (t, u) in fl.items():
            flags.setdefault(int(canon.at[idx, "Src Row"]), []).append((f, t, u))

    # ---- text
    canon["MC Raw"] = canon["MC SL"].map(_clean_mc)
    canon["Order Name"] = canon["Order Name"].map(_clean_txt)
    canon["Item Name"] = canon["Item Name"].map(_clean_txt)
    canon["Color"] = canon["Color"].map(_clean_txt).fillna("-")
    canon["Acc Code"] = canon["Acc Code"].map(_clean_acc)

    src_good = canon["A Good"].fillna(0) + canon["B Good"].fillna(0)
    canon["Source Good"] = src_good
    summary = canon["MC Raw"].fillna("").str.lower().str.match(r"^(sub\s*)?total|^grand")
    identity = canon["MC Raw"].notna() | canon["Order Name"].notna() | canon["Item Name"].notna()
    sheet_good = float(src_good[~summary].sum())

    entry = ~summary & ((canon["MC Raw"].notna() & canon["Order Name"].notna()) | (identity & (src_good != 0)))
    nid = ~summary & ~identity & (src_good != 0)
    if nid.any():
        rows = ", ".join(str(int(r)) for r in canon.loc[nid, "Src Row"].head(8))
        notes.append((ERROR, "Rows not counted", f"Tab '{sname}': production figures on Excel row(s) {rows} have no machine / order / item, so they are NOT counted ({int(src_good[nid].sum()):,} pcs)"))

    ent = canon[entry].copy()
    ent["Item Name"] = ent["Item Name"].fillna("(blank item)")
    miss_mc = ent["MC Raw"].isna()
    miss_od = ent["Order Name"].isna()
    ent["MC Raw"] = ent["MC Raw"].fillna("(blank)")
    ent["Order Name"] = ent["Order Name"].fillna("(blank)")

    # ---- suspected duplicates (before chess merge; chess rows excluded)
    dup_of = {}
    nonchess = ~ent["Item Name"].map(is_chess_item)
    cand = ent[nonchess & ((ent["A Good"].fillna(0) + ent["B Good"].fillna(0)) > 0)]
    if not cand.empty:
        sig = ["MC Raw", "Order Name", "Item Name", "Acc Code", "Cavity", "CT", "A Good", "B Good"]
        first = cand.groupby(sig, dropna=False)["Src Row"].transform("min")
        isdup = cand.duplicated(subset=sig, keep="first")
        for sr, fr in zip(cand.loc[isdup, "Src Row"], first[isdup]):
            dup_of[int(sr)] = int(fr)

    # ---- chess family molds
    ent, row_map = consolidate_chess_family_mold(ent)
    ent = ent.reset_index(drop=True)
    flags_m = {}
    for sr, lst in flags.items():
        flags_m.setdefault(row_map.get(sr, sr), []).extend(lst)

    ent["Row Key"] = ent["Src Row"].map(lambda r: f"{floor}|{date_str}|{int(r)}")
    ent["MC Used"] = ent["MC Raw"]
    ent["Excluded"] = False
    ent["Edited"] = False

    # ---- user corrections (validated against order|item so a shifted sheet can never mis-apply)
    applied, stale = set(), []
    prefix = f"{floor}|{date_str}|"
    by_row = {int(r): i for i, r in zip(ent.index, ent["Src Row"])}
    for key, ov in corr_rows.items():
        if not key.startswith(prefix):
            continue
        try:
            sr = int(key.split("|")[2])
        except (IndexError, ValueError):
            continue
        i = by_row.get(sr)
        if i is None or ov.get("sig") != f"{ent.at[i, 'Order Name']}|{ent.at[i, 'Item Name']}":
            stale.append(key)
            continue
        applied.add(key)
        if ov.get("exclude"):
            ent.at[i, "Excluded"] = True
        for k, col in [("ct", "CT"), ("cavity", "Cavity"), ("unit_wt", "Unit Wt"), ("a_good", "A Good"), ("b_good", "B Good"), ("a_rej", "A Rej"), ("b_rej", "B Rej")]:
            if ov.get(k) is not None:
                ent.at[i, col] = float(ov[k])
                ent.at[i, "Edited"] = True
        if ov.get("mc_sl"):
            ent.at[i, "MC Used"] = str(ov["mc_sl"]).strip()
            ent.at[i, "Edited"] = True

    # ---- machine identity
    cache = {}

    def _res(raw_txt):
        if raw_txt not in cache:
            cache[raw_txt] = resolve_machine_info(raw_txt, floor)
        return cache[raw_txt]

    infos = ent["MC Used"].map(_res)
    ent["Machine"] = [inf["position"] if inf else mu for inf, mu in zip(infos, ent["MC Used"])]
    ent["Resolved"] = [inf is not None for inf in infos]
    ent["MC Size"] = [machine_size(inf, mu) for inf, mu in zip(infos, ent["MC Used"])]
    ent["Line Group"] = [derive_line_group(floor, m) for m in ent["Machine"]]

    # ---- calculations (same formulas as before)
    ex = ent["Excluded"]
    ct = ent["CT"].fillna(0)
    cav = ent["Cavity"].fillna(0)
    wt = ent["Unit Wt"].fillna(0)
    ag = ent["A Good"].fillna(0).where(~ex, 0.0)
    bg = ent["B Good"].fillna(0).where(~ex, 0.0)
    ar = ent["A Rej"].fillna(0).where(~ex, 0.0)
    br = ent["B Rej"].fillna(0).where(~ex, 0.0)
    atot = ent["A Counter"].fillna(0)
    btot = ent["B Counter"].fillna(0)
    std = np.where((ct > 0) & (cav > 0), 43200.0 / ct.where(ct > 0, 1) * cav, 0.0)
    a_rt = np.where(std > 0, ag * 12.0 / np.where(std > 0, std, 1), 0.0)
    b_rt = np.where(std > 0, bg * 12.0 / np.where(std > 0, std, 1), 0.0)
    tgood = ag + bg
    trej = ar + br
    tbad = np.where((atot + btot) > tgood, (atot + btot) - tgood, trej)

    rec = pd.DataFrame({
        "Floor": floor, "Line Group": ent["Line Group"], "Date": date_str, "DateObj": dt,
        "Machine": ent["Machine"], "MC SL": ent["Machine"], "MC SL Source": ent["MC Raw"], "MC Used": ent["MC Used"], "MC Size": ent["MC Size"],
        "Customer": ent["Order Name"].map(lambda o: o.split("-")[0].strip().upper() if "-" in o else o),
        "Order Name": ent["Order Name"], "Acc Code": ent["Acc Code"], "Item Name": ent["Item Name"],
        "Color": ent["Color"],
        "Demand Qty": ent["Demand"].fillna(0), "Up to Prod": ent["Up to Prod"].fillna(0),
        "Due Prod Prev": ent["Due Prev"].fillna(0), "Last Day Prod Col": ent["Last Day Prod"].fillna(0),
        "Due Prod Present": ent["Due Present"].fillna(0),
        "Cavity": cav, "CT": ct, "Unit Wt (kg)": wt, "Unit Wt": wt, "STD Cap/Shift": std,
        "A Total": atot, "A Good": ag, "Shift A Good": ag, "Shift A Rej": ar, "Shift A Runtime": a_rt,
        "Shift A Prod Ton": ag * wt / 1000.0,
        "B Total": btot, "B Good": bg, "Shift B Good": bg, "Shift B Rej": br, "Shift B Runtime": b_rt,
        "Shift B Prod Ton": bg * wt / 1000.0,
        "Total Good": tgood, "T-Good": tgood, "T-Bad": tbad, "Total Rejections": trej,
        "Total Runtime (Hrs)": a_rt + b_rt, "Total Prod Ton": (ag + bg) * wt / 1000.0,
        "Src Row": ent["Src Row"].astype(int), "Sheet": sname, "Row Key": ent["Row Key"],
        "Source Good": ent["Source Good"], "Excluded": ex, "Edited": ent["Edited"],
        "Sheet Ton": ent["Sheet Ton"],
    })

    # ---- row-level issues
    def emit(sev, cat, i, detail):
        issues.append({
            "Key": ent.at[i, "Row Key"], "Severity": sev, "Category": cat, "Floor": floor, "Date": date_str,
            "Sheet": sname, "Src Row": int(ent.at[i, "Src Row"]), "Machine": ent.at[i, "Machine"],
            "Order": ent.at[i, "Order Name"], "Item": ent.at[i, "Item Name"], "Detail": detail,
        })

    for i in ent.index:
        if ex.at[i]:
            continue
        sr = int(ent.at[i, "Src Row"])
        prod = ent.at[i, "Source Good"] != 0 or tgood.at[i] != 0
        if prod:
            if ent.at[i, "MC Used"] == "(blank)":
                emit(ERROR, "Machine name", i, "Machine (MC SL) is blank on a row with production")
            elif not ent.at[i, "Resolved"]:
                emit(ERROR, "Machine name", i, f"'{ent.at[i, 'MC Used']}' is not in the {floor} machine master - machine/size/line unknown")
            else:
                inf = infos.at[i]
                if _size_mismatch(ent.at[i, "MC Used"], inf):
                    emit(WARN, "Machine size", i, f"'{ent.at[i, 'MC Used']}' was read as {inf['position']} but the tonnage in the name differs")
            if ent.at[i, "Order Name"] == "(blank)":
                emit(ERROR, "Order name", i, "Order Name is blank on a row with production")
            if ct.at[i] <= 0 or cav.at[i] <= 0:
                emit(ERROR, "Missing CT/Cavity", i, f"CT={ct.at[i]:g}, Cavity={cav.at[i]:g} on a row with production - capacity & runtime are 0")
            if wt.at[i] <= 0:
                emit(WARN, "Missing Unit Wt", i, "Unit weight is blank/0 on a row with production - tonnage counted as 0")
            if ent.at[i, "Item Name"] == "(blank item)":
                emit(WARN, "Item name", i, "Item Name is blank on a row with production")
        ov = corr_rows.get(ent.at[i, "Row Key"], {}) if ent.at[i, "Row Key"] in applied else {}
        for f, t, u in flags_m.get(sr, []):
            if _FIELD_OVERRIDE.get(f) in ov:
                continue
            if u is not None:
                emit(WARN, "Unreadable number", i, f"{f}: cell '{t}' is text - read as {u:g}")
            elif f in STRICT_NUM:
                emit(ERROR, "Unreadable number", i, f"{f}: cell '{t}' is not a number - counted as 0")
            else:
                emit(WARN, "Unreadable number", i, f"{f}: cell '{t}' is not a number - counted as 0")
        neg = [n for n, v in [("A Good", ag.at[i]), ("B Good", bg.at[i]), ("A Rej", ar.at[i]), ("B Rej", br.at[i])] if v < 0]
        if neg:
            emit(ERROR, "Negative value", i, f"Negative value in {', '.join(neg)}")
        if atot.at[i] > 0 and ag.at[i] > atot.at[i] + 0.5:
            emit(WARN, "Good > Counter", i, f"Shift A good {ag.at[i]:,.0f} is more than the shift A counter {atot.at[i]:,.0f}")
        if btot.at[i] > 0 and bg.at[i] > btot.at[i] + 0.5:
            emit(WARN, "Good > Counter", i, f"Shift B good {bg.at[i]:,.0f} is more than the shift B counter {btot.at[i]:,.0f}")
        if sr in dup_of:
            emit(WARN, "Duplicate row", i, f"Identical (machine, order, item, cavity, CT, A & B pieces) to Excel row {dup_of[sr]} - kept in the numbers, please confirm")
        if ent.at[i, "Sheet Ton"] > 0.0005 and ent.at[i, "Source Good"] == 0 and not ent.at[i, "Edited"]:
            emit(WARN, "Tonnage without pieces", i, f"Sheet shows {ent.at[i, 'Sheet Ton']:.3f} T produced but A-Good/B-Good are blank")

    # ---- runtime above 12 h per shift on one machine
    live = ~ex
    for shift, rt, gcol in [("A", a_rt, "A Good"), ("B", b_rt, "B Good")]:
        s = pd.Series(np.asarray(rt), index=ent.index)[live]
        for mc, grp in s.groupby(ent.loc[live, "Machine"]):
            if grp.sum() > 12.01 and (grp > 0).any():
                i = grp.idxmax()
                tot = grp.sum()
                if tot > OVERRUN_MINOR_LIMIT:
                    emit(WARN, "Over 12h runtime", i, f"{mc}: shift {shift} derived runtime is {tot:.1f} h (> 12 h) over {int((grp > 0).sum())} entries - CT/cavity/pieces may be wrong")
                else:
                    emit(INFO, "Over 12h (minor)", i, f"{mc}: shift {shift} derived runtime is {tot:.1f} h - slightly above 12 h, usually CT tolerance")

    # ---- machine auto-matches (info only, aggregated later)
    mm = ent.loc[ent["Resolved"] & (ent["MC Raw"] != ent["Machine"]) & (ent["MC Raw"] != "(blank)"), ["MC Raw", "Machine"]]
    matches = [{"Floor": floor, "Date": date_str, "Raw": r, "Master": m} for r, m in zip(mm["MC Raw"], mm["Machine"])]

    recon = {
        "Floor": floor, "Date": date_str, "Sheet": sname, "Sheet Good": sheet_good,
        "Parsed Good": float(ent["Source Good"].sum()),
        "Excluded by you": float(ent.loc[ex, "Source Good"].sum()),
        "Edited by you": float((tgood[~ex] - ent.loc[~ex, "Source Good"]).sum()),
        "Final Good": float(tgood.sum()),
        "Rows": int(len(ent)),
    }
    return {"rec": rec, "issues": issues, "notes": notes, "matches": matches, "recon": recon,
            "applied": applied, "stale": stale}, notes


# ---------------------------------------------------------------------------
# 5. WHOLE FLOOR
# ---------------------------------------------------------------------------
def _fi(sev, cat, floor, detail, date=""):
    return {"Severity": sev, "Category": cat, "Floor": floor, "Date": date, "Detail": detail}


def parse_floor(file_bytes, floor, year, month, last_day, corr_json="{}"):
    corr = json.loads(corr_json) if corr_json else {}
    corr_rows = corr.get("rows", {})
    xls = pd.ExcelFile(io.BytesIO(file_bytes))
    scan = _scan_names(xls.sheet_names)

    file_issues, sheet_rows, records, row_issues, matches, recons, cover = [], [], [], [], [], [], []
    applied_all, stale_all = set(), []

    in_period = lambda r: r["date"] is not None and r["date"].year == year and r["date"].month == month
    by_day = {}
    for r in scan:
        if r["kind"] in ("date", "variant") and in_period(r):
            by_day.setdefault(r["date"].day, []).append(r)

    # tab roles for the report
    other_month = 0
    for r in scan:
        nm = str(r["name"]).strip()
        if r["kind"] == "invalid_date":
            file_issues.append(_fi(WARN, "Sheet name", floor, r["note"]))
            sheet_rows.append({"Floor": floor, "Tab": nm, "Date": "", "Role": "Skipped - invalid date", "Note": r["note"]})
        elif r["kind"] == "quarantined" and in_period(r):
            sheet_rows.append({"Floor": floor, "Tab": nm, "Date": r["date"].strftime("%d-%m-%Y"), "Role": "Skipped - looks like inventory/utility tab", "Note": f"'{r['residual']}' in the name"})
        elif r["kind"] in ("date", "variant") and not in_period(r):
            other_month += 1
        elif r["kind"] == "non_date":
            sheet_rows.append({"Floor": floor, "Tab": nm, "Date": "", "Role": "Not a daily tab", "Note": ""})
    if other_month:
        file_issues.append(_fi(INFO, "Sheet selection", floor, f"{other_month} dated tab(s) belong to other months and were ignored"))

    def _load(rec_):
        raw, _, rn = _read_sheet(xls, rec_["name"])
        return raw, rn

    for day in range(1, last_day + 1):
        dt = datetime(year, month, day)
        ds = dt.strftime("%d-%m-%Y")
        cands = sorted(by_day.get(day, []), key=lambda r: (len(r["rkey"]), r["pos"]))
        quarantined = [r for r in scan if r["kind"] == "quarantined" and r["date"] == dt]
        if not cands:
            hint = f" (found only {[str(q['name']).strip() for q in quarantined]})" if quarantined else ""
            file_issues.append(_fi(ERROR, "Missing day", floor, f"No production tab for {ds}{hint} - this day is NOT in the totals", ds))
            cover.append({"Floor": floor, "Date": ds, "Sheet Used": "-", "Status": "Missing", "Entries": 0, "Good Pcs": 0.0})
            continue

        used = cands[0]
        try:
            raw, rn = _load(used)
        except Exception as e:  # noqa: BLE001 - we report every read failure
            file_issues.append(_fi(ERROR, "Sheet unreadable", floor, f"Tab '{str(used['name']).strip()}' could not be read: {e}", ds))
            cover.append({"Floor": floor, "Date": ds, "Sheet Used": str(used["name"]).strip(), "Status": "Unreadable", "Entries": 0, "Good Pcs": 0.0})
            continue
        for sev, cat, det in rn:
            file_issues.append(_fi(sev, cat, floor, det, ds))
        if raw is None:
            cover.append({"Floor": floor, "Date": ds, "Sheet Used": str(used["name"]).strip(), "Status": "Unreadable", "Entries": 0, "Good Pcs": 0.0})
            continue

        res, notes = _process_sheet(raw, floor, dt, used["name"], corr_rows)
        if res is None:
            for sev, cat, det in notes:
                file_issues.append(_fi(sev, cat, floor, det, ds))
            cover.append({"Floor": floor, "Date": ds, "Sheet Used": str(used["name"]).strip(), "Status": "Unreadable", "Entries": 0, "Good Pcs": 0.0})
            continue
        for sev, cat, det in res["notes"]:
            file_issues.append(_fi(sev, cat, floor, det, ds))
        records.append(res["rec"])
        row_issues += res["issues"]
        matches += res["matches"]
        recons.append(res["recon"])
        applied_all |= res["applied"]
        stale_all += res["stale"]

        status = "OK" if used["rkey"] == "" else "OK (tab name has extra text)"
        entries = int((res["rec"]["Total Good"] > 0).sum())
        cover.append({"Floor": floor, "Date": ds, "Sheet Used": str(used["name"]).strip(), "Status": status,
                      "Entries": entries, "Good Pcs": float(res["recon"]["Final Good"])})
        sheet_rows.append({"Floor": floor, "Tab": str(used["name"]).strip(), "Date": ds, "Role": "USED",
                           "Note": "clean date-only tab" if used["rkey"] == "" else "no clean tab exists - used the closest one"})

        # duplicate tabs for the same date: never pick them, but compare totals and tell the user
        for extra in cands[1:]:
            note, role_sev = "", INFO
            try:
                raw2, _ = _load(extra)
                if raw2 is not None:
                    c2, _n = _canonicalize(raw2, extra["name"])
                    if c2 is not None:
                        g2 = float((pd.to_numeric(c2["A Good"], errors="coerce").fillna(0) + pd.to_numeric(c2["B Good"], errors="coerce").fillna(0)).sum())
                        g1 = res["recon"]["Sheet Good"]
                        if abs(g2 - g1) > max(1.0, 0.001 * abs(g1)):
                            role_sev = WARN
                            note = f"production differs: used tab {g1:,.0f} pcs vs ignored tab {g2:,.0f} pcs"
                        else:
                            note = "same production total as the used tab"
            except Exception as e:  # noqa: BLE001
                note = f"could not compare ({e})"
            en = str(extra["name"]).strip()
            file_issues.append(_fi(role_sev, "Duplicate tab", floor, f"{ds}: tab '{en}' ignored, using '{str(used['name']).strip()}' - {note}", ds))
            sheet_rows.append({"Floor": floor, "Tab": en, "Date": ds, "Role": "Ignored - duplicate date", "Note": note})

    # saved corrections that no longer match the sheet
    for key in stale_all:
        file_issues.append(_fi(WARN, "Saved correction", floor, f"Correction for {key} was NOT applied - the row/order/item in the sheet no longer matches what you corrected"))
    if records:
        df = pd.concat(records, ignore_index=True)
        df = _add_weighted_capacity(df)
    else:
        df = pd.DataFrame()

    return {
        "records": df,
        "row_issues": pd.DataFrame(row_issues),
        "file_issues": pd.DataFrame(file_issues),
        "sheets": pd.DataFrame(sheet_rows),
        "coverage": pd.DataFrame(cover),
        "recon": pd.DataFrame(recons),
        "matches": pd.DataFrame(matches),
    }


def _add_weighted_capacity(df):
    """Same weighted-capacity rule as before, per Floor|Machine|Date."""
    df["Helper"] = df["Floor"].astype(str) + "|" + df["Machine"].astype(str) + "|" + df["Date"].astype(str)
    s_col = df["Shift A Runtime"].fillna(0)
    t_col = df["Shift B Runtime"].fillna(0)
    k_col = df["STD Cap/Shift"].fillna(0)
    sum_s = df.groupby("Helper")["Shift A Runtime"].transform("sum")
    sum_t = df.groupby("Helper")["Shift B Runtime"].transform("sum")
    cap_a = np.where(sum_s > 0, np.where(sum_s > 12.01, k_col * (s_col > 0).astype(float), k_col * (s_col / sum_s.where(sum_s > 0, 1))), 0.0)
    cap_b = np.where(sum_t > 0, np.where(sum_t > 12.01, k_col * (t_col > 0).astype(float), k_col * (t_col / sum_t.where(sum_t > 0, 1))), 0.0)
    df["Weighted Cap Pcs"] = cap_a + cap_b
    df["Weighted Cap Ton"] = df["Weighted Cap Pcs"] * df["Unit Wt (kg)"] / 1000.0
    df["Daily Cap Pcs"] = df["Weighted Cap Pcs"]
    df["Daily Cap Ton"] = df["Weighted Cap Ton"]
    return df


# ---------------------------------------------------------------------------
# 6. HEALTH REPORT (both floors)
# ---------------------------------------------------------------------------
def build_health(results, period, corr_json="{}"):
    """results: {floor: parse_floor() dict}. Returns one health dict used by the UI and the Excel exports."""
    corr = json.loads(corr_json) if corr_json else {}
    reviewed = corr.get("reviewed", {})

    rows = [r["row_issues"] for r in results.values() if not r["row_issues"].empty]
    ri = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(
        columns=["Key", "Severity", "Category", "Floor", "Date", "Sheet", "Src Row", "Machine", "Order", "Item", "Detail"])
    if not ri.empty:
        sig = ri.groupby("Key")["Category"].apply(lambda s: ";".join(sorted(set(s))))
        ri["Status"] = [("Reviewed" if reviewed.get(k) == sig[k] else "Open") for k in ri["Key"]]
        ri["Row Signature"] = ri["Key"].map(sig)
    else:
        ri["Status"] = []
        ri["Row Signature"] = []

    fi_parts = [r["file_issues"] for r in results.values() if not r["file_issues"].empty]
    fi = pd.concat(fi_parts, ignore_index=True) if fi_parts else pd.DataFrame(columns=["Severity", "Category", "Floor", "Date", "Detail"])

    # period level checks
    pf = []
    if period and period["gap_days"] > 3:
        pf.append(_fi(WARN, "Period", "ALL",
                      f"Latest tab date {period['latest']:%d-%m-%Y} is {period['gap_days']} days after the previous tab "
                      f"({period['gap_prev']:%d-%m-%Y}). If that date is a typo, the whole report period is wrong."))
    if pf:
        fi = pd.concat([pd.DataFrame(pf), fi], ignore_index=True)

    cov = [r["coverage"] for r in results.values() if not r["coverage"].empty]
    cov = pd.concat(cov, ignore_index=True) if cov else pd.DataFrame(columns=["Floor", "Date", "Sheet Used", "Status", "Entries", "Good Pcs"])
    rc = [r["recon"] for r in results.values() if not r["recon"].empty]
    rc = pd.concat(rc, ignore_index=True) if rc else pd.DataFrame(columns=["Floor", "Date", "Sheet", "Sheet Good", "Parsed Good", "Excluded by you", "Edited by you", "Final Good", "Rows"])
    if not rc.empty:
        rc["Lost in parsing"] = (rc["Sheet Good"] - rc["Parsed Good"]).round(3)
        rc["Check"] = np.where(rc["Lost in parsing"].abs() < 0.5, "OK", "MISMATCH")
        extra = []
        for _, r in rc[rc["Check"] != "OK"].iterrows():
            extra.append(_fi(ERROR, "Reconciliation", r["Floor"],
                             f"{r['Date']}: the sheet totals {r['Sheet Good']:,.0f} good pcs but only {r['Parsed Good']:,.0f} reached the report (difference {r['Lost in parsing']:,.0f})", r["Date"]))
        if extra:
            fi = pd.concat([pd.DataFrame(extra), fi], ignore_index=True)

    sh = [r["sheets"] for r in results.values() if not r["sheets"].empty]
    sh = pd.concat(sh, ignore_index=True) if sh else pd.DataFrame(columns=["Floor", "Tab", "Date", "Role", "Note"])
    mt = [r["matches"] for r in results.values() if not r["matches"].empty]
    if mt:
        mt = pd.concat(mt, ignore_index=True)
        mt = mt.groupby(["Floor", "Raw", "Master"]).agg(Rows=("Date", "size"), Days=("Date", "nunique")).reset_index()
    else:
        mt = pd.DataFrame(columns=["Floor", "Raw", "Master", "Rows", "Days"])

    open_ri = ri[(ri["Status"] == "Open") & ri["Severity"].isin([ERROR, WARN])] if not ri.empty else ri
    fi_act = fi[fi["Severity"].isin([ERROR, WARN])] if not fi.empty else fi
    counts = {
        "errors": int((open_ri["Severity"] == ERROR).sum() if not open_ri.empty else 0) + int((fi_act["Severity"] == ERROR).sum() if not fi_act.empty else 0),
        "warnings": int((open_ri["Severity"] == WARN).sum() if not open_ri.empty else 0) + int((fi_act["Severity"] == WARN).sum() if not fi_act.empty else 0),
        "reviewed": int(((ri["Status"] == "Reviewed") & ri["Severity"].isin([ERROR, WARN])).sum()) if not ri.empty else 0,
        "rows_flagged": int(open_ri["Key"].nunique()) if not open_ri.empty else 0,
    }
    counts["open"] = counts["errors"] + counts["warnings"]
    return {"row_issues": ri, "file_issues": fi, "coverage": cov, "recon": rc, "sheets": sh,
            "matches": mt, "counts": counts, "period": period}
