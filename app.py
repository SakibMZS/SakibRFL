# ============================================
# SECTION 1: IMPORTS & STREAMLIT SETUP
# ============================================
import io
import os
import re
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(
    page_title="Plastic-3 Operations Console | FF & GF",
    page_icon="🏭",
    layout="wide",
    initial_sidebar_state="expanded",
)


def load_css(file_name="style.css"):
    if os.path.exists(file_name):
        with open(file_name) as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)


load_css("style.css")

# ============================================
# SECTION 2: EXCEL CONFIGURATION & SIZING
# ============================================
EXCEL_SIZES = [
    "160",
    "90",
    "120",
    "250",
    "270",
    "280",
    "380",
    "330",
    "470",
    "530",
    "800",
    "428",
]
SORTED_SIZES = sorted(EXCEL_SIZES, key=len, reverse=True)


def extract_excel_mc_size(mc_sl, size_col_val=None):
    """Extracts machine tonnage size class with typo resilience (e.g., 'B8-119' -> '120')."""
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


# ============================================
# SECTION 3: DATA PARSING & AGGREGATION ENGINE
# ============================================
@st.cache_data
def load_and_parse_floor_data(file_bytes, floor_label):
    """Parses raw Excel floor production sheets and computes shift-proportional capacity."""
    file_stream = io.BytesIO(file_bytes)
    xls = pd.ExcelFile(file_stream)

    valid_sheets = []
    all_parsed_dates = []

    for s in xls.sheet_names:
        s_clean = s.strip()
        match = re.search(r"(\d{2}-\d{2}-\d{4})", s_clean)
        if match:
            dt_str = match.group(1)
            try:
                dt = pd.to_datetime(dt_str, format="%d-%m-%Y")
                valid_sheets.append((s, dt))
                all_parsed_dates.append(dt)
            except Exception:
                pass

    if all_parsed_dates:
        latest_date = max(all_parsed_dates)
        latest_month = latest_date.month
        latest_year = latest_date.year

        date_sheets = [
            s
            for s, dt in valid_sheets
            if dt.month == latest_month and dt.year == latest_year
        ]
    else:
        date_sheets = []

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

            # Shift-proportional capacity scaling
            shifts_active = (1.0 if a_good > 0 else 0.0) + (
                1.0 if b_good > 0 else 0.0
            )
            if shifts_active == 0.0 and (a_rej > 0 or b_rej > 0):
                shifts_active = 1.0

            act_cap_day_pcs = std_cap_shift * shifts_active
            act_cap_day_ton = (act_cap_day_pcs * unit_wt_kg) / 1000.0

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

    # Runtime-weighted multi-job entry weighting
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
            "Shift A Good": tot_a_good,
            "Shift B Good": tot_b_good,
            "Total Good": tot_good,
            "Total Rejections": tot_bad,
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
    records = []
    for lg, grp in df_subset.groupby("Line Group"):
        mc_qty = grp["Machine"].nunique()
        tot_runtime = grp["Total Runtime (Hrs)"].sum()

        tot_cap_pcs = grp["Weighted Cap Pcs"].sum()
        tot_prod_pcs = grp["Total Good"].sum()
        tot_cap_ton = grp["Weighted Cap Ton"].sum()
        tot_prod_ton = grp["Total Prod Ton"].sum()

        ach_pcs = (tot_prod_pcs / tot_cap_pcs * 100) if tot_cap_pcs > 0 else 0.0
        ach_ton = (tot_prod_ton / tot_cap_ton * 100) if tot_cap_ton > 0 else 0.0

        records.append({
            "Line Group": lg,
            "Running MC Qty": mc_qty,
            "Uptime (Hrs)": round(tot_runtime, 2),
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
    Computes Machine Size Summary matching Excel Sheet2 standard.
    - Daily Mode: MC QTY = Unique running machines on selected date.
    - As-Of Mode: MC QTY = Cumulative running machine-days across period.
    """
    days_count = df_subset["Date"].nunique()
    records = []

    for sz in EXCEL_SIZES:
        grp = df_subset[df_subset["MC Size"] == sz]
        if grp.empty:
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

        tot_runtime = grp["Total Runtime (Hrs)"].sum()

        if mode == "as_of":
            # Cumulative active machine-days count (e.g. 257 for August)
            mc_qty = grp.groupby(["Date", "Floor", "Machine"]).ngroups
            run_hr_avg = tot_runtime / mc_qty if mc_qty > 0 else 0.0
        else:
            # Unique active machines count on single date (e.g. 39 for Aug 7)
            mc_qty = grp["Machine"].nunique()
            run_hr_avg = (
                tot_runtime / (mc_qty * days_count)
                if (mc_qty > 0 and days_count > 0)
                else 0.0
            )

        if tot_runtime > 0:
            avg_ct = (
                grp["CT"] * grp["Total Runtime (Hrs)"]
            ).sum() / tot_runtime
        else:
            avg_ct = grp["CT"].mean()

        tot_cap_pcs = grp["Weighted Cap Pcs"].sum()
        tot_prod_pcs = grp["Total Good"].sum()
        tot_cap_ton = grp["Weighted Cap Ton"].sum()
        tot_prod_ton = grp["Total Prod Ton"].sum()

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
    """Adds a Sub-Total row averaging non-zero active size classes for Run Hour Average."""
    if df.empty:
        return df

    res_df = df.copy()
    tot_row = {}

    for c in df.columns:
        if c == label_col:
            tot_row[c] = "Sub Total"
        elif c in sum_cols:
            val = df[c].sum()
            tot_row[c] = round(val, 2) if isinstance(val, float) else val
        elif c in avg_cols:
            non_zero = df[df[c] > 0][c]
            tot_row[c] = (
                round(non_zero.mean(), 2) if not non_zero.empty else 0.0
            )
        else:
            tot_row[c] = "-"

    if "Total Cap (Pcs)" in df.columns and "Total Prod (Pcs)" in df.columns:
        tc_p = pd.to_numeric(df["Total Cap (Pcs)"], errors="coerce").sum()
        tp_p = pd.to_numeric(df["Total Prod (Pcs)"], errors="coerce").sum()
        ach = (tp_p / tc_p * 100) if tc_p > 0 else 0.0
        if "% OF Ach Pcs" in df.columns:
            tot_row["% OF Ach Pcs"] = f"{ach:.2f}%"
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

    tot_df = pd.DataFrame([tot_row])
    return pd.concat([res_df, tot_df], ignore_index=True)


# ============================================
# SECTION 4: TABLE FORMATTING & ALIGNMENT HELPERS
# ============================================
def clean_and_format_dataframe(df):
    """
    Cleans data types, rounds numeric values, and prepares
    clean dataframes for Streamlit rendering.
    """
    df_clean = df.copy()

    for col in df_clean.columns:
        if df_clean[col].dtype in ["float64", "float32"]:
            df_clean[col] = df_clean[col].round(2)
        elif df_clean[col].dtype in ["int64", "int32"]:
            df_clean[col] = df_clean[col].astype(int)

    return df_clean


def get_column_configurations(df):
    """
    Returns Streamlit native column configurations:
    - Text/Mixed columns -> Left aligned
    - Numbers, Quantities & Percentages -> Center aligned with proper formatting
    """
    config = {}

    for col in df.columns:
        col_lower = col.lower()

        if "%" in col or "ach" in col_lower or "util" in col_lower:
            config[col] = st.column_config.Column(
                col,
                width="medium",
            )
        elif (
            df[col].dtype in ["float64", "float32", "int64", "int32"]
            or "qty" in col_lower
            or "pcs" in col_lower
            or "ton" in col_lower
            or "good" in col_lower
            or "rej" in col_lower
            or "runtime" in col_lower
            or "uptime" in col_lower
            or "ct" in col_lower
            or "cavity" in col_lower
            or "cap" in col_lower
            or "demand" in col_lower
        ):
            config[col] = st.column_config.NumberColumn(
                col,
                format="%.2f" if df[col].dtype in ["float64", "float32"] else "%d",
            )
        else:
            config[col] = st.column_config.TextColumn(
                col,
            )

    return config


def column_visibility_selector(df, key_prefix=""):
    """Manages column visibility selector with default exclusions."""
    all_cols = df.columns.tolist()

    # Columns excluded from default table view
    excluded_defaults = ["Entry Count", "Is Mixed", "Line Group", "MC Size"]
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
# SECTION 7: MAIN DASHBOARD CONSOLE & SIDEBAR
# ============================================
else:
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
            # SECTION 8: MODULE 1 — DAILY DATA
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
                    f"Uptime: {tot_time:.2f} Hrs",
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

                    v_cols = column_visibility_selector(
                        df_line_day_tot, "daily_line"
                    )
                    st.dataframe(
                        clean_and_format_dataframe(df_line_day_tot[v_cols]),
                        column_config=get_column_configurations(df_line_day_tot[v_cols]),
                        use_container_width=True,
                        hide_index=True,
                    )

                    st.download_button(
                        "📥 Export Daily Line Summary (CSV)",
                        df_line_day_tot[v_cols].to_csv(index=False),
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

                    v_cols = column_visibility_selector(
                        df_daily_totals, "daily_mc"
                    )
                    st.dataframe(
                        clean_and_format_dataframe(df_daily_totals[v_cols]),
                        column_config=get_column_configurations(df_daily_totals[v_cols]),
                        use_container_width=True,
                        hide_index=True,
                    )

                    st.download_button(
                        "📥 Export Daily Machine Summary (CSV)",
                        df_daily_totals[v_cols].to_csv(index=False),
                        "Daily_Machine_Summary.csv",
                        "text/csv",
                    )

                    mixed_mcs = df_daily[df_daily["Is Mixed"]][
                        "Machine"
                    ].tolist()
                    if mixed_mcs:
                        st.divider()
                        st.markdown(
                            "#### 🔍 Inspect Mixed Machine Breakdown (Inside"
                            " Story)"
                        )
                        sel_mc = st.selectbox(
                            "Select a Mixed Machine ID to view its mold run"
                            " breakdown:",
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

                        st.dataframe(
                            clean_and_format_dataframe(
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
                            ),
                            column_config=get_column_configurations(
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
                            ),
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
                    st.dataframe(
                        clean_and_format_dataframe(df_size_day_tot[v_cols]),
                        column_config=get_column_configurations(df_size_day_tot[v_cols]),
                        use_container_width=True,
                        hide_index=True,
                    )

                    st.download_button(
                        "📥 Export Daily Size Summary (CSV)",
                        df_size_day_tot[v_cols].to_csv(index=False),
                        "Daily_Size_Summary.csv",
                        "text/csv",
                    )

                elif daily_mode == "📦 Job-Order Wise (Daily Active)":
                    st.markdown("### 📦 Active Orders Run On Selected Date")

                    search_term = st.text_input(
                        "🔍 Search Job Order or Item Name:",
                        "",
                        placeholder="Type order name or item description...",
                    )

                    records_job_day = []
                    for (
                        cust,
                        ord_name,
                        itm_name,
                    ), grp in df_daily_raw.groupby(
                        ["Customer", "Order Name", "Item Name"]
                    ):
                        demand_val = grp["Demand Qty"].max()
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
                            "Item Name": itm_name,
                            "Demand Qty": demand_val,
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

                    v_cols = column_visibility_selector(
                        job_day_tot, "daily_job"
                    )
                    st.dataframe(
                        clean_and_format_dataframe(job_day_tot[v_cols]),
                        column_config=get_column_configurations(job_day_tot[v_cols]),
                        use_container_width=True,
                        hide_index=True,
                    )

                    st.download_button(
                        "📥 Export Daily Active Job Summary (CSV)",
                        job_day_tot[v_cols].to_csv(index=False),
                        "Daily_Job_Summary.csv",
                        "text/csv",
                    )

            # ============================================
            # SECTION 9: MODULE 2 — AS OF DATA (MTD)
            # ============================================
            elif nav_choice == "📊 As of Data (MTD)":
                all_dates = sorted(list(df_active["Date"].unique()))

                latest_date_str = all_dates[-1]
                latest_dt = pd.to_datetime(
                    latest_date_str, format="%d-%m-%Y", errors="coerce"
                )
                if pd.notna(latest_dt):
                    start_date_str = f"01-{latest_dt.month:02d}-{latest_dt.year}"
                else:
                    start_date_str = all_dates[0]

                st.markdown(
                    f"### 📊 As-Of Production Period: **{start_date_str}** to"
                    f" **{latest_date_str}**"
                )

                as_of_date = st.select_slider(
                    "📅 Adjust As-Of Cutoff Date:",
                    options=all_dates,
                    value=latest_date_str,
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
                    "Total Operating Hours",
                    f"{tot_runtime:.2f} Hrs",
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

                    v_cols = column_visibility_selector(
                        df_line_mtd_tot, "mtd_line"
                    )
                    st.dataframe(
                        clean_and_format_dataframe(df_line_mtd_tot[v_cols]),
                        column_config=get_column_configurations(df_line_mtd_tot[v_cols]),
                        use_container_width=True,
                        hide_index=True,
                    )

                    st.download_button(
                        "📥 Export As-Of Line Summary (CSV)",
                        df_line_mtd_tot[v_cols].to_csv(index=False),
                        "AsOf_Line_Summary.csv",
                        "text/csv",
                    )

                elif mtd_mode == "📏 Sizewise":
                    st.markdown(
                        f"### 📏 Machine Size Summary (As of {as_of_date})"
                    )

                    # Computes As-Of Size Summary matching Sheet2 cumulative machine-days standard
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
                    st.dataframe(
                        clean_and_format_dataframe(df_size_mtd_tot[v_cols]),
                        column_config=get_column_configurations(df_size_mtd_tot[v_cols]),
                        use_container_width=True,
                        hide_index=True,
                    )

                    st.download_button(
                        "📥 Export As-Of Size Summary (CSV)",
                        df_size_mtd_tot[v_cols].to_csv(index=False),
                        "AsOf_Size_Summary.csv",
                        "text/csv",
                    )

                elif mtd_mode == "📦 Job-Order Wise (Cumulative)":
                    st.markdown(
                        "### 📦 Master Order Completion Summary (As of"
                        f" {as_of_date})"
                    )

                    search_term_mtd = st.text_input(
                        "🔍 Search Cumulative Job Order or Item Name:",
                        "",
                        placeholder="Type order name or item description...",
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
                    ).apply(lambda x: f"{x:.2f}%" if pd.notna(x) else "0.00%")

                    if search_term_mtd.strip():
                        term = search_term_mtd.strip().lower()
                        job_agg = job_agg[
                            job_agg["Order Name"].str.lower().str.contains(term)
                            | job_agg["Item Name"].str.lower().str.contains(term)
                            | job_agg["Customer"].str.lower().str.contains(term)
                        ]

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

                    v_cols = column_visibility_selector(
                        job_agg_tot, "mtd_job"
                    )
                    st.dataframe(
                        clean_and_format_dataframe(job_agg_tot[v_cols]),
                        column_config=get_column_configurations(job_agg_tot[v_cols]),
                        use_container_width=True,
                        hide_index=True,
                    )

                    st.download_button(
                        "📥 Export Master Job Summary (CSV)",
                        job_agg_tot[v_cols].to_csv(index=False),
                        "Master_Job_Summary.csv",
                        "text/csv",
                    )

            # ============================================
            # SECTION 10: MODULE 3 — SHIFTWISE DATA
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
                    st.dataframe(
                        clean_and_format_dataframe(shift_daily_tot[v_cols]),
                        column_config=get_column_configurations(shift_daily_tot[v_cols]),
                        use_container_width=True,
                        hide_index=True,
                    )

                    st.download_button(
                        "📥 Export Daily Shiftwise Log (CSV)",
                        shift_daily_tot[v_cols].to_csv(index=False),
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
