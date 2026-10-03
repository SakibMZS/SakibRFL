"""
reports.py  -  Pure-pandas summary calculations (no Streamlit), so they can be tested on real files.

Consistent definitions used everywhere
  * a machine is "running" on a day when its Total Good > 0
  * CT / Cavity averages in Sub Total rows are runtime-weighted (same as the rows above them)
  * the Sizewise tables always include an 'Other' row if a running machine has no known size,
    so Sizewise totals always tie to Linewise totals
  * an item's overall cavity is the MAX cavity used (a broken cavity that was later fixed
    does not lower the figure); CT is the CT of the latest run
"""
import numpy as np
import pandas as pd

from config import EXCEL_SIZES


def running(df):
    return df[df["Total Good"] > 0]


def _pct(num, den):
    return (num / den * 100.0) if den and den > 0 else 0.0


# ---------------------------------------------------------------------------
# machine / line / size summaries
# ---------------------------------------------------------------------------
def consolidate_daily_machines(df_day):
    """One row per Floor+Machine for the day, with runtime-weighted CT and cavity."""
    records = []
    for (floor_val, mc), group in df_day.groupby(["Floor", "Machine"]):
        orders = group["Order Name"].unique()
        items = group["Item Name"].unique()
        mc_rt = group["Total Runtime (Hrs)"].sum()
        if mc_rt > 0:
            w_ct = (group["CT"] * group["Total Runtime (Hrs)"]).sum() / mc_rt
            w_cav = (group["Cavity"] * group["Total Runtime (Hrs)"]).sum() / mc_rt
        else:
            w_ct, w_cav = group["CT"].mean(), group["Cavity"].mean()
        tot_good = group["Total Good"].sum()
        cap_pcs = group["Weighted Cap Pcs"].sum()
        cap_ton = group["Weighted Cap Ton"].sum()
        prod_ton = group["Total Prod Ton"].sum()
        records.append({
            "Floor": floor_val,
            "Line Group": group["Line Group"].iloc[0],
            "Machine": mc,
            "MC Size": group["MC Size"].iloc[0],
            "Customer": group["Customer"].iloc[0] if group["Customer"].nunique() == 1 else "Mixed",
            "Order Name": orders[0] if len(orders) == 1 else "Mixed",
            "Item Name": items[0] if len(items) == 1 else "Mixed",
            "Is Mixed": len(group) > 1,
            "Entry Count": len(group),
            "Cavity": round(w_cav, 2),
            "CT": round(w_ct, 2),
            "Shift A Good": round(group["Shift A Good"].sum(), 2),
            "Shift B Good": round(group["Shift B Good"].sum(), 2),
            "Total Good": round(tot_good, 2),
            "Total Rejections": round(group["Total Rejections"].sum(), 2),
            "Shift A Runtime": round(group["Shift A Runtime"].sum(), 2),
            "Shift B Runtime": round(group["Shift B Runtime"].sum(), 2),
            "Total Runtime (Hrs)": round(mc_rt, 2),
            "Weighted Cap Pcs": round(cap_pcs, 2),
            "Weighted Cap Ton": round(cap_ton, 2),
            "Total Prod Ton": round(prod_ton, 2),
            "Ach Pcs %": f"{_pct(tot_good, cap_pcs):.2f}%",
            "Ach Ton %": f"{_pct(prod_ton, cap_ton):.2f}%",
        })
    return pd.DataFrame(records)


def _line_rows(df_subset, mtd):
    records = []
    for lg, grp in df_subset.groupby("Line Group"):
        act = running(grp)
        if mtd:
            mc_qty = act.groupby("Date")["Machine"].nunique().sum()
        else:
            mc_qty = act["Machine"].nunique()
        cap_pcs, prod_pcs = act["Weighted Cap Pcs"].sum(), act["Total Good"].sum()
        cap_ton, prod_ton = act["Weighted Cap Ton"].sum(), act["Total Prod Ton"].sum()
        records.append({
            "Line Group": lg,
            "Running MC Qty": int(mc_qty),
            "Runtime (Hrs)": round(act["Total Runtime (Hrs)"].sum(), 2),
            "Cap (Pcs)": round(cap_pcs, 2),
            "Prod (Pcs)": round(prod_pcs, 2),
            "Pcs Ach %": f"{_pct(prod_pcs, cap_pcs):.2f}%",
            "Cap (Ton)": round(cap_ton, 2),
            "Prod (Ton)": round(prod_ton, 2),
            "Ton Ach %": f"{_pct(prod_ton, cap_ton):.2f}%",
        })
    return pd.DataFrame(records)


def compute_line_summary(df_subset):
    return _line_rows(df_subset, mtd=False)


def compute_line_summary_mtd(df_subset):
    return _line_rows(df_subset, mtd=True)


def compute_size_summary(df_subset, mode="daily"):
    """Machine-size summary (Excel 'Sheet2' layout). Adds an 'Other' row if needed."""
    records = []
    sizes = list(EXCEL_SIZES)
    other_active = running(df_subset[~df_subset["MC Size"].isin(EXCEL_SIZES)])
    if not other_active.empty:
        sizes.append("Other")

    for sz in sizes:
        grp = df_subset[df_subset["MC Size"] == sz] if sz != "Other" else df_subset[~df_subset["MC Size"].isin(EXCEL_SIZES)]
        act = running(grp)
        if act.empty:
            records.append({"MC Size": sz, "MC QTY": 0, "CT Average": 0.0, "Run Hour Average": 0.0,
                            "Total Cap (Pcs)": 0.0, "Total Prod (Pcs)": 0.0, "% OF Ach Pcs": "0.00%",
                            "Cap (Ton)": 0.0, "Prod (Ton)": 0.0, "% OF Ach Ton": "0.00%"})
            continue
        rt = act["Total Runtime (Hrs)"].sum()
        mc_qty = act.groupby("Date")["Machine"].nunique().sum() if mode == "as_of" else act["Machine"].nunique()
        avg_ct = (act["CT"] * act["Total Runtime (Hrs)"]).sum() / rt if rt > 0 else act["CT"].mean()
        cap_pcs, prod_pcs = act["Weighted Cap Pcs"].sum(), act["Total Good"].sum()
        cap_ton, prod_ton = act["Weighted Cap Ton"].sum(), act["Total Prod Ton"].sum()
        records.append({
            "MC Size": sz,
            "MC QTY": int(mc_qty),
            "CT Average": round(avg_ct, 2),
            "Run Hour Average": round(rt / mc_qty if mc_qty > 0 else 0.0, 2),
            "Total Cap (Pcs)": round(cap_pcs, 2),
            "Total Prod (Pcs)": round(prod_pcs, 2),
            "% OF Ach Pcs": f"{_pct(prod_pcs, cap_pcs):.2f}%",
            "Cap (Ton)": round(cap_ton, 2),
            "Prod (Ton)": round(prod_ton, 2),
            "% OF Ach Ton": f"{_pct(prod_ton, cap_ton):.2f}%",
        })
    return pd.DataFrame(records)


# ---------------------------------------------------------------------------
# Sub Total rows
# ---------------------------------------------------------------------------
_PCT_PAIRS = [  # (percent column, produced column, capacity column)
    ("% OF Ach Pcs", "Total Prod (Pcs)", "Total Cap (Pcs)"),
    ("% OF Ach Ton", "Prod (Ton)", "Cap (Ton)"),
    ("Pcs Ach %", "Prod (Pcs)", "Cap (Pcs)"),
    ("Ton Ach %", "Prod (Ton)", "Cap (Ton)"),
    ("Ach Pcs %", "Total Good", "Weighted Cap Pcs"),
    ("Ach Ton %", "Total Prod Ton", "Weighted Cap Ton"),
    ("Daily Util (Pcs %)", "Daily Prod (Pcs)", "Daily Cap (Pcs)"),
    ("Daily Util (Ton %)", "Daily Prod (Ton)", "Daily Cap (Ton)"),
    ("Last Day Util %", "Last Day Output (Pcs)", "Last Day Cap (Pcs)"),
    ("As of %", "As of Production", "Order Qty"),
    ("Fulfillment %", "Total Produced (Pcs)", "Demand Qty"),
]


def _num(df, c):
    return pd.to_numeric(df[c], errors="coerce")


def add_total_row(df, label_col, sum_cols, avg_cols, weight_col=None):
    """
    Adds a Sub Total row.  Sums for sum_cols; percentage columns are recomputed from their own
    totals; avg_cols are averaged over rows with a value > 0, weighted by weight_col when given.
    """
    if df.empty:
        return df
    tot = {}
    for c in df.columns:
        if c == label_col:
            tot[c] = "Sub Total"
        elif c in sum_cols:
            v = _num(df, c).sum()
            tot[c] = round(v, 2) if isinstance(v, (float, np.floating)) else v
        elif c in avg_cols:
            vals = _num(df, c)
            m = vals > 0
            if weight_col and weight_col in df.columns:
                w = _num(df, weight_col).where(m, 0)
                tot[c] = round((vals.where(m, 0) * w).sum() / w.sum(), 2) if w.sum() > 0 else (round(vals[m].mean(), 2) if m.any() else 0.0)
            else:
                tot[c] = round(vals[m].mean(), 2) if m.any() else 0.0
        else:
            tot[c] = "-"
    for pc, num_c, den_c in _PCT_PAIRS:
        if pc in df.columns and num_c in df.columns and den_c in df.columns:
            tot[pc] = f"{_pct(_num(df, num_c).sum(), _num(df, den_c).sum()):.2f}%"
    return pd.concat([df, pd.DataFrame([tot])], ignore_index=True)


def add_size_total_row(df):
    """Sizewise Sub Total with correctly weighted CT average and run-hour average."""
    sums = ["MC QTY", "Total Cap (Pcs)", "Total Prod (Pcs)", "Cap (Ton)", "Prod (Ton)"]
    out = add_total_row(df, "MC Size", sums, [])
    if df.empty:
        return out
    qty = _num(df, "MC QTY")
    hours = _num(df, "Run Hour Average") * qty
    ct = _num(df, "CT Average")
    out.loc[out.index[-1], "Run Hour Average"] = round(hours.sum() / qty.sum(), 2) if qty.sum() > 0 else 0.0
    out.loc[out.index[-1], "CT Average"] = round((ct * hours).sum() / hours.sum(), 2) if hours.sum() > 0 else 0.0
    return out


# ---------------------------------------------------------------------------
# Daily job-order view
# ---------------------------------------------------------------------------
def build_job_daily(df_day_raw):
    records = []
    for (cust, ord_name, acc), grp in df_day_raw.groupby(["Customer", "Order Name", "Acc Code"]):
        good, ton = grp["Total Good"].sum(), grp["Total Prod Ton"].sum()
        cap_ton, cap_pcs = grp["Weighted Cap Ton"].sum(), grp["Weighted Cap Pcs"].sum()
        records.append({
            "Customer": cust, "Order Name": ord_name, "Acc Code": acc,
            "Item Name": grp["Item Name"].iloc[0] if grp["Item Name"].nunique() == 1 else "Mixed items",
            "Demand Qty": grp["Demand Qty"].sum(),
            "Total Good": good, "Total Prod Ton": round(ton, 2),
            "Running Molds": grp["Machine"].nunique(),
            "MC Positions": ", ".join(sorted(grp["Machine"].unique())),
            "Daily Cap (Pcs)": round(cap_pcs, 2), "Daily Prod (Pcs)": round(good, 2),
            "Daily Util (Pcs %)": f"{_pct(good, cap_pcs):.2f}%",
            "Daily Cap (Ton)": round(cap_ton, 2), "Daily Prod (Ton)": round(ton, 2),
            "Daily Util (Ton %)": f"{_pct(ton, cap_ton):.2f}%",
            "Daily Runtime (Hrs)": round(grp["Total Runtime (Hrs)"].sum(), 2),
        })
    return pd.DataFrame(records)


# ---------------------------------------------------------------------------
# As-of job-order view (one row per order + item, ledger = LAST available date)
# ---------------------------------------------------------------------------
def _latest_sorted(grp):
    return grp.sort_values(["DateObj", "Floor", "Src Row"], kind="stable")


def _ledger_note(grp, last_date):
    last = grp[grp["Date"] == last_date]
    n = last["Due Prod Present"].round(2).nunique()
    if n > 1:
        return f"{len(last)} ledger lines on last date with {n} different due balances - last entry used"
    return ""


def build_job_mtd(df_mtd):
    records = []
    for (cust, ord_name, acc, item), grp in df_mtd.groupby(["Customer", "Order Name", "Acc Code", "Item Name"]):
        g = _latest_sorted(grp)
        latest = g.iloc[-1]
        last_date = latest["Date"]
        qty = latest["Demand Qty"] if latest["Demand Qty"] > 0 else g["Demand Qty"].max()
        due = latest["Due Prod Present"]
        as_of_prod = max(0.0, qty - due) if qty > 0 else g["Total Good"].sum()
        last_runs = g[g["Date"] == last_date]
        last_mcs = ", ".join(sorted(last_runs[last_runs["Total Good"] > 0]["Machine"].unique()))
        last_out = last_runs["Last Day Prod Col"].sum()
        last_cap = last_runs["Daily Cap Pcs"].sum()
        pct = _pct(as_of_prod, qty)
        records.append({
            "Customer": cust, "Order Name": ord_name, "Acc Code": acc, "Item Name": item,
            "Order Qty": qty, "Due Production": round(due, 2), "As of Production": round(as_of_prod, 2),
            "As of %": f"{pct:.2f}%", "Last Run Date": last_date, "Last MC Assigned": last_mcs,
            "Last Day Cap (Pcs)": round(last_cap, 2), "Last Day Output (Pcs)": round(last_out, 2),
            "Last Day Util %": f"{_pct(last_out, last_cap):.2f}%",
            "Total Prod Ton": round(g["Total Prod Ton"].sum(), 2),
            "Total Runtime (Hrs)": round(g["Total Runtime (Hrs)"].sum(), 2),
            "Is Completed": bool(due <= 0 or pct >= 100.0),
            "Ledger Note": _ledger_note(g, last_date),
        })
    return pd.DataFrame(records)


# ---------------------------------------------------------------------------
# Job Order Analysis (one order -> its items -> daily timeline)
# ---------------------------------------------------------------------------
def build_order_items(df_order, order_name):
    records = []
    for item, grp in df_order.groupby("Item Name"):
        g = _latest_sorted(grp)
        latest = g.iloc[-1]
        demand = latest["Demand Qty"] if latest["Demand Qty"] > 0 else g["Demand Qty"].max()
        due = latest["Due Prod Present"]
        produced = max(0.0, demand - due) if demand > 0 else latest["Up to Prod"] + latest["Total Good"]
        if due <= 0 and demand > 0:
            status = f"Done on {latest['Date']}"
        elif produced > 0:
            status = "In Progress"
        else:
            status = "Not Started"
        records.append({
            "Job Order": order_name, "Acc Code": latest["Acc Code"], "Item Name": item, "Color": latest.get("Color", "-"),
            "Demand Qty": demand, "Total Produced (Pcs)": produced, "Remaining Due": round(due, 2),
            "Fulfillment %": f"{_pct(produced, demand):.2f}%", "Status": status,
            "Last Run Date": latest["Date"], "Last MC Run": latest["Machine"],
            "Total Produced (Ton)": round(g["Total Prod Ton"].sum(), 2),
            "Total Runtime (Hrs)": round(g["Total Runtime (Hrs)"].sum(), 2),
            "Unit Wt (kg)": latest["Unit Wt (kg)"],
            "Cavity": g["Cavity"].max(),            # max cavity ever used for this item
            "CT": latest["CT"],                       # CT of the latest run
            "Ledger Note": _ledger_note(g, latest["Date"]),
        })
    return pd.DataFrame(records)


def build_item_timeline(df_item_runs, target_demand):
    records, cum_pcs, cum_ton = [], 0.0, 0.0
    g = df_item_runs.sort_values(["DateObj", "Floor", "Src Row"], kind="stable")
    for d_val, d_grp in g.groupby("Date", sort=False):
        act = running(d_grp)
        if act.empty:
            continue
        good, ton = act["Total Good"].sum(), act["Total Prod Ton"].sum()
        cum_pcs += good
        cum_ton += ton
        rem = max(0.0, target_demand - cum_pcs) if target_demand > 0 else 0.0
        if target_demand > 0 and cum_pcs >= target_demand:
            status = f"Demand Done ({d_val})" if cum_pcs - good < target_demand else "Buffer / Over-run"
        else:
            status = "In Progress"
        records.append({
            "Date": d_val, "Floor": ", ".join(sorted(act["Floor"].unique())),
            "Active Machines": ", ".join(sorted(act["Machine"].unique())),
            "Shift A Good (Pcs)": act["Shift A Good"].sum(), "Shift B Good (Pcs)": act["Shift B Good"].sum(),
            "Day Output (Pcs)": good, "Rejections (Pcs)": act["Total Rejections"].sum(),
            "Day Output (Ton)": round(ton, 3), "Runtime (Hrs)": round(act["Total Runtime (Hrs)"].sum(), 2),
            "Cumulative Output (Pcs)": cum_pcs, "Cumulative Output (Ton)": round(cum_ton, 2),
            "Remaining Due (Pcs)": int(rem), "Status": status,
        })
    return pd.DataFrame(records)


# ---------------------------------------------------------------------------
# Display formatting (unchanged behaviour)
# ---------------------------------------------------------------------------
_INT_KEYS = ("good", "rej", "pcs", "qty", "production", "due", "output", "cap")


def clean_and_format_dataframe(df):
    out = df.copy()
    for col in out.columns:
        lc = col.lower()
        if out[col].dtype in ("float64", "float32"):
            if any(k in lc for k in _INT_KEYS):
                out[col] = out[col].apply(lambda x: f"{int(round(x)):,}" if pd.notna(x) and str(x) != "-" else "-")
            else:
                out[col] = out[col].apply(lambda x: f"{x:.2f}" if pd.notna(x) and str(x) != "-" else "-")
        elif out[col].dtype in ("int64", "int32"):
            out[col] = out[col].apply(lambda x: f"{x:,}" if pd.notna(x) and str(x) != "-" else "-")
    return out
