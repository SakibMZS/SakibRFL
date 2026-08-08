import io
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st
import time

# Streamlit Page Setup
st.set_page_config(
    page_title="Plastic-3 Operations Console | FF & GF",
    page_icon="🏭",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============================================
# HIGH-CONTRAST PROFESSIONAL CSS (FIXED CONTRAST)
# ============================================
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

    /* Global Theme */
    .stApp {
        background-color: #f8fafc;
        font-family: 'Inter', -apple-system, sans-serif;
        color: #0f172a;
    }
    
    /* Ensure all text labels & headers have crisp dark contrast */
    p, label, span, div, h1, h2, h3, h4, h5, h6 {
        color: #0f172a !important;
    }
    
    /* File Uploader Custom High-Contrast Styling */
    [data-testid="stFileUploader"] {
        background-color: #ffffff !important;
        border: 2px dashed #cbd5e1 !important;
        border-radius: 10px !important;
        padding: 16px !important;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05) !important;
    }
    [data-testid="stFileUploader"] * {
        color: #0f172a !important;
    }
    [data-testid="stFileUploader"] button {
        background-color: #2563eb !important;
        color: #ffffff !important;
        border: none !important;
        border-radius: 6px !important;
    }
    [data-testid="stFileUploader"] button * {
        color: #ffffff !important;
    }
    
    /* Sidebar Styling */
    [data-testid="stSidebar"] {
        background-color: #0f172a !important;
    }
    [data-testid="stSidebar"] * {
        color: #f8fafc !important;
    }
    [data-testid="stSidebar"] p, [data-testid="stSidebar"] label {
        color: #cbd5e1 !important;
    }
    
    /* Top Navbar */
    .top-navbar {
        background-color: #ffffff;
        padding: 16px 24px;
        border-radius: 12px;
        border: 1px solid #e2e8f0;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 20px;
    }
    
    /* Custom Setup Cards */
    .setup-card {
        background-color: #ffffff;
        padding: 24px;
        border-radius: 12px;
        border: 1px solid #e2e8f0;
        box-shadow: 0 2px 4px rgba(0,0,0,0.04);
        margin-bottom: 20px;
    }
    .setup-card.ff { border-top: 5px solid #2563eb; }
    .setup-card.gf { border-top: 5px solid #10b981; }
    
    /* Status Footer */
    .status-footer {
        background-color: #ffffff;
        border: 1px solid #e2e8f0;
        padding: 12px 20px;
        border-radius: 10px;
        display: flex;
        justify-content: space-between;
        font-size: 13px;
        color: #64748b !important;
        margin-top: 20px;
    }
    </style>
""",
    unsafe_allow_html=True,
)

# ============================================
# EXCEL CONFIGURATION & PARSER ENGINE
# ============================================
EXCEL_SIZES = [
    "160",
    "120",
    "280",
    "380",
    "330",
    "470",
    "530",
    "800",
    "270",
    "250",
    "428",
    "90",
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
    """Parses daily date sheets for a specific floor (FF or GF)."""
    # Wrap raw bytes inside io.BytesIO to resolve pandas TypeError
    file_stream = io.BytesIO(file_bytes)
    xls = pd.ExcelFile(file_stream)
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
                if pd.notna(row.get("CT"))
                else 0.0
            )
            cavity = (
                pd.to_numeric(row.get("Cavity"), errors="coerce")
                if pd.notna(row.get("Cavity"))
                else 0.0
            )
            unit_wt_kg = (
                pd.to_numeric(row.get("Unit Wt"), errors="coerce")
                if pd.notna(row.get("Unit Wt"))
                else 0.0
            )

            if pd.isna(ct):
                ct = 0.0
            if pd.isna(cavity):
                cavity = 0.0
            if pd.isna(unit_wt_kg):
                unit_wt_kg = 0.0

            std_cap_shift = (
                (43200.0 / ct) * cavity if ct > 0 and cavity > 0 else 0.0
            )
            act_cap_day_pcs = std_cap_shift * 2.0
            act_cap_day_ton = (act_cap_day_pcs * unit_wt_kg) / 1000.0

            demand_qty = (
                pd.to_numeric(row.get("Demand"), errors="coerce")
                if pd.notna(row.get("Demand"))
                else 0.0
            )
            if pd.isna(demand_qty):
                demand_qty = 0.0

            a_good = (
                pd.to_numeric(row.get("A-Good"), errors="coerce")
                if pd.notna(row.get("A-Good"))
                else 0.0
            )
            a_rej = (
                pd.to_numeric(row.get("A-Rejec"), errors="coerce")
                if pd.notna(row.get("A-Rejec"))
                else 0.0
            )
            if pd.isna(a_good):
                a_good = 0.0
            if pd.isna(a_rej):
                a_rej = 0.0

            a_runtime = (
                (a_good * 12.0) / std_cap_shift if std_cap_shift > 0 else 0.0
            )
            a_prod_ton = (a_good * unit_wt_kg) / 1000.0

            b_good = (
                pd.to_numeric(row.get("B-Good"), errors="coerce")
                if pd.notna(row.get("B-Good"))
                else 0.0
            )
            b_rej_val = row.get("B-Reject")
            if pd.isna(b_rej_val):
                b_rej_val = row.get("B-Reject Cause of Less Prod")
            b_rej = (
                pd.to_numeric(b_rej_val, errors="coerce")
                if pd.notna(b_rej_val)
                else 0.0
            )
            if pd.isna(b_good):
                b_good = 0.0
            if pd.isna(b_rej):
                b_rej = 0.0

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
            if r["MC_Daily_Runtime"] > 0
            else 1.0
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
            / tot_runtime
            if tot_runtime > 0
            else grp_other["CT"].mean()
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
            if tot_cap_pcs > 0
            else 0.0,
            "Cap (Ton)": tot_cap_ton,
            "Prod (Ton)": tot_prod_ton,
            "Ton Ach %": (tot_prod_ton / tot_cap_ton * 100)
            if tot_cap_ton > 0
            else 0.0,
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
# SESSION STATE INITIALIZATION
# ============================================
if "app_launched" not in st.session_state:
    st.session_state["app_launched"] = False

# ============================================
# LANDING SCREEN (HIGH-CONTRAST FILE SETUP)
# ============================================
if not st.session_state["app_launched"]:
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

    c_btn, _ = st.columns([1, 3])
    with c_btn:
        if st.button(
            "🚀 Launch Dashboard", type="primary", use_container_width=True
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
# MAIN DASHBOARD CONSOLE
# ============================================
else:
    # Sidebar Navigation
    with st.sidebar:
        st.markdown("### 🏭 **PLASTIC-3 CONSOLE**")
        st.caption("Active Production Session")
        st.divider()

        nav_choice = st.radio(
            "📍 **Select Module:**",
            [
                "📅 Daily Data",
                "📊 As of Data (MTD)",
                "🌗 Shiftwise Data",
            ],
        )

        st.divider()

        hide_zero_runs = st.toggle(
            "🚫 Hide Non-Running Machines",
            value=True,
            help="Filters out idle machines with zero production",
        )

        st.divider()

        if st.button("⚙️ Change Uploaded Files", use_container_width=True):
            st.session_state["app_launched"] = False
            st.session_state.pop("ff_bytes", None)
            st.session_state.pop("gf_bytes", None)
            st.rerun()

    # Parse Loaded Binary Bytes
    all_floor_data = []

    if "ff_bytes" in st.session_state:
        df_ff = load_and_parse_floor_data(st.session_state["ff_bytes"], "FF")
        if not df_ff.empty:
            all_floor_data.append(df_ff)

    if "gf_bytes" in st.session_state:
        df_gf = load_and_parse_floor_data(st.session_state["gf_bytes"], "GF")
        if not df_gf.empty:
            all_floor_data.append(df_gf)

    if not all_floor_data:
        st.error(
            "No valid data parsed. Click '⚙️ Change Uploaded Files' in"
            " sidebar."
        )
    else:
        df_data_raw = pd.concat(all_floor_data, ignore_index=True)

        # Header Bar
        col_hdr1, col_hdr2 = st.columns([3, 2])
        with col_hdr1:
            st.markdown(f"## {nav_choice}")
            st.caption(
                "Plastic-3 Production Optimization & Live Monitoring Panel"
            )

        with col_hdr2:
            floor_choice = st.radio(
                "🏢 Floor View Toggle:",
                ["ALL FLOORS", "FF", "GF"],
                horizontal=True,
                key="floor_toggle",
            )

        st.divider()

        # Handle Missing File Prompts
        if floor_choice == "FF" and "ff_bytes" not in st.session_state:
            st.warning(
                "⚠️ **First Floor (FF) file is not uploaded.** Please click '⚙️"
                " Change Uploaded Files' in the sidebar to upload the FF file."
            )
        elif floor_choice == "GF" and "gf_bytes" not in st.session_state:
            st.warning(
                "⚠️ **Ground Floor (GF) file is not uploaded.** Please click"
                " '⚙️ Change Uploaded Files' in the sidebar to upload the GF"
                " file."
            )
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

            # ============================================
            # 1. DAILY DATA MODULE
            # ============================================
            if nav_choice == "📅 Daily Data":
                all_dates = sorted(list(df_active["Date"].unique()))
                selected_date = st.selectbox(
                    "📅 Select Operational Date:", all_dates
                )

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
                    f"{tot_prod_ton:.1f} / {tot_cap_ton:.1f} T",
                    f"Ach: {ton_ach:.1f}%",
                )
                c2.metric(
                    "Prod vs Cap (Pieces)",
                    f"{int(tot_good_pcs):,} Pcs",
                    f"Ach: {pcs_ach:.1f}%",
                )
                c3.metric(
                    "Total Rejections",
                    f"{int(tot_rej):,} Pcs",
                    f"Quality Loss: {(tot_rej/tot_good_pcs*100):.1f}%"
                    if tot_good_pcs > 0
                    else "0%",
                )
                c4.metric(
                    "Running Machines",
                    f"{df_daily['Machine'].nunique()} MCs",
                    f"Uptime: {tot_time:.1f} Hrs",
                )

                st.divider()

                daily_mode = st.radio(
                    "Daily View Mode:",
                    [
                        "📊 Linewise",
                        "🏭 MC Wise",
                        "📏 Sizewise",
                        "📦 Job-Order Wise (Daily Active)",
                    ],
                    horizontal=True,
                )

                if daily_mode == "📊 Linewise":
                    st.markdown("### 📈 Line-Wise Performance Summary")
                    df_line_day = compute_line_summary(df_daily_raw)
                    df_line_day_tot = add_total_row(
                        df_line_day,
                        "Line Group",
                        [
                            "Running MC Qty",
                            "Uptime (Hrs)",
                            "Cap (Pcs)",
                            "Prod (Pcs)",
                            "Cap (Ton)",
                            "Prod (Ton)",
                        ],
                        [],
                    )
                    st.dataframe(
                        df_line_day_tot,
                        use_container_width=True,
                        hide_index=True,
                    )
                    st.download_button(
                        "📥 Export Daily Line Summary (CSV)",
                        df_line_day_tot.to_csv(index=False),
                        "Daily_Line_Summary.csv",
                        "text/csv",
                    )

                elif daily_mode == "🏭 MC Wise":
                    st.markdown("### 🏭 Consolidated Machine Performance")
                    df_daily_totals = add_total_row(
                        df_daily,
                        "Machine",
                        [
                            "Total Good",
                            "Total Rejections",
                            "Total Runtime (Hrs)",
                            "Weighted Cap Pcs",
                            "Weighted Cap Ton",
                            "Total Prod Ton",
                        ],
                        ["CT", "Cavity"],
                    )

                    st.dataframe(
                        df_daily_totals[[
                            "Floor",
                            "Line Group",
                            "Machine",
                            "MC Size",
                            "Order Name",
                            "Item Name",
                            "Cavity",
                            "CT",
                            "Total Good",
                            "Total Rejections",
                            "Total Runtime (Hrs)",
                            "Weighted Cap Pcs",
                            "Weighted Cap Ton",
                            "Total Prod Ton",
                            "Ach Ton %",
                        ]],
                        use_container_width=True,
                        hide_index=True,
                    )

                    st.download_button(
                        "📥 Export Daily Machine Summary (CSV)",
                        df_daily_totals.to_csv(index=False),
                        "Daily_Machine_Summary.csv",
                        "text/csv",
                    )

                    mixed_mcs = df_daily[df_daily["Is Mixed"]][
                        "Machine"
                    ].tolist()
                    if mixed_mcs:
                        with st.expander("🔍 Inspect Mixed Machine Breakdown"):
                            sel_mc = st.selectbox("Select Machine:", mixed_mcs)
                            sub_raw = df_daily_raw[
                                df_daily_raw["Machine"] == sel_mc
                            ]
                            st.dataframe(
                                sub_raw[[
                                    "Floor",
                                    "Order Name",
                                    "Item Name",
                                    "CT",
                                    "Cavity",
                                    "Shift A Good",
                                    "Shift B Good",
                                    "Total Good",
                                    "Total Runtime (Hrs)",
                                    "Total Prod Ton",
                                ]],
                                use_container_width=True,
                                hide_index=True,
                            )

                elif daily_mode == "📏 Sizewise":
                    st.markdown("### 📏 Machine Size Summary")
                    df_size_day = compute_size_summary(df_daily_raw)
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
                        ["CT Average", "Run Hour Avg"],
                    )
                    st.dataframe(
                        df_size_day_tot,
                        use_container_width=True,
                        hide_index=True,
                    )
                    st.download_button(
                        "📥 Export Daily Size Summary (CSV)",
                        df_size_day_tot.to_csv(index=False),
                        "Daily_Size_Summary.csv",
                        "text/csv",
                    )

                elif daily_mode == "📦 Job-Order Wise (Daily Active)":
                    st.markdown("### 📦 Active Orders Run On Selected Date")
                    job_day = (
                        df_daily_raw.groupby(
                            ["Customer", "Order Name", "Item Name"]
                        )
                        .agg({
                            "Total Good": "sum",
                            "Total Rejections": "sum",
                            "Total Prod Ton": "sum",
                            "Weighted Cap Ton": "sum",
                            "Weighted Cap Pcs": "sum",
                            "Total Runtime (Hrs)": "sum",
                            "Machine": "nunique",
                        })
                        .reset_index()
                        .rename(columns={"Machine": "Running Molds"})
                    )

                    job_day["Ach Ton %"] = (
                        job_day["Total Prod Ton"]
                        / job_day["Weighted Cap Ton"]
                        * 100
                    ).fillna(0)

                    job_day_tot = add_total_row(
                        job_day,
                        "Order Name",
                        [
                            "Total Good",
                            "Total Rejections",
                            "Total Prod Ton",
                            "Weighted Cap Ton",
                            "Weighted Cap Pcs",
                            "Total Runtime (Hrs)",
                            "Running Molds",
                        ],
                        [],
                    )

                    st.dataframe(
                        job_day_tot, use_container_width=True, hide_index=True
                    )
                    st.download_button(
                        "📥 Export Daily Active Job Summary (CSV)",
                        job_day_tot.to_csv(index=False),
                        "Daily_Job_Summary.csv",
                        "text/csv",
                    )

            # ============================================
            # 2. AS OF DATA (MTD) MODULE
            # ============================================
            elif nav_choice == "📊 As of Data (MTD)":
                all_dates = sorted(list(df_active["Date"].unique()))
                as_of_date = st.select_slider(
                    "📅 Filter Cumulative Data Up To Date:",
                    options=all_dates,
                    value=all_dates[-1],
                )

                df_mtd = df_active[df_active["Date"] <= as_of_date].copy()

                tot_prod = df_mtd["Total Prod Ton"].sum()
                tot_cap = df_mtd["Weighted Cap Ton"].sum()
                tot_good = df_mtd["Total Good"].sum()
                tot_cap_pcs = df_mtd["Weighted Cap Pcs"].sum()
                tot_runtime = df_mtd["Total Runtime (Hrs)"].sum()
                ach_rate = (tot_prod / tot_cap * 100) if tot_cap > 0 else 0.0

                c1, c2, c3, c4 = st.columns(4)
                c1.metric(
                    "Cumulative Tonnage",
                    f"{tot_prod:.1f} T",
                    f"Cap: {tot_cap:.1f} T",
                )
                c2.metric(
                    "Cumulative Pieces",
                    f"{int(tot_good):,} Pcs",
                    f"Cap: {int(tot_cap_pcs):,} Pcs",
                )
                c3.metric("Achievement Rate", f"{ach_rate:.1f}%")
                c4.metric(
                    "Total Operating Hours",
                    f"{tot_runtime:.1f} Hrs",
                    f"Days Count: {df_mtd['Date'].nunique()}",
                )

                st.divider()

                mtd_mode = st.radio(
                    "As-Of View Mode:",
                    [
                        "📊 Linewise",
                        "📏 Sizewise",
                        "📦 Job-Order Wise (Cumulative)",
                    ],
                    horizontal=True,
                )

                if mtd_mode == "📊 Linewise":
                    st.markdown(
                        f"### 📈 Line-Wise Summary (As of {as_of_date})"
                    )
                    df_line_mtd = compute_line_summary(df_mtd)
                    df_line_mtd_tot = add_total_row(
                        df_line_mtd,
                        "Line Group",
                        [
                            "Running MC Qty",
                            "Uptime (Hrs)",
                            "Cap (Pcs)",
                            "Prod (Pcs)",
                            "Cap (Ton)",
                            "Prod (Ton)",
                        ],
                        [],
                    )
                    st.dataframe(
                        df_line_mtd_tot,
                        use_container_width=True,
                        hide_index=True,
                    )
                    st.download_button(
                        "📥 Export As-Of Line Summary (CSV)",
                        df_line_mtd_tot.to_csv(index=False),
                        "AsOf_Line_Summary.csv",
                        "text/csv",
                    )

                elif mtd_mode == "📏 Sizewise":
                    st.markdown(
                        f"### 📏 Machine Size Summary (As of {as_of_date})"
                    )
                    df_size_mtd = compute_size_summary(df_mtd)
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
                        ["CT Average", "Run Hour Avg"],
                    )
                    st.dataframe(
                        df_size_mtd_tot,
                        use_container_width=True,
                        hide_index=True,
                    )
                    st.download_button(
                        "📥 Export As-Of Size Summary (CSV)",
                        df_size_mtd_tot.to_csv(index=False),
                        "AsOf_Size_Summary.csv",
                        "text/csv",
                    )

                elif mtd_mode == "📦 Job-Order Wise (Cumulative)":
                    st.markdown(
                        "### 📦 Master Order Completion Summary (As of"
                        f" {as_of_date})"
                    )
                    cust_list = ["ALL CUSTOMERS"] + sorted(
                        list(df_mtd["Customer"].unique())
                    )
                    selected_cust = st.selectbox(
                        "Select Customer Account:", cust_list
                    )

                    if selected_cust == "ALL CUSTOMERS":
                        df_cust = df_mtd.copy()
                    else:
                        df_cust = df_mtd[
                            df_mtd["Customer"] == selected_cust
                        ].copy()

                    job_agg = (
                        df_cust.groupby(
                            ["Customer", "Order Name", "Item Name"]
                        )
                        .agg({
                            "Demand Qty": "max",
                            "Total Good": "sum",
                            "Total Rejections": "sum",
                            "Total Prod Ton": "sum",
                            "Weighted Cap Ton": "sum",
                            "Total Runtime (Hrs)": "sum",
                        })
                        .reset_index()
                    )

                    job_agg["Due Production"] = (
                        job_agg["Demand Qty"] - job_agg["Total Good"]
                    ).apply(lambda x: max(0.0, x))
                    job_agg["Completion %"] = (
                        job_agg["Total Good"] / job_agg["Demand Qty"] * 100
                    ).fillna(0)

                    job_agg_tot = add_total_row(
                        job_agg,
                        "Order Name",
                        [
                            "Demand Qty",
                            "Total Good",
                            "Due Production",
                            "Total Prod Ton",
                            "Weighted Cap Ton",
                            "Total Runtime (Hrs)",
                        ],
                        [],
                    )

                    st.dataframe(
                        job_agg_tot, use_container_width=True, hide_index=True
                    )
                    st.download_button(
                        "📥 Export Master Job Summary (CSV)",
                        job_agg_tot.to_csv(index=False),
                        "Master_Job_Summary.csv",
                        "text/csv",
                    )

            # ============================================
            # 3. SHIFTWISE DATA MODULE
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
                    st.metric("Day Shift Tonnage", f"{a_ton:.1f} T")
                    st.metric(
                        "Day Shift Output",
                        f"{int(a_good):,} Pcs",
                        f"Rejections: {int(a_rej):,}",
                    )

                with c2:
                    st.markdown("#### 🌙 Shift B (Night Shift)")
                    st.metric("Night Shift Tonnage", f"{b_ton:.1f} T")
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

                    st.dataframe(
                        shift_daily_tot,
                        use_container_width=True,
                        hide_index=True,
                    )
                    st.download_button(
                        "📥 Export Daily Shiftwise Log (CSV)",
                        shift_daily_tot.to_csv(index=False),
                        "Daily_Shiftwise_Log.csv",
                        "text/csv",
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
