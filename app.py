# ============================================
# SECTION 1: IMPORTS & STREAMLIT SETUP
# ============================================
import io
import os
import re
from datetime import datetime
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

from config import (
    MACHINE_MASTER,
    EXCEL_SIZES,
    SORTED_SIZES,
    MC_COUNT_BY_SIZE,
    resolve_machine_info,
)
from chess import consolidate_chess_family_mold

st.set_page_config(
    page_title="Plastic-3 Operations Console | FF & GF",
    page_icon="🏭",
    layout="wide",
    initial_sidebar_state="locked",
)


def load_css(file_name="style.css"):
    if os.path.exists(file_name):
        with open(file_name) as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)


load_css("style.css")

# Initialize Typo Overrides in Session State
if "typo_overrides" not in st.session_state:
    st.session_state["typo_overrides"] = {}


# ============================================
# SECTION 2: PARSING HELPERS
# ============================================
def extract_date_from_sheet_name(sheet_name):
    """
    Ultra-resilient sheet date parser.
    Catches '22-08-2026', '22-08-26 ', '22/08/2026', '22.08.2026', text months, trailing whitespace, etc.
    """
    if not isinstance(sheet_name, str):
        return None

    s_clean = sheet_name.strip().replace("\xa0", " ")

    # 1. Standard numeric date pattern (DD-MM-YYYY or DD-MM-YY with -, /, ., _, or spaces)
    match = re.search(r"(\d{1,2})[-/\._\s](\d{1,2})[-/\._\s](\d{2,4})", s_clean)
    if match:
        d_str, m_str, y_str = match.group(1), match.group(2), match.group(3)
        try:
            d, m, y = int(d_str), int(m_str), int(y_str)
            if y < 100:
                y += 2000
            if 1 <= d <= 31 and 1 <= m <= 12 and 2000 <= y <= 2099:
                return datetime(y, m, d)
        except Exception:
            pass

    # 2. Text month pattern (e.g., '22-Aug-2026', '22Aug26')
    month_names = {
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12
    }
    match_txt = re.search(r"(\b\d{1,2})[-/\._\s]?([a-zA-Z]{3,9})[-/\._\s]?(\d{2,4})?", s_clean)
    if match_txt:
        d_str = match_txt.group(1)
        m_txt = match_txt.group(2).lower()[:3]
        y_str = match_txt.group(3)
        if m_txt in month_names:
            try:
                d = int(d_str)
                m = month_names[m_txt]
                y = int(y_str) if y_str else datetime.now().year
                if y < 100:
                    y += 2000
                if 1 <= d <= 31 and 1 <= m <= 12:
                    return datetime(y, m, d)
            except Exception:
                pass

    return None


def extract_excel_mc_size(mc_sl, size_col_val=None):
    """Extracts machine tonnage size class strictly matching standard sizes without silent overrides."""
    if pd.notna(size_col_val):
        try:
            return str(int(float(size_col_val)))
        except (ValueError, TypeError):
            pass

    mc_str = str(mc_sl).strip().upper()

    if "119" in mc_str:
        return "120"

    for sz in SORTED_SIZES:
        if sz in mc_str:
            return sz
    return "Other"


def derive_line_group(floor_code, mc_sl):
    mc_str = str(mc_sl).strip().upper()
    prefix = mc_str[0] if len(mc_str) > 0 else ""

    if prefix in ["A", "B"]:
        line_code = "Line A-B"
    elif prefix in ["C", "D"]:
        line_code = "Line C-D"
    elif prefix in ["E", "F"]:
        line_code = "Line E-F"
    else:
        line_code = "Line Other"

    return f"{floor_code} {line_code}"


def convert_df_to_excel_bytes(df):
    """Converts dataframe into clean Excel (.xlsx) file bytes for download."""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Data")
    return output.getvalue()


# ============================================
# SECTION 3: DATA PARSING & SHIFT-ISOLATED ENGINE
# ============================================
@st.cache_data
def load_and_parse_floor_data(file_bytes, floor_label, typo_overrides=None):
    """Parses raw Excel floor production sheets, consolidates family molds, applies capacity, and audits typos."""
    if typo_overrides is None:
        typo_overrides = {}

    file_stream = io.BytesIO(file_bytes)
    xls = pd.ExcelFile(file_stream)

    valid_sheets = []
    all_parsed_dates = []

    for s in xls.sheet_names:
        dt = extract_date_from_sheet_name(s)
        if dt:
            valid_sheets.append((s, dt))
            all_parsed_dates.append(dt)

    if all_parsed_dates:
        latest_date = max(all_parsed_dates)
        latest_month = latest_date.month
        latest_year = latest_date.year

        date_sheets = [
            (s, dt)
            for s, dt in valid_sheets
            if dt.month == latest_month and dt.year == latest_year
        ]
        date_sheets.sort(key=lambda x: x[1])
    else:
        date_sheets = []

    all_records = []
    typo_logs = []

    for sheet, dt_val in date_sheets:
        dt_str_clean = dt_val.strftime("%d-%m-%Y")
        df = pd.read_excel(xls, sheet_name=sheet)
        df = df.dropna(how="all").reset_index(drop=True)

        if "MC SL" not in df.columns or "Order Name" not in df.columns:
            continue

        df = df[df["MC SL"].notna() & df["Order Name"].notna()].copy()

        # APPLY CHESS FAMILY MOLD CONSOLIDATION (Prevents 5x runtime multiplication)
        df = consolidate_chess_family_mold(df)

        for idx, row in df.iterrows():
            raw_val = row.get("MC SL")
            if isinstance(raw_val, float) and raw_val.is_integer():
                raw_mc_sl = str(int(raw_val)).strip()
            else:
                raw_mc_sl = str(raw_val).strip()

            order = str(row.get("Order Name")).strip()
            item = str(row.get("Item Name", "")).strip()
            color = str(row.get("Color", "")).strip() if pd.notna(row.get("Color")) else "-"

            acc_code_val = row.get("Acc Code")
            try:
                acc_code = (
                    str(int(float(acc_code_val)))
                    if pd.notna(acc_code_val)
                    else "-"
                )
            except (ValueError, TypeError):
                acc_code = (
                    str(acc_code_val).strip()
                    if pd.notna(acc_code_val)
                    else "-"
                )

            # Check for Session-Based Typo Overrides
            override_key = f"{dt_str_clean}_{floor_label}_{raw_mc_sl}_{order}_{idx}"
            if override_key in typo_overrides:
                mc_sl = typo_overrides[override_key].get("mc_sl", raw_mc_sl)
                ct_override = typo_overrides[override_key].get("ct", None)
                cavity_override = typo_overrides[override_key].get("cavity", None)
            else:
                mc_sl = raw_mc_sl
                ct_override = None
                cavity_override = None

            cust_prefix = (
                order.split("-")[0].strip().upper() if "-" in order else order
            )
            mc_size = extract_excel_mc_size(mc_sl, row.get("Size"))
            line_group = derive_line_group(floor_label, mc_sl)

            ct_raw = ct_override if ct_override is not None else row.get("CT")
            ct_num = pd.to_numeric(ct_raw, errors="coerce")
            ct = 0.0 if pd.isna(ct_num) else float(ct_num)

            cavity_raw = cavity_override if cavity_override is not None else row.get("Cavity")
            cavity_num = pd.to_numeric(cavity_raw, errors="coerce")
            cavity = 0.0 if pd.isna(cavity_num) else float(cavity_num)

            unit_wt_num = pd.to_numeric(row.get("Unit Wt"), errors="coerce")
            unit_wt_kg = 0.0 if pd.isna(unit_wt_num) else float(unit_wt_num)

            a_good_num = pd.to_numeric(row.get("A-Good"), errors="coerce")
            a_good = 0.0 if pd.isna(a_good_num) else float(a_good_num)

            a_rej_num = pd.to_numeric(row.get("A-Rejec"), errors="coerce")
            a_rej = 0.0 if pd.isna(a_rej_num) else float(a_rej_num)

            b_good_num = pd.to_numeric(row.get("B-Good"), errors="coerce")
            b_good = 0.0 if pd.isna(b_good_num) else float(b_good_num)

            b_rej_val = row.get("B-Reject")
            if pd.isna(b_rej_val):
                b_rej_val = row.get("B-Reject Cause of Less Prod")
            b_rej_num = pd.to_numeric(b_rej_val, errors="coerce")
            b_rej = 0.0 if pd.isna(b_rej_num) else float(b_rej_num)

            # Audit Conditions
            is_size_typo = mc_size not in EXCEL_SIZES
            is_missing_params = (a_good > 0 or b_good > 0) and (ct <= 0 or cavity <= 0)

            master_match = resolve_machine_info(raw_mc_sl, floor_label)
            suggested_mc = master_match["position"] if master_match else raw_mc_sl

            if is_size_typo or is_missing_params:
                issue_msg = (
                    f"Invalid Machine SL / Size '{mc_sl}' (Extracted Size: '{mc_size}')"
                    if is_size_typo
                    else f"Missing CT/Cavity (CT: {ct}, Cavity: {cavity}) on active run"
                )
                typo_logs.append({
                    "Key": override_key,
                    "Date": dt_str_clean,
                    "Floor": floor_label,
                    "Machine SL": raw_mc_sl,
                    "Order Name": order,
                    "Acc Code": acc_code,
                    "Issue Detected": issue_msg,
                    "Suggested MC SL": suggested_mc,
                    "Current MC SL": mc_sl,
                    "Current CT": ct,
                    "Current Cavity": cavity,
                })

            std_cap_shift = (
                (43200.0 / ct) * cavity if ct > 0 and cavity > 0 else 0.0
            )

            demand_num = pd.to_numeric(row.get("Demand"), errors="coerce")
            demand_qty = 0.0 if pd.isna(demand_num) else float(demand_num)

            up_to_prod_num = pd.to_numeric(row.get("Up to Prod"), errors="coerce")
            up_to_prod = 0.0 if pd.isna(up_to_prod_num) else float(up_to_prod_num)

            due_prev_num = pd.to_numeric(row.get("Due Prod"), errors="coerce")
            due_prod_prev = 0.0 if pd.isna(due_prev_num) else float(due_prev_num)

            last_day_col_num = pd.to_numeric(row.get("Last Day Prod"), errors="coerce")
            last_day_prod_col = 0.0 if pd.isna(last_day_col_num) else float(last_day_col_num)

            due_present_num = pd.to_numeric(row.get("Due Prod.1"), errors="coerce")
            due_prod_present = 0.0 if pd.isna(due_present_num) else float(due_present_num)

            a_runtime = (
                (a_good * 12.0) / std_cap_shift if std_cap_shift > 0 else 0.0
            )
            a_prod_ton = (a_good * unit_wt_kg) / 1000.0

            b_runtime = (
                (b_good * 12.0) / std_cap_shift if std_cap_shift > 0 else 0.0
            )
            b_prod_ton = (b_good * unit_wt_kg) / 1000.0

            total_good = a_good + b_good
            total_rej = a_rej + b_rej
            total_runtime = a_runtime + b_runtime
            total_prod_ton = a_prod_ton + b_prod_ton

            all_records.append({
                "Floor": floor_label,
                "Line Group": line_group,
                "Date": dt_str_clean,
                "DateObj": dt_val,
                "Machine": mc_sl,
                "MC Size": mc_size,
                "Customer": cust_prefix,
                "Order Name": order,
                "Acc Code": acc_code,
                "Item Name": item,
                "Color": color,
                "Demand Qty": demand_qty,
                "Up to Prod": up_to_prod,
                "Due Prod Prev": due_prod_prev,
                "Last Day Prod Col": last_day_prod_col,
                "Due Prod Present": due_prod_present,
                "Cavity": cavity,
                "CT": ct,
                "Unit Wt (kg)": unit_wt_kg,
                "STD Cap/Shift": std_cap_shift,
                "Shift A Good": a_good,
                "Shift A Rej": a_rej,
                "Shift A Runtime": a_runtime,
                "Shift A Prod Ton": a_prod_ton,
                "Shift B Good": b_good,
                "Shift B Rej": b_rej,
                "Shift B Runtime": b_runtime,
                "Shift B Prod Ton": b_prod_ton,
                "Total Good": total_good,
                "Total Rejections": total_rej,
                "Total Runtime (Hrs)": total_runtime,
                "Total Prod Ton": total_prod_ton,
            })

    df_res = pd.DataFrame(all_records)
    df_audit = pd.DataFrame(typo_logs)

    if df_res.empty:
        return df_res, df_audit

    # EXACT SHIFT-ISOLATED PROPORTIONAL CAPACITY (Matching Details!L:L)
    df_res["Helper"] = df_res["Floor"].astype(str) + "|" + df_res["Machine"].astype(str) + "|" + df_res["Date"].astype(str)

    s_col = df_res["Shift A Runtime"].fillna(0)
    t_col = df_res["Shift B Runtime"].fillna(0)
    k_col = df_res["STD Cap/Shift"].fillna(0)

    sum_s_map = df_res.groupby("Helper")["Shift A Runtime"].transform("sum")
    sum_t_map = df_res.groupby("Helper")["Shift B Runtime"].transform("sum")

    cap_a = np.where(
        sum_s_map > 0,
        np.where(sum_s_map > 12.01, k_col * (s_col > 0).astype(float), k_col * (s_col / sum_s_map)),
        0.0
    )
    cap_b = np.where(
        sum_t_map > 0,
        np.where(sum_t_map > 12.01, k_col * (t_col > 0).astype(float), k_col * (t_col / sum_t_map)),
        0.0
    )

    df_res["Weighted Cap Pcs"] = cap_a + cap_b
    df_res["Weighted Cap Ton"] = (df_res["Weighted Cap Pcs"] * df_res["Unit Wt (kg)"]) / 1000.0
    df_res["Daily Cap Pcs"] = df_res["Weighted Cap Pcs"]
    df_res["Daily Cap Ton"] = df_res["Weighted Cap Ton"]

    return df_res, df_audit


def consolidate_daily_machines(df_day):
    """Consolidates machine performance per day with runtime-weighted CT and cavity averages."""
    records = []
    for (floor_val, mc), group in df_day.groupby(["Floor", "Machine"]):
        orders = group["Order Name"].unique()
        items = group["Item Name"].unique()

        ord_name = orders[0] if len(orders) == 1 else "Mixed"
        item_name = items[0] if len(items) == 1 else "Mixed"

        mc_tot_runtime = group["Total Runtime (Hrs)"].sum()

        if mc_tot_runtime > 0:
            weighted_ct = (
                group["CT"] * group["Total Runtime (Hrs)"]
            ).sum() / mc_tot_runtime
            weighted_cavity = (
                group["Cavity"] * group["Total Runtime (Hrs)"]
            ).sum() / mc_tot_runtime
        else:
            weighted_ct = group["CT"].mean()
            weighted_cavity = group["Cavity"].mean()

        tot_a_good = group["Shift A Good"].sum()
        tot_b_good = group["Shift B Good"].sum()
        tot_good = group["Total Good"].sum()
        tot_bad = group["Total Rejections"].sum()
        a_runtime = group["Shift A Runtime"].sum()
        b_runtime = group["Shift B Runtime"].sum()

        cap_pcs = group["Weighted Cap Pcs"].sum()
        cap_ton = group["Weighted Cap Ton"].sum()
        prod_ton = group["Total Prod Ton"].sum()

        mc_size = group["MC Size"].iloc[0]
        line_grp = group["Line Group"].iloc[0]
        cust_name = (
            group["Customer"].iloc[0]
            if len(group["Customer"].unique()) == 1
            else "Mixed"
        )

        records.append({
            "Floor": floor_val,
            "Line Group": line_grp,
            "Machine": mc,
            "MC Size": mc_size,
            "Customer": cust_name,
            "Order Name": ord_name,
            "Item Name": item_name,
            "Is Mixed": len(group) > 1,
            "Entry Count": len(group),
            "Cavity": round(weighted_cavity, 2),
            "CT": round(weighted_ct, 2),
            "Shift A Good": round(tot_a_good, 2),
            "Shift B Good": round(tot_b_good, 2),
            "Total Good": round(tot_good, 2),
            "Total Rejections": round(tot_bad, 2),
            "Shift A Runtime": round(a_runtime, 2),
            "Shift B Runtime": round(b_runtime, 2),
            "Total Runtime (Hrs)": round(mc_tot_runtime, 2),
            "Weighted Cap Pcs": round(cap_pcs, 2),
            "Weighted Cap Ton": round(cap_ton, 2),
            "Total Prod Ton": round(prod_ton, 2),
            "Ach Pcs %": f"{(tot_good / cap_pcs * 100):.2f}%"
            if cap_pcs > 0
            else "0.00%",
            "Ach Ton %": f"{(prod_ton / cap_ton * 100):.2f}%"
            if cap_ton > 0
            else "0.00%",
        })
    return pd.DataFrame(records)


def compute_line_summary(df_subset):
    """Computes daily line summary counting distinct active machines on that date."""
    records = []
    for lg, grp in df_subset.groupby("Line Group"):
        active_grp = grp[(grp["Total Good"] > 0) | (grp["Total Runtime (Hrs)"] > 0)]
        mc_qty = active_grp["Machine"].nunique()
        tot_runtime = active_grp["Total Runtime (Hrs)"].sum()

        tot_cap_pcs = active_grp["Weighted Cap Pcs"].sum()
        tot_prod_pcs = active_grp["Total Good"].sum()
        tot_cap_ton = active_grp["Weighted Cap Ton"].sum()
        tot_prod_ton = active_grp["Total Prod Ton"].sum()

        ach_pcs = (tot_prod_pcs / tot_cap_pcs * 100) if tot_cap_pcs > 0 else 0.0
        ach_ton = (tot_prod_ton / tot_cap_ton * 100) if tot_cap_ton > 0 else 0.0

        records.append({
            "Line Group": lg,
            "Running MC Qty": mc_qty,
            "Runtime (Hrs)": round(tot_runtime, 2),
            "Cap (Pcs)": round(tot_cap_pcs, 2),
            "Prod (Pcs)": round(tot_prod_pcs, 2),
            "Pcs Ach %": f"{ach_pcs:.2f}%",
            "Cap (Ton)": round(tot_cap_ton, 2),
            "Prod (Ton)": round(tot_prod_ton, 2),
            "Ton Ach %": f"{ach_ton:.2f}%",
        })
    return pd.DataFrame(records)


def compute_line_summary_mtd(df_subset):
    """Computes MTD Line Summary summing daily active machine counts (Cumulative Machine-Days)."""
    records = []
    for lg, grp in df_subset.groupby("Line Group"):
        active_grp = grp[(grp["Total Good"] > 0) | (grp["Total Runtime (Hrs)"] > 0)]
        cum_mc_days = active_grp.groupby("Date")["Machine"].nunique().sum()
        tot_runtime = active_grp["Total Runtime (Hrs)"].sum()

        tot_cap_pcs = active_grp["Weighted Cap Pcs"].sum()
        tot_prod_pcs = active_grp["Total Good"].sum()
        tot_cap_ton = active_grp["Weighted Cap Ton"].sum()
        tot_prod_ton = active_grp["Total Prod Ton"].sum()

        ach_pcs = (tot_prod_pcs / tot_cap_pcs * 100) if tot_cap_pcs > 0 else 0.0
        ach_ton = (tot_prod_ton / tot_cap_ton * 100) if tot_cap_ton > 0 else 0.0

        records.append({
            "Line Group": lg,
            "Running MC Qty": cum_mc_days,
            "Runtime (Hrs)": round(tot_runtime, 2),
            "Cap (Pcs)": round(tot_cap_pcs, 2),
            "Prod (Pcs)": round(tot_prod_pcs, 2),
            "Pcs Ach %": f"{ach_pcs:.2f}%",
            "Cap (Ton)": round(tot_cap_ton, 2),
            "Prod (Ton)": round(tot_prod_ton, 2),
            "Ton Ach %": f"{ach_ton:.2f}%",
        })
    return pd.DataFrame(records)


def compute_size_summary(df_subset, mode="daily"):
    """
    Computes Machine Size Summary strictly matching Excel Sheet2 standard.
    - Evaluates running machines with active production/runtime.
    """
    records = []

    for sz in EXCEL_SIZES:
        grp = df_subset[df_subset["MC Size"] == sz]
        active_grp = grp[(grp["Total Good"] > 0) | (grp["Total Runtime (Hrs)"] > 0)]

        if active_grp.empty:
            records.append({
                "MC Size": sz,
                "MC QTY": 0,
                "CT Average": 0.00,
                "Run Hour Average": 0.00,
                "Total Cap (Pcs)": 0.00,
                "Total Prod (Pcs)": 0.00,
                "% OF Ach Pcs": "0.00%",
                "Cap (Ton)": 0.00,
                "Prod (Ton)": 0.00,
                "% OF Ach Ton": "0.00%",
            })
            continue

        tot_runtime = active_grp["Total Runtime (Hrs)"].sum()

        if mode == "as_of":
            mc_qty = active_grp.groupby("Date")["Machine"].nunique().sum()
        else:
            mc_qty = active_grp["Machine"].nunique()

        run_hr_avg = tot_runtime / mc_qty if mc_qty > 0 else 0.0

        if tot_runtime > 0:
            avg_ct = (
                active_grp["CT"] * active_grp["Total Runtime (Hrs)"]
            ).sum() / tot_runtime
        else:
            avg_ct = active_grp["CT"].mean()

        tot_cap_pcs = active_grp["Weighted Cap Pcs"].sum()
        tot_prod_pcs = active_grp["Total Good"].sum()
        tot_cap_ton = active_grp["Weighted Cap Ton"].sum()
        tot_prod_ton = active_grp["Total Prod Ton"].sum()

        ach_pcs = (tot_prod_pcs / tot_cap_pcs * 100) if tot_cap_pcs > 0 else 0.0
        ach_ton = (tot_prod_ton / tot_cap_ton * 100) if tot_cap_ton > 0 else 0.0

        records.append({
            "MC Size": sz,
            "MC QTY": mc_qty,
            "CT Average": round(avg_ct, 2),
            "Run Hour Average": round(run_hr_avg, 2),
            "Total Cap (Pcs)": round(tot_cap_pcs, 2),
            "Total Prod (Pcs)": round(tot_prod_pcs, 2),
            "% OF Ach Pcs": f"{ach_pcs:.2f}%",
            "Cap (Ton)": round(tot_cap_ton, 2),
            "Prod (Ton)": round(tot_prod_ton, 2),
            "% OF Ach Ton": f"{ach_ton:.2f}%",
        })

    return pd.DataFrame(records)


def add_total_row(df, label_col, sum_cols, avg_cols):
    """Adds a complete Sub-Total summary row calculating sums, Excel-matched unweighted averages, and percentages."""
    if df.empty:
        return df

    res_df = df.copy()
    tot_row = {}

    for c in df.columns:
        if c == label_col:
            tot_row[c] = "Sub Total"
        elif c in sum_cols:
            val = pd.to_numeric(df[c], errors="coerce").sum()
            tot_row[c] = round(val, 2) if isinstance(val, float) else val
        elif c in avg_cols:
            non_zero = pd.to_numeric(df[df[c] > 0][c], errors="coerce")
            tot_row[c] = (
                round(non_zero.mean(), 2) if not non_zero.empty else 0.0
            )
        else:
            tot_row[c] = "-"

    # Overall Achievement % Calculations
    if "Total Cap (Pcs)" in df.columns and "Total Prod (Pcs)" in df.columns:
        tc_p = pd.to_numeric(df["Total Cap (Pcs)"], errors="coerce").sum()
        tp_p = pd.to_numeric(df["Total Prod (Pcs)"], errors="coerce").sum()
        ach = (tp_p / tc_p * 100) if tc_p > 0 else 0.0
        if "% OF Ach Pcs" in df.columns:
            tot_row["% OF Ach Pcs"] = f"{ach:.2f}%"

    if "Cap (Pcs)" in df.columns and "Prod (Pcs)" in df.columns:
        tc_p = pd.to_numeric(df["Cap (Pcs)"], errors="coerce").sum()
        tp_p = pd.to_numeric(df["Prod (Pcs)"], errors="coerce").sum()
        ach = (tp_p / tc_p * 100) if tc_p > 0 else 0.0
        if "Pcs Ach %" in df.columns:
            tot_row["Pcs Ach %"] = f"{ach:.2f}%"

    if "Cap (Ton)" in df.columns and "Prod (Ton)" in df.columns:
        tc_t = pd.to_numeric(df["Cap (Ton)"], errors="coerce").sum()
        tp_t = pd.to_numeric(df["Prod (Ton)"], errors="coerce").sum()
        ach = (tp_t / tc_t * 100) if tc_t > 0 else 0.0
        if "% OF Ach Ton" in df.columns:
            tot_row["% OF Ach Ton"] = f"{ach:.2f}%"
        if "Ton Ach %" in df.columns:
            tot_row["Ton Ach %"] = f"{ach:.2f}%"

    if "Daily Cap (Pcs)" in df.columns and "Daily Prod (Pcs)" in df.columns:
        dc_p = pd.to_numeric(df["Daily Cap (Pcs)"], errors="coerce").sum()
        dp_p = pd.to_numeric(df["Daily Prod (Pcs)"], errors="coerce").sum()
        ach = (dp_p / dc_p * 100) if dc_p > 0 else 0.0
        if "Daily Util (Pcs %)" in df.columns:
            tot_row["Daily Util (Pcs %)"] = f"{ach:.2f}%"

    if "Daily Cap (Ton)" in df.columns and "Daily Prod (Ton)" in df.columns:
        dc_t = pd.to_numeric(df["Daily Cap (Ton)"], errors="coerce").sum()
        dp_t = pd.to_numeric(df["Daily Prod (Ton)"], errors="coerce").sum()
        ach = (dp_t / dc_t * 100) if dc_t > 0 else 0.0
        if "Daily Util (Ton %)" in df.columns:
            tot_row["Daily Util (Ton %)"] = f"{ach:.2f}%"

    if "Demand Qty" in df.columns and "Total Good" in df.columns:
        dem = pd.to_numeric(df["Demand Qty"], errors="coerce").sum()
        good = pd.to_numeric(df["Total Good"], errors="coerce").sum()
        ach = (good / dem * 100) if dem > 0 else 0.0
        if "Completion %" in df.columns:
            tot_row["Completion %"] = f"{ach:.2f}%"

    if "Demand Qty" in df.columns and "Total Produced (Pcs)" in df.columns:
        dem = pd.to_numeric(df["Demand Qty"], errors="coerce").sum()
        prod_pcs = pd.to_numeric(df["Total Produced (Pcs)"], errors="coerce").sum()
        ach = (prod_pcs / dem * 100) if dem > 0 else 0.0
        if "Fulfillment %" in df.columns:
            tot_row["Fulfillment %"] = f"{ach:.2f}%"

    if "Order Qty" in df.columns and "As of Production" in df.columns:
        dem = pd.to_numeric(df["Order Qty"], errors="coerce").sum()
        good = pd.to_numeric(df["As of Production"], errors="coerce").sum()
        ach = (good / dem * 100) if dem > 0 else 0.0
        if "As of %" in df.columns:
            tot_row["As of %"] = f"{ach:.2f}%"

    if "Last Day Cap (Pcs)" in df.columns and "Last Day Output (Pcs)" in df.columns:
        c_p = pd.to_numeric(df["Last Day Cap (Pcs)"], errors="coerce").sum()
        o_p = pd.to_numeric(df["Last Day Output (Pcs)"], errors="coerce").sum()
        u_p = (o_p / c_p * 100) if c_p > 0 else 0.0
        if "Last Day Util %" in df.columns:
            tot_row["Last Day Util %"] = f"{u_p:.2f}%"

    tot_df = pd.DataFrame([tot_row])
    return pd.concat([res_df, tot_df], ignore_index=True)


# ============================================
# SECTION 4: TABLE FORMATTING & ALIGNMENT HELPERS
# ============================================
def clean_and_format_dataframe(df):
    """Rounds float metrics to 2 decimal places and formats piece counts."""
    df_clean = df.copy()

    for col in df_clean.columns:
        col_lower = col.lower()
        if df_clean[col].dtype in ["float64", "float32"]:
            if (
                "good" in col_lower
                or "rej" in col_lower
                or "pcs" in col_lower
                or "qty" in col_lower
                or "production" in col_lower
                or "due" in col_lower
                or "output" in col_lower
                or "cap" in col_lower
            ):
                df_clean[col] = df_clean[col].apply(
                    lambda x: (
                        f"{int(round(x)):,}"
                        if pd.notna(x) and str(x) != "-"
                        else "-"
                    )
                )
            else:
                df_clean[col] = df_clean[col].apply(
                    lambda x: f"{x:.2f}" if pd.notna(x) and str(x) != "-" else "-"
                )
        elif df_clean[col].dtype in ["int64", "int32"]:
            df_clean[col] = df_clean[col].apply(
                lambda x: f"{x:,}" if pd.notna(x) and str(x) != "-" else "-"
            )

    return df_clean


def column_visibility_selector(df, key_prefix="", custom_exclusions=None):
    """Manages column visibility selector with default exclusions."""
    all_cols = df.columns.tolist()

    excluded_defaults = [
        "Entry Count",
        "Is Mixed",
        "Is Completed",
        "Last Run Date",
        "Last MC Assigned",
        "Last Day Cap (Pcs)",
        "Last Day Output (Pcs)",
        "Last Day Util %",
    ]
    if custom_exclusions:
        excluded_defaults.extend(custom_exclusions)

    default_cols = [c for c in all_cols if c not in excluded_defaults]

    if f"{key_prefix}_visible_cols" not in st.session_state:
        st.session_state[f"{key_prefix}_visible_cols"] = default_cols

    with st.popover("👁️ Columns"):
        st.caption("Check or uncheck columns to customize active table view:")
        visible = []
        for col in all_cols:
            checked = st.checkbox(
                col,
                value=col in st.session_state[f"{key_prefix}_visible_cols"],
                key=f"{key_prefix}_col_{col}",
            )
            if checked:
                visible.append(col)
        if st.button(
            "Apply View", key=f"{key_prefix}_apply", use_container_width=True
        ):
            st.session_state[f"{key_prefix}_visible_cols"] = visible
            st.rerun()

    selected = st.session_state[f"{key_prefix}_visible_cols"]
    return [c for c in selected if c in df.columns]


# ============================================
# SECTION 5: SESSION STATE INITIALIZATION
# ============================================
if "app_launched" not in st.session_state:
    st.session_state["app_launched"] = False

# ============================================
# SECTION 6: LANDING SETUP SCREEN
# ============================================
if not st.session_state["app_launched"]:
    st.markdown(
        '<div class="landing-page-marker"></div>',
        unsafe_allow_html=True,
    )

    st.markdown("## 🏭 **PLASTIC-3 CONSOLE SETUP**")
    st.markdown("##### Upload your production entry files to launch.")
    st.divider()

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(
            '<div class="setup-card ff"><h3>🏢 First Floor (FF)</h3><p'
            ' style="color:#64748b !important;">Select the FF Excel production'
            " file</p></div>",
            unsafe_allow_html=True,
        )
        ff_file = st.file_uploader(
            "Upload First Floor File (.xlsx)",
            type=["xlsx", "xls"],
            key="init_ff",
        )

    with col2:
        st.markdown(
            '<div class="setup-card gf"><h3>🏬 Ground Floor (GF)</h3><p'
            ' style="color:#64748b !important;">Select the GF Excel production'
            " file</p></div>",
            unsafe_allow_html=True,
        )
        gf_file = st.file_uploader(
            "Upload Ground Floor File (.xlsx)",
            type=["xlsx", "xls"],
            key="init_gf",
        )

    st.divider()

    if st.button(
        "🚀 Launch Dashboard",
        type="primary",
        use_container_width=True,
    ):
        if ff_file is None and gf_file is None:
            st.error("Please upload at least one floor file to launch.")
        else:
            if ff_file is not None:
                st.session_state["ff_bytes"] = ff_file.getvalue()
            if gf_file is not None:
                st.session_state["gf_bytes"] = gf_file.getvalue()

            st.session_state["app_launched"] = True
            st.rerun()

# ============================================
# SECTION 7: MAIN DASHBOARD CONSOLE & SIDEBAR
# ============================================
else:
    st.markdown(
        '<div class="dashboard-page-marker"></div>',
        unsafe_allow_html=True,
    )

    all_parsed_dfs = []
    all_audit_dfs = []

    typo_overrides = st.session_state.get("typo_overrides", {})

    if "ff_bytes" in st.session_state:
        df_ff, df_ff_audit = load_and_parse_floor_data(
            st.session_state["ff_bytes"], "FF", typo_overrides
        )
        if not df_ff.empty:
            all_parsed_dfs.append(df_ff)
        if not df_ff_audit.empty:
            all_audit_dfs.append(df_ff_audit)

    if "gf_bytes" in st.session_state:
        df_gf, df_gf_audit = load_and_parse_floor_data(
            st.session_state["gf_bytes"], "GF", typo_overrides
        )
        if not df_gf.empty:
            all_parsed_dfs.append(df_gf)
        if not df_gf_audit.empty:
            all_audit_dfs.append(df_gf_audit)

    if not all_parsed_dfs:
        st.error(
            "No valid data parsed. Click '⚙️ Change Uploaded Files' in"
            " sidebar."
        )
    else:
        df_data_raw = pd.concat(all_parsed_dfs, ignore_index=True)
        df_typo_audit = (
            pd.concat(all_audit_dfs, ignore_index=True)
            if all_audit_dfs
            else pd.DataFrame()
        )

        st.session_state["df_data_raw"] = df_data_raw
        st.session_state["dashboard_ready"] = True

        with st.sidebar:
            col_logo, col_text = st.columns([1, 2.3], gap="small", vertical_alignment="center")
            with col_logo:
                if os.path.exists("logo.png"):
                    st.image("logo.png", use_container_width=True)
                else:
                    st.markdown("🏭")
            with col_text:
                st.markdown("### **PLASTIC-3 CONSOLE**")
                st.caption("Active Production Session")

            st.divider()

            nav_choice = st.radio(
                "📍 **Select Module:**",
                [
                    "📅 Daily Data",
                    "📊 As of Data (MTD)",
                    "📦 Job Order Analysis",
                    "🌗 Shiftwise Data",
                ],
            )

            st.divider()

            floor_choice = st.radio(
                "🏢 **Floor View:**",
                ["ALL FLOORS", "FF", "GF"],
                horizontal=True,
                key="floor_toggle",
            )

            st.divider()

            hide_zero_runs = st.toggle(
                "🚫 Hide Non-Running Machines",
                value=True,
                help="Filters out idle machines with zero production on Floor View",
            )

            st.divider()

            if st.button("📱 Launch SMS Module", use_container_width=True):
                st.switch_page("pages/sms.py")

            st.divider()

            if st.button("⚙️ Change Uploaded Files", use_container_width=True):
                st.session_state["app_launched"] = False
                st.session_state.pop("ff_bytes", None)
                st.session_state.pop("gf_bytes", None)
                st.session_state.pop("typo_overrides", None)
                st.session_state.pop("df_data_raw", None)
                st.session_state.pop("dashboard_ready", None)
                st.rerun()

        if floor_choice == "FF" and "ff_bytes" not in st.session_state:
            st.warning("⚠️ **First Floor (FF) file is not uploaded.**")
        elif floor_choice == "GF" and "gf_bytes" not in st.session_state:
            st.warning("⚠️ **Ground Floor (GF) file is not uploaded.**")
        else:
            if floor_choice != "ALL FLOORS":
                df_curr = df_data_raw[
                    df_data_raw["Floor"] == floor_choice
                ].copy()
            else:
                df_curr = df_data_raw.copy()

            if hide_zero_runs:
                df_active = df_curr[
                    (df_curr["Total Good"] > 0)
                    | (df_curr["Total Runtime (Hrs)"] > 0)
                ].copy()
            else:
                df_active = df_curr.copy()

            def render_typo_popover():
                if not df_typo_audit.empty:
                    with st.popover(f"🚨 {len(df_typo_audit)} Typos Found"):
                        st.markdown("#### 🔍 Data Quality & In-App Typo Correction")
                        st.caption(
                            "Review flagged drag-down errors or edit individually below:"
                        )

                        for idx_t, t_row in df_typo_audit.iterrows():
                            t_key = t_row["Key"]
                            with st.expander(
                                f"📍 {t_row['Date']} | {t_row['Floor']} - {t_row['Machine SL']} ({t_row['Order Name']})"
                            ):
                                st.write(f"**Issue:** {t_row['Issue Detected']}")
                                st.caption(
                                    "Suggested Master Position:"
                                    f" `{t_row['Suggested MC SL']}`"
                                )

                                col_t1, col_t2, col_t3 = st.columns(3)
                                with col_t1:
                                    new_mc = st.text_input(
                                        "Machine SL",
                                        value=str(t_row["Suggested MC SL"]),
                                        key=f"mc_{t_key}",
                                    )
                                with col_t2:
                                    new_ct = st.number_input(
                                        "CT (s)",
                                        value=float(t_row["Current CT"]),
                                        key=f"ct_{t_key}",
                                    )
                                with col_t3:
                                    new_cav = st.number_input(
                                        "Cavity",
                                        value=float(t_row["Current Cavity"]),
                                        key=f"cav_{t_key}",
                                    )

                                if st.button("💾 Apply Correction", key=f"btn_{t_key}"):
                                    if "typo_overrides" not in st.session_state:
                                        st.session_state["typo_overrides"] = {}
                                    st.session_state["typo_overrides"][t_key] = {
                                        "mc_sl": new_mc,
                                        "ct": new_ct,
                                        "cavity": new_cav,
                                    }
                                    st.success("Correction saved! Refreshing console...")
                                    st.rerun()

                        st.divider()

                        # 1-CLICK BATCH AUTO-CORRECT ALL TYPOS AT BOTTOM OF LIST
                        if st.button(
                            f"⚡ Auto-Correct All Typos ({len(df_typo_audit)})",
                            type="primary",
                            use_container_width=True,
                        ):
                            if "typo_overrides" not in st.session_state:
                                st.session_state["typo_overrides"] = {}
                            for _, t_row in df_typo_audit.iterrows():
                                t_key = t_row["Key"]
                                st.session_state["typo_overrides"][t_key] = {
                                    "mc_sl": t_row["Suggested MC SL"],
                                    "ct": t_row["Current CT"],
                                    "cavity": t_row["Current Cavity"],
                                }
                            st.success(
                                "All machine typos resolved to master registry! Refreshing..."
                            )
                            st.rerun()

                        if st.button("🔄 Reset All Corrections", use_container_width=True):
                            st.session_state["typo_overrides"] = {}
                            st.rerun()
                else:
                    st.button("🟢 All Data Valid", disabled=True)

            # ============================================
            # SECTION 8: MODULE 1 — DAILY DATA
            # ============================================
            if nav_choice == "📅 Daily Data":
                all_dates = sorted(list(df_active["Date"].unique()))

                col_nav1, col_nav2, col_nav3 = st.columns([3.5, 1.2, 1.3])

                with col_nav1:
                    daily_mode = st.radio(
                        "Daily View Mode:",
                        [
                            "📊 Linewise",
                            "🏭 MC Wise",
                            "📏 Sizewise",
                            "📦 Job-Order Wise",
                        ],
                        horizontal=True,
                        label_visibility="collapsed",
                    )

                with col_nav2:
                    selected_date = st.selectbox(
                        "Operational Date",
                        all_dates,
                        index=len(all_dates) - 1 if all_dates else 0,
                        label_visibility="collapsed",
                    )

                with col_nav3:
                    render_typo_popover()

                st.divider()

                df_daily_raw = df_active[
                    df_active["Date"] == selected_date
                ].copy()
                df_daily = consolidate_daily_machines(df_daily_raw)

                tot_prod_ton = df_daily["Total Prod Ton"].sum()
                tot_cap_ton = df_daily["Weighted Cap Ton"].sum()
                tot_good_pcs = df_daily["Total Good"].sum()
                tot_cap_pcs = df_daily["Weighted Cap Pcs"].sum()
                tot_rej = df_daily["Total Rejections"].sum()
                tot_time = df_daily["Total Runtime (Hrs)"].sum()

                ton_ach = (
                    (tot_prod_ton / tot_cap_ton * 100)
                    if tot_cap_ton > 0
                    else 0.0
                )
                pcs_ach = (
                    (tot_good_pcs / tot_cap_pcs * 100)
                    if tot_cap_pcs > 0
                    else 0.0
                )

                c1, c2, c3, c4 = st.columns(4)
                c1.metric(
                    "Prod vs Cap (Tons)",
                    f"{tot_prod_ton:.2f} / {tot_cap_ton:.2f} T",
                    f"Ach: {ton_ach:.2f}%",
                )
                c2.metric(
                    "Prod vs Cap (Pieces)",
                    f"{int(tot_good_pcs):,} Pcs",
                    f"Ach: {pcs_ach:.2f}%",
                )
                c3.metric(
                    "Total Rejections",
                    f"{int(tot_rej):,} Pcs",
                    f"Quality Loss: {(tot_rej/tot_good_pcs*100):.2f}%"
                    if tot_good_pcs > 0
                    else "0.00%",
                )
                c4.metric(
                    "Running Machines",
                    f"{df_daily['Machine'].nunique()} MCs",
                    f"Runtime: {tot_time:.2f} Hrs",
                )

                st.divider()

                if daily_mode == "📊 Linewise":
                    st.markdown("### 📈 Line-Wise Performance Summary")
                    df_line_day = compute_line_summary(df_daily_raw)
                    df_line_day_tot = add_total_row(
                        df_line_day,
                        "Line Group",
                        [
                            "Running MC Qty",
                            "Runtime (Hrs)",
                            "Cap (Pcs)",
                            "Prod (Pcs)",
                            "Cap (Ton)",
                            "Prod (Ton)",
                        ],
                        [],
                    )

                    v_cols = column_visibility_selector(
                        df_line_day_tot, "daily_line"
                    )
                    clean_line_df = clean_and_format_dataframe(df_line_day_tot[v_cols])
                    st.dataframe(
                        clean_line_df,
                        use_container_width=True,
                        hide_index=True,
                    )

                    st.download_button(
                        "📥 Export Daily Line Summary (.xlsx)",
                        convert_df_to_excel_bytes(clean_line_df),
                        "Daily_Line_Summary.xlsx",
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )

                elif daily_mode == "🏭 MC Wise":
                    st.markdown("### 🏭 Consolidated Machine Performance")
                    df_daily_totals = add_total_row(
                        df_daily,
                        "Machine",
                        [
                            "Shift A Good",
                            "Shift B Good",
                            "Total Good",
                            "Total Rejections",
                            "Shift A Runtime",
                            "Shift B Runtime",
                            "Total Runtime (Hrs)",
                            "Weighted Cap Pcs",
                            "Weighted Cap Ton",
                            "Total Prod Ton",
                        ],
                        ["CT", "Cavity"],
                    )

                    v_cols = column_visibility_selector(
                        df_daily_totals, "daily_mc"
                    )
                    clean_mc_df = clean_and_format_dataframe(df_daily_totals[v_cols])
                    st.dataframe(
                        clean_mc_df,
                        use_container_width=True,
                        hide_index=True,
                    )

                    st.download_button(
                        "📥 Export Daily Machine Summary (.xlsx)",
                        convert_df_to_excel_bytes(clean_mc_df),
                        "Daily_Machine_Summary.xlsx",
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )

                    mixed_mcs = df_daily[df_daily["Is Mixed"]][
                        "Machine"
                    ].tolist()
                    if mixed_mcs:
                        st.divider()
                        st.markdown(
                            "#### 🔍 Inspect Mixed Machine Breakdown (Inside Story)"
                        )
                        sel_mc = st.selectbox(
                            "Select a Mixed Machine ID to view its mold run breakdown:",
                            mixed_mcs,
                        )
                        sub_raw = df_daily_raw[
                            df_daily_raw["Machine"] == sel_mc
                        ].copy()

                        sub_raw["Daily Cap (Pcs)"] = sub_raw[
                            "Weighted Cap Pcs"
                        ].round(2)
                        sub_raw["Daily Prod (Ton)"] = sub_raw[
                            "Total Prod Ton"
                        ].round(2)
                        sub_raw["Runtime (Hrs)"] = sub_raw[
                            "Total Runtime (Hrs)"
                        ].round(2)

                        clean_sub_raw = clean_and_format_dataframe(
                            sub_raw[[
                                "Floor",
                                "Order Name",
                                "Item Name",
                                "CT",
                                "Cavity",
                                "Shift A Good",
                                "Shift B Good",
                                "Total Good",
                                "Runtime (Hrs)",
                                "Daily Prod (Ton)",
                            ]]
                        )
                        st.dataframe(
                            clean_sub_raw,
                            use_container_width=True,
                            hide_index=True,
                        )

                elif daily_mode == "📏 Sizewise":
                    st.markdown("### 📏 Machine Size Summary")
                    df_size_day = compute_size_summary(
                        df_daily_raw, mode="daily"
                    )
                    df_size_day_tot = add_total_row(
                        df_size_day,
                        "MC Size",
                        [
                            "MC QTY",
                            "Total Cap (Pcs)",
                            "Total Prod (Pcs)",
                            "Cap (Ton)",
                            "Prod (Ton)",
                        ],
                        ["CT Average", "Run Hour Average"],
                    )

                    v_cols = column_visibility_selector(
                        df_size_day_tot, "daily_size"
                    )
                    clean_size_df = clean_and_format_dataframe(df_size_day_tot[v_cols])
                    st.dataframe(
                        clean_size_df,
                        use_container_width=True,
                        hide_index=True,
                    )

                    st.download_button(
                        "📥 Export Daily Size Summary (.xlsx)",
                        convert_df_to_excel_bytes(clean_size_df),
                        "Daily_Size_Summary.xlsx",
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )

                elif daily_mode == "📦 Job-Order Wise":
                    st.markdown("### 📦 Active Orders Run On Selected Date")

                    col_top1, col_top2 = st.columns([1.2, 2.5])

                    records_job_day = []
                    for (
                        cust,
                        ord_name,
                        acc_cd,
                    ), grp in df_daily_raw.groupby(
                        ["Customer", "Order Name", "Acc Code"]
                    ):
                        itm_name = grp["Item Name"].iloc[0]
                        merged_demand = grp["Demand Qty"].sum()
                        tot_good_val = grp["Total Good"].sum()
                        tot_prod_ton_val = grp["Total Prod Ton"].sum()
                        cap_ton_val = grp["Weighted Cap Ton"].sum()
                        cap_pcs_val = grp["Weighted Cap Pcs"].sum()
                        tot_runtime_val = grp["Total Runtime (Hrs)"].sum()

                        mc_count = grp["Machine"].nunique()
                        mc_pos = ", ".join(sorted(grp["Machine"].unique()))

                        ach_ton_val = (
                            (tot_prod_ton_val / cap_ton_val * 100)
                            if cap_ton_val > 0
                            else 0.0
                        )
                        ach_pcs_val = (
                            (tot_good_val / cap_pcs_val * 100)
                            if cap_pcs_val > 0
                            else 0.0
                        )

                        records_job_day.append({
                            "Customer": cust,
                            "Order Name": ord_name,
                            "Acc Code": acc_cd,
                            "Item Name": itm_name,
                            "Demand Qty": merged_demand,
                            "Total Good": tot_good_val,
                            "Total Prod Ton": round(tot_prod_ton_val, 2),
                            "Running Molds": mc_count,
                            "MC Positions": mc_pos,
                            "Daily Cap (Pcs)": round(cap_pcs_val, 2),
                            "Daily Prod (Pcs)": round(tot_good_val, 2),
                            "Daily Util (Pcs %)": f"{ach_pcs_val:.2f}%",
                            "Daily Cap (Ton)": round(cap_ton_val, 2),
                            "Daily Prod (Ton)": round(tot_prod_ton_val, 2),
                            "Daily Util (Ton %)": f"{ach_ton_val:.2f}%",
                            "Daily Runtime (Hrs)": round(tot_runtime_val, 2),
                        })

                    job_day = pd.DataFrame(records_job_day)

                    with col_top2:
                        search_term = st.text_input(
                            "Search Daily Orders",
                            "",
                            placeholder="🔍 Search Job Order or Item Name...",
                            label_visibility="collapsed",
                            key="search_daily_job",
                        )

                    if search_term.strip():
                        term = search_term.strip().lower()
                        job_day = job_day[
                            job_day["Order Name"].str.lower().str.contains(term)
                            | job_day["Item Name"].str.lower().str.contains(term)
                            | job_day["Customer"].str.lower().str.contains(term)
                        ]

                    job_day_tot = add_total_row(
                        job_day,
                        "Order Name",
                        [
                            "Demand Qty",
                            "Total Good",
                            "Total Prod Ton",
                            "Running Molds",
                            "Daily Cap (Pcs)",
                            "Daily Prod (Pcs)",
                            "Daily Cap (Ton)",
                            "Daily Prod (Ton)",
                            "Daily Runtime (Hrs)",
                        ],
                        [],
                    )

                    with col_top1:
                        v_cols = column_visibility_selector(
                            job_day_tot, "daily_job"
                        )

                    clean_job_day_df = clean_and_format_dataframe(job_day_tot[v_cols])
                    st.dataframe(
                        clean_job_day_df,
                        use_container_width=True,
                        hide_index=True,
                    )

                    st.download_button(
                        "📥 Export Daily Active Job Summary (.xlsx)",
                        convert_df_to_excel_bytes(clean_job_day_df),
                        "Daily_Job_Summary.xlsx",
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )

            # ============================================
            # SECTION 9: MODULE 2 — AS OF DATA (MTD)
            # ============================================
            elif nav_choice == "📊 As of Data (MTD)":
                all_dates = sorted(list(df_active["Date"].unique()))

                col_mtd1, col_mtd2, col_mtd3 = st.columns([3.5, 1.2, 1.3])

                with col_mtd1:
                    mtd_mode = st.radio(
                        "As-Of View Mode:",
                        [
                            "📊 Linewise",
                            "📏 Sizewise",
                            "📦 Job-Order Wise",
                        ],
                        horizontal=True,
                        label_visibility="collapsed",
                    )

                with col_mtd2:
                    as_of_date = st.selectbox(
                        "As-Of Cutoff Date",
                        all_dates,
                        index=len(all_dates) - 1 if all_dates else 0,
                        label_visibility="collapsed",
                    )

                with col_mtd3:
                    render_typo_popover()

                st.divider()

                df_mtd = df_active[df_active["Date"] <= as_of_date].copy()

                tot_prod = df_mtd["Total Prod Ton"].sum()
                tot_cap = df_mtd["Weighted Cap Ton"].sum()
                tot_good = df_mtd["Total Good"].sum()
                tot_cap_pcs = df_mtd["Weighted Cap Pcs"].sum()
                tot_runtime = df_mtd["Total Runtime (Hrs)"].sum()
                ach_rate = (tot_prod / tot_cap * 100) if tot_cap > 0 else 0.0

                cum_mc_days = df_mtd[df_mtd["Total Good"] > 0].groupby("Date")["Machine"].nunique().sum()

                c1, c2, c3, c4 = st.columns(4)
                c1.metric(
                    "Cumulative Tonnage",
                    f"{tot_prod:.2f} T",
                    f"Cap: {tot_cap:.2f} T",
                )
                c2.metric(
                    "Cumulative Pieces",
                    f"{int(tot_good):,} Pcs",
                    f"Cap: {int(tot_cap_pcs):,} Pcs",
                )
                c3.metric("Achievement Rate", f"{ach_rate:.2f}%")
                c4.metric(
                    "Cumulative MC-Days",
                    f"{cum_mc_days} MC-Days",
                    f"Runtime: {tot_runtime:.2f} Hrs",
                )

                st.divider()

                if mtd_mode == "📊 Linewise":
                    st.markdown(
                        f"### 📈 Line-Wise Summary (As of {as_of_date})"
                    )
                    df_line_mtd = compute_line_summary_mtd(df_mtd)
                    df_line_mtd_tot = add_total_row(
                        df_line_mtd,
                        "Line Group",
                        [
                            "Running MC Qty",
                            "Runtime (Hrs)",
                            "Cap (Pcs)",
                            "Prod (Pcs)",
                            "Cap (Ton)",
                            "Prod (Ton)",
                        ],
                        [],
                    )

                    v_cols = column_visibility_selector(
                        df_line_mtd_tot, "mtd_line"
                    )
                    clean_line_mtd_df = clean_and_format_dataframe(df_line_mtd_tot[v_cols])
                    st.dataframe(
                        clean_line_mtd_df,
                        use_container_width=True,
                        hide_index=True,
                    )

                    st.download_button(
                        "📥 Export As-Of Line Summary (.xlsx)",
                        convert_df_to_excel_bytes(clean_line_mtd_df),
                        "AsOf_Line_Summary.xlsx",
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )

                elif mtd_mode == "📏 Sizewise":
                    st.markdown(
                        f"### 📏 Machine Size Summary (As of {as_of_date})"
                    )

                    df_size_mtd = compute_size_summary(df_mtd, mode="as_of")
                    df_size_mtd_tot = add_total_row(
                        df_size_mtd,
                        "MC Size",
                        [
                            "MC QTY",
                            "Total Cap (Pcs)",
                            "Total Prod (Pcs)",
                            "Cap (Ton)",
                            "Prod (Ton)",
                        ],
                        ["CT Average", "Run Hour Average"],
                    )

                    v_cols = column_visibility_selector(
                        df_size_mtd_tot, "mtd_size"
                    )
                    clean_size_mtd_df = clean_and_format_dataframe(df_size_mtd_tot[v_cols])
                    st.dataframe(
                        clean_size_mtd_df,
                        use_container_width=True,
                        hide_index=True,
                    )

                    st.download_button(
                        "📥 Export As-Of Size Summary (.xlsx)",
                        convert_df_to_excel_bytes(clean_size_mtd_df),
                        "AsOf_Size_Summary.xlsx",
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )

                elif mtd_mode == "📦 Job-Order Wise":
                    st.markdown(
                        f"### 📦 Master Order Completion Summary (As of {as_of_date})"
                    )

                    job_records = []
                    for (cust, ord_name, acc_cd), grp in df_mtd.groupby(
                        ["Customer", "Order Name", "Acc Code"]
                    ):
                        latest_run = grp.sort_values("DateObj").iloc[-1]
                        last_run_date = latest_run["Date"]
                        itm_name = latest_run["Item Name"]

                        cutoff_grp = grp[grp["Date"] == as_of_date]

                        if not cutoff_grp.empty:
                            order_qty = cutoff_grp["Demand Qty"].sum()
                            due_prod_present = cutoff_grp["Due Prod Present"].sum()
                            as_of_prod = order_qty - due_prod_present
                            last_mcs = ", ".join(sorted(cutoff_grp[cutoff_grp["Total Good"] > 0]["Machine"].unique()))
                            last_day_output = cutoff_grp["Last Day Prod Col"].sum()
                            last_day_cap = cutoff_grp["Daily Cap Pcs"].sum()
                        else:
                            order_qty = latest_run["Demand Qty"] if latest_run["Demand Qty"] > 0 else grp["Demand Qty"].max()
                            due_prod_present = latest_run["Due Prod Present"]
                            as_of_prod = max(0.0, order_qty - due_prod_present) if order_qty > 0 else grp["Total Good"].sum()
                            last_date_runs = grp[grp["Date"] == last_run_date]
                            last_mcs = ", ".join(sorted(last_date_runs[last_date_runs["Total Good"] > 0]["Machine"].unique()))
                            last_day_output = last_date_runs["Last Day Prod Col"].sum()
                            last_day_cap = last_date_runs["Daily Cap Pcs"].sum()

                        tot_prod_ton_cum = grp["Total Prod Ton"].sum()
                        tot_runtime_cum = grp["Total Runtime (Hrs)"].sum()

                        as_of_pct = (
                            (as_of_prod / order_qty * 100)
                            if order_qty > 0
                            else 0.0
                        )

                        last_day_util = (
                            (last_day_output / last_day_cap * 100)
                            if last_day_cap > 0
                            else 0.0
                        )

                        job_records.append({
                            "Customer": cust,
                            "Order Name": ord_name,
                            "Acc Code": acc_cd,
                            "Item Name": itm_name,
                            "Order Qty": order_qty,
                            "Due Production": round(due_prod_present, 2),
                            "As of Production": round(as_of_prod, 2),
                            "As of %": f"{as_of_pct:.2f}%",
                            "Last Run Date": last_run_date,
                            "Last MC Assigned": last_mcs,
                            "Last Day Cap (Pcs)": round(last_day_cap, 2),
                            "Last Day Output (Pcs)": round(last_day_output, 2),
                            "Last Day Util %": f"{last_day_util:.2f}%",
                            "Total Prod Ton": round(tot_prod_ton_cum, 2),
                            "Total Runtime (Hrs)": round(tot_runtime_cum, 2),
                            "Is Completed": due_prod_present <= 0 or as_of_pct >= 100.0,
                        })

                    df_job_mtd = pd.DataFrame(job_records)

                    if df_job_mtd.empty:
                        st.info("No active or completed job orders logged up to the selected cutoff date.")
                    else:
                        st_tab1, st_tab2 = st.tabs([
                            f"🔄 Active Orders ({len(df_job_mtd[~df_job_mtd['Is Completed']])})",
                            f"✅ Completed Orders ({len(df_job_mtd[df_job_mtd['Is Completed']])})",
                        ])

                        with st_tab1:
                            col_top1, col_top2 = st.columns([1.2, 2.5])

                            df_active_jobs = df_job_mtd[
                                ~df_job_mtd["Is Completed"]
                            ].copy()

                            with col_top2:
                                search_active = st.text_input(
                                    "Search Active Orders",
                                    "",
                                    placeholder="🔍 Search Job Order or Item Name...",
                                    label_visibility="collapsed",
                                    key="search_active_mtd",
                                )

                            if search_active.strip():
                                term = search_active.strip().lower()
                                df_active_jobs = df_active_jobs[
                                    df_active_jobs["Order Name"]
                                    .str.lower()
                                    .str.contains(term)
                                    | df_active_jobs["Item Name"]
                                    .str.lower()
                                    .str.contains(term)
                                    | df_active_jobs["Customer"]
                                    .str.lower()
                                    .str.contains(term)
                                ]

                            df_active_tot = add_total_row(
                                df_active_jobs,
                                "Order Name",
                                [
                                    "Order Qty",
                                    "Due Production",
                                    "As of Production",
                                    "Total Prod Ton",
                                    "Total Runtime (Hrs)",
                                    "Last Day Cap (Pcs)",
                                    "Last Day Output (Pcs)",
                                ],
                                [],
                            )

                            with col_top1:
                                v_cols = column_visibility_selector(
                                    df_active_tot, "mtd_job_active"
                                )

                            clean_job_act_df = clean_and_format_dataframe(df_active_tot[v_cols])
                            st.dataframe(
                                clean_job_act_df,
                                use_container_width=True,
                                hide_index=True,
                            )

                            st.download_button(
                                "📥 Export Active MTD Job Summary (.xlsx)",
                                convert_df_to_excel_bytes(clean_job_act_df),
                                "Active_MTD_Job_Summary.xlsx",
                                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            )

                        with st_tab2:
                            col_top1_d, col_top2_d = st.columns([1.2, 2.5])

                            df_done_jobs = df_job_mtd[
                                df_job_mtd["Is Completed"]
                            ].copy()

                            with col_top2_d:
                                search_done = st.text_input(
                                    "Search Done Orders",
                                    "",
                                    placeholder="🔍 Search Job Order or Item Name...",
                                    label_visibility="collapsed",
                                    key="search_done_mtd",
                                )

                            if search_done.strip():
                                term = search_done.strip().lower()
                                df_done_jobs = df_done_jobs[
                                    df_done_jobs["Order Name"]
                                    .str.lower()
                                    .str.contains(term)
                                    | df_done_jobs["Item Name"]
                                    .str.lower()
                                    .str.contains(term)
                                    | df_done_jobs["Customer"]
                                    .str.lower()
                                    .str.contains(term)
                                ]

                            if df_done_jobs.empty:
                                st.info("No completed job orders recorded yet for this date.")
                            else:
                                df_done_tot = add_total_row(
                                    df_done_jobs,
                                    "Order Name",
                                    [
                                        "Order Qty",
                                        "Due Production",
                                        "As of Production",
                                        "Total Prod Ton",
                                        "Total Runtime (Hrs)",
                                        "Last Day Cap (Pcs)",
                                        "Last Day Output (Pcs)",
                                    ],
                                    [],
                                )

                                with col_top1_d:
                                    v_cols = column_visibility_selector(
                                        df_done_tot, "mtd_job_done"
                                    )

                                clean_job_done_df = clean_and_format_dataframe(df_done_tot[v_cols])
                                st.dataframe(
                                    clean_job_done_df,
                                    use_container_width=True,
                                    hide_index=True,
                                )

                                st.download_button(
                                    "📥 Export Completed MTD Job Summary (.xlsx)",
                                    convert_df_to_excel_bytes(clean_job_done_df),
                                    "Completed_MTD_Job_Summary.xlsx",
                                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                )

            # ============================================
            # SECTION 10: MODULE 3 — JOB ORDER ANALYSIS
            # ============================================
            elif nav_choice == "📦 Job Order Analysis":
                st.markdown("### 📦 Job Order Lifecycle & Full Period Analysis")
                st.caption("Inspect order demand completion milestones, item-wise daily machine allocations, and cumulative outputs.")
                st.divider()

                # Always use df_curr so unstarted items with 0 production remain visible
                all_unique_orders = sorted([str(o).strip() for o in df_curr["Order Name"].dropna().unique() if str(o).strip()])

                if not all_unique_orders:
                    st.info("No Job Orders found in the active dataset.")
                else:
                    col_sel1, col_sel2 = st.columns([2.5, 1.5])
                    with col_sel1:
                        sel_order = st.selectbox(
                            "🔍 **Search & Select Job Order:**",
                            all_unique_orders,
                            key="sel_job_analysis_order",
                        )

                    # Query full parsed orders
                    df_ord_raw = df_curr[df_curr["Order Name"] == sel_order].copy()
                    df_ord_raw = df_ord_raw.sort_values("DateObj")

                    cust_name = df_ord_raw["Customer"].iloc[0] if not df_ord_raw.empty else "-"
                    acc_code_name = df_ord_raw["Acc Code"].iloc[0] if not df_ord_raw.empty else "-"

                    with col_sel2:
                        st.markdown("<div style='margin-top: 1.6rem;'></div>", unsafe_allow_html=True)
                        st.markdown(f"**Customer:** `{cust_name}` &nbsp;|&nbsp; **Acc Code:** `{acc_code_name}`")

                    # Order-level Item Aggregates
                    item_summary_records = []
                    for item_name, i_grp in df_ord_raw.groupby("Item Name"):
                        i_grp_sorted = i_grp.sort_values("DateObj")
                        latest_item_entry = i_grp_sorted.iloc[-1]

                        i_demand = latest_item_entry["Demand Qty"] if latest_item_entry["Demand Qty"] > 0 else i_grp["Demand Qty"].max()
                        i_due = latest_item_entry["Due Prod Present"]
                        i_good_cum = i_grp["Total Good"].sum()
                        i_ton_cum = i_grp["Total Prod Ton"].sum()
                        i_runtime_cum = i_grp["Total Runtime (Hrs)"].sum()
                        i_color = latest_item_entry.get("Color", "-")

                        # Determine Last Run Date & Last MC Run & Last Day Capacity / Output
                        active_item_runs = i_grp_sorted[(i_grp_sorted["Total Good"] > 0) | (i_grp_sorted["Total Runtime (Hrs)"] > 0)]
                        if not active_item_runs.empty:
                            latest_active = active_item_runs.iloc[-1]
                            last_run_date = str(latest_active["Date"])
                            last_active_date_runs = active_item_runs[active_item_runs["Date"] == last_run_date]
                            last_mc_run = ", ".join(sorted(last_active_date_runs["Machine"].unique()))
                            last_day_prod_pcs = last_active_date_runs["Total Good"].sum()
                            # Proportional capacity calculated matching Daily Sizewise engine
                            last_day_cap_pcs = last_active_date_runs["Weighted Cap Pcs"].sum()
                        else:
                            last_run_date = "-"
                            last_mc_run = "-"
                            last_day_prod_pcs = 0.0
                            last_day_cap_pcs = 0.0

                        # Determine Completion Milestone
                        cum_tracker = 0
                        completion_date = None
                        for _, r_row in i_grp_sorted.iterrows():
                            cum_tracker += r_row["Total Good"]
                            if i_demand > 0 and cum_tracker >= i_demand:
                                completion_date = r_row["Date"]
                                break

                        if completion_date:
                            i_status = f"✅ Done on {completion_date}"
                        elif i_due <= 0 and i_demand > 0 and i_good_cum >= i_demand:
                            i_status = "✅ Completed"
                        elif i_good_cum > 0:
                            i_status = "🔄 In Progress"
                        else:
                            i_status = "⏳ Not Started"

                        i_pct = (i_good_cum / i_demand * 100) if i_demand > 0 else 0.0

                        item_summary_records.append({
                            "Job Order": sel_order,
                            "Item Name": item_name,
                            "Acc Code": latest_item_entry["Acc Code"],
                            "Color": i_color,
                            "Demand Qty": i_demand,
                            "Total Produced (Pcs)": i_good_cum,
                            "Remaining Due": round(max(0.0, i_demand - i_good_cum) if i_demand > 0 else i_due, 2),
                            "Fulfillment %": f"{i_pct:.2f}%",
                            "Last Run Date": last_run_date,
                            "Last MC Run": last_mc_run,
                            "Last Day Cap (Pcs)": round(last_day_cap_pcs, 2),
                            "Last Day Output (Pcs)": round(last_day_prod_pcs, 2),
                            "Total Produced (Ton)": round(i_ton_cum, 2),
                            "Total Runtime (Hrs)": round(i_runtime_cum, 2),
                            "Status": i_status,
                            "Completion Date": completion_date,
                            "Unit Wt (kg)": latest_item_entry["Unit Wt (kg)"],
                            "Cavity": latest_item_entry["Cavity"],
                            "CT": latest_item_entry["CT"],
                        })

                    df_items_sum = pd.DataFrame(item_summary_records)

                    # Top KPI Cards for Selected Order
                    tot_ord_demand = df_items_sum["Demand Qty"].sum()
                    tot_ord_prod = df_items_sum["Total Produced (Pcs)"].sum()
                    tot_ord_ton = df_items_sum["Total Produced (Ton)"].sum()
                    tot_ord_due = df_items_sum["Remaining Due"].sum()
                    ord_fulfill_pct = (tot_ord_prod / tot_ord_demand * 100) if tot_ord_demand > 0 else 0.0

                    k1, k2, k3, k4 = st.columns(4)
                    k1.metric("Total Order Demand", f"{int(tot_ord_demand):,} Pcs")
                    k2.metric("Produced to Date", f"{int(tot_ord_prod):,} Pcs", f"{tot_ord_ton:.2f} Tons")
                    k3.metric("Remaining Due Balance", f"{int(tot_ord_due):,} Pcs")
                    k4.metric("Order Fulfillment", f"{ord_fulfill_pct:.2f}%", "Overall Progress")

                    st.markdown("#### 📋 Items Under This Job Order")

                    # Base columns available in the table
                    item_display_cols = [
                        "Job Order",
                        "Item Name",
                        "Acc Code",
                        "Color",
                        "Demand Qty",
                        "Total Produced (Pcs)",
                        "Remaining Due",
                        "Fulfillment %",
                        "Last Run Date",
                        "Last MC Run",
                        "Last Day Cap (Pcs)",
                        "Last Day Output (Pcs)",
                        "Total Produced (Ton)",
                        "Total Runtime (Hrs)",
                        "Status",
                    ]

                    df_items_display = df_items_sum[item_display_cols].copy()

                    # Add total row
                    df_items_tot = add_total_row(
                        df_items_display,
                        "Item Name",
                        [
                            "Demand Qty",
                            "Total Produced (Pcs)",
                            "Remaining Due",
                            "Last Day Cap (Pcs)",
                            "Last Day Output (Pcs)",
                            "Total Produced (Ton)",
                            "Total Runtime (Hrs)",
                        ],
                        [],
                    )

                    # Hidden by default on-screen: Job Order, Acc Code, Color, Last Day Cap/Output, Ton, Runtime
                    v_item_cols = column_visibility_selector(
                        df_items_tot,
                        key_prefix="job_analysis_items",
                        custom_exclusions=[
                            "Job Order",
                            "Acc Code",
                            "Color",
                            "Last Day Cap (Pcs)",
                            "Last Day Output (Pcs)",
                            "Total Produced (Ton)",
                            "Total Runtime (Hrs)",
                        ],
                    )

                    clean_items_df = clean_and_format_dataframe(df_items_tot[v_item_cols])
                    st.dataframe(
                        clean_items_df,
                        use_container_width=True,
                        hide_index=True,
                    )

                    # Export includes all columns including Job Order
                    full_export_df = clean_and_format_dataframe(df_items_tot)
                    st.download_button(
                        f"📥 Export {sel_order} Item Summary (.xlsx)",
                        convert_df_to_excel_bytes(full_export_df),
                        f"JobOrder_{sel_order}_Items.xlsx",
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )

                    st.divider()

                    # Item-level Drill-down
                    st.markdown("#### 🔬 Item Daily Run Lifecycle & Machine Allocations")

                    unique_items = df_items_sum["Item Name"].tolist()
                    sel_item = st.selectbox("Select Item to Inspect Daily Production Timeline:", unique_items, key="sel_job_item_inspect")

                    df_sel_item_runs = df_ord_raw[df_ord_raw["Item Name"] == sel_item].sort_values("DateObj").copy()
                    item_meta = df_items_sum[df_items_sum["Item Name"] == sel_item].iloc[0]

                    col_m1, col_m2, col_m3, col_m4 = st.columns(4)
                    col_m1.caption(f"**Item Demand:** {int(item_meta['Demand Qty']):,} Pcs")
                    col_m2.caption(f"**Unit Weight:** {item_meta['Unit Wt (kg)']:.4f} kg")
                    col_m3.caption(f"**Cavity / CT:** {item_meta['Cavity']} Cav / {item_meta['CT']} s")
                    col_m4.caption(f"**Status:** {item_meta['Status']}")

                    timeline_records = []
                    running_cum_pcs = 0
                    running_cum_ton = 0.0
                    target_demand = item_meta["Demand Qty"]

                    for d_val, d_grp in df_sel_item_runs.groupby("Date", sort=False):
                        active_d_grp = d_grp[(d_grp["Total Good"] > 0) | (d_grp["Total Runtime (Hrs)"] > 0)]
                        if active_d_grp.empty:
                            continue

                        d_mcs = ", ".join(sorted(active_d_grp["Machine"].unique()))
                        d_floors = ", ".join(sorted(active_d_grp["Floor"].unique()))

                        d_a_good = active_d_grp["Shift A Good"].sum()
                        d_b_good = active_d_grp["Shift B Good"].sum()
                        d_good = active_d_grp["Total Good"].sum()
                        d_rej = active_d_grp["Total Rejections"].sum()
                        d_ton = active_d_grp["Total Prod Ton"].sum()
                        d_runtime = active_d_grp["Total Runtime (Hrs)"].sum()

                        running_cum_pcs += d_good
                        running_cum_ton += d_ton
                        rem_due = max(0.0, target_demand - running_cum_pcs) if target_demand > 0 else 0.0

                        if target_demand > 0 and running_cum_pcs >= target_demand:
                            if running_cum_pcs - d_good < target_demand:
                                day_status = f"🎯 Demand Done ({d_val})"
                            else:
                                day_status = "🟢 Buffer / Over-run"
                        else:
                            day_status = "🟡 In Progress"

                        timeline_records.append({
                            "Date": d_val,
                            "Floor": d_floors,
                            "Active Machines": d_mcs,
                            "Shift A Good (Pcs)": d_a_good,
                            "Shift B Good (Pcs)": d_b_good,
                            "Day Output (Pcs)": d_good,
                            "Rejections (Pcs)": d_rej,
                            "Day Output (Ton)": round(d_ton, 3),
                            "Runtime (Hrs)": round(d_runtime, 2),
                            "Cumulative Output (Pcs)": running_cum_pcs,
                            "Cumulative Output (Ton)": round(running_cum_ton, 2),
                            "Remaining Due (Pcs)": int(rem_due),
                            "Status": day_status,
                        })

                    df_timeline = pd.DataFrame(timeline_records)

                    if df_timeline.empty:
                        st.info("No active production runs found for this item.")
                    else:
                        df_timeline_tot = add_total_row(
                            df_timeline,
                            "Date",
                            [
                                "Shift A Good (Pcs)",
                                "Shift B Good (Pcs)",
                                "Day Output (Pcs)",
                                "Rejections (Pcs)",
                                "Day Output (Ton)",
                                "Runtime (Hrs)",
                            ],
                            [],
                        )

                        clean_timeline_df = clean_and_format_dataframe(df_timeline_tot)
                        st.dataframe(
                            clean_timeline_df,
                            use_container_width=True,
                            hide_index=True,
                        )

                        st.download_button(
                            f"📥 Export {sel_order} - {sel_item} Timeline (.xlsx)",
                            convert_df_to_excel_bytes(clean_timeline_df),
                            f"JobOrder_{sel_order}_{sel_item}_Timeline.xlsx",
                            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        )

            # ============================================
            # SECTION 11: MODULE 4 — SHIFTWISE DATA
            # ============================================
            elif nav_choice == "🌗 Shiftwise Data":
                shift_mode = st.radio(
                    "Shiftwise Mode:",
                    [
                        "📅 Daily Shiftwise",
                        "📊 As-Of Cumulative Shiftwise",
                    ],
                    horizontal=True,
                )

                a_ton = df_active["Shift A Prod Ton"].sum()
                a_good = df_active["Shift A Good"].sum()
                a_rej = df_active["Shift A Rej"].sum()
                a_hrs = df_active["Shift A Runtime"].sum()

                b_ton = df_active["Shift B Prod Ton"].sum()
                b_good = df_active["Shift B Good"].sum()
                b_rej = df_active["Shift B Rej"].sum()
                b_hrs = df_active["Shift B Runtime"].sum()

                c1, c2 = st.columns(2)
                with c1:
                    st.markdown("#### ☀️ Shift A (Day Shift)")
                    st.metric("Day Shift Tonnage", f"{a_ton:.2f} T")
                    st.metric(
                        "Day Shift Output",
                        f"{int(a_good):,} Pcs",
                        f"Rejections: {int(a_rej):,}",
                    )

                with c2:
                    st.markdown("#### 🌙 Shift B (Night Shift)")
                    st.metric("Night Shift Tonnage", f"{b_ton:.2f} T")
                    st.metric(
                        "Night Shift Output",
                        f"{int(b_good):,} Pcs",
                        f"Rejections: {int(b_rej):,}",
                    )

                st.divider()

                if shift_mode == "📅 Daily Shiftwise":
                    shift_daily = (
                        df_active.groupby("Date")[
                            [
                                "Shift A Good",
                                "Shift B Good",
                                "Shift A Prod Ton",
                                "Shift B Prod Ton",
                            ]
                        ]
                        .sum()
                        .reset_index()
                    )

                    shift_daily_tot = add_total_row(
                        shift_daily,
                        "Date",
                        [
                            "Shift A Good",
                            "Shift B Good",
                            "Shift A Prod Ton",
                            "Shift B Prod Ton",
                        ],
                        [],
                    )

                    v_cols = column_visibility_selector(
                        shift_daily_tot, "daily_shift"
                    )
                    clean_shift_df = clean_and_format_dataframe(shift_daily_tot[v_cols])
                    st.dataframe(
                        clean_shift_df,
                        use_container_width=True,
                        hide_index=True,
                    )

                    st.download_button(
                        "📥 Export Daily Shiftwise Log (.xlsx)",
                        convert_df_to_excel_bytes(clean_shift_df),
                        "Daily_Shiftwise_Log.xlsx",
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )

                elif shift_mode == "📊 As-Of Cumulative Shiftwise":
                    fig_shift = px.bar(
                        df_active.groupby("Date")[
                            ["Shift A Prod Ton", "Shift B Prod Ton"]
                        ]
                        .sum()
                        .reset_index(),
                        x="Date",
                        y=["Shift A Prod Ton", "Shift B Prod Ton"],
                        title="Daily Shift Comparison (Tonnage)",
                        barmode="group",
                        color_discrete_sequence=["#f59e0b", "#0f172a"],
                    )
                    st.plotly_chart(fig_shift, use_container_width=True)
