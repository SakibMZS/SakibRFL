"""
chess.py  -  Chess family-mold consolidation.

Works on the *canonical* columns produced by ingest.py (headers are already
normalised, so it no longer depends on the exact spelling of 'Due Prod',
'Colo+G:AHr', 'B-Reject Cause of Less Prod', ... in the Excel sheet).

Rule (unchanged): the 5 component rows of one chess set (same machine, order and
colour) run together in one family mold, so they are merged into ONE row:
  * cavities are summed (2+2+4+4+4 = 16)
  * unit weight is the cavity-weighted average
  * counters / good / reject / ledger columns are summed
Changes vs the previous version:
  * groupby(dropna=False): a row with a blank colour is NOT silently dropped.
  * the merged row keeps the ORIGINAL position of its first component row.
  * returns a row map so audit messages for component rows point at the merged row.
  * CT = first positive CT among the components (first row may be blank).
"""
import numpy as np
import pandas as pd

CHESS_SET_NAME = "DT 3 IN 1 Classic Game Board Chess Set"

SUM_COLS = [
    "A Counter", "B Counter", "A Good", "A Rej", "B Good", "B Rej",
    "Demand", "Up to Prod", "Due Prev", "Due Present", "Last Day Prod",
    "Sheet Ton", "Source Good",
]


def is_chess_item(item_name):
    """Detects chess family-mold items by keyword."""
    if item_name is None or (not isinstance(item_name, str) and pd.isna(item_name)):
        return False
    return "chess" in str(item_name).lower()


def consolidate_chess_family_mold(df):
    """
    df: canonical frame (one row per Excel row; must contain 'Src Row').
    Returns (df_out, row_map) where row_map maps component Src Row -> merged Src Row.
    """
    row_map = {}
    if df is None or df.empty or "Item Name" not in df.columns:
        return df, row_map

    is_chess = df["Item Name"].apply(is_chess_item)
    if not is_chess.any():
        return df, row_map

    df_non = df[~is_chess].copy()
    df_chess = df[is_chess].copy()

    group_cols = ["MC Raw", "Order Name", "Color"]
    merged_rows = []
    for _, grp in df_chess.groupby(group_cols, sort=False, dropna=False):
        first = grp.iloc[0].copy()

        cav = pd.to_numeric(grp["Cavity"], errors="coerce").fillna(0)
        wts = pd.to_numeric(grp["Unit Wt"], errors="coerce").fillna(0)
        total_cav = cav.sum()
        first["Cavity"] = total_cav
        first["Unit Wt"] = (wts * cav).sum() / total_cav if total_cav > 0 else wts.mean()

        cts = pd.to_numeric(grp["CT"], errors="coerce")
        pos = cts[cts > 0]
        first["CT"] = pos.iloc[0] if not pos.empty else (cts.dropna().iloc[0] if cts.notna().any() else np.nan)

        for c in SUM_COLS:
            if c in grp.columns:
                first[c] = pd.to_numeric(grp[c], errors="coerce").fillna(0).sum()

        first["Item Name"] = CHESS_SET_NAME
        merged_rows.append(first)
        for sr in grp["Src Row"].tolist():
            row_map[int(sr)] = int(first["Src Row"])

    df_merged = pd.DataFrame(merged_rows)
    out = pd.concat([df_non, df_merged], ignore_index=True)
    out = out.sort_values("Src Row", kind="stable").reset_index(drop=True)
    # rows rebuilt from Series come back as 'object'; restore numeric dtypes
    for col in df.columns:
        if pd.api.types.is_numeric_dtype(df[col]) and not pd.api.types.is_bool_dtype(df[col]):
            out[col] = pd.to_numeric(out[col], errors="coerce")
    return out, row_map
