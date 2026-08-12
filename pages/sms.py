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
# SMS DATA PARSING ENGINES
# ---------------------------------------------------------
@st.cache_data
def parse_oee_report(file_bytes):
    df_raw = pd.read_excel(io.BytesIO(file_bytes), header=10)
    df_raw = df_raw.dropna(subset=["Date", "Machine"]).copy()

    df_raw["Date_Obj"] = pd.to_datetime(df_raw["Date"])
    df_raw["Date_Clean"] = df_raw["Date_Obj"].dt.strftime("%d-%m-%Y")
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

    df_raw["Date_Obj"] = pd.to_datetime(df_raw["Added Date"])
    df_raw["Date_Clean"] = df_raw["Date_Obj"].dt.strftime("%d-%m-%Y")
    df_raw["Machine_Clean"] = df_raw["Machine"].astype(str).str.strip()

    df_raw["Position"] = df_raw["Machine_Clean"].apply(
        lambda m: resolve_machine_info(m)["position"] if resolve_machine_info(m) else m
    )

    df_raw["Actual_Pcs"] = pd.to_numeric(df_raw["Quantity"], errors="coerce").fillna(0.0) * 1000.0
    df_raw["Weight_Kg"] = pd.to_numeric(df_raw["Weight"], errors="coerce").fillna(0.0)
    df_raw["Cause"] = df_raw["Cause"].astype(str).str.strip()
    df_raw["Item"] = df_raw["Item"].astype(str).str.strip()
    df_raw["Added By"] = df_raw["Added By"].astype(str).str.strip()

    return df_raw

# ---------------------------------------------------------
# SIDEBAR RE-UPLOAD & PERSISTENCE ENGINE
# ---------------------------------------------------------
with st.sidebar:
    if os.path.exists("logo.png"):
        st.image("logo.png", use_container_width=True)

    st.markdown("### **SMS CONSOLE**")
    st.caption("Smart Manufacturing System Analytics")
    st.divider()

    sms_main_nav = st.radio(
        "📍 **Select Main Module:**",
        [
            "📊 OEE Analysis",
            "🚨 Rejection Analysis",
        ]
    )

    st.divider()

    with st.expander("📁 **Re-upload / Update Reports**"):
        up_oee = st.file_uploader("SMS OEE Report (.xlsx)", type=["xlsx", "xls"], key="sb_oee")
        if up_oee is not None:
            st.session_state["sms_oee_bytes"] = up_oee.getvalue()

        up_rej = st.file_uploader("SMS Rejection Report (.xlsx)", type=["xlsx", "xls"], key="sb_rej")
        if up_rej is not None:
            st.session_state["sms_rej_bytes"] = up_rej.getvalue()

        if st.button("🔄 Clear SMS Data", use_container_width=True):
            st.session_state.pop("sms_oee_bytes", None)
            st.session_state.pop("sms_rej_bytes", None)
            st.rerun()

    st.divider()

    if st.button("⬅️ Main Operations Console", use_container_width=True):
        st.switch_page("app.py")

# Retrieve Stored Bytes
oee_bytes = st.session_state.get("sms_oee_bytes", None)
rej_bytes = st.session_state.get("sms_rej_bytes", None)

# Parse Stored Datasets
df_oee = parse_oee_report(oee_bytes) if oee_bytes is not None else pd.DataFrame()
df_rej = parse_rejection_report(rej_bytes) if rej_bytes is not None else pd.DataFrame()

# ---------------------------------------------------------
# TOP STATUS & DATE AUDIT BADGE
# ---------------------------------------------------------
local_dates = set(df_local["Date"].unique())
oee_dates = set(df_oee["Date_Clean"].unique()) if not df_oee.empty else set()
rej_dates = set(df_rej["Date_Clean"].unique()) if not df_rej.empty else set()

missing_oee = sorted(list(local_dates - oee_dates))
missing_rej = sorted(list(local_dates - rej_dates))

# Render Date Audit Badge at Sidebar Top
with st.sidebar:
    st.markdown("#### 📅 **Date Alignment Audit**")
    if not oee_bytes and not rej_bytes:
        st.info("Awaiting SMS Uploads...")
    elif not missing_oee and not missing_rej:
        st.success("🟢 **All Dates Gathered**")
    else:
        if missing_oee:
            st.error(f"❌ **Missing OEE Dates ({len(missing_oee)}d):**\n" + ", ".join(missing_oee))
        if missing_rej:
            st.error(f"❌ **Missing Rejection Dates ({len(missing_rej)}d):**\n" + ", ".join(missing_rej))

# Landing Upload Prompts (Disappears once uploaded)
if oee_bytes is None and rej_bytes is None:
    st.title("📱 **SMART MANUFACTURING SYSTEM (SMS) ANALYTICS**")
    st.caption("Upload official SMS OEE & Rejection exports to launch analytics.")
    st.divider()

    c_up1, c_up2 = st.columns(2)
    with c_up1:
        oee_init = st.file_uploader("Upload SMS OEE Report (.xlsx)", type=["xlsx", "xls"], key="init_oee")
        if oee_init is not None:
            st.session_state["sms_oee_bytes"] = oee_init.getvalue()
            st.rerun()

    with c_up2:
        rej_init = st.file_uploader("Upload SMS Rejection Report (.xlsx)", type=["xlsx", "xls"], key="init_rej")
        if rej_init is not None:
            st.session_state["sms_rej_bytes"] = rej_init.getvalue()
            st.rerun()

    st.stop()

# ---------------------------------------------------------
# MODULE 1: OEE ANALYSIS
# ---------------------------------------------------------
if sms_main_nav == "📊 OEE Analysis":
    st.title("📊 **OEE & EQUIPMENT EFFICIENCY ANALYTICS**")

    if df_oee.empty:
        st.warning("⚠️ OEE Report is not uploaded yet. Use the sidebar to upload the OEE Excel export.")
    else:
        # Top Sub-module Selector
        oee_sub_nav = st.radio(
            "Select OEE View:",
            ["📊 As-Of OEE", "📅 Datewise OEE", "📈 See Graph (Everyday OEE)"],
            horizontal=True,
            label_visibility="collapsed"
        )
        st.divider()

        # Exclude machines with 0 Availability
        df_oee_active = df_oee[df_oee["Availability"] > 0].copy()

        # 5 KPI Cards Strip
        k1, k2, c3, c4, k5 = st.columns(5)
        k1.metric("Active Run Records", f"{len(df_oee_active):,}")
        k2.metric("Avg Availability", f"{df_oee_active['Availability'].mean():.2f}%")
        c3.metric("Avg Performance", f"{df_oee_active['Performance'].mean():.2f}%")
        c4.metric("Avg Quality", f"{df_oee_active['Quality'].mean():.2f}%")
        k5.metric("Avg OEE", f"{df_oee_active['OEE'].mean():.2f}%")

        st.divider()

        if oee_sub_nav == "📊 As-Of OEE":
            st.markdown("### 📊 As-Of Cumulative Machine OEE Summary")
            oee_mc_summary = df_oee_active.groupby(["Position", "Machine_Clean"])[
                ["Availability", "Performance", "Quality", "OEE"]
            ].mean().round(2).reset_index()
            st.dataframe(oee_mc_summary, use_container_width=True, hide_index=True)

        elif oee_sub_nav == "📅 Datewise OEE":
            st.markdown("### 📅 Operational Datewise OEE Breakdown")
            all_oee_dates = sorted(list(df_oee_active["Date_Clean"].unique()))
            sel_oee_date = st.selectbox("Select Operational Date:", all_oee_dates, key="sel_oee_dt")

            df_oee_day = df_oee_active[df_oee_active["Date_Clean"] == sel_oee_date].copy()
            oee_day_summary = df_oee_day[["Position", "Machine_Clean", "Availability", "Performance", "Quality", "OEE"]].reset_index(drop=True)
            st.dataframe(oee_day_summary, use_container_width=True, hide_index=True)

        elif oee_sub_nav == "📈 See Graph (Everyday OEE)":
            st.markdown("### 📈 Everyday OEE Trend (Day-by-Day)")

            # Daily mean calculations
            df_trend = df_oee_active.groupby(["Date_Obj", "Date_Clean"])[
                ["Availability", "Performance", "Quality", "OEE"]
            ].mean().reset_index().sort_values("Date_Obj")

            fig_oee_trend = px.line(
                df_trend,
                x="Date_Clean",
                y=["Availability", "Performance", "Quality", "OEE"],
                title="Everyday OEE Trend Analysis",
                markers=True,
                color_discrete_map={
                    "Availability": "#3b82f6",
                    "Performance": "#ef4444",
                    "Quality": "#22c55e",
                    "OEE": "#f59e0b"
                }
            )
            fig_oee_trend.update_layout(
                yaxis_title="Percentage (%)",
                xaxis_title="Operational Date",
                hovermode="x unified"
            )
            st.plotly_chart(fig_oee_trend, use_container_width=True)

# ---------------------------------------------------------
# MODULE 2: REJECTION ANALYSIS
# ---------------------------------------------------------
elif sms_main_nav == "🚨 Rejection Analysis":
    st.title("🚨 **REJECTION & DEFECT ANALYTICS**")

    if df_rej.empty:
        st.warning("⚠️ Rejection Report is not uploaded yet. Use the sidebar to upload the Rejection Excel export.")
    else:
        # Top Sub-module Selector
        rej_sub_nav = st.radio(
            "Select Rejection View:",
            ["📊 As-Of Summary", "⚠️ >50 Pcs Threshold Audit", "📅 Datewise Summary", "👤 Added By Performance"],
            horizontal=True,
            label_visibility="collapsed"
        )
        st.divider()

        tot_pcs = df_rej["Actual_Pcs"].sum()
        tot_wt = df_rej["Weight_Kg"].sum()

        r1, r2, r3 = st.columns(3)
        r1.metric("Total Rejection", f"{int(round(tot_pcs)):,} Pcs")
        r2.metric("Total Scrap Weight", f"{tot_wt:.2f} Kg")
        r3.metric("Defect Entries Logged", f"{len(df_rej):,}")

        st.divider()

        if rej_sub_nav == "📊 As-Of Summary":
            st.markdown("### 📊 As-Of Defect & Rejection Summary")
            cause_summary = df_rej.groupby("Cause")[["Actual_Pcs", "Weight_Kg"]].sum().reset_index()
            cause_summary = cause_summary.sort_values("Actual_Pcs", ascending=False)

            fig_cause = px.bar(
                cause_summary.head(10),
                x="Cause", y="Actual_Pcs",
                title="Top 10 Rejection Causes (Actual Pcs)",
                color_discrete_sequence=["#ef4444"]
            )
            st.plotly_chart(fig_cause, use_container_width=True)

            st.dataframe(cause_summary, use_container_width=True, hide_index=True)

        elif rej_sub_nav == "⚠️ >50 Pcs Threshold Audit":
            st.markdown("### ⚠️ Machines Exceeding 50 Pcs Rejection on Selected Date")
            all_rej_dates = sorted(list(df_rej["Date_Clean"].unique()))
            sel_rej_date = st.selectbox("Select Operational Date:", all_rej_dates, key="thresh_dt")

            df_day_rej = df_rej[df_rej["Date_Clean"] == sel_rej_date].copy()

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

            df_thresh = pd.DataFrame(summary_records)
            if df_thresh.empty:
                st.success(f"🎉 No machines exceeded 50 pcs rejection on {sel_rej_date}!")
            else:
                df_thresh = df_thresh.sort_values("Qty", ascending=False).reset_index(drop=True)
                st.dataframe(df_thresh, use_container_width=True, hide_index=True)

        elif rej_sub_nav == "📅 Datewise Summary":
            st.markdown("### 📅 Daily Rejection Logs & Mold Breakdown")
            all_rej_dates = sorted(list(df_rej["Date_Clean"].unique()))
            sel_rej_date = st.selectbox("Select Operational Date:", all_rej_dates, key="dtwise_rej_dt")

            df_day_logs = df_rej[df_rej["Date_Clean"] == sel_rej_date].copy()
            st.dataframe(
                df_day_logs[["Position", "Machine_Clean", "Item", "Actual_Pcs", "Weight_Kg", "Cause", "Added By"]],
                use_container_width=True,
                hide_index=True
            )

        elif rej_sub_nav == "👤 Added By Performance":
            st.markdown("### 👤 User Logging Performance (As-Of)")
            user_summary = df_rej.groupby("Added By").agg(
                Logged_Entries=("Actual_Pcs", "count"),
                Total_Scrap_Pcs=("Actual_Pcs", lambda x: int(round(x.sum()))),
                Total_Scrap_Kg=("Weight_Kg", lambda x: round(x.sum(), 2))
            ).reset_index().sort_values("Logged_Entries", ascending=False)

            st.dataframe(user_summary, use_container_width=True, hide_index=True)
