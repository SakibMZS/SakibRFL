import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(
    page_title="Plastic-3 FF Production Dashboard",
    page_icon="📊",
    layout="wide",
)

st.title("📊 Plastic-3 FF Daily Production Dashboard")


def parse_daily_sheet(df, sheet_date):
    """Resilient parser to extract and standardize Shift A & Shift B production data

    from daily log sheets.
    """
    # Clean string columns
    df = df.dropna(how="all").reset_index(drop=True)

    # Ensure required base columns exist
    if "MC SL" not in df.columns or "Order Name" not in df.columns:
        return pd.DataFrame()

    # Drop blank spacer rows between machine entries
    df = df[df["MC SL"].notna() & df["Order Name"].notna()].copy()

    records = []
    for _, row in df.iterrows():
        mc_sl = row.get("MC SL")
        order = row.get("Order Name")
        item = row.get("Item Name", "")
        cavity = row.get("Cavity", 0)

        # Shift A (Day Shift) Metrics
        a_good = pd.to_numeric(row.get("A-Good"), errors="coerce") or 0
        a_rej = pd.to_numeric(row.get("A-Rejec"), errors="coerce") or 0
        a_ton = pd.to_numeric(row.get("Prod Ton"), errors="coerce") or 0
        a_cap_ton = pd.to_numeric(row.get("Cap/Ton"), errors="coerce") or 0
        a_dt = pd.to_numeric(row.get("D\\T- Shift A Min"), errors="coerce") or 0
        a_cause = row.get("Cause of Less Utilization", "")

        if a_good > 0 or a_ton > 0 or a_cap_ton > 0:
            records.append({
                "Date": sheet_date,
                "Machine": mc_sl,
                "Order Name": order,
                "Item Name": item,
                "Cavity": cavity,
                "Shift": "Shift A (Day)",
                "Good Prod": a_good,
                "Rejections": a_rej,
                "Prod Ton": a_ton,
                "Cap Ton": a_cap_ton,
                "Downtime Min": a_dt,
                "Downtime Cause": a_cause,
            })

        # Shift B (Night Shift) Metrics
        b_good = pd.to_numeric(row.get("B-Good"), errors="coerce") or 0
        b_rej = (
            pd.to_numeric(
                row.get(
                    "B-Reject Cause of Less Prod"
                ),  # Handles merged header column
                errors="coerce",
            )
            or pd.to_numeric(row.get("B-Reject"), errors="coerce")
            or 0
        )
        b_ton = pd.to_numeric(row.get("Prod Ton B"), errors="coerce") or 0
        b_cap_ton = pd.to_numeric(row.get("Cap/Ton.1"), errors="coerce") or 0
        b_dt = 0  # Default filler if shift B DT min column is omitted
        b_cause = row.get("Cause of Less Prod", "")

        if b_good > 0 or b_ton > 0 or b_cap_ton > 0:
            records.append({
                "Date": sheet_date,
                "Machine": mc_sl,
                "Order Name": order,
                "Item Name": item,
                "Cavity": cavity,
                "Shift": "Shift B (Night)",
                "Good Prod": b_good,
                "Rejections": b_rej,
                "Prod Ton": b_ton,
                "Cap Ton": b_cap_ton,
                "Downtime Min": b_dt,
                "Downtime Cause": b_cause,
            })

    return pd.DataFrame(records)


uploaded_file = st.file_uploader(
    "Upload Production Entry Excel File", type=["xlsx", "xls"]
)

if uploaded_file is not None:
    xls = pd.ExcelFile(uploaded_file)

    # Filter ONLY date-based sheets (containing '-202' or standard date pattern)
    date_sheets = [
        s for s in xls.sheet_names if "-" in s and ("202" in s or "203" in s)
    ]

    if not date_sheets:
        st.error(
            "No daily date sheets found in the uploaded file. Please check sheet names."
        )
    else:
        all_daily_data = []

        for sheet in date_sheets:
            clean_date_str = sheet.strip()
            df_sheet = pd.read_excel(uploaded_file, sheet_name=sheet)
            parsed_df = parse_daily_sheet(df_sheet, clean_date_str)
            if not parsed_df.empty:
                all_daily_data.append(parsed_df)

        if all_daily_data:
            df_combined = pd.concat(all_daily_data, ignore_index=True)

            tab1, tab2 = st.tabs(
                ["📈 Executive Summary & Trends", "📋 Daily Log Inspection"]
            )

            # TAB 1: EXECUTIVE SUMMARY
            with tab1:
                st.subheader("Month-to-Date Key Performance Indicators")

                total_prod_ton = df_combined["Prod Ton"].sum()
                total_cap_ton = df_combined["Cap Ton"].sum()
                overall_ach = (
                    (total_prod_ton / total_cap_ton * 100)
                    if total_cap_ton > 0
                    else 0
                )
                total_good = df_combined["Good Prod"].sum()
                total_rej = df_combined["Rejections"].sum()
                rej_rate = (
                    (total_rej / (total_good + total_rej) * 100)
                    if (total_good + total_rej) > 0
                    else 0
                )

                col1, col2, col3, col4 = st.columns(4)
                col1.metric("Produced Tons", f"{total_prod_ton:.2f} Ton")
                col2.metric("Target Capacity", f"{total_cap_ton:.2f} Ton")
                col3.metric("Achievement Rate", f"{overall_ach:.1f}%")
                col4.metric("Rejection Rate", f"{rej_rate:.2f}%")

                st.divider()

                # Tonnage Trend Chart
                daily_summary = (
                    df_combined.groupby("Date")[["Prod Ton", "Cap Ton"]]
                    .sum()
                    .reset_index()
                )
                fig_trend = px.line(
                    daily_summary,
                    x="Date",
                    y=["Cap Ton", "Prod Ton"],
                    title="Daily Tonnage Trend (Target vs Actual)",
                    markers=True,
                    labels={"value": "Tons", "variable": "Metric"},
                )
                st.plotly_chart(fig_trend, use_container_width=True)

                # Shift Comparison
                shift_summary = (
                    df_combined.groupby("Shift")[["Prod Ton", "Rejections"]]
                    .sum()
                    .reset_index()
                )
                fig_shift = px.bar(
                    shift_summary,
                    x="Shift",
                    y="Prod Ton",
                    color="Shift",
                    title="Total Produced Tons by Shift",
                    text_auto=".2f",
                )
                st.plotly_chart(fig_shift, use_container_width=True)

            # TAB 2: DAILY INSPECTION
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
                    d_col1, d_col2, d_col3 = st.columns(3)
                    d_col1.metric(
                        "Daily Produced Tons",
                        f"{date_filtered['Prod Ton'].sum():.2f} Ton",
                    )
                    d_col2.metric(
                        "Daily Good Output",
                        f"{int(date_filtered['Good Prod'].sum()):,}",
                    )
                    d_col3.metric(
                        "Daily Rejections",
                        f"{int(date_filtered['Rejections'].sum()):,}",
                    )

                    st.write("### Machine Production Breakdown")
                    st.dataframe(
                        date_filtered[[
                            "Machine",
                            "Shift",
                            "Order Name",
                            "Item Name",
                            "Good Prod",
                            "Rejections",
                            "Prod Ton",
                            "Downtime Cause",
                        ]],
                        use_container_width=True,
                    )
else:
    st.info("👈 Please upload an Excel production file to generate summaries.")
