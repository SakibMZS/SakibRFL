import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

# Streamlit Page Setup
st.set_page_config(
    page_title="Plastic-3 Operations Console | FF & GF",
    page_icon="🏭",
    layout="wide",
    initial_sidebar_state="expanded",
)

# AdminLTE / Industrial Console CSS Styling
st.markdown(
    """
    <style>
    .stApp { background-color: #f4f6f9; font-family: 'Source Sans Pro', sans-serif; }
    [data-testid="stSidebar"] { background-color: #1e293b; }
    [data-testid="stSidebar"] * { color: #f8fafc !important; }
    
    .dashboard-header {
        background: linear-gradient(135deg, #0f172a 0%, #1e3a8a 100%);
        padding: 20px 28px;
        border-radius: 10px;
        color: white;
        margin-bottom: 24px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
    }
    .dashboard-header h1 { color: #ffffff !important; margin: 0; font-size: 26px; font-weight: 700; }
    .dashboard-header p { color: #94a3b8 !important; margin: 4px 0 0 0; font-size: 14px; }

    .metric-card {
        background-color: #ffffff;
        border-radius: 8px;
        padding: 18px 22px;
        border-left: 5px solid #2563eb;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
        margin-bottom: 16px;
    }
    .metric-card.success { border-left-color: #10b981; }
    .metric-card.warning { border-left-color: #f59e0b; }
    .metric-card.danger { border-left-color: #ef4444; }
    .metric-card.info { border-left-color: #06b6d4; }
    
    .metric-title { font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px; color: #64748b; font-weight: 600; margin-bottom: 4px; }
    .metric-value { font-size: 22px; font-weight: 700; color: #0f172a; }
    .metric-sub { font-size: 12px; color: #94a3b8; margin-top: 4px; }
    </style>
""",
    unsafe_allow_html=True,
)

# Exact Excel Machine Size Tonnage List
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
    """Replicates Excel SEARCH/LOOKUP formula for machine size extraction."""
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
    """Categorizes machine into standard production lines (GF Line A-B, GF Line

    C-D, GF Line E-F, FF Line A-B, FF Line C-D).
    """
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

            # Shift A Production
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

            # Shift B Production
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

            # Direct Sum for Physical Actuals
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

    # Run-Time Weighting for Capacities
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
    """Consolidates multiple entries per machine into a single row per machine on a

    given date.
    """
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
    """Computes Line-Wise Performance Breakdown (GF Line A-B, GF Line C-D, GF Line

    E-F, FF Line A-B, FF Line C-D).
    """
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
    """Computes Machine Size Summary table using exact tonnage classes."""
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

    # Catch any leftover 'Other' sizes
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
    """Appends a highlighted TOTAL & AVERAGE summary row at the bottom of a table."""
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


def render_card(title, value, subtext="", card_type="info"):
    st.markdown(
        f"""
        <div class="metric-card {card_type}">
            <div class="metric-title">{title}</div>
            <div class="metric-value">{value}</div>
            <div class="metric-sub">{subtext}</div>
        </div>
    """,
        unsafe_allow_html=True,
    )


# Sidebar Branding
st.sidebar.markdown(
    "## 🏭 **PLASTIC-3 CONSOLE**\n*First Floor (FF) & Ground Floor (GF)*"
)
st.sidebar.divider()

# Dual File Uploaders
ff_file = st.sidebar.file_uploader(
    "1. Upload First Floor (FF) File (.xlsx)",
    type=["xlsx", "xls"],
    key="ff_up",
)
gf_file = st.sidebar.file_uploader(
    "2. Upload Ground Floor (GF) File (.xlsx)",
    type=["xlsx", "xls"],
    key="gf_up",
)

hide_zero_runs = st.sidebar.toggle(
    "Hide Non-Running Machines/Items", value=True
)

all_floor_data = []

if ff_file is not None:
    df_ff = load_and_parse_floor_data(ff_file, "FF")
    if not df_ff.empty:
        all_floor_data.append(df_ff)

if gf_file is not None:
    df_gf = load_and_parse_floor_data(gf_file, "GF")
    if not df_gf.empty:
        all_floor_data.append(df_gf)

if all_floor_data:
    df_data = pd.concat(all_floor_data, ignore_index=True)

    st.sidebar.divider()
    st.sidebar.markdown("### 🏢 **Floor Selector**")
    floor_choice = st.sidebar.radio(
        "Select Active Production Floor View:", ["ALL FLOORS", "FF", "GF"]
    )

    if floor_choice != "ALL FLOORS":
        df_data = df_data[df_data["Floor"] == floor_choice].copy()

    if hide_zero_runs:
        df_active = df_data[
            (df_data["Total Good"] > 0) | (df_data["Total Runtime (Hrs)"] > 0)
        ].copy()
    else:
        df_active = df_data.copy()

    nav_choice = st.sidebar.radio(
        "Select Dashboard View:",
        [
            "📅 Daily Data",
            "📊 As of Data (MTD)",
            "🌗 Shiftwise Data",
            "📦 Job-Order Wise Data",
        ],
    )

    st.sidebar.divider()
    st.sidebar.info(
        f"🟢 Active Entries: **{len(df_active)}** records across"
        f" **{df_active['Date'].nunique()}** dates."
    )

    st.markdown(
        f"""
        <div class="dashboard-header">
            <h1>{nav_choice} — [{floor_choice}]</h1>
            <p>Plastic-3 FF & GF Multi-Floor Industrial Production Monitoring Panel</p>
        </div>
    """,
        unsafe_allow_html=True,
    )

    # ---------------------------------------------------------------------
    # 1. DAILY DATA VIEW
    # ---------------------------------------------------------------------
    if nav_choice == "📅 Daily Data":
        all_dates = sorted(list(df_active["Date"].unique()))
        selected_date = st.selectbox("Select Operational Date:", all_dates)

        df_daily_raw = df_active[df_active["Date"] == selected_date].copy()
        df_daily = consolidate_daily_machines(df_daily_raw)

        # Top Metric Banner (Running Machines Only)
        tot_prod_ton = df_daily["Total Prod Ton"].sum()
        tot_cap_ton = df_daily["Weighted Cap Ton"].sum()
        tot_good_pcs = df_daily["Total Good"].sum()
        tot_cap_pcs = df_daily["Weighted Cap Pcs"].sum()
        tot_rej = df_daily["Total Rejections"].sum()
        tot_time = df_daily["Total Runtime (Hrs)"].sum()

        ton_ach = (
            (tot_prod_ton / tot_cap_ton * 100) if tot_cap_ton > 0 else 0.0
        )
        pcs_ach = (
            (tot_good_pcs / tot_cap_pcs * 100) if tot_cap_pcs > 0 else 0.0
        )

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            render_card(
                "Running Cap vs Prod (Ton)",
                f"{tot_prod_ton:.2f} / {tot_cap_ton:.2f} Ton",
                f"Tonnage Ach: {ton_ach:.1f}%",
                "info",
            )
        with c2:
            render_card(
                "Running Cap vs Prod (Pcs)",
                f"{int(tot_good_pcs):,} / {int(tot_cap_pcs):,} Pcs",
                f"Piece Ach: {pcs_ach:.1f}%",
                "success",
            )
        with c3:
            render_card(
                "Total Rejections (T-Bad)",
                f"{int(tot_rej):,} Pcs",
                "Quality Loss",
                "danger" if tot_rej > 1000 else "success",
            )
        with c4:
            render_card(
                "Running Machine Uptime",
                f"{tot_time:.1f} Hrs",
                f"Running Machines: {df_daily['Machine'].nunique()}",
                "info",
            )

        st.divider()

        st.write("### 📈 Line-Wise Capacity vs Production Summary")
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
            df_line_day_tot, use_container_width=True, hide_index=True
        )

        st.divider()

        st.write("### 🏭 Consolidated Machine Performance (Single Row / Machine)")
        st.caption(
            "Note: Multi-job machines show 'Mixed'. Expand below for row-level"
            " inside story details."
        )

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

        # Mixed Machine Modal
        mixed_machines = df_daily[df_daily["Is Mixed"]]["Machine"].tolist()
        if mixed_machines:
            with st.expander(
                "🔍 Inspect Mixed Machine Entry Inside Story Details"
            ):
                sel_mc = st.selectbox("Select Mixed Machine:", mixed_machines)
                sub_raw = df_daily_raw[df_daily_raw["Machine"] == sel_mc]
                st.write(
                    f"**Row-Level Production Entries for Machine {sel_mc}:**"
                )
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

        st.divider()

        st.write("### 📊 Machine Size Wise Summary (Daily Snapshot)")
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
            df_size_day_tot, use_container_width=True, hide_index=True
        )

    # ---------------------------------------------------------------------
    # 2. AS OF DATA (MTD / CUMULATIVE) VIEW
    # ---------------------------------------------------------------------
    elif nav_choice == "📊 As of Data (MTD)":
        all_dates = sorted(list(df_active["Date"].unique()))
        as_of_date = st.select_slider(
            "Filter Data Up To Date (As-Of):",
            options=all_dates,
            value=all_dates[-1],
        )

        df_mtd = df_active[df_active["Date"] <= as_of_date].copy()

        tot_prod = df_mtd["Total Prod Ton"].sum()
        tot_cap = df_mtd["Weighted Cap Ton"].sum()
        tot_good = df_mtd["Total Good"].sum()
        tot_cap_pcs = df_mtd["Weighted Cap Pcs"].sum()
        tot_rej = df_mtd["Total Rejections"].sum()
        tot_runtime = df_mtd["Total Runtime (Hrs)"].sum()
        ach_rate = (tot_prod / tot_cap * 100) if tot_cap > 0 else 0.0

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            render_card(
                "Cumulative Tonnage",
                f"{tot_prod:.2f} Ton",
                f"Cap: {tot_cap:.2f} Ton",
                "info",
            )
        with c2:
            render_card(
                "Cumulative Pieces",
                f"{int(tot_good):,} Pcs",
                f"Cap: {int(tot_cap_pcs):,} Pcs",
                "success",
            )
        with c3:
            render_card(
                "Achievement Rate",
                f"{ach_rate:.1f}%",
                f"As of {as_of_date}",
                "success" if ach_rate >= 85 else "warning",
            )
        with c4:
            render_card(
                "Total Operating Uptime",
                f"{tot_runtime:.1f} Hrs",
                f"Days Count: {df_mtd['Date'].nunique()}",
                "info",
            )

        st.divider()

        st.write(
            f"### 📈 Line-Wise Capacity vs Production Summary (As-Of to"
            f" {as_of_date})"
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
            df_line_mtd_tot, use_container_width=True, hide_index=True
        )

        st.divider()

        st.write(
            f"### 📊 Machine Size Summary (As-Of Cumulative to {as_of_date})"
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
            df_size_mtd_tot, use_container_width=True, hide_index=True
        )

    # ---------------------------------------------------------------------
    # 3. SHIFTWISE DATA VIEW
    # ---------------------------------------------------------------------
    elif nav_choice == "🌗 Shiftwise Data":
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
            st.markdown("### ☀️ Shift A (Day Shift)")
            render_card(
                "Day Shift Tonnage",
                f"{a_ton:.2f} Ton",
                f"Operating Hours: {a_hrs:.1f} Hrs",
                "info",
            )
            render_card(
                "Day Shift Good Output",
                f"{int(a_good):,} Pcs",
                f"Defects: {int(a_rej):,} Pcs",
                "success",
            )

        with c2:
            st.markdown("### 🌙 Shift B (Night Shift)")
            render_card(
                "Night Shift Tonnage",
                f"{b_ton:.2f} Ton",
                f"Operating Hours: {b_hrs:.1f} Hrs",
                "info",
            )
            render_card(
                "Night Shift Good Output",
                f"{int(b_good):,} Pcs",
                f"Defects: {int(b_rej):,} Pcs",
                "success",
            )

        st.divider()

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

        st.write("### Daily Shiftwise Production Log")
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
            shift_daily_tot, use_container_width=True, hide_index=True
        )

    # ---------------------------------------------------------------------
    # 4. JOB-ORDER WISE & CUSTOMER MODULE
    # ---------------------------------------------------------------------
    elif nav_choice == "📦 Job-Order Wise Data":
        cust_list = ["ALL CUSTOMERS"] + sorted(
            list(df_active["Customer"].unique())
        )
        selected_cust = st.selectbox("Select Customer Account:", cust_list)

        latest_date = sorted(list(df_active["Date"].unique()))[-1]

        if selected_cust == "ALL CUSTOMERS":
            df_cust = df_active.copy()
        else:
            df_cust = df_active[df_active["Customer"] == selected_cust].copy()

        job_agg = (
            df_cust.groupby(["Customer", "Order Name", "Item Name"])
            .agg({
                "Demand Qty": "max",
                "Total Good": "sum",
                "Total Rejections": "sum",
                "Total Prod Ton": "sum",
                "Weighted Cap Ton": "sum",
                "Weighted Cap Pcs": "sum",
                "Total Runtime (Hrs)": "sum",
            })
            .reset_index()
        )

        job_agg["Due Production"] = (
            job_agg["Demand Qty"] - job_agg["Total Good"]
        ).apply(lambda x: max(0.0, x))

        df_latest = df_cust[df_cust["Date"] == latest_date]

        last_day_stats = []
        for _, r in job_agg.iterrows():
            ord_name = r["Order Name"]
            itm_name = r["Item Name"]

            sub_latest = df_latest[
                (df_latest["Order Name"] == ord_name)
                & (df_latest["Item Name"] == itm_name)
            ]

            if not sub_latest.empty:
                mc_pos = ", ".join(sub_latest["Machine"].unique())
                mc_count = sub_latest["Machine"].nunique()
                ld_cap_pcs = sub_latest["Weighted Cap Pcs"].sum()
                ld_prod_pcs = sub_latest["Total Good"].sum()
                ld_cap_ton = sub_latest["Weighted Cap Ton"].sum()
                ld_prod_ton = sub_latest["Total Prod Ton"].sum()
                ld_runtime = sub_latest["Total Runtime (Hrs)"].sum()

                ld_util_pcs = (
                    (ld_prod_pcs / ld_cap_pcs * 100) if ld_cap_pcs > 0 else 0.0
                )
                ld_util_ton = (
                    (ld_prod_ton / ld_cap_ton * 100) if ld_cap_ton > 0 else 0.0
                )
            else:
                mc_pos = "-"
                mc_count = 0
                ld_cap_pcs = 0.0
                ld_prod_pcs = 0.0
                ld_cap_ton = 0.0
                ld_prod_ton = 0.0
                ld_runtime = 0.0
                ld_util_pcs = 0.0
                ld_util_ton = 0.0

            last_day_stats.append({
                "Order Name": ord_name,
                "Item Name": itm_name,
                "Running Molds": mc_count,
                "MC Positions": mc_pos,
                "Last Day Cap (Pcs)": ld_cap_pcs,
                "Last Day Prod (Pcs)": ld_prod_pcs,
                "Last Day Util (Pcs %)": ld_util_pcs,
                "Last Day Cap (Ton)": ld_cap_ton,
                "Last Day Prod (Ton)": ld_prod_ton,
                "Last Day Util (Ton %)": ld_util_ton,
                "Last Day Runtime (Hrs)": ld_runtime,
            })

        df_ld = pd.DataFrame(last_day_stats)
        job_final = job_agg.merge(
            df_ld, on=["Order Name", "Item Name"]
        ).sort_values(by="Total Prod Ton", ascending=False)

        st.write(
            f"### Consolidated Order Performance Summary ({selected_cust})"
        )

        job_final_tot = add_total_row(
            job_final,
            "Order Name",
            [
                "Demand Qty",
                "Total Good",
                "Due Production",
                "Total Prod Ton",
                "Running Molds",
                "Last Day Cap (Pcs)",
                "Last Day Prod (Pcs)",
                "Last Day Cap (Ton)",
                "Last Day Prod (Ton)",
                "Last Day Runtime (Hrs)",
            ],
            [],
        )

        st.dataframe(
            job_final_tot[[
                "Customer",
                "Order Name",
                "Item Name",
                "Demand Qty",
                "Total Good",
                "Due Production",
                "Total Prod Ton",
                "Running Molds",
                "MC Positions",
                "Last Day Cap (Pcs)",
                "Last Day Prod (Pcs)",
                "Last Day Util (Pcs %)",
                "Last Day Cap (Ton)",
                "Last Day Prod (Ton)",
                "Last Day Util (Ton %)",
                "Last Day Runtime (Hrs)",
            ]],
            use_container_width=True,
            hide_index=True,
        )

        st.download_button(
            "📥 Export Job-Order Summary (CSV)",
            job_final_tot.to_csv(index=False),
            "Job_Order_Summary.csv",
            "text/csv",
        )

else:
    st.info(
        "👈 **Welcome!** Please upload your First Floor (FF) and Ground Floor"
        " (GF) production Excel files in the sidebar to launch the console."
    )
