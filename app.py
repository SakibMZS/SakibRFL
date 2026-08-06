import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(
    page_title="Plastic-3 FF Production Dashboard",
    page_icon="📊",
    layout="wide",
)

st.title("📊 Plastic-3 FF Daily Production Dashboard")


def process_daily_sheet(df, sheet_date):
    """Processes daily date sheets using engineering formulas for equivalent runtime,

    shift capacity, tonnage capacity, and rejections.
    """
    df = df.dropna(how="all").reset_index(drop=True)

    if "MC SL" not in df.columns or "Order Name" not in df.columns:
        return pd.DataFrame()

    df = df[df["MC SL"].notna() & df["Order Name"].notna()].copy()

    records = []
    for _, row in df.iterrows():
        mc_sl = str(row.get("MC SL")).strip()
        order = str(row.get("Order Name")).strip()
        item = str(row.get("Item Name", "")).strip()

        # Physical Mold Parameters
        ct = pd.to_numeric(row.get("CT"), errors="coerce") or 0
        cavity = pd.to_numeric(row.get("Cavity"), errors="coerce") or 0
        unit_wt_kg = pd.to_numeric(row.get("Unit Wt"), errors="coerce") or 0

        # Calculate Engineering Standard Capacities
        if ct > 0 and cavity > 0:
            std_cap_shift = (43200.0 / ct) * cavity
        else:
            std_cap_shift = 0.0

        act_cap_day_pcs = std_cap_shift * 2.0
        act_cap_day_ton = (act_cap_day_pcs * unit_wt_kg) / 1000.0

        # Shift A (Day Shift) Metrics
        a_good = pd.to_numeric(row.get("A-Good"), errors="coerce") or 0.0
        a_rej = pd.to_numeric(row.get("A-Rejec"), errors="coerce") or 0.0
        a_runtime = (
            (a_good * 12.0) / std_cap_shift if std_cap_shift > 0 else 0.0
        )
        a_prod_ton = (a_good * unit_wt_kg) / 1000.0

        # Shift B (Night Shift) Metrics
        b_good = pd.to_numeric(row.get("B-Good"), errors="coerce") or 0.0
        b_rej = (
            pd.to_numeric(row.get("B-Reject"), errors="coerce")
            or pd.to_numeric(
                row.get("B-Reject Cause of Less Prod"), errors="coerce"
            )
            or 0.0
        )
        b_runtime = (
            (b_good * 12.0) / std_cap_shift if std_cap_shift > 0 else 0.0
        )
        b_prod_ton = (b_good * unit_wt_kg) / 1000.0

        # Total Job Metrics
        total_good = a_good + b_good
        total_rej = a_rej + b_rej
        total_runtime = a_runtime + b_runtime
        total_prod_ton = a_prod_ton + b_prod_ton

        # Handle zero-production filtering rule
        if total_good == 0 and total_runtime == 0:
            continue

        # Adjust capacity for single-shift run
        if (a_good > 0 and b_good == 0) or (a_good == 0 and b_good > 0):
            effective_cap_pcs = std_cap_shift
            effective_cap_ton = act_cap_day_ton / 2.0
        else:
            effective_cap_pcs = act_cap_day_pcs
            effective_cap_ton = act_cap_day_ton

        records.append({
            "Date": sheet_date,
            "Machine": mc_sl,
            "Order Name": order,
            "Item Name": item,
            "Cavity": cavity,
            "CT": ct,
            "Unit Wt (kg)": unit_wt_kg,
            "STD Cap/Shift": std_cap_shift,
            "Effective Cap Pcs": effective_cap_pcs,
            "Effective Cap Ton": effective_cap_ton,
            "Shift A Good": a_good,
            "Shift A Runtime": a_runtime,
            "Shift B Good": b_good,
            "Shift B Runtime": b_runtime,
            "Total Good": total_good,
            "Total Rejections (T-Bad)": total_rej,
            "Total Runtime (Hrs)": total_runtime,
            "Total Prod Ton": total_prod_ton,
        })

    df_res = pd.DataFrame(records)
    if df_res.empty:
        return df_res

    # Apply Run-Time Weighting per Physical Machine
    mc_totals = (
        df_res.groupby("Machine")["Total Runtime (Hrs)"]
        .sum()
        .reset_index()
        .rename(columns={"Total Runtime (Hrs)": "MC_Total_Runtime"})
    )
    df_res = df_res.merge(mc_totals, on="Machine")

    df_res["Runtime Weight"] = df_res.apply(
        lambda r: (
            r["Total Runtime (Hrs)"] / r["MC_Total_Runtime"]
            if r["MC_Total_Runtime"] > 0
            else 1.0
        ),
        axis=1,
    )

    df_res["Weighted Cap Ton"] = (
        df_res["Effective Cap Ton"] * df_res["Runtime Weight"]
    )
    df_res["Weighted Cap Pcs"] = (
        df_res["Effective Cap Pcs"] * df_res["Runtime Weight"]
    )

    return df_res


uploaded_file = st.file_uploader(
    "Upload Production Entry Excel File", type=["xlsx", "xls"]
)

if uploaded_file is not None:
    xls = pd.ExcelFile(uploaded_file)
    date_sheets = [
        s for s in xls.sheet_names if "-" in s and ("202" in s or "203" in s)
    ]

    if not date_sheets:
        st.error("No valid daily date sheets found in the uploaded file.")
    else:
        all_daily_data = []
        for sheet in date_sheets:
            df_sheet = pd.read_excel(uploaded_file, sheet_name=sheet)
            parsed_df = process_daily_sheet(df_sheet, sheet.strip())
            if not parsed_df.empty:
                all_daily_data.append(parsed_df)

        if all_daily_data:
            df_combined = pd.concat(all_daily_data, ignore_index=True)

            tab1, tab2 = st.tabs(
                ["📈 Executive Summary & Trends", "📋 Daily Log Inspection"]
            )

            # TAB 1: EXECUTIVE SUMMARY
            with tab1:
                st.subheader(
                    "Month-to-Date Weighted Key Performance Indicators"
                )

                total_prod_ton = df_combined["Total Prod Ton"].sum()
                total_cap_ton = df_combined["Weighted Cap Ton"].sum()
                overall_ach = (
                    (total_prod_ton / total_cap_ton * 100)
                    if total_cap_ton > 0
                    else 0
                )

                total_good = df_combined["Total Good"].sum()
                total_rej = df_combined["Total Rejections (T-Bad)"].sum()
                rej_rate = (
                    (total_rej / (total_good + total_rej) * 100)
                    if (total_good + total_rej) > 0
                    else 0
                )
                total_runtime = df_combined["Total Runtime (Hrs)"].sum()

                col1, col2, col3, col4, col5 = st.columns(5)
                col1.metric("Produced Tons", f"{total_prod_ton:.2f} Ton")
                col2.metric("Weighted Target", f"{total_cap_ton:.2f} Ton")
                col3.metric("Achievement Rate", f"{overall_ach:.1f}%")
                col4.metric("Rejection Rate", f"{rej_rate:.2f}%")
                col5.metric("Total Operating Hrs", f"{total_runtime:.1f} Hrs")

                st.divider()

                # Tonnage Trend Chart
                daily_summary = (
                    df_combined.groupby("Date")[
                        ["Total Prod Ton", "Weighted Cap Ton"]
                    ]
                    .sum()
                    .reset_index()
                )
                fig_trend = px.line(
                    daily_summary,
                    x="Date",
                    y=["Weighted Cap Ton", "Total Prod Ton"],
                    title="Daily Tonnage Trend (Weighted Target vs Actual Produced)",
                    markers=True,
                    labels={"value": "Metric Tons", "variable": "Metric"},
                )
                st.plotly_chart(fig_trend, use_container_width=True)

            # TAB 2: DAILY LOG INSPECTION
            with tab2:
                st.subheader("Single Date Detailed Inspection")
                selected_date = st.selectbox(
                    "Select Date to Inspect:", date_sheets
                )

                date_filtered = df_combined[
                    df_combined["Date"] == selected_date.strip()
                ]

                if date_filtered.empty:
                    st.info("No active production entries for this date.")
                else:
                    d_col1, d_col2, d_col3, d_col4 = st.columns(4)
                    d_col1.metric(
                        "Produced Tons",
                        f"{date_filtered['Total Prod Ton'].sum():.2f} Ton",
                    )
                    d_col2.metric(
                        "Weighted Target Tons",
                        f"{date_filtered['Weighted Cap Ton'].sum():.2f} Ton",
                    )
                    d_col3.metric(
                        "Good Pieces",
                        f"{int(date_filtered['Total Good'].sum()):,}",
                    )
                    d_col4.metric(
                        "Rejections (T-Bad)",
                        f"{int(date_filtered['Total Rejections (T-Bad)'].sum()):,}",
                    )

                    st.write("### Machine Run Details & Weighted Metrics")
                    st.dataframe(
                        date_filtered[[
                            "Machine",
                            "Order Name",
                            "Item Name",
                            "CT",
                            "Cavity",
                            "Total Good",
                            "Total Rejections (T-Bad)",
                            "Total Runtime (Hrs)",
                            "Total Prod Ton",
                            "Weighted Cap Ton",
                            "Runtime Weight",
                        ]],
                        use_container_width=True,
                    )
else:
    st.info("👈 Please upload an Excel production file to generate summaries.")
