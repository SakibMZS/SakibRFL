import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# Streamlit Page Configuration
st.set_page_config(
    page_title="Plastic-3 FF | Executive Operations Dashboard",
    page_icon="🏭",
    layout="wide",
    initial_sidebar_state="expanded",
)

# AdminLTE / Modern Professional Dashboard CSS Styling
st.markdown(
    """
    <style>
    /* Global Styles */
    .stApp {
        background-color: #f4f6f9;
        font-family: 'Source Sans Pro', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }
    
    /* Sidebar Theme */
    [data-testid="stSidebar"] {
        background-color: #1e293b;
        color: #f8fafc;
    }
    [data-testid="stSidebar"] * {
        color: #f8fafc !important;
    }
    
    /* Header Container */
    .dashboard-header {
        background: linear-gradient(135deg, #1e3a8a 0%, #0f172a 100%);
        padding: 20px 28px;
        border-radius: 10px;
        color: white;
        margin-bottom: 24px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
    }
    .dashboard-header h1 {
        color: #ffffff !important;
        margin: 0;
        font-size: 26px;
        font-weight: 700;
    }
    .dashboard-header p {
        color: #94a3b8 !important;
        margin: 4px 0 0 0;
        font-size: 14px;
    }

    /* AdminLTE Styled Cards */
    .metric-card {
        background-color: #ffffff;
        border-radius: 8px;
        padding: 18px 22px;
        border-left: 5px solid #2563eb;
        box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.1), 0 1px 2px 0 rgba(0, 0, 0, 0.06);
        margin-bottom: 16px;
    }
    .metric-card.success { border-left-color: #10b981; }
    .metric-card.warning { border-left-color: #f59e0b; }
    .metric-card.danger { border-left-color: #ef4444; }
    .metric-card.info { border-left-color: #06b6d4; }
    
    .metric-title {
        font-size: 13px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        color: #64748b;
        font-weight: 600;
        margin-bottom: 6px;
    }
    .metric-value {
        font-size: 24px;
        font-weight: 700;
        color: #0f172a;
    }
    .metric-sub {
        font-size: 12px;
        color: #94a3b8;
        margin-top: 4px;
    }

    /* Table & Container Improvements */
    .stDataFrame {
        background-color: #ffffff;
        border-radius: 8px;
        padding: 8px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }
    </style>
""",
    unsafe_allow_html=True,
)


@st.cache_data
def load_and_parse_data(file_bytes):
    """Parses and calculates all daily production sheets using exact standard engineering

    formulas.
    """
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

            # Shift A
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

            # Shift B
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

            # Strict Filter: Exclude if machine didn't run on either shift on that date
            if total_good == 0 and total_runtime == 0:
                continue

            all_records.append({
                "Date": sheet.strip(),
                "Machine": mc_sl,
                "Order Name": order,
                "Item Name": item,
                "Cavity": cavity,
                "CT": ct,
                "Unit Wt (kg)": unit_wt_kg,
                "STD Cap/Shift": std_cap_shift,
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

    # Calculate Run-Time Weights per machine per date
    mc_totals = (
        df_res.groupby(["Date", "Machine"])["Total Runtime (Hrs)"]
        .sum()
        .reset_index()
        .rename(columns={"Total Runtime (Hrs)": "MC_Daily_Runtime"})
    )
    df_res = df_res.merge(mc_totals, on=["Date", "Machine"])

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

    return df_res


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


# Sidebar Header
st.sidebar.markdown(
    "## 🏭 **PLASTIC-3 FF**\n*Industrial Operations Console*"
)
st.sidebar.divider()

uploaded_file = st.sidebar.file_uploader(
    "Upload Production Entry File (.xlsx)", type=["xlsx", "xls"]
)

if uploaded_file is not None:
    df_data = load_and_parse_data(uploaded_file)

    if df_data.empty:
        st.error(
            "No active daily production entries found in the uploaded workbook."
        )
    else:
        # Navigation Options
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
            f"🟢 Active Records Loaded: **{len(df_data)}** entries across"
            f" **{df_data['Date'].nunique()}** operational dates."
        )

        # Header Title Banner
        st.markdown(
            f"""
            <div class="dashboard-header">
                <h1>{nav_choice}</h1>
                <p>Plastic-3 FF Production Optimization & Real-Time Monitoring Panel</p>
            </div>
        """,
            unsafe_allow_html=True,
        )

        # ---------------------------------------------------------------------
        # 1. DAILY DATA VIEW
        # ---------------------------------------------------------------------
        if nav_choice == "📅 Daily Data":
            all_dates = sorted(list(df_data["Date"].unique()))
            selected_date = st.selectbox("Select Date to Inspect:", all_dates)

            df_daily = df_data[df_data["Date"] == selected_date].copy()

            # KPI Cards
            tot_prod = df_daily["Total Prod Ton"].sum()
            tot_cap = df_daily["Weighted Cap Ton"].sum()
            tot_good = df_daily["Total Good"].sum()
            tot_rej = df_daily["Total Rejections"].sum()
            tot_time = df_daily["Total Runtime (Hrs)"].sum()
            ach_rate = (tot_prod / tot_cap * 100) if tot_cap > 0 else 0.0

            c1, c2, c3, c4 = st.columns(4)
            with c1:
                render_card(
                    "Produced Tonnage",
                    f"{tot_prod:.2f} Ton",
                    f"Target: {tot_cap:.2f} Ton",
                    "info",
                )
            with c2:
                render_card(
                    "Achievement Rate",
                    f"{ach_rate:.1f}%",
                    "Target vs Produced Ton",
                    "success" if ach_rate >= 85 else "warning",
                )
            with c3:
                render_card(
                    "Good Output",
                    f"{int(tot_good):,} Pcs",
                    f"Defects: {int(tot_rej):,} Pcs",
                    "success",
                )
            with c4:
                render_card(
                    "Active Uptime",
                    f"{tot_time:.1f} Hrs",
                    f"Running Machines: {df_daily['Machine'].nunique()}",
                    "info",
                )

            st.write("### Active Machine Production Summary")
            st.caption(
                "Note: Only machines/items that ran on this date are displayed"
                " below."
            )

            st.dataframe(
                df_daily[[
                    "Machine",
                    "Order Name",
                    "Item Name",
                    "CT",
                    "Cavity",
                    "Shift A Good",
                    "Shift B Good",
                    "Total Good",
                    "Total Rejections",
                    "Total Runtime (Hrs)",
                    "Total Prod Ton",
                    "Weighted Cap Ton",
                ]],
                use_container_width=True,
                hide_index=True,
            )

        # ---------------------------------------------------------------------
        # 2. AS OF DATA (MTD / CUMULATIVE) VIEW
        # ---------------------------------------------------------------------
        elif nav_choice == "📊 As of Data (MTD)":
            all_dates = sorted(list(df_data["Date"].unique()))
            as_of_date = st.select_slider(
                "Filter Data Up To Date (As-of):",
                options=all_dates,
                value=all_dates[-1],
            )

            df_mtd = df_data[df_data["Date"] <= as_of_date].copy()

            tot_prod = df_mtd["Total Prod Ton"].sum()
            tot_cap = df_mtd["Weighted Cap Ton"].sum()
            tot_good = df_mtd["Total Good"].sum()
            tot_rej = df_mtd["Total Rejections"].sum()
            rej_rate = (
                (tot_rej / (tot_good + tot_rej) * 100)
                if (tot_good + tot_rej) > 0
                else 0.0
            )
            ach_rate = (tot_prod / tot_cap * 100) if tot_cap > 0 else 0.0

            c1, c2, c3, c4 = st.columns(4)
            with c1:
                render_card(
                    "Cumulative Output",
                    f"{tot_prod:.2f} Ton",
                    f"Capacity: {tot_cap:.2f} Ton",
                    "info",
                )
            with c2:
                render_card(
                    "Overall Achievement",
                    f"{ach_rate:.1f}%",
                    f"As of {as_of_date}",
                    "success" if ach_rate >= 85 else "warning",
                )
            with c3:
                render_card(
                    "Rejection Rate",
                    f"{rej_rate:.2f}%",
                    f"Total Scrap: {int(tot_rej):,} Pcs",
                    "danger" if rej_rate > 3 else "success",
                )
            with c4:
                render_card(
                    "Total Production Volume",
                    f"{int(tot_good):,} Pcs",
                    f"Active Days: {df_mtd['Date'].nunique()}",
                    "info",
                )

            st.divider()

            # Tonnage Trend Chart
            daily_agg = (
                df_mtd.groupby("Date")[["Total Prod Ton", "Weighted Cap Ton"]]
                .sum()
                .reset_index()
            )
            fig_trend = px.line(
                daily_agg,
                x="Date",
                y=["Weighted Cap Ton", "Total Prod Ton"],
                title="Daily Tonnage Trend (Target vs Actual)",
                markers=True,
                color_discrete_sequence=["#94a3b8", "#2563eb"],
            )
            fig_trend.update_layout(
                margin=dict(l=20, r=20, t=40, b=20),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
            )
            st.plotly_chart(fig_trend, use_container_width=True)

        # ---------------------------------------------------------------------
        # 3. SHIFTWISE DATA VIEW
        # ---------------------------------------------------------------------
        elif nav_choice == "`🌗 Shiftwise Data`":
            a_ton = df_data["Shift A Prod Ton"].sum()
            a_good = df_data["Shift A Good"].sum()
            a_rej = df_data["Shift A Rej"].sum()
            a_hrs = df_data["Shift A Runtime"].sum()

            b_ton = df_data["Shift B Prod Ton"].sum()
            b_good = df_data["Shift B Good"].sum()
            b_rej = df_data["Shift B Rej"].sum()
            b_hrs = df_data["Shift B Runtime"].sum()

            c1, c2 = st.columns(2)
            with c1:
                st.markdown("### ☀️ Shift A (Day Shift)")
                render_card(
                    "Shift A Tonnage",
                    f"{a_ton:.2f} Ton",
                    f"Uptime: {a_hrs:.1f} Hours",
                    "info",
                )
                render_card(
                    "Shift A Good Output",
                    f"{int(a_good):,} Pcs",
                    f"Rejections: {int(a_rej):,} Pcs",
                    "success",
                )

            with c2:
                st.markdown("### 🌙 Shift B (Night Shift)")
                render_card(
                    "Shift B Tonnage",
                    f"{b_ton:.2f} Ton",
                    f"Uptime: {b_hrs:.1f} Hours",
                    "info",
                )
                render_card(
                    "Shift B Good Output",
                    f"{int(b_good):,} Pcs",
                    f"Rejections: {int(b_rej):,} Pcs",
                    "success",
                )

            st.divider()

            # Date-wise Shift Comparison Chart
            shift_daily = (
                df_data.groupby("Date")[
                    ["Shift A Prod Ton", "Shift B Prod Ton"]
                ]
                .sum()
                .reset_index()
            )
            fig_shift = px.bar(
                shift_daily,
                x="Date",
                y=["Shift A Prod Ton", "Shift B Prod Ton"],
                title="Daily Production Tonnage Comparison: Shift A vs Shift B",
                barmode="group",
                color_discrete_sequence=["#f59e0b", "#1e293b"],
            )
            fig_shift.update_layout(
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)"
            )
            st.plotly_chart(fig_shift, use_container_width=True)

        # ---------------------------------------------------------------------
        # 4. JOB-ORDER WISE DATA VIEW
        # ---------------------------------------------------------------------
        elif nav_choice == "📦 Job-Order Wise Data":
            job_summary = (
                df_data.groupby(["Order Name", "Item Name"])
                .agg({
                    "Total Good": "sum",
                    "Total Rejections": "sum",
                    "Total Prod Ton": "sum",
                    "Weighted Cap Ton": "sum",
                    "Total Runtime (Hrs)": "sum",
                })
                .reset_index()
            )

            job_summary["Achievement %"] = (
                job_summary["Total Prod Ton"]
                / job_summary["Weighted Cap Ton"]
                * 100
            ).fillna(0)

            c1, c2, c3 = st.columns(3)
            with c1:
                render_card(
                    "Total Active Jobs",
                    f"{job_summary['Order Name'].nunique()}",
                    "Distinct Orders Processed",
                    "info",
                )
            with c2:
                render_card(
                    "Top Produced Order",
                    f"{job_summary.loc[job_summary['Total Prod Ton'].idxmax(), 'Order Name']}",
                    f"{job_summary['Total Prod Ton'].max():.2f} Tons Produced",
                    "success",
                )
            with c3:
                render_card(
                    "Total Order Volume",
                    f"{int(job_summary['Total Good'].sum()):,} Pcs",
                    "Good Units Delivered",
                    "info",
                )

            st.write("### Production Performance by Job Order")
            st.dataframe(
                job_summary.sort_values(
                    by="Total Prod Ton", ascending=False
                ),
                use_container_width=True,
                hide_index=True,
            )

else:
    # Landing Placeholder Page
    st.info(
        "👈 **Welcome to the Console!** Please upload your production Excel"
        " file in the sidebar to initialize the dashboard."
    )
