# ============================================
# PLASTIC-3 OPERATIONS CONSOLE  (FF + GF)
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
from config import EXCEL_SIZES  # noqa: F401

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


@st.cache_data(show_spinner="Reading and validating production tabs...")
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

    with st.popover("👁 Columns"):
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
    
    # Auto-versioned timestamped download filename
    date_tag = datetime.now().strftime("%Y%m%d_%H%M")
    versioned_dl_name = f"Plastic3_{floor_choice}_{date_tag}_{dl_name}"
    
    st.download_button(dl_label, xl(clean), versioned_dl_name, XLSX_MIME)
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
        st.markdown('<div class="setup-card ff"><h3>🏢 First Floor (FF)</h3><p style="color:#64748b !important;">Select FF Excel file</p></div>', unsafe_allow_html=True)
        ff_file = st.file_uploader("Upload First Floor File (.xlsx)", type=["xlsx", "xls"], key="init_ff")
    with col2:
        st.markdown('<div class="setup-card gf"><h3>🏬 Ground Floor (GF)</h3><p style="color:#64748b !important;">Select GF Excel file</p></div>', unsafe_allow_html=True)
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
    st.error("❌ **No dated daily production tab was found**.")
    change_files_button("fatal")
    st.stop()

results = {}
for fl in scans:
    try:
        results[fl] = cached_parse(floor_bytes[fl], fl, period["year"], period["month"], period["last_day"], corr_rows_only())
    except Exception as e:
        st.error(f"❌ **{fl} file failed while reading:** {e}.")

if not results:
    change_files_button("fatal2")
    st.stop()

health = ingest.build_health(results, period, corr_full())
frames = [r["records"] for r in results.values() if not r["records"].empty]
if not frames:
    st.error("❌ **No production rows could be read from the uploaded file(s).**")
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
    hide_zero_runs = st.toggle("🚫 Hide Non-Running Machines", value=True)
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
        st.error(f"❌ **Missing or unreadable day(s): {lst}.**")
    if c["errors"] or c["warnings"]:
        left, right = st.columns([5, 1.4])
        with left:
            box = st.error if c["errors"] else st.warning
            box(f"🩺 {c['errors']} error(s) and {c['warnings']} warning(s) are still open.")
        with right:
            st.button("Open Data Health", key=f"bn_{module_key}", on_click=go_health, use_container_width=True)
    else:
        st.success("🟢 No open data issues - every day ties to source sheets.")


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
        daily_mode = st.radio("Daily View Mode:", ["📊 Linewise", "🏭 MC Wise", "📏 Sizewise", "📦 Job-Order Wise", "🗺️️ Plant Matrix"], horizontal=True, label_visibility="collapsed")
    with col_nav2:
        selected_date = st.selectbox("Operational Date", all_dates, index=len(all_dates) - 1, label_visibility="collapsed")
    with col_nav3:
        st.button(f"🩺 {health['counts']['open']} open", key="hb_daily", on_click=go_health, use_container_width=True)
    st.divider()

    df_daily_raw = df_active[df_active["Date"] == selected_date].copy()
    if df_daily_raw.empty:
        st.info(f"No machine produced on {selected_date} in this view.")
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

    if daily_mode == "🗺️ Plant Matrix":
        st.markdown(f"### 🗺️ Plant Floor Machine Status Matrix ({selected_date})")
        df_matrix = df_daily.copy()
        df_matrix["Status"] = df_matrix["Total Good"].apply(lambda g: "🟢 Active (>0 Pcs)" if g > 0 else "⚪ Idle")
        st.dataframe(df_matrix[["Floor", "Machine", "MC Size", "Order Name", "Item Name", "Total Good", "Total Runtime (Hrs)", "Status"]], use_container_width=True, hide_index=True)
    elif daily_mode == "📊 Linewise":
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
    elif daily_mode == "📏 Sizewise":
        st.markdown("### 📏 Machine Size Summary")
        t = reports.add_size_total_row(reports.compute_size_summary(df_daily_raw, mode="daily"))
        render_table(t, "daily_size", "📥 Export Daily Size Summary (.xlsx)", "Daily_Size_Summary.xlsx")
    elif daily_mode == "📦 Job-Order Wise":
        st.markdown("### 📦 Active Orders Run On Selected Date")
        col_top1, col_top2 = st.columns([1.2, 2.5])
        job_day = reports.build_job_daily(df_daily_raw)
        with col_top2:
            term = st.text_input("Search Daily Orders", "", placeholder="🔍 Search...", label_visibility="collapsed", key="search_daily_job")
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
        df_job = reports.build_job_mtd(df_mtd)
        if df_job.empty:
            st.info("No active or completed job orders logged.")
        else:
            sum_cols = ["Order Qty", "Due Production", "As of Production", "Total Prod Ton", "Total Runtime (Hrs)"]
            tab_a, tab_d = st.tabs([f"🔄 Active Orders ({int((~df_job['Is Completed']).sum())})", f"✅ Completed Orders ({int(df_job['Is Completed'].sum())})"])
            for tab, done, label, skey in [(tab_a, False, "Active", "mtd_job_active"), (tab_d, True, "Completed", "mtd_job_done")]:
                with tab:
                    top1, top2 = st.columns([1.2, 2.5])
                    sub = df_job[df_job["Is Completed"] == done].copy()
                    with top2:
                        term = st.text_input(f"Search {label} Orders", "", placeholder="🔍 Search...", label_visibility="collapsed", key=f"search_{skey}")
                    sub = search_filter(sub, term)
                    if sub.empty:
                        st.info(f"No {label.lower()} job orders.")
                        continue
                    t = reports.add_total_row(sub, "Order Name", sum_cols, [])
                    render_table(t, skey, f"📥 Export {label} MTD Job Summary (.xlsx)", f"{label}_MTD_Job_Summary.xlsx", selector_slot=top1)

# ============================================
# MODULE: JOB ORDER ANALYSIS
# ============================================
elif nav_choice == "📦 Job Order Analysis":
    render_banner("job")
    st.markdown("### 📦 Job Order Lifecycle & Full Period Analysis")
    st.divider()

    orders = sorted({str(o).strip() for o in df_curr["Order Name"].dropna().unique() if str(o).strip()})
    if not orders:
        st.info("No Job Orders found.")
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
    default_cols = ["Job Order", "Acc Code", "Item Name", "Color", "Demand Qty", "Total Produced (Pcs)", "Remaining Due", "Fulfillment %", "Status"]
    t = reports.add_total_row(items, "Item Name", ["Demand Qty", "Total Produced (Pcs)", "Remaining Due", "Total Produced (Ton)", "Total Runtime (Hrs)"], [])
    render_table(t, "job_analysis_items", f"📥 Export {sel_order} Item Summary (.xlsx)", f"JobOrder_{sel_order}_Items.xlsx", default_cols=default_cols)

    st.divider()
    st.markdown("#### 🔬 Item & Color Daily Run Lifecycle & Machine Allocations")
    items["Display Label"] = items["Item Name"] + " [" + items["Color"] + "]"
    sel_item_label = st.selectbox("Select Item & Color to Inspect Daily Production Timeline:", items["Display Label"].tolist(), key="sel_job_item_inspect")
    meta = items[items["Display Label"] == sel_item_label].iloc[0]
    
    tl = reports.build_item_timeline(df_ord[(df_ord["Item Name"] == meta["Item Name"]) & (df_ord["Color"] == meta["Color"])], meta["Demand Qty"])
    if not tl.empty:
        tl_tot = reports.add_total_row(tl, "Date", ["Shift A Good (Pcs)", "Shift B Good (Pcs)", "Day Output (Pcs)", "Rejections (Pcs)", "Day Output (Ton)", "Runtime (Hrs)"], [])
        render_table(tl_tot, "job_timeline", f"📥 Export {sel_order} Timeline (.xlsx)", f"JobOrder_{sel_order}_Timeline.xlsx")

# ============================================
# MODULE: SHIFTWISE DATA (WhatsApp Brief)
# ============================================
elif nav_choice == "🌗 Shiftwise Data":
    render_banner("shift")
    st.markdown("### 📱 Shift-Handover WhatsApp Brief Generator")
    st.caption("Copy-paste this formatted brief directly into the plant supervisor WhatsApp group.")
    
    sel_shift_date = st.selectbox("Select Date for WhatsApp Brief:", sort_dates(df_curr["Date"].unique()), key="brief_date")
    df_brief = df_curr[df_curr["Date"] == sel_shift_date]
    
    s_a_ton = df_brief["Shift A Prod Ton"].sum()
    s_b_ton = df_brief["Shift B Prod Ton"].sum()
    s_a_pcs = df_brief["Shift A Good"].sum()
    s_b_pcs = df_brief["Shift B Good"].sum()
    tot_rej = df_brief["Total Rejections"].sum()
    running_mcs = df_brief[df_brief["Total Good"] > 0]["Machine"].nunique()

    whatsapp_text = f"""🏭 *PLASTIC-3 SHIFT PRODUCTION BRIEF*
📅 *Date:* {sel_shift_date}
🏢 *Floor:* {floor_choice}
⚙️ *Active Machines:* {running_mcs} MCs

☀️ *Shift A (Day):*
• Output: {int(s_a_pcs):,} Pcs ({s_a_ton:.2f} Tons)

🌙 *Shift B (Night):*
• Output: {int(s_b_pcs):,} Pcs ({s_b_ton:.2f} Tons)

📊 *Summary:*
• Total Production: {(s_a_ton + s_b_ton):.2f} Tons
• Total Rejections: {int(tot_rej):,} Pcs

_Generated automatically via Plastic-3 Operations Console_"""

    st.text_area("WhatsApp Message Preview (Select & Copy):", whatsapp_text, height=220)

# ============================================
# MODULE: MONTHLY MASTER EXPORT
# ============================================
elif nav_choice == "📑 Monthly Master Export":
    render_banner("master")
    st.markdown("### 📑 Monthly Master Production Ledger (`Details.xlsx`)")
    st.divider()

    master = exporter.master_frame(df_curr)
    c1, c2, c3 = st.columns(3)
    c1.metric("Active Runs Logged", f"{len(master):,} Records")
    c2.metric("Total Monthly Good", f"{int(master['T-Good'].sum()):,} Pcs")
    c3.metric("Total Monthly Tonnage", f"{master['Total Prod Ton'].sum():.2f} Tons")
    st.divider()

    xbytes, nrows = exporter.build_master_workbook(df_curr, QUALITY)
    date_tag = datetime.now().strftime("%Y%m%d_%H%M")
    master_dl_name = f"Plastic3_{floor_choice}_{date_tag}_Monthly_Master_Details.xlsx"
    st.download_button("📥 Export Monthly Master Production (Details.xlsx)", xbytes, master_dl_name, XLSX_MIME, use_container_width=True)

# ============================================
# MODULE: DATA HEALTH (Batch Suggestions + Fix Rows)
# ============================================
elif nav_choice == HEALTH_NAV:
    st.markdown("### 🩺 Data Health & Corrections")
    c = health["counts"]
    cov, rc = health["coverage"], health["recon"]
    ok_days = int(rc["Check"].eq("OK").sum()) if not rc.empty else 0
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("🔴 Open errors", c["errors"])
    k2.metric("🟡 Open warnings", c["warnings"])
    k3.metric("✅ Reviewed", c["reviewed"])
    k4.metric("Days tying to sheet", f"{ok_days} / {len(rc)}")
    st.divider()

    ri = health["row_issues"]
    unresolved = ri[(ri["Category"] == "Machine name") & (ri["Status"] == "Open")]
    
    if not unresolved.empty:
        st.markdown("##### ⚡ Batch Machine Suggestions")
        high_conf = []
        for _, r in unresolved.iterrows():
            _, conf, _ = ingest.suggest_machine_fix(df_all, r["Key"])
            if conf == "High":
                high_conf.append((r["Key"], r["Order"], r["Item"]))
        if high_conf:
            if st.button(f"⚡ Accept All High-Confidence Suggestions ({len(high_conf)} items)", type="primary"):
                corr = st.session_state["corrections"]
                for key, order, item in high_conf:
                    sugg_mc, _, _ = ingest.suggest_machine_fix(df_all, key)
                    corr["rows"].setdefault(key, {})["mc_sl"] = sugg_mc
                st.session_state["corrections"] = corr
                st.success(f"Applied {len(high_conf)} suggestions successfully!")
                st.rerun()

    t_cov, t_rec, t_fix, t_notes, t_file = st.tabs(["🗓 Coverage", "⚖️ Reconciliation", "🛠 Fix Rows", "📋 Sheets & Notes", "💾 Corrections File"])

    with t_cov:
        st.markdown("##### Expected: every day from 1 to latest date")
        rows = []
        for d in range(1, period["last_day"] + 1):
            ds = datetime(period["year"], period["month"], d).strftime("%d-%m-%Y")
            row = {"Date": ds}
            for fl in sorted(scans):
                m = cov[(cov["Floor"] == fl) & (cov["Date"] == ds)]
                row[f"{fl} Status"] = m.iloc[0]["Status"] if not m.empty else "Missing"
            rows.append(row)
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

    with t_rec:
        st.markdown("##### Reconciliation: Sheet vs Report")
        if not rc.empty:
            st.dataframe(rc, hide_index=True, use_container_width=True)

    with t_fix:
        st.markdown("##### Unresolved Machine Audit & Smart Suggestions")
        if unresolved.empty:
            st.success("🟢 No unresolved machine names found!")
        else:
            for _, r in unresolved.iterrows():
                key = r["Key"]
                row_matches = df_all[df_all["Row Key"] == key]
                if row_matches.empty:
                    continue
                row_data = row_matches.iloc[0]
                
                col_a, col_b, col_c = st.columns([2, 3, 2])
                with col_a:
                    st.markdown(f"**Date:** {r['Date']}\n\n**Excel Row:** {r['Src Row']}\n\n**Typed:** `{row_data['MC Used']}`")
                with col_b:
                    sugg_mc, conf, reason = ingest.suggest_machine_fix(df_all, key)
                    st.markdown(f"**Order/Item:** {r['Order']} / {r['Item']}\n\n💡 **Suggestion:** `{sugg_mc}` (*{conf}*)\n*{reason}*")
                with col_c:
                    if st.button(f"✅ Accept `{sugg_mc}`", key=f"acc_{key}", use_container_width=True):
                        corr = st.session_state["corrections"]
                        corr["rows"].setdefault(key, {})["mc_sl"] = sugg_mc
                        st.session_state["corrections"] = corr
                        st.rerun()
                    if st.button("🗑️ Exclude Row", key=f"exc_{key}", use_container_width=True):
                        corr = st.session_state["corrections"]
                        corr["rows"].setdefault(key, {})["exclude"] = True
                        st.session_state["corrections"] = corr
                        st.rerun()
                st.divider()

        st.dataframe(ri, use_container_width=True, hide_index=True)

    with t_notes:
        st.markdown("##### Sheet Notes & Audit Logs")
        if not health["sheets"].empty:
            st.dataframe(health["sheets"], hide_index=True, use_container_width=True)

    with t_file:
        st.markdown("##### Corrections File Manager")
        payload = json.dumps(st.session_state["corrections"], indent=2)
        st.download_button("📥 Download corrections (.json)", payload, f"corrections_{period['year']}-{period['month']:02d}.json", "application/json")
