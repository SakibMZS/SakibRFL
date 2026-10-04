# ============================================
# PLASTIC-3 OPERATIONS CONSOLE  (FF + GF)
# app.py  - screens only. Logic lives in:
#    ingest.py   (read + validate + reconcile the Excel files)
#    reports.py  (summary calculations)
#    exporter.py (Excel exports)
# ============================================
import io
import json
import os
from datetime import datetime

import pandas as pd
import plotly.express as px
import streamlit as st

import exporter
import ingest
import reports
from config import EXCEL_SIZES  # noqa: F401  (kept for compatibility)

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

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
NAV = [
    "📅 Daily Data",
    "📊 As of Data (MTD)",
    "📦 Job Order Analysis",
    "🌗 Shiftwise Data",
    "📑 Monthly Master Export",
    "🩺 Data Health",
]
HEALTH_NAV = NAV[-1]

if "corrections" not in st.session_state:
    st.session_state["corrections"] = {"rows": {}, "reviewed": {}}
if "app_launched" not in st.session_state:
    st.session_state["app_launched"] = False


def sort_dates(date_strs):
    return sorted(date_strs, key=lambda s: datetime.strptime(s, "%d-%m-%Y"))


def to_obj(date_str):
    return datetime.strptime(date_str, "%d-%m-%Y")


def corr_full():
    return json.dumps(st.session_state["corrections"], sort_keys=True)


def corr_rows_only():
    return json.dumps({"rows": st.session_state["corrections"]["rows"]}, sort_keys=True)


def go_health():
    st.session_state["nav_choice"] = HEALTH_NAV


# ============================================
# CACHED READERS
# ============================================
@st.cache_data(show_spinner="Scanning workbook tabs...")
def cached_scan(file_bytes):
    return ingest.scan_workbook(file_bytes)


@st.cache_data(show_spinner="Reading and validating every production tab...")
def cached_parse(file_bytes, floor, year, month, last_day, corr_rows_json):
    return ingest.parse_floor(file_bytes, floor, year, month, last_day, corr_rows_json)


# ============================================
# TABLE HELPERS
# ============================================
def column_visibility_selector(df, key_prefix="", default_visible_cols=None):
    all_cols = df.columns.tolist()
    if default_visible_cols:
        initial = [c for c in default_visible_cols if c in all_cols]
    else:
        initial = [c for c in all_cols if c not in ("Entry Count", "Is Mixed", "Is Completed")]
    skey = f"{key_prefix}_visible_cols"
    if skey not in st.session_state:
        st.session_state[skey] = initial

    with st.popover("👁️️ Columns"):
        st.caption("Check or uncheck columns to customize active table view:")
        visible = []
        for col in all_cols:
            if st.checkbox(col, value=col in st.session_state[skey], key=f"{key_prefix}_col_{col}"):
                visible.append(col)
        if st.button("Apply View", key=f"{key_prefix}_apply", use_container_width=True):
            st.session_state[skey] = visible
            st.rerun()
    chosen = [c for c in st.session_state[skey] if c in df.columns]
    return chosen or initial or all_cols


def render_table(df_tot, key, dl_label, dl_name, default_cols=None, selector_slot=None):
    if selector_slot is not None:
        with selector_slot:
            v_cols = column_visibility_selector(df_tot, key, default_cols)
    else:
        v_cols = column_visibility_selector(df_tot, key, default_cols)
    clean = reports.clean_and_format_dataframe(df_tot[v_cols])
    st.dataframe(clean, use_container_width=True, hide_index=True)
    st.download_button(dl_label, xl(clean), dl_name, XLSX_MIME)
    return clean


def xl(df):
    return exporter.convert_df_to_excel_bytes(df, QUALITY)


def search_filter(df, term):
    t = term.strip().lower()
    if not t or df.empty:
        return df
    m = pd.Series(False, index=df.index)
    for c in ("Order Name", "Item Name", "Customer"):
        if c in df.columns:
            m |= df[c].astype(str).str.lower().str.contains(t, regex=False)
    return df[m]


# ============================================
# LANDING SCREEN
# ============================================
if not st.session_state["app_launched"]:
    st.markdown('<div class="landing-page-marker"></div>', unsafe_allow_html=True)
    st.markdown("## 🏭 **PLASTIC-3 CONSOLE SETUP**")
    st.markdown("##### Upload your production entry files to launch.")
    st.divider()

    col1, col2 = st.columns(2)
    with col1:
        st.markdown('<div class="setup-card ff"><h3>🏢 First Floor (FF)</h3><p style="color:#64748b !important;">Select the FF Excel production file</p></div>', unsafe_allow_html=True)
        ff_file = st.file_uploader("Upload First Floor File (.xlsx)", type=["xlsx", "xls"], key="init_ff")
    with col2:
        st.markdown('<div class="setup-card gf"><h3>🏬 Ground Floor (GF)</h3><p style="color:#64748b !important;">Select the GF Excel production file</p></div>', unsafe_allow_html=True)
        gf_file = st.file_uploader("Upload Ground Floor File (.xlsx)", type=["xlsx", "xls"], key="init_gf")

    with st.expander("💾 Have a saved corrections file from before? (optional)"):
        corr_file = st.file_uploader("Corrections file (.json)", type=["json"], key="init_corr")

    st.divider()
    if st.button("🚀 Launch Dashboard", type="primary", use_container_width=True):
        if ff_file is None and gf_file is None:
            st.error("Please upload at least one floor file to launch.")
        else:
            if ff_file is not None:
                st.session_state["ff_bytes"] = ff_file.getvalue()
            if gf_file is not None:
                st.session_state["gf_bytes"] = gf_file.getvalue()
            if corr_file is not None:
                try:
                    data = json.loads(corr_file.getvalue().decode("utf-8"))
                    st.session_state["corrections"] = {"rows": data.get("rows", {}), "reviewed": data.get("reviewed", {})}
                except Exception as e:
                    st.error(f"Corrections file could not be read ({e}). Launching without it.")
            st.session_state["app_launched"] = True
            st.rerun()
    st.stop()

# ============================================
# LOAD + VALIDATE
# ============================================
st.markdown('<div class="dashboard-page-marker"></div>', unsafe_allow_html=True)


def change_files_button(where="main"):
    if st.button("⚙️ Change Uploaded Files", use_container_width=True, key=f"chg_{where}"):
        for k in ("app_launched", "ff_bytes", "gf_bytes", "df_data_raw", "dashboard_ready", "health"):
            if k == "app_launched":
                st.session_state[k] = False
            else:
                st.session_state.pop(k, None)
        st.rerun()


floor_bytes = {}
if "ff_bytes" in st.session_state:
    floor_bytes["FF"] = st.session_state["ff_bytes"]
if "gf_bytes" in st.session_state:
    floor_bytes["GF"] = st.session_state["gf_bytes"]

scans, read_errors = {}, []
for fl, b in floor_bytes.items():
    try:
        scans[fl] = cached_scan(b)
    except Exception as e:
        read_errors.append(f"{fl}: the file could not be opened as an Excel workbook ({e})")

for msg in read_errors:
    st.error(f"❌ {msg}")

period = ingest.choose_period(scans) if scans else None
if period is None:
    st.error("❌ **No dated daily production tab was found** (tab names like `29-09-26` or `29-09-2026`). Nothing can be reported.")
    for fl, sc in scans.items():
        with st.expander(f"Tabs found in the {fl} file"):
            st.dataframe(pd.DataFrame([{"Tab": str(r["name"]).strip(), "Read as": r["kind"], "Note": r["note"]} for r in sc]), hide_index=True, use_container_width=True)
    change_files_button("fatal")
    st.stop()

results = {}
for fl in scans:
    try:
        results[fl] = cached_parse(floor_bytes[fl], fl, period["year"], period["month"], period["last_day"], corr_rows_only())
    except Exception as e:
        st.error(f"❌ **{fl} file failed while reading:** {e}. None of its data is shown.")

if not results:
    change_files_button("fatal2")
    st.stop()

health = ingest.build_health(results, period, corr_full())
frames = [r["records"] for r in results.values() if not r["records"].empty]
if not frames:
    st.error("❌ **No production rows could be read from the uploaded file(s).** See the reasons below.")
    st.dataframe(health["file_issues"], hide_index=True, use_container_width=True)
    change_files_button("fatal3")
    st.stop()

df_all = pd.concat(frames, ignore_index=True)
df_data_raw = df_all[~df_all["Excluded"]].copy()
st.session_state["df_data_raw"] = df_data_raw
st.session_state["health"] = health
st.session_state["dashboard_ready"] = True

# ============================================
# SIDEBAR
# ============================================
with st.sidebar:
    col_logo, col_text = st.columns([1, 2.3], gap="small", vertical_alignment="center")
    with col_logo:
        if os.path.exists("logo.png"):
            st.image("logo.png", use_container_width=True)
        else:
            st.markdown("🏭")
    with col_text:
        st.markdown("### **PLASTIC-3 CONSOLE**")
        st.caption(f"{period['label']} · days 1–{period['last_day']}")
    st.divider()

    nav_choice = st.radio("📍 **Select Module:**", NAV, key="nav_choice")
    st.divider()
    floor_choice = st.radio("🏢 **Floor View:**", ["ALL FLOORS", "FF", "GF"], horizontal=True, key="floor_toggle")
    st.divider()
    hide_zero_runs = st.toggle("🚫 Hide Non-Running Machines", value=True, help="Filters out idle machines with zero production on Floor View")
    st.divider()

    c = health["counts"]
    if c["errors"]:
        st.error(f"🔴 {c['errors']} error(s) · 🟡 {c['warnings']} warning(s) open")
    elif c["warnings"]:
        st.warning(f"🟡 {c['warnings']} warning(s) open")
    else:
        st.success("🟢 No open data issues")
    st.button("🩺 Open Data Health", use_container_width=True, on_click=go_health, key="sb_health")
    st.divider()

    if st.button("📱 Launch SMS Module", use_container_width=True):
        st.switch_page("pages/sms.py")
    st.divider()
    change_files_button("sidebar")

# ============================================
# STATUS BANNER + COMMON FILTERS
# ============================================
def render_banner(module_key):
    cov = health["coverage"]
    c = health["counts"]
    parts = []
    for fl in sorted(scans):
        ok = int(cov[(cov["Floor"] == fl) & cov["Status"].str.startswith("OK")].shape[0]) if not cov.empty else 0
        parts.append(f"{fl}: {ok}/{period['last_day']} days")
    st.caption(f"📆 **{period['label']}**  ·  " + "  ·  ".join(parts))

    bad = cov[cov["Status"].isin(["Missing", "Unreadable"])] if not cov.empty else cov
    if not bad.empty:
        lst = ", ".join(f"{r.Floor} {r.Date}" for r in bad.itertuples())
        st.error(f"❌ **Missing or unreadable day(s): {lst}.** These days are NOT included in any figure on this page.")
    if c["errors"] or c["warnings"]:
        left, right = st.columns([5, 1.4])
        with left:
            box = st.error if c["errors"] else st.warning
            box(f"🩺 {c['errors']} error(s) and {c['warnings']} warning(s) are still open - figures may be affected until they are fixed or reviewed.")
        with right:
            st.button("Open Data Health", key=f"bn_{module_key}", on_click=go_health, use_container_width=True)
    else:
        st.success("🟢 No open data issues - every day ties to the source sheets.")


if floor_choice == "FF" and "ff_bytes" not in st.session_state:
    st.warning("⚠️ **First Floor (FF) file is not uploaded.**")
    st.stop()
if floor_choice == "GF" and "gf_bytes" not in st.session_state:
    st.warning("⚠️ **Ground Floor (GF) file is not uploaded.**")
    st.stop()

df_curr = df_data_raw if floor_choice == "ALL FLOORS" else df_data_raw[df_data_raw["Floor"] == floor_choice].copy()
df_active = df_curr[df_curr["Total Good"] > 0].copy() if hide_zero_runs else df_curr.copy()
QUALITY = exporter.quality_pack(health, floor_choice)

# ============================================
# MODULE: DAILY DATA
# ============================================
if nav_choice == "📅 Daily Data":
    render_banner("daily")
    all_dates = sort_dates(df_curr["Date"].unique())
    if not all_dates:
        st.info("No data for this floor view.")
        st.stop()

    col_nav1, col_nav2, col_nav3 = st.columns([3.5, 1.2, 1.3])
    with col_nav1:
        daily_mode = st.radio("Daily View Mode:", ["📊 Linewise", "🏭 MC Wise", "📏 Sizewise", "📦 Job-Order Wise"], horizontal=True, label_visibility="collapsed")
    with col_nav2:
        selected_date = st.selectbox("Operational Date", all_dates, index=len(all_dates) - 1, label_visibility="collapsed")
    with col_nav3:
        st.button(f"🩺 {health['counts']['open']} open", key="hb_daily", on_click=go_health, use_container_width=True)
    st.divider()

    df_daily_raw = df_active[df_active["Date"] == selected_date].copy()
    if df_daily_raw.empty:
        st.info(f"No machine produced on {selected_date} in this view (sheet was read; all rows are idle).")
        st.stop()
    df_daily = reports.consolidate_daily_machines(df_daily_raw)

    tot_prod_ton, tot_cap_ton = df_daily["Total Prod Ton"].sum(), df_daily["Weighted Cap Ton"].sum()
    tot_good_pcs, tot_cap_pcs = df_daily["Total Good"].sum(), df_daily["Weighted Cap Pcs"].sum()
    tot_rej, tot_time = df_daily["Total Rejections"].sum(), df_daily["Total Runtime (Hrs)"].sum()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Prod vs Cap (Tons)", f"{tot_prod_ton:.2f} / {tot_cap_ton:.2f} T", f"Ach: {(tot_prod_ton / tot_cap_ton * 100) if tot_cap_ton > 0 else 0:.2f}%")
    c2.metric("Prod vs Cap (Pieces)", f"{int(tot_good_pcs):,} Pcs", f"Ach: {(tot_good_pcs / tot_cap_pcs * 100) if tot_cap_pcs > 0 else 0:.2f}%")
    c3.metric("Total Rejections", f"{int(tot_rej):,} Pcs", f"Quality Loss: {(tot_rej / tot_good_pcs * 100):.2f}%" if tot_good_pcs > 0 else "0.00%")
    c4.metric("Running Machines", f"{df_daily['Machine'].nunique()} MCs", f"Runtime: {tot_time:.2f} Hrs")
    st.divider()

    if daily_mode == "📊 Linewise":
        st.markdown("### 📈 Line-Wise Performance Summary")
        t = reports.add_total_row(reports.compute_line_summary(df_daily_raw), "Line Group",
                                  ["Running MC Qty", "Runtime (Hrs)", "Cap (Pcs)", "Prod (Pcs)", "Cap (Ton)", "Prod (Ton)"], [])
        render_table(t, "daily_line", "📥 Export Daily Line Summary (.xlsx)", "Daily_Line_Summary.xlsx")

    elif daily_mode == "🏭 MC Wise":
        st.markdown("### 🏭 Consolidated Machine Performance")
        t = reports.add_total_row(df_daily, "Machine",
                                  ["Shift A Good", "Shift B Good", "Total Good", "Total Rejections", "Shift A Runtime", "Shift B Runtime",
                                   "Total Runtime (Hrs)", "Weighted Cap Pcs", "Weighted Cap Ton", "Total Prod Ton"],
                                  ["CT", "Cavity"], weight_col="Total Runtime (Hrs)")
        render_table(t, "daily_mc", "📥 Export Daily Machine Summary (.xlsx)", "Daily_Machine_Summary.xlsx")

        mixed = df_daily[df_daily["Is Mixed"]]["Machine"].tolist()
        if mixed:
            st.divider()
            st.markdown("#### 🔍 Inspect Mixed Machine Breakdown (Inside Story)")
            sel_mc = st.selectbox("Select a Mixed Machine ID to view its mold run breakdown:", mixed)
            sub = df_daily_raw[df_daily_raw["Machine"] == sel_mc].copy()
            sub["Runtime (Hrs)"] = sub["Total Runtime (Hrs)"].round(2)
            sub["Daily Prod (Ton)"] = sub["Total Prod Ton"].round(2)
            st.dataframe(reports.clean_and_format_dataframe(sub[["Floor", "Order Name", "Item Name", "CT", "Cavity", "Shift A Good", "Shift B Good", "Total Good", "Runtime (Hrs)", "Daily Prod (Ton)"]]),
                         use_container_width=True, hide_index=True)

    elif daily_mode == "📏 Sizewise":
        st.markdown("### 📏 Machine Size Summary")
        t = reports.add_size_total_row(reports.compute_size_summary(df_daily_raw, mode="daily"))
        render_table(t, "daily_size", "📥 Export Daily Size Summary (.xlsx)", "Daily_Size_Summary.xlsx")

    elif daily_mode == "📦 Job-Order Wise":
        st.markdown("### 📦 Active Orders Run On Selected Date")
        col_top1, col_top2 = st.columns([1.2, 2.5])
        job_day = reports.build_job_daily(df_daily_raw)
        with col_top2:
            term = st.text_input("Search Daily Orders", "", placeholder="🔍 Search Job Order or Item Name...", label_visibility="collapsed", key="search_daily_job")
        job_day = search_filter(job_day, term)
        t = reports.add_total_row(job_day, "Order Name",
                                  ["Demand Qty", "Total Good", "Total Prod Ton", "Running Molds", "Daily Cap (Pcs)", "Daily Prod (Pcs)",
                                   "Daily Cap (Ton)", "Daily Prod (Ton)", "Daily Runtime (Hrs)"], [])
        render_table(t, "daily_job", "📥 Export Daily Active Job Summary (.xlsx)", "Daily_Job_Summary.xlsx", selector_slot=col_top1)

# ============================================
# MODULE: AS OF (MTD)
# ============================================
elif nav_choice == "📊 As of Data (MTD)":
    render_banner("mtd")
    all_dates = sort_dates(df_curr["Date"].unique())
    if not all_dates:
        st.info("No data for this floor view.")
        st.stop()

    col1, col2, col3 = st.columns([3.5, 1.2, 1.3])
    with col1:
        mtd_mode = st.radio("As-Of View Mode:", ["📊 Linewise", "📏 Sizewise", "📦 Job-Order Wise"], horizontal=True, label_visibility="collapsed")
    with col2:
        as_of_date = st.selectbox("As-Of Cutoff Date", all_dates, index=len(all_dates) - 1, label_visibility="collapsed")
    with col3:
        st.button(f"🩺 {health['counts']['open']} open", key="hb_mtd", on_click=go_health, use_container_width=True)
    st.divider()

    cutoff = to_obj(as_of_date)
    df_mtd = df_active[df_active["DateObj"] <= cutoff].copy()
    run_mtd = reports.running(df_mtd)
    tot_prod, tot_cap = df_mtd["Total Prod Ton"].sum(), df_mtd["Weighted Cap Ton"].sum()
    tot_good, tot_cap_pcs = df_mtd["Total Good"].sum(), df_mtd["Weighted Cap Pcs"].sum()
    cum_mc_days = run_mtd.groupby("Date")["Machine"].nunique().sum() if not run_mtd.empty else 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Cumulative Tonnage", f"{tot_prod:.2f} T", f"Cap: {tot_cap:.2f} T")
    c2.metric("Cumulative Pieces", f"{int(tot_good):,} Pcs", f"Cap: {int(tot_cap_pcs):,} Pcs")
    c3.metric("Achievement Rate", f"{(tot_prod / tot_cap * 100) if tot_cap > 0 else 0:.2f}%")
    c4.metric("Cumulative MC-Days", f"{int(cum_mc_days)} MC-Days", f"Runtime: {df_mtd['Total Runtime (Hrs)'].sum():.2f} Hrs")
    st.divider()

    if mtd_mode == "📊 Linewise":
        st.markdown(f"### 📈 Line-Wise Summary (As of {as_of_date})")
        t = reports.add_total_row(reports.compute_line_summary_mtd(df_mtd), "Line Group",
                                  ["Running MC Qty", "Runtime (Hrs)", "Cap (Pcs)", "Prod (Pcs)", "Cap (Ton)", "Prod (Ton)"], [])
        render_table(t, "mtd_line", "📥 Export As-Of Line Summary (.xlsx)", "AsOf_Line_Summary.xlsx")

    elif mtd_mode == "📏 Sizewise":
        st.markdown(f"### 📏 Machine Size Summary (As of {as_of_date})")
        t = reports.add_size_total_row(reports.compute_size_summary(df_mtd, mode="as_of"))
        render_table(t, "mtd_size", "📥 Export As-Of Size Summary (.xlsx)", "AsOf_Size_Summary.xlsx")

    elif mtd_mode == "📦 Job-Order Wise":
        st.markdown(f"### 📦 Master Order Completion Summary (As of {as_of_date})")
        st.caption("One row per order + item + color. Due balance is taken from the item's LAST available run date.")
        df_job = reports.build_job_mtd(df_mtd)
        if df_job.empty:
            st.info("No active or completed job orders logged up to the selected cutoff date.")
        else:
            n_note = int((df_job["Ledger Note"] != "").sum())
            if n_note:
                st.caption(f"ℹ️ {n_note} item(s) have several ledger lines with different due balances on their last date - the last entry is used (see 'Ledger Note' column).")
            sum_cols = ["Order Qty", "Due Production", "As of Production", "Total Prod Ton", "Total Runtime (Hrs)", "Last Day Cap (Pcs)", "Last Day Output (Pcs)"]
            tab_a, tab_d = st.tabs([f"🔄 Active Orders ({int((~df_job['Is Completed']).sum())})", f"✅ Completed Orders ({int(df_job['Is Completed'].sum())})"])
            for tab, done, label, skey in [(tab_a, False, "Active", "mtd_job_active"), (tab_d, True, "Completed", "mtd_job_done")]:
                with tab:
                    top1, top2 = st.columns([1.2, 2.5])
                    sub = df_job[df_job["Is Completed"] == done].copy()
                    with top2:
                        term = st.text_input(f"Search {label} Orders", "", placeholder="🔍 Search Job Order or Item Name...", label_visibility="collapsed", key=f"search_{skey}")
                    sub = search_filter(sub, term)
                    if sub.empty:
                        st.info(f"No {label.lower()} job orders for this date/search.")
                        continue
                    t = reports.add_total_row(sub, "Order Name", sum_cols, [])
                    render_table(t, skey, f"📥 Export {label} MTD Job Summary (.xlsx)", f"{label}_MTD_Job_Summary.xlsx", selector_slot=top1)

# ============================================
# MODULE: JOB ORDER ANALYSIS
# ============================================
elif nav_choice == "📦 Job Order Analysis":
    render_banner("job")
    st.markdown("### 📦 Job Order Lifecycle & Full Period Analysis")
    st.caption("Inspect order demand completion milestones, item-wise daily machine allocations, and cumulative outputs.")
    st.divider()

    orders = sorted({str(o).strip() for o in df_curr["Order Name"].dropna().unique() if str(o).strip()})
    if not orders:
        st.info("No Job Orders found in the active dataset.")
        st.stop()

    cs1, cs2 = st.columns([2.5, 1.5])
    with cs1:
        sel_order = st.selectbox("🔍 **Search & Select Job Order:**", orders, key="sel_job_analysis_order")
    df_ord = df_curr[df_curr["Order Name"] == sel_order].copy()
    with cs2:
        st.markdown("<div style='margin-top: 1.6rem;'></div>", unsafe_allow_html=True)
        st.markdown(f"**Customer:** `{df_ord['Customer'].iloc[0]}` &nbsp;|&nbsp; **Acc Code:** `{df_ord['Acc Code'].iloc[0]}`")

    items = reports.build_order_items(df_ord, sel_order)
    tot_dem, tot_prod = items["Demand Qty"].sum(), items["Total Produced (Pcs)"].sum()
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Total Order Demand", f"{int(tot_dem):,} Pcs")
    k2.metric("Produced to Date", f"{int(tot_prod):,} Pcs", f"{items['Total Produced (Ton)'].sum():.2f} Tons")
    k3.metric("Remaining Due Balance", f"{int(items['Remaining Due'].sum()):,} Pcs")
    k4.metric("Order Fulfillment", f"{(tot_prod / tot_dem * 100) if tot_dem > 0 else 0:.2f}%", "Overall Progress")

    st.markdown("#### 📋 Items Under This Job Order")
    if (items["Ledger Note"] != "").any():
        st.caption("ℹ️ Some items have several ledger lines with different due balances on their last date - the last entry is used (see 'Ledger Note').")
    default_cols = ["Job Order", "Acc Code", "Item Name", "Color", "Demand Qty", "Total Produced (Pcs)", "Remaining Due", "Fulfillment %", "Status"]
    t = reports.add_total_row(items, "Item Name", ["Demand Qty", "Total Produced (Pcs)", "Remaining Due", "Total Produced (Ton)", "Total Runtime (Hrs)"], [])
    render_table(t, "job_analysis_items", f"📥 Export {sel_order} Item Summary (.xlsx)", f"JobOrder_{sel_order}_Items.xlsx", default_cols=default_cols)

    st.divider()
    st.markdown("#### 🔬 Item & Color Daily Run Lifecycle & Machine Allocations")
    
    items["Display Label"] = items["Item Name"] + " [" + items["Color"] + "]"
    sel_item_label = st.selectbox("Select Item & Color to Inspect Daily Production Timeline:", items["Display Label"].tolist(), key="sel_job_item_inspect")
    
    meta = items[items["Display Label"] == sel_item_label].iloc[0]
    sel_item = meta["Item Name"]
    sel_color = meta["Color"]
    
    m1, m2, m3, m4 = st.columns(4)
    m1.caption(f"**Item Demand:** {int(meta['Demand Qty']):,} Pcs")
    m2.caption(f"**Unit Weight:** {meta['Unit Wt (kg)']:.4f} kg")
    m3.caption(f"**Max Cavity / Latest CT:** {meta['Cavity']:g} Cav / {meta['CT']:g} s")
    m4.caption(f"**Status:** {meta['Status']}")

    tl = reports.build_item_timeline(df_ord[(df_ord["Item Name"] == sel_item) & (df_ord["Color"] == sel_color)], meta["Demand Qty"])
    if tl.empty:
        st.info("No active production runs found for this item and color.")
    else:
        tl_tot = reports.add_total_row(tl, "Date", ["Shift A Good (Pcs)", "Shift B Good (Pcs)", "Day Output (Pcs)", "Rejections (Pcs)", "Day Output (Ton)", "Runtime (Hrs)"], [])
        clean = reports.clean_and_format_dataframe(tl_tot)
        st.dataframe(clean, use_container_width=True, hide_index=True)
        st.download_button(f"📥 Export {sel_order} - {sel_item} [{sel_color}] Timeline (.xlsx)", xl(clean), f"JobOrder_{sel_order}_{sel_item}_{sel_color}_Timeline.xlsx", XLSX_MIME)

# ============================================
# MODULE: SHIFTWISE
# ============================================
elif nav_choice == "🌗 Shiftwise Data":
    render_banner("shift")
    shift_mode = st.radio("Shiftwise Mode:", ["📅 Daily Shiftwise", "📊 As-Of Cumulative Shiftwise"], horizontal=True)
    a_ton, a_good, a_rej = df_active["Shift A Prod Ton"].sum(), df_active["Shift A Good"].sum(), df_active["Shift A Rej"].sum()
    b_ton, b_good, b_rej = df_active["Shift B Prod Ton"].sum(), df_active["Shift B Good"].sum(), df_active["Shift B Rej"].sum()
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("#### ☀️ Shift A (Day Shift)")
        st.metric("Day Shift Tonnage", f"{a_ton:.2f} T")
        st.metric("Day Shift Output", f"{int(a_good):,} Pcs", f"Rejections: {int(a_rej):,}")
    with c2:
        st.markdown("#### 🌙 Shift B (Night Shift)")
        st.metric("Night Shift Tonnage", f"{b_ton:.2f} T")
        st.metric("Night Shift Output", f"{int(b_good):,} Pcs", f"Rejections: {int(b_rej):,}")
    st.divider()

    sh = df_active.groupby("Date")[["Shift A Good", "Shift B Good", "Shift A Prod Ton", "Shift B Prod Ton"]].sum().reset_index()
    sh["_k"] = sh["Date"].map(to_obj)
    sh = sh.sort_values("_k").drop(columns="_k").reset_index(drop=True)

    if shift_mode == "📅 Daily Shiftwise":
        t = reports.add_total_row(sh, "Date", ["Shift A Good", "Shift B Good", "Shift A Prod Ton", "Shift B Prod Ton"], [])
        render_table(t, "daily_shift", "📥 Export Daily Shiftwise Log (.xlsx)", "Daily_Shiftwise_Log.xlsx")
    else:
        fig = px.bar(sh, x="Date", y=["Shift A Prod Ton", "Shift B Prod Ton"], title="Daily Shift Comparison (Tonnage)",
                     barmode="group", color_discrete_sequence=["#f59e0b", "#0f172a"])
        st.plotly_chart(fig, use_container_width=True)

# ============================================
# MODULE: MONTHLY MASTER EXPORT
# ============================================
elif nav_choice == "📑 Monthly Master Export":
    render_banner("master")
    st.markdown("### 📑 Monthly Master Production Ledger (`Details.xlsx`)")
    st.caption("Every production row of every day (1 to N) from the selected floor(s): standard machine SL, chess family molds merged, "
               "no blank rows, full-precision values and real date cells.")
    st.divider()

    master = exporter.master_frame(df_curr)
    c1, c2, c3 = st.columns(3)
    c1.metric("Active Runs Logged", f"{len(master):,} Records")
    c2.metric("Total Monthly Good", f"{int(master['T-Good'].sum()):,} Pcs")
    c3.metric("Total Monthly Tonnage", f"{master['Total Prod Ton'].sum():.2f} Tons")
    st.divider()

    view = master[exporter.MASTER_COLUMNS].copy()
    st.dataframe(view, use_container_width=True, hide_index=True, column_config={
        "Unit Wt": st.column_config.NumberColumn(format="%.5f"),
        "CT": st.column_config.NumberColumn(format="%.2f"),
        "STD Cap/Shift": st.column_config.NumberColumn(format="%.0f"),
        "A Total": st.column_config.NumberColumn(format="%.0f"),
        "A Good": st.column_config.NumberColumn(format="%.0f"),
        "B Total": st.column_config.NumberColumn(format="%.0f"),
        "B Good": st.column_config.NumberColumn(format="%.0f"),
        "T-Good": st.column_config.NumberColumn(format="%.0f"),
        "T-Bad": st.column_config.NumberColumn(format="%.0f"),
    })
    if health["counts"]["open"]:
        st.warning(f"This file will carry a 'Data Quality' sheet listing {health['counts']['errors']} open error(s) and {health['counts']['warnings']} open warning(s).")
    xbytes, nrows = exporter.build_master_workbook(df_curr, QUALITY)
    st.download_button("📥 Export Monthly Master Production (Details.xlsx)", xbytes, "Monthly_Master_Production_Details.xlsx", XLSX_MIME, use_container_width=True)

# ============================================
# MODULE: DATA HEALTH
# ============================================
elif nav_choice == HEALTH_NAV:
    st.markdown("### 🩺 Data Health & Corrections")
    st.caption("Everything the console found while reading your files. Nothing is hidden: if a day, row or number could not be used, it is listed here.")
    c = health["counts"]
    cov, rc = health["coverage"], health["recon"]
    ok_days = int(rc["Check"].eq("OK").sum()) if not rc.empty else 0
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("🔴 Open errors", c["errors"])
    k2.metric("🟡 Open warnings", c["warnings"])
    k3.metric("✅ Reviewed", c["reviewed"])
    k4.metric("Days tying to sheet", f"{ok_days} / {len(rc)}")
    st.divider()

    t_cov, t_rec, t_fix, t_notes, t_file = st.tabs(["🗓 Coverage", "⚖️ Reconciliation", "🛠 Fix Rows", "📋 Sheets & Notes", "💾 Corrections File"])

    # ---- coverage calendar
    with t_cov:
        st.markdown("##### Expected: every day from 1 to the latest date, on each uploaded floor")
        rows = []
        for d in range(1, period["last_day"] + 1):
            ds = datetime(period["year"], period["month"], d).strftime("%d-%m-%Y")
            row = {"Date": ds}
            for fl in sorted(scans):
                m = cov[(cov["Floor"] == fl) & (cov["Date"] == ds)]
                if m.empty:
                    row[f"{fl} Tab"], row[f"{fl} Status"], row[f"{fl} Good Pcs"] = "-", "❌ MISSING", 0
                else:
                    r0 = m.iloc[0]
                    stt = r0["Status"]
                    row[f"{fl} Tab"] = r0["Sheet Used"]
                    row[f"{fl} Status"] = "✅ OK" if stt == "OK" else ("🟡 " + stt if stt.startswith("OK") else "❌ " + stt.upper())
                    row[f"{fl} Good Pcs"] = float(r0["Good Pcs"])
            rows.append(row)
        cov_tbl = pd.DataFrame(rows)
        st.dataframe(cov_tbl, hide_index=True, use_container_width=True)
        for fl in sorted(scans):
            good = cov[(cov["Floor"] == fl) & (cov["Good Pcs"] > 0)]["Good Pcs"]
            if len(good) >= 5:
                med = good.median()
                low = cov[(cov["Floor"] == fl) & (cov["Status"].str.startswith("OK")) & (cov["Good Pcs"] < 0.5 * med)]
                if not low.empty:
                    items_txt = ", ".join(f"{d} ({int(g):,} pcs)" for d, g in zip(low["Date"], low["Good Pcs"]))
                    st.caption(f"🔵 {fl}: low-output day(s) (under half the monthly median - information only): {items_txt}")

    # ---- reconciliation
    with t_rec:
        st.markdown("##### Pieces in the Excel tab vs pieces that reached the report")
        if rc.empty:
            st.info("No days were read.")
        else:
            bad = rc[rc["Check"] != "OK"]
            if bad.empty:
                st.success(f"✅ All {len(rc)} floor-days tie exactly: every good piece in the sheets is in the report.")
            else:
                st.error(f"❌ {len(bad)} floor-day(s) do NOT tie - see the MISMATCH rows.")
            show = rc.copy()
            show["Check"] = show["Check"].map({"OK": "✅ OK", "MISMATCH": "❌ MISMATCH"})
            st.dataframe(show[["Floor", "Date", "Sheet", "Sheet Good", "Parsed Good", "Lost in parsing", "Excluded by you", "Edited by you", "Final Good", "Check"]],
                         hide_index=True, use_container_width=True)
            st.caption("Final = Parsed − Excluded + Edited. 'Lost in parsing' must always be 0.")

    # ---- fix rows (includes Smart Unresolved Machine Suggestions)
    with t_fix:
        ri = health["row_issues"]
        
        st.markdown("##### 🛠️ Unresolved Machine Audit & Smart Suggestions")
        st.caption("Rows with invalid or mistyped machine names appear in 'Line Other'. Review the system suggestions below and choose to Accept or Exclude.")

        unresolved_issues = ri[(ri["Category"] == "Machine name") & (ri["Status"] == "Open")]
        if unresolved_issues.empty:
            st.success("🟢 No unresolved machine names found! 'Line Other' is clear.")
        else:
            for _, r in unresolved_issues.iterrows():
                key = r["Key"]
                row_matches = df_all[df_all["Row Key"] == key] if 'df_all' in globals() else pd.DataFrame()
                if row_matches.empty:
                    continue
                row_data = row_matches.iloc[0]
                
                col_a, col_b, col_c = st.columns([2, 3, 2])
                with col_a:
                    st.markdown(f"**Date:** {r['Date']}\n\n**Excel Row:** {r['Src Row']}\n\n**Typed Name:** `{row_data['MC Used']}`")
                with col_b:
                    sugg_mc, conf, reason = ingest.suggest_machine_fix(df_all, key)
                    st.markdown(f"**Order / Item:** {r['Order']} / {r['Item']}\n\n**Pieces:** {int(row_data['Total Good']):,} Pcs\n\n💡 **Suggestion:** `{sugg_mc}` (*{conf} Confidence*)\n*{reason}*")
                with col_c:
                    st.markdown("<div style='margin-top: 1rem;'></div>", unsafe_allow_html=True)
                    if st.button(f"✅ Accept `{sugg_mc}`", key=f"acc_{key}", use_container_width=True):
                        corr = st.session_state["corrections"]
                        ov = dict(corr["rows"].get(key, {"sig": f"{r['Order']}|{r['Item']}"}))
                        ov["mc_sl"] = sugg_mc
                        corr["rows"][key] = ov
                        st.session_state["corrections"] = corr
                        st.success(f"Accepted {sugg_mc}!")
                        st.rerun()
                    if st.button("🗑️ Exclude Row", key=f"exc_{key}", use_container_width=True):
                        corr = st.session_state["corrections"]
                        ov = dict(corr["rows"].get(key, {"sig": f"{r['Order']}|{r['Item']}"}))
                        ov["exclude"] = True
                        corr["rows"][key] = ov
                        st.session_state["corrections"] = corr.copy()
                        st.warning("Row excluded.")
                        st.rerun()
                st.divider()

        st.markdown("##### General Row Issue Edits")
        f1, f2, f3, f4 = st.columns([1.2, 1.2, 1.4, 1.2])
        with f1:
            show_status = st.selectbox("Show", ["Open", "Reviewed", "All"], key="hf_status")
        with f2:
            show_minor = st.toggle("Include minor notes", value=False, key="hf_minor", help="Runtime between 12 and 13 h etc.")
        cats = sorted(ri["Category"].unique()) if not ri.empty else []
        with f3:
            sel_cats = st.multiselect("Category", cats, default=cats, key="hf_cats")
        with f4:
            sel_floor = st.selectbox("Floor", ["All"] + sorted(scans), key="hf_floor")

        view = ri.copy()
        if not view.empty:
            sevs = ["Error", "Warning"] + (["Info"] if show_minor else [])
            view = view[view["Severity"].isin(sevs) & view["Category"].isin(sel_cats)]
            if show_status != "All":
                view = view[view["Status"] == show_status]
            if sel_floor != "All":
                view = view[view["Floor"] == sel_floor]

        if view.empty:
            st.success("Nothing to fix in this view.")
        else:
            view = view.assign(_t=view["Category"] + ": " + view["Detail"])
            rank = {"Error": 0, "Warning": 1, "Info": 2}
            grp = view.groupby("Key", sort=False)
            base = grp.agg(Sev=("Severity", lambda s: min(s, key=lambda x: rank[x])), Floor=("Floor", "first"), Date=("Date", "first"),
                           Row=("Src Row", "first"), Order=("Order", "first"), Item=("Item", "first"),
                           Issues=("_t", lambda s: "  •  ".join(s)), Status=("Status", "first")).reset_index().rename(columns={"Key": "Row Key"})
            cur = df_all.set_index("Row Key")
            def _cur(col, key):
                return cur.at[key, col] if key in cur.index else None
            base["Machine SL"] = [_cur("MC Used", k) for k in base["Row Key"]]
            base["CT"] = [float(_cur("CT", k)) for k in base["Row Key"]]
            base["Cavity"] = [float(_cur("Cavity", k)) for k in base["Row Key"]]
            base["Unit Wt"] = [float(_cur("Unit Wt", k)) for k in base["Row Key"]]
            base["A Good"] = [float(_cur("A Good", k)) for k in base["Row Key"]]
            base["B Good"] = [float(_cur("B Good", k)) for k in base["Row Key"]]
            base["A Rej"] = [float(_cur("Shift A Rej", k)) for k in base["Row Key"]]
            base["B Rej"] = [float(_cur("Shift B Rej", k)) for k in base["Row Key"]]
            base["Exclude row"] = False
            base["Reviewed"] = base["Status"] == "Reviewed"
            base["_r"] = base["Sev"].map(rank)
            base["_d"] = base["Date"].map(to_obj)
            base = base.sort_values(["_r", "_d", "Floor", "Row"], kind="stable").drop(columns=["_r", "_d"]).reset_index(drop=True)
            base["Sev"] = base["Sev"].map({"Error": "🔴", "Warning": "🟡", "Info": "🔵"})

            st.caption(f"{len(base)} row(s). Edit the white columns, tick **Reviewed** if the figure is correct as entered, or **Exclude row** to leave it out of all totals. Then press Save.")
            edited = st.data_editor(
                base, hide_index=True, use_container_width=True, num_rows="fixed", key="fix_editor",
                disabled=["Sev", "Floor", "Date", "Row", "Order", "Item", "Issues", "Status"],
                column_config={
                    "Row Key": None, "Status": None,
                    "Sev": st.column_config.TextColumn("", width="small"),
                    "Row": st.column_config.NumberColumn("Excel row", format="%d"),
                    "Issues": st.column_config.TextColumn(width="large"),
                    "Unit Wt": st.column_config.NumberColumn(format="%.5f"),
                })
            if st.button("💾 Save changes", type="primary", key="fix_save"):
                corr = st.session_state["corrections"]
                sig_by_key = view.groupby("Key")["Row Signature"].first().to_dict()
                changed = 0
                for o, n in zip(base.to_dict("records"), edited.to_dict("records")):
                    key = o["Row Key"]
                    ov = dict(corr["rows"].get(key, {"sig": f"{o['Order']}|{o['Item']}"}))
                    touched = False
                    for col, fld in [("CT", "ct"), ("Cavity", "cavity"), ("Unit Wt", "unit_wt"), ("A Good", "a_good"),
                                     ("B Good", "b_good"), ("A Rej", "a_rej"), ("B Rej", "b_rej")]:
                        nv = n[col]
                        nv = 0.0 if nv is None or pd.isna(nv) else float(nv)
                        if abs(nv - float(o[col])) > 1e-9:
                            ov[fld] = nv
                            touched = True
                    if str(n["Machine SL"] or "").strip() != str(o["Machine SL"] or "").strip():
                        ov["mc_sl"] = str(n["Machine SL"]).strip()
                        touched = True
                    if n["Exclude row"] and not o["Exclude row"]:
                        ov["exclude"] = True
                        touched = True
                    if touched:
                        corr["rows"][key] = ov
                        changed += 1
                    if bool(n["Reviewed"]) != bool(o["Reviewed"]):
                        if n["Reviewed"]:
                            corr["reviewed"][key] = sig_by_key.get(key, "")
                        else:
                            corr["reviewed"].pop(key, None)
                        changed += 1
                st.session_state["corrections"] = corr
                st.success(f"Saved {changed} change(s). Recalculating...")
                st.rerun()

        excl = {k: v for k, v in st.session_state["corrections"]["rows"].items() if v.get("exclude")}
        if excl:
            st.divider()
            st.markdown("##### Rows you excluded")
            ex_df = pd.DataFrame([{"Row Key": k, "Floor": k.split("|")[0], "Date": k.split("|")[1], "Excel row": k.split("|")[2],
                                   "Order | Item": v.get("sig", ""), "Restore": False} for k, v in excl.items()])
            ed = st.data_editor(ex_df, hide_index=True, use_container_width=True, num_rows="fixed", key="restore_editor",
                                disabled=["Floor", "Date", "Excel row", "Order | Item"], column_config={"Row Key": None})
            if st.button("↩️ Restore ticked rows", key="restore_btn"):
                for r in ed.to_dict("records"):
                    if r["Restore"]:
                        st.session_state["corrections"]["rows"][r["Row Key"]].pop("exclude", None)
                st.rerun()

    # ---- sheets & notes
    with t_notes:
        fi = health["file_issues"]
        st.markdown("##### Day / sheet level findings")
        if fi.empty:
            st.success("None.")
        else:
            st.dataframe(fi.assign(Severity=fi["Severity"].map({"Error": "🔴 Error", "Warning": "🟡 Warning", "Info": "🔵 Info"})),
                         hide_index=True, use_container_width=True)
        st.markdown("##### Which tab was used for each day")
        st.dataframe(health["sheets"], hide_index=True, use_container_width=True)
        st.markdown("##### Machine names that were auto-matched to the master list")
        if health["matches"].empty:
            st.caption("None - every machine name already matched exactly.")
        else:
            st.dataframe(health["matches"], hide_index=True, use_container_width=True)

    # ---- corrections file
    with t_file:
        st.markdown("##### Save / load your corrections")
        st.caption("Corrections live only in this session. Download the file to keep them, and load it again after re-uploading the Excel files.")
        payload = json.dumps(st.session_state["corrections"], indent=2)
        st.download_button("📥 Download corrections (.json)", payload, f"corrections_{period['year']}-{period['month']:02d}.json", "application/json")
        up = st.file_uploader("Load a corrections file (.json)", type=["json"], key="corr_upload")
        if up is not None and st.button("Load corrections", key="corr_load"):
            try:
                data = json.loads(up.getvalue().decode("utf-8"))
                cur = st.session_state["corrections"]
                cur["rows"].update(data.get("rows", {}))
                cur["reviewed"].update(data.get("reviewed", {}))
                st.rerun()
            except Exception as e:
                st.error(f"Could not read that file: {e}")
        if st.button("🗑 Reset ALL corrections and reviews", key="corr_reset"):
            st.session_state["corrections"] = {"rows": {}, "reviewed": {}}
            st.rerun()
