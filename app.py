import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st
from streamlit_option_menu import option_menu
import time

# Streamlit Page Setup
st.set_page_config(
    page_title="Plastic-3 Operations Console | FF & GF",
    page_icon="🏭",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============================================
# ENHANCED PROFESSIONAL CSS
# ============================================
st.markdown(
    """
    <style>
    /* ===== GLOBAL ===== */
    .stApp {
        background: #f0f4f8;
        font-family: 'Inter', 'Segoe UI', sans-serif;
    }
    
    /* ===== SIDEBAR ===== */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0f172a 0%, #1e293b 100%);
        border-right: 1px solid rgba(255,255,255,0.05);
    }
    [data-testid="stSidebar"] * {
        color: #e2e8f0 !important;
    }
    [data-testid="stSidebar"] .stSelectbox label,
    [data-testid="stSidebar"] .stRadio label {
        color: #94a3b8 !important;
        font-weight: 500;
        font-size: 12px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    [data-testid="stSidebar"] .stFileUploader {
        border: 2px dashed #334155;
        border-radius: 8px;
        padding: 12px;
        background: rgba(255,255,255,0.03);
    }
    [data-testid="stSidebar"] .stFileUploader:hover {
        border-color: #3b82f6;
        background: rgba(59,130,246,0.05);
    }
    
    /* ===== TOP NAVBAR ===== */
    .top-navbar {
        position: sticky;
        top: 0;
        z-index: 999;
        background: linear-gradient(135deg, #ffffff 0%, #f8fafc 100%);
        padding: 12px 32px;
        border-bottom: 1px solid #e2e8f0;
        box-shadow: 0 1px 3px rgba(0,0,0,0.04);
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 24px;
    }
    .navbar-brand {
        display: flex;
        align-items: center;
        gap: 12px;
    }
    .navbar-brand h1 {
        font-size: 20px;
        font-weight: 700;
        color: #0f172a;
        margin: 0;
        letter-spacing: -0.5px;
    }
    .navbar-brand span {
        font-size: 13px;
        color: #64748b;
        font-weight: 400;
        margin-left: 8px;
    }
    .navbar-stats {
        display: flex;
        gap: 28px;
        align-items: center;
    }
    .navbar-stat {
        display: flex;
        flex-direction: column;
        align-items: center;
    }
    .navbar-stat .label {
        font-size: 10px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        color: #94a3b8;
        font-weight: 600;
    }
    .navbar-stat .value {
        font-size: 16px;
        font-weight: 700;
        color: #0f172a;
    }
    .navbar-stat .value.success { color: #10b981; }
    .navbar-stat .value.warning { color: #f59e0b; }
    .navbar-stat .value.danger { color: #ef4444; }
    
    .live-indicator {
        display: flex;
        align-items: center;
        gap: 8px;
        font-size: 12px;
        color: #64748b;
        background: #f1f5f9;
        padding: 6px 14px;
        border-radius: 20px;
    }
    .live-dot {
        width: 8px;
        height: 8px;
        background: #10b981;
        border-radius: 50%;
        animation: pulse 2s infinite;
    }
    @keyframes pulse {
        0%, 100% { opacity: 1; transform: scale(1); }
        50% { opacity: 0.5; transform: scale(0.8); }
    }
    
    /* ===== METRIC CARDS ===== */
    .metric-grid {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 16px;
        margin-bottom: 24px;
    }
    .metric-card {
        background: #ffffff;
        border-radius: 12px;
        padding: 20px 24px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.04);
        border: 1px solid #f1f5f9;
        transition: all 0.3s ease;
        position: relative;
        overflow: hidden;
    }
    .metric-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(0,0,0,0.08);
    }
    .metric-card .icon {
        position: absolute;
        top: 16px;
        right: 16px;
        font-size: 28px;
        opacity: 0.15;
    }
    .metric-card .title {
        font-size: 11px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        color: #94a3b8;
        font-weight: 600;
        margin-bottom: 6px;
    }
    .metric-card .value {
        font-size: 26px;
        font-weight: 700;
        color: #0f172a;
        line-height: 1.2;
    }
    .metric-card .sub {
        font-size: 13px;
        color: #64748b;
        margin-top: 6px;
    }
    .metric-card .progress-bar {
        width: 100%;
        height: 4px;
        background: #f1f5f9;
        border-radius: 2px;
        margin-top: 10px;
        overflow: hidden;
    }
    .metric-card .progress-bar .fill {
        height: 100%;
        border-radius: 2px;
        transition: width 1s ease;
    }
    .metric-card .progress-bar .fill.green { background: #10b981; }
    .metric-card .progress-bar .fill.yellow { background: #f59e0b; }
    .metric-card .progress-bar .fill.red { background: #ef4444; }
    
    /* ===== TABS ===== */
    .custom-tabs {
        display: flex;
        gap: 4px;
        background: #f1f5f9;
        padding: 4px;
        border-radius: 10px;
        margin-bottom: 24px;
        border: 1px solid #e2e8f0;
    }
    .custom-tab {
        padding: 8px 20px;
        border-radius: 8px;
        font-size: 13px;
        font-weight: 500;
        color: #64748b;
        cursor: pointer;
        transition: all 0.2s ease;
        border: none;
        background: transparent;
        flex: 1;
        text-align: center;
    }
    .custom-tab:hover {
        color: #0f172a;
        background: rgba(255,255,255,0.5);
    }
    .custom-tab.active {
        background: #ffffff;
        color: #0f172a;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    }
    
    /* ===== TABLES ===== */
    .table-container {
        background: #ffffff;
        border-radius: 12px;
        padding: 20px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.06);
        border: 1px solid #f1f5f9;
        margin-bottom: 20px;
    }
    .table-container .table-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 16px;
    }
    .table-container .table-header h3 {
        font-size: 16px;
        font-weight: 600;
        color: #0f172a;
        margin: 0;
    }
    .table-container .table-header .controls {
        display: flex;
        gap: 12px;
        align-items: center;
    }
    
    /* Achievement Badges */
    .badge {
        padding: 3px 10px;
        border-radius: 12px;
        font-size: 12px;
        font-weight: 600;
        display: inline-block;
    }
    .badge.green { background: #d1fae5; color: #065f46; }
    .badge.yellow { background: #fef3c7; color: #92400e; }
    .badge.red { background: #fee2e2; color: #991b1b; }
    
    /* ===== EXPANDABLE ROWS ===== */
    .expand-btn {
        background: none;
        border: 1px solid #e2e8f0;
        border-radius: 6px;
        padding: 2px 10px;
        font-size: 14px;
        cursor: pointer;
        color: #64748b;
        transition: all 0.2s;
    }
    .expand-btn:hover {
        background: #f1f5f9;
        border-color: #94a3b8;
    }
    .expandable-content {
        background: #f8fafc;
        border-radius: 8px;
        padding: 16px;
        margin: 8px 0;
        border-left: 3px solid #3b82f6;
    }
    
    /* ===== STATUS BAR ===== */
    .status-bar {
        background: #ffffff;
        border-top: 1px solid #e2e8f0;
        padding: 10px 24px;
        margin-top: 24px;
        border-radius: 0 0 12px 12px;
        display: flex;
        justify-content: space-between;
        font-size: 12px;
        color: #94a3b8;
    }
    .status-bar .right {
        display: flex;
        gap: 20px;
    }
    
    /* ===== RESPONSIVE ===== */
    @media (max-width: 1024px) {
        .metric-grid { grid-template-columns: repeat(2, 1fr); }
        .navbar-stats { gap: 16px; }
    }
    @media (max-width: 640px) {
        .metric-grid { grid-template-columns: 1fr; }
        .top-navbar { flex-direction: column; gap: 12px; }
        .navbar-stats { flex-wrap: wrap; justify-content: center; }
        .custom-tabs { flex-wrap: wrap; }
        .custom-tab { flex: 1 1 auto; }
    }
    
    /* ===== ANIMATIONS ===== */
    @keyframes slideUp {
        from { opacity: 0; transform: translateY(20px); }
        to { opacity: 1; transform: translateY(0); }
    }
    .animate-in {
        animation: slideUp 0.5s ease forwards;
    }
    @keyframes countUp {
        from { opacity: 0; transform: scale(0.8); }
        to { opacity: 1; transform: scale(1); }
    }
    .count-animate {
        animation: countUp 0.6s ease forwards;
    }
    </style>
""",
    unsafe_allow_html=True,
)

# ============================================
# EXCEL CONFIGURATION (Your existing functions)
# ============================================
EXCEL_SIZES = [
    "160", "120", "280", "380", "330", "470", "530",
    "800", "270", "250", "428", "90"
]
SORTED_SIZES = sorted(EXCEL_SIZES, key=len, reverse=True)

def extract_excel_mc_size(mc_sl, size_col_val=None):
    if pd.notna(size_col_val):
        try:
            return str(int(float(size_col_val)))
        except (ValueError, TypeError):
            pass
    mc_str = str(mc_sl).strip().upper()
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

@st.cache_data
def load_and_parse_floor_data(file_bytes, floor_label):
    xls = pd.ExcelFile(file_bytes)
    date_sheets = [
        s for s in xls.sheet_names if "-" in s and ("202" in s or "203" in s)
    ]
    all_records = []
    for sheet in date_sheets:
        df = pd.read_excel(xls, sheet_name=sheet)
        df = df.dropna(how="all").reset_index(drop=True)
        if "MC SL" not in df.columns or "Order Name" not in df.columns:
            continue
        df = df[df["MC SL"].notna() & df["Order Name"].notna()].copy()
        for _, row in df.iterrows():
            mc_sl = str(row.get("MC SL")).strip()
            order = str(row.get("Order Name")).strip()
            item = str(row.get("Item Name", "")).strip()
            cust_prefix = (
                order.split("-")[0].strip().upper() if "-" in order else order
            )
            mc_size = extract_excel_mc_size(mc_sl, row.get("Size"))
            line_group = derive_line_group(floor_label, mc_sl)
            ct = (
                pd.to_numeric(row.get("CT"), errors="coerce")
                if pd.notna(row.get("CT")) else 0.0
            )
            cavity = (
                pd.to_numeric(row.get("Cavity"), errors="coerce")
                if pd.notna(row.get("Cavity")) else 0.0
            )
            unit_wt_kg = (
                pd.to_numeric(row.get("Unit Wt"), errors="coerce")
                if pd.notna(row.get("Unit Wt")) else 0.0
            )
            if pd.isna(ct): ct = 0.0
            if pd.isna(cavity): cavity = 0.0
            if pd.isna(unit_wt_kg): unit_wt_kg = 0.0
            std_cap_shift = (
                (43200.0 / ct) * cavity if ct > 0 and cavity > 0 else 0.0
            )
            act_cap_day_pcs = std_cap_shift * 2.0
            act_cap_day_ton = (act_cap_day_pcs * unit_wt_kg) / 1000.0
            demand_qty = (
                pd.to_numeric(row.get("Demand"), errors="coerce")
                if pd.notna(row.get("Demand")) else 0.0
            )
            if pd.isna(demand_qty): demand_qty = 0.0
            a_good = (
                pd.to_numeric(row.get("A-Good"), errors="coerce")
                if pd.notna(row.get("A-Good")) else 0.0
            )
            a_rej = (
                pd.to_numeric(row.get("A-Rejec"), errors="coerce")
                if pd.notna(row.get("A-Rejec")) else 0.0
            )
            if pd.isna(a_good): a_good = 0.0
            if pd.isna(a_rej): a_rej = 0.0
            a_runtime = (
                (a_good * 12.0) / std_cap_shift if std_cap_shift > 0 else 0.0
            )
            a_prod_ton = (a_good * unit_wt_kg) / 1000.0
            b_good = (
                pd.to_numeric(row.get("B-Good"), errors="coerce")
                if pd.notna(row.get("B-Good")) else 0.0
            )
            b_rej_val = row.get("B-Reject")
            if pd.isna(b_rej_val):
                b_rej_val = row.get("B-Reject Cause of Less Prod")
            b_rej = (
                pd.to_numeric(b_rej_val, errors="coerce")
                if pd.notna(b_rej_val) else 0.0
            )
            if pd.isna(b_good): b_good = 0.0
            if pd.isna(b_rej): b_rej = 0.0
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
                "Date": sheet.strip(),
                "Machine": mc_sl,
                "MC Size": mc_size,
                "Customer": cust_prefix,
                "Order Name": order,
                "Item Name": item,
                "Demand Qty": demand_qty,
                "Cavity": cavity,
                "CT": ct,
                "Unit Wt (kg)": unit_wt_kg,
                "STD Cap/Shift": std_cap_shift,
                "Daily Cap Pcs": act_cap_day_pcs,
                "Daily Cap Ton": act_cap_day_ton,
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
    if df_res.empty:
        return df_res
    mc_totals = (
        df_res.groupby(["Floor", "Date", "Machine"])["Total Runtime (Hrs)"]
        .sum()
        .reset_index()
        .rename(columns={"Total Runtime (Hrs)": "MC_Daily_Runtime"})
    )
    df_res = df_res.merge(mc_totals, on=["Floor", "Date", "Machine"])
    df_res["Runtime Weight"] = df_res.apply(
        lambda r: (
            r["Total Runtime (Hrs)"] / r["MC_Daily_Runtime"]
            if r["MC_Daily_Runtime"] > 0 else 1.0
        ),
        axis=1,
    )
    df_res["Weighted Cap Ton"] = (
        df_res["Daily Cap Ton"] * df_res["Runtime Weight"]
    )
    df_res["Weighted Cap Pcs"] = (
        df_res["Daily Cap Pcs"] * df_res["Runtime Weight"]
    )
    return df_res

def consolidate_daily_machines(df_day):
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
            group["Customer"].iloc[0] if len(group["Customer"].unique()) == 1 else "Mixed"
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
            "Cavity": round(weighted_cavity, 1),
            "CT": round(weighted_ct, 1),
            "Shift A Good": tot_a_good,
            "Shift B Good": tot_b_good,
            "Total Good": tot_good,
            "Total Rejections": tot_bad,
            "Shift A Runtime": a_runtime,
            "Shift B Runtime": b_runtime,
            "Total Runtime (Hrs)": mc_tot_runtime,
            "Weighted Cap Pcs": cap_pcs,
            "Weighted Cap Ton": cap_ton,
            "Total Prod Ton": prod_ton,
            "Ach Pcs %": (tot_good / cap_pcs * 100) if cap_pcs > 0 else 0.0,
            "Ach Ton %": (prod_ton / cap_ton * 100) if cap_ton > 0 else 0.0,
        })
    return pd.DataFrame(records)

def compute_line_summary(df_subset):
    records = []
    for lg, grp in df_subset.groupby("Line Group"):
        mc_qty = grp["Machine"].nunique()
        tot_runtime = grp["Total Runtime (Hrs)"].sum()
        tot_cap_pcs = grp["Weighted Cap Pcs"].sum()
        tot_prod_pcs = grp["Total Good"].sum()
        tot_cap_ton = grp["Weighted Cap Ton"].sum()
        tot_prod_ton = grp["Total Prod Ton"].sum()
        ach_pcs = (
            (tot_prod_pcs / tot_cap_pcs * 100) if tot_cap_pcs > 0 else 0.0
        )
        ach_ton = (
            (tot_prod_ton / tot_cap_ton * 100) if tot_cap_ton > 0 else 0.0
        )
        records.append({
            "Line Group": lg,
            "Running MC Qty": mc_qty,
            "Uptime (Hrs)": tot_runtime,
            "Cap (Pcs)": tot_cap_pcs,
            "Prod (Pcs)": tot_prod_pcs,
            "Pcs Ach %": ach_pcs,
            "Cap (Ton)": tot_cap_ton,
            "Prod (Ton)": tot_prod_ton,
            "Ton Ach %": ach_ton,
        })
    return pd.DataFrame(records)

def compute_size_summary(df_subset):
    records = []
    for sz in EXCEL_SIZES:
        grp = df_subset[df_subset["MC Size"] == sz]
        if grp.empty:
            continue
        mc_qty = grp["Machine"].nunique()
        tot_runtime = grp["Total Runtime (Hrs)"].sum()
        if tot_runtime > 0:
            avg_ct = (
                grp["CT"] * grp["Total Runtime (Hrs)"]
            ).sum() / tot_runtime
        else:
            avg_ct = grp["CT"].mean()
        avg_run_hrs = tot_runtime / mc_qty if mc_qty > 0 else 0.0
        tot_cap_pcs = grp["Weighted Cap Pcs"].sum()
        tot_prod_pcs = grp["Total Good"].sum()
        tot_cap_ton = grp["Weighted Cap Ton"].sum()
        tot_prod_ton = grp["Total Prod Ton"].sum()
        ach_pcs = (
            (tot_prod_pcs / tot_cap_pcs * 100) if tot_cap_pcs > 0 else 0.0
        )
        ach_ton = (
            (tot_prod_ton / tot_cap_ton * 100) if tot_cap_ton > 0 else 0.0
        )
        records.append({
            "MC Size": sz,
            "MC QTY": mc_qty,
            "CT Average": round(avg_ct, 1),
            "Run Hour Avg": round(avg_run_hrs, 2),
            "Total Cap (Pcs)": tot_cap_pcs,
            "Total Prod (Pcs)": tot_prod_pcs,
            "Pcs Ach %": ach_pcs,
            "Cap (Ton)": tot_cap_ton,
            "Prod (Ton)": tot_prod_ton,
            "Ton Ach %": ach_ton,
        })
    grp_other = df_subset[~df_subset["MC Size"].isin(EXCEL_SIZES)]
    if not grp_other.empty:
        mc_qty = grp_other["Machine"].nunique()
        tot_runtime = grp_other["Total Runtime (Hrs)"].sum()
        avg_ct = (
            (grp_other["CT"] * grp_other["Total Runtime (Hrs)"]).sum()
            / tot_runtime if tot_runtime > 0 else grp_other["CT"].mean()
        )
        avg_run_hrs = tot_runtime / mc_qty if mc_qty > 0 else 0.0
        tot_cap_pcs = grp_other["Weighted Cap Pcs"].sum()
        tot_prod_pcs = grp_other["Total Good"].sum()
        tot_cap_ton = grp_other["Weighted Cap Ton"].sum()
        tot_prod_ton = grp_other["Total Prod Ton"].sum()
        records.append({
            "MC Size": "Other",
            "MC QTY": mc_qty,
            "CT Average": round(avg_ct, 1),
            "Run Hour Avg": round(avg_run_hrs, 2),
            "Total Cap (Pcs)": tot_cap_pcs,
            "Total Prod (Pcs)": tot_prod_pcs,
            "Pcs Ach %": (tot_prod_pcs / tot_cap_pcs * 100)
            if tot_cap_pcs > 0 else 0.0,
            "Cap (Ton)": tot_cap_ton,
            "Prod (Ton)": tot_prod_ton,
            "Ton Ach %": (tot_prod_ton / tot_cap_ton * 100)
            if tot_cap_ton > 0 else 0.0,
        })
    return pd.DataFrame(records)

def add_total_row(df, label_col, sum_cols, avg_cols):
    if df.empty:
        return df
    res_df = df.copy()
    tot_row = {}
    for c in df.columns:
        if c == label_col:
            tot_row[c] = "TOTAL / OVERALL"
        elif c in sum_cols:
            tot_row[c] = df[c].sum()
        elif c in avg_cols:
            tot_row[c] = df[c].mean()
        else:
            tot_row[c] = "-"
    if "Total Cap (Pcs)" in df.columns and "Total Prod (Pcs)" in df.columns:
        tc_p = df["Total Cap (Pcs)"].sum()
        tp_p = df["Total Prod (Pcs)"].sum()
        tot_row["Pcs Ach %"] = (tp_p / tc_p * 100) if tc_p > 0 else 0.0
    if "Cap (Ton)" in df.columns and "Prod (Ton)" in df.columns:
        tc_t = df["Cap (Ton)"].sum()
        tp_t = df["Prod (Ton)"].sum()
        tot_row["Ton Ach %"] = (tp_t / tc_t * 100) if tc_t > 0 else 0.0
    if "Cap (Pcs)" in df.columns and "Prod (Pcs)" in df.columns:
        tc_p = df["Cap (Pcs)"].sum()
        tp_p = df["Prod (Pcs)"].sum()
        tot_row["Pcs Ach %"] = (tp_p / tc_p * 100) if tc_p > 0 else 0.0
    tot_df = pd.DataFrame([tot_row])
    return pd.concat([res_df, tot_df], ignore_index=True)

# ============================================
# HELPER FUNCTIONS FOR UI ENHANCEMENTS
# ============================================

def get_achievement_badge(value, target=80):
    """Return HTML badge based on achievement percentage."""
    if value >= target:
        return '<span class="badge green">✓ On Target</span>'
    elif value >= target - 20:
        return '<span class="badge yellow">⚠ Needs Attention</span>'
    else:
        return '<span class="badge red">✗ Below Target</span>'

def render_metric_card(title, value, subtext="", icon="📊", progress=None, progress_color="green"):
    """Render a professional metric card with optional progress bar."""
    progress_html = ""
    if progress is not None:
        progress_html = f"""
        <div class="progress-bar">
            <div class="fill {progress_color}" style="width: {min(progress, 100)}%"></div>
        </div>
        """
    
    return f"""
    <div class="metric-card animate-in">
        <div class="icon">{icon}</div>
        <div class="title">{title}</div>
        <div class="value count-animate">{value}</div>
        <div class="sub">{subtext}</div>
        {progress_html}
    </div>
    """

def apply_pagination(df, rows_per_page, page_number):
    """Apply pagination to a DataFrame."""
    start_idx = page_number * rows_per_page
    end_idx = start_idx + rows_per_page
    return df.iloc[start_idx:end_idx]

def pagination_controls(total_rows, rows_per_page, key_prefix=""):
    """Generate pagination controls."""
    total_pages = max(1, (total_rows + rows_per_page - 1) // rows_per_page)
    current_page = st.session_state.get(f"{key_prefix}_page", 0)
    
    cols = st.columns([1, 3, 1])
    with cols[0]:
        if st.button("◀ Previous", key=f"{key_prefix}_prev", disabled=current_page == 0):
            current_page = max(0, current_page - 1)
            st.session_state[f"{key_prefix}_page"] = current_page
            st.rerun()
    with cols[1]:
        st.caption(f"Page {current_page + 1} of {total_pages} ({total_rows} rows)")
    with cols[2]:
        if st.button("Next ▶", key=f"{key_prefix}_next", disabled=current_page >= total_pages - 1):
            current_page = min(total_pages - 1, current_page + 1)
            st.session_state[f"{key_prefix}_page"] = current_page
            st.rerun()
    
    return current_page, total_pages

def column_visibility_selector(df, key_prefix=""):
    """Generate column visibility selector dropdown."""
    all_cols = df.columns.tolist()
    default_cols = [c for c in all_cols if c not in ['Entry Count', 'Is Mixed']]
    
    if f"{key_prefix}_visible_cols" not in st.session_state:
        st.session_state[f"{key_prefix}_visible_cols"] = default_cols
    
    with st.popover("👁️ Columns"):
        visible = []
        for col in all_cols:
            checked = st.checkbox(
                col,
                value=col in st.session_state[f"{key_prefix}_visible_cols"],
                key=f"{key_prefix}_col_{col}"
            )
            if checked:
                visible.append(col)
        if st.button("Apply", key=f"{key_prefix}_apply"):
            st.session_state[f"{key_prefix}_visible_cols"] = visible
            st.rerun()
    
    return st.session_state[f"{key_prefix}_visible_cols"]

# ============================================
# SIDEBAR - File Upload & Controls
# ============================================
with st.sidebar:
    st.markdown("### 🏭 **PLASTIC-3 CONSOLE**")
    st.markdown("*FF & GF Production Monitoring*")
    st.divider()
    
    ff_file = st.file_uploader(
        "📁 First Floor (FF) File",
        type=["xlsx", "xls"],
        key="ff_up",
    )
    gf_file = st.file_uploader(
        "📁 Ground Floor (GF) File",
        type=["xlsx", "xls"],
        key="gf_up",
    )
    
    hide_zero_runs = st.toggle(
        "Hide Non-Running Machines",
        value=True,
        help="Filters out machines with zero production"
    )
    
    st.divider()
    
    # Floor selector
    floor_choice = st.radio(
        "🏢 Floor View",
        ["ALL FLOORS", "FF", "GF"],
        horizontal=True
    )
    
    st.divider()
    
    # Quick stats in sidebar
    if 'all_floor_data' in locals() and all_floor_data:
        st.markdown("### 📊 Quick Stats")
        st.caption(f"📅 Days: {df_data['Date'].nunique()}")
        st.caption(f"🏭 Machines: {df_data['Machine'].nunique()}")
        st.caption(f"📦 Orders: {df_data['Order Name'].nunique()}")

# ============================================
# MAIN CONTENT
# ============================================

# Load data
all_floor_data = []

if ff_file is not None:
    df_ff = load_and_parse_floor_data(ff_file, "FF")
    if not df_ff.empty:
        all_floor_data.append(df_ff)

if gf_file is not None:
    df_gf = load_and_parse_floor_data(gf_file, "GF")
   
