import io
import os
import pandas as pd
import plotly.express as px
import streamlit as st
from config import MACHINE_MASTER, SMART_TO_POSITION, resolve_machine_info

# ---------------------------------------------------------
# PAGE CONFIGURATION & SESSION ACCESS CONTROL
# ---------------------------------------------------------
st.set_page_config(
    page_title="SMS Module | Plastic-3 Console",
    page_icon="📱",
    layout="wide",
)

# Load custom styling
if os.path.exists("style.css"):
    with open("style.css") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

# Access control check for main console session data
if not st.session_state.get("dashboard_ready", False) or "df_data_raw" not in st.session_state:
    st.error("🔒 **Access Denied / No Active Session**")
    st.caption("Please upload First Floor (FF) and Ground Floor (GF) production files in the main console first.")
    if st.button("⬅️ Back to Main Console", type="primary"):
        st.switch_page("app.py")
    st.stop()

df_local = st.session_state["df_data_raw"]

# ---------------------------------------------------------
# SMS DATA PARSING ENGINES (WITH CACHING)
# ---------------------------------------------------------
@st.cache_data
def parse_oee_report(file_bytes):
    df_raw = pd.read_excel(io.BytesIO(file_bytes), header=10)
    df_raw = df_raw.dropna(subset=["Date", "Machine"]).copy()

    df_raw["Date_Clean"] = pd.to_datetime(df_raw["Date"]).dt.strftime("%d-%m-%Y")
    df_raw["Machine_Clean"] = df_raw["Machine"].astype(str).str.strip()

    df_raw["Position"] = df_raw["Machine_Clean"].apply(
        lambda m: resolve_machine_info(m)["position"] if resolve_machine_info(m) else m
    )

    for col in ["Availability", "Performance", "Quality", "OEE"]:
        df_raw[col] = pd.to_numeric(df_raw[col], errors="coerce").fillna(0.0)

    return df_raw


@st.cache_data
def parse_rejection_report(file_bytes):
    df_raw = pd.read_excel(io.BytesIO(file_bytes), header=7)
    df_raw = df_raw.dropna(subset=["Machine", "Item"]).copy()

    df_raw["Date_Clean"] = pd.to_datetime(df_raw["Added Date"]).dt.strftime("%d-%m-%Y")
    df_raw["Machine_Clean"] = df_raw["Machine"].astype(str).str.strip()

    df_raw["Position"] = df_raw["Machine_Clean"].apply(
        lambda m: resolve_machine_info(m)["position"] if resolve_machine_info(m) else m
    )

    df_raw["Actual_Pcs"] = pd.to_numeric(df_raw["Quantity"], errors="coerce").fillna(0.0) * 1000.0
    df_raw["Weight_Kg"] = pd.to_numeric(df_raw["Weight"], errors="coerce").fillna(0.0)
    df_raw["Cause"] = df_raw["Cause"].astype(str).str.strip()
    df_raw["Item"] = df_raw["Item"].astype(str).str.strip()

    return df_raw

# ---------------------------------------------------------
# INDEPENDENT SMS SIDEBAR
# ---------------------------------------------------------
with st.sidebar:
    if os.path.exists("logo.png"):
        st.image("logo.png", use_container_width=True)

    st.markdown("### **SMS CONSOLE**")
    st.caption("Smart Manufacturing System Analytics")
    st.divider()

    sms_nav = st.radio(
        "📍 **Select SMS Module:**",
        [
            "⚠️ Daily >50 Pcs Audit",
            "📊 OEE Analysis",
            "🚨 Rejection Analysis",
        ]
    )

    st.divider()

    if st.button("🔄 Reset SMS Uploads", use_container_width=True):
        st.session_state.pop("sms_oee_bytes", None)
        st.session_state.pop("sms_rej_bytes", None)
        st.rerun()

    st.divider()

    if st.button("⬅️ Main Operations Console", use_container_width=True):
        st.switch_page("app.py")

# ---------------------------------------------------------
# UI HEADER & FILE UPLOADER WITH SESSION PERSISTENCE
# ---------------------------------------------------------
st.title("📱 **SMART MANUFACTURING SYSTEM (SMS) ANALYTICS**")
st.caption("Cross-reference official SMS OEE & Rejection exports with local shop floor performance.")
st.divider()

col1, col2 = st.columns(2)

with col1:
    oee_file = st.file_uploader("Upload SMS OEE Report (.xlsx)", type=["xlsx", "xls"], key="sms_oee_input")
    if oee_file is not None:
        st.session_state["sms_oee_bytes"] = oee_file.getvalue()

with col2:
    rej_file = st.file_uploader("Upload SMS Rejection Report (.xlsx)", type=["xlsx", "xls"], key="sms_rej_input")
    if rej_file is not None:
        st.session_state["sms_rej_bytes"] = rej_file.getvalue()

# Retrieve stored bytes from session state if available
oee_bytes = st.session_state.get("sms_oee_bytes", None)
rej_bytes = st.session_state.get("sms_rej_bytes", None)

if oee_bytes is None and rej_bytes is None:
    st.info("👆 Please upload at least one SMS export (OEE or Rejection Report) to launch analysis.")
    st.stop()

# Parse Datasets from Session State Bytes
df_oee = parse_oee_report(oee_bytes) if oee_bytes is not None else pd.DataFrame()
df_rej = parse_rejection_report(rej_bytes) if rej_bytes is not None else pd.DataFrame()

# ---------------------------------------------------------
# CROSS-SYSTEM DATE ALIGNMENT AUDIT
# ---------------------------------------------------------
local_dates = set(df_local["Date"].unique())
oee_dates = set(df_oee["Date_Clean"].unique()) if not df_oee.empty else set()
rej_dates = set(df_rej["Date_Clean"].unique()) if not df_rej.empty else set()

missing_oee_dates = sorted(list(local_dates - oee_dates))
missing_rej_dates = sorted(list(local_dates - rej_dates))

if missing_oee_dates:
    st.warning(f"⚠️ **OEE Data Gap Detected**: {len(missing_oee_dates)} date(s) missing from OEE upload ({', '.join(missing_oee_dates)}).")

if missing_rej_dates:
    st.warning(f"⚠️ **Rejection Data Gap Detected**: {len(missing_rej_dates)} date(s) missing from Rejection upload ({', '.join(missing_rej_dates)}).")

st.divider()

# ---------------------------------------------------------
# DYNAMIC MODULE ROUTING (CONTROLLED BY SMS SIDEBAR)
# ---------------------------------------------------------
if sms_nav == "⚠️ Daily >50 Pcs Audit":
    if df_rej.empty:
        st.info("Upload Rejection Report to view Daily Threshold Audit.")
    else:
        st.markdown("### ⚠️ Daily Machines Exceeding 50 Pcs Rejection")

        all_rej_dates = sorted(list(df_rej["Date_Clean"].unique()))
        selected_rej_date = st.selectbox("Select Operational Date:", all_rej_dates, key="rej_date_select")

        df_day_rej = df_rej[df_rej["Date_Clean"] == selected_rej_date].copy()

        summary_records = []
        for (pos, mc), grp in df_day_rej.groupby(["Position", "Machine_Clean"]):
            tot_day_pcs = grp["Actual_Pcs"].sum()

            if tot_day_pcs > 50:
                causes = ", ".join(sorted(grp["Cause"].unique()))
                molds = ", ".join(sorted(grp["Item"].unique()))

                summary_records.append({
                    "Position": pos,
                    "Machine": mc,
                    "Causes": causes,
                    "Qty": int(round(tot_day_pcs)),
                    "Mold": molds
                })

        df_summary = pd.DataFrame(summary_records)

        if df_summary.empty:
            st.success(f"🎉 No machines exceeded 50 pcs rejection on {selected_rej_date}!")
        else:
            df_summary = df_summary.sort_values("Qty", ascending=False).reset_index(drop=True)

            col_met1, col_met2 = st.columns(2)
            col_met1.metric("Flagged Machines (>50 Pcs)", f"{len(df_summary)} MCs")
            col_met2.metric("Total Flagged Scrap", f"{df_summary['Qty'].sum():,} Pcs")

            st.dataframe(df_summary, use_container_width=True, hide_index=True)

            st.download_button(
                "📥 Export Daily Rejection Threshold Summary (CSV)",
                df_summary.to_csv(index=False),
                f"Daily_Rejection_Audit_{selected_rej_date}.csv",
                "text/csv"
            )

elif sms_nav == "📊 OEE Analysis":
    if df_oee.empty:
        st.info("Upload OEE Report to view OEE Analytics.")
    else:
        st.markdown("### 📊 OEE & Equipment Efficiency Summary")

        df_oee_active = df_oee[df_oee["Availability"] > 0].copy()

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Active Run Records", f"{len(df_oee_active):,}")
        c2.metric("Avg Availability", f"{df_oee_active['Availability'].mean():.2f}%")
        c3.metric("Avg Performance", f"{df_oee_active['Performance'].mean():.2f}%")
        c4.metric("Avg Quality", f"{df_oee_active['Quality'].mean():.2f}%")

        st.divider()

        oee_mc_summary = df_oee_active.groupby(["Position", "Machine_Clean"])[
            ["Availability", "Performance", "Quality", "OEE"]
        ].mean().round(2).reset_index()

        st.dataframe(oee_mc_summary, use_container_width=True, hide_index=True)

elif sms_nav == "🚨 Rejection Analysis":
    if df_rej.empty:
        st.info("Upload Rejection Report to view Defect Analytics.")
    else:
        st.markdown("### 🚨 SMS Rejection & Defect Analysis")

        tot_pcs = df_rej["Actual_Pcs"].sum()
        tot_wt = df_rej["Weight_Kg"].sum()

        c1, c2, c3 = st.columns(3)
        c1.metric("Total Rejection (Pcs)", f"{int(tot_pcs):,} Pcs")
        c2.metric("Total Scrap Weight", f"{tot_wt:.2f} Kg")
        c3.metric("Defect Entries Logged", f"{len(df_rej):,}")

        st.divider()

        cause_summary = df_rej.groupby("Cause")[["Actual_Pcs", "Weight_Kg"]].sum().reset_index()
        cause_summary = cause_summary.sort_values("Actual_Pcs", ascending=False)

        fig_cause = px.bar(
            cause_summary.head(10),
            x="Cause", y="Actual_Pcs",
            title="Top 10 Rejection Causes (Actual Pcs)",
            color_discrete_sequence=["#ef4444"]
        )
        st.plotly_chart(fig_cause, use_container_width=True)
