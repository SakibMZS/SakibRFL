import pandas as pd
import numpy as np

def is_chess_item(item_name):
    """Detects chess family-mold items by keyword."""
    if not item_name or pd.isna(item_name):
        return False
    return "chess" in str(item_name).lower()


def consolidate_chess_family_mold(df_sheet):
    """
    Combines multi-component chess family mold entries into single operational set entries.
    Groups by machine, order, AND color/active state to isolate running sets (16 cavity)
    from unrun/idle setups.
    """
    if df_sheet.empty or "Item Name" not in df_sheet.columns:
        return df_sheet

    is_chess = df_sheet["Item Name"].apply(is_chess_item)
    if not is_chess.any():
        return df_sheet

    df_non_chess = df_sheet[~is_chess].copy()
    df_chess = df_sheet[is_chess].copy()

    # Isolate color to prevent merging Black and Cream setups together
    color_col = "Color" if "Color" in df_chess.columns else "Colo+G:AHr"
    if color_col not in df_chess.columns:
        df_chess["Color"] = "-"
        color_col = "Color"

    group_cols = ["MC SL", "Order Name", color_col]
    if "Date" in df_chess.columns:
        group_cols.append("Date")

    consolidated_rows = []
    for keys, grp in df_chess.groupby(group_cols, sort=False):
        first_row = grp.iloc[0].copy()

        # Sum cavities across components of the same color setup (e.g. 2 + 2 + 4 + 4 + 4 = 16)
        total_cavity = pd.to_numeric(grp["Cavity"], errors="coerce").fillna(0).sum()

        weights = pd.to_numeric(grp["Unit Wt"], errors="coerce").fillna(0)
        cavs = pd.to_numeric(grp["Cavity"], errors="coerce").fillna(0)
        weighted_unit_wt = (weights * cavs).sum() / total_cavity if total_cavity > 0 else weights.mean()

        sum_a_tot = pd.to_numeric(grp.get("T Counter", grp.get("Counter", grp.get("A Total", 0))), errors="coerce").fillna(0).sum()
        sum_b_tot = pd.to_numeric(grp.get("Total Counter B", grp.get("Counter B", grp.get("B Total", 0))), errors="coerce").fillna(0).sum()

        sum_a_good = pd.to_numeric(grp.get("A-Good", 0), errors="coerce").fillna(0).sum()
        sum_a_rej = pd.to_numeric(grp.get("A-Rejec", 0), errors="coerce").fillna(0).sum()
        sum_b_good = pd.to_numeric(grp.get("B-Good", 0), errors="coerce").fillna(0).sum()

        b_rej_col = "B-Reject" if "B-Reject" in grp.columns else "B-Reject Cause of Less Prod"
        sum_b_rej = pd.to_numeric(grp.get(b_rej_col, 0), errors="coerce").fillna(0).sum()

        sum_demand = pd.to_numeric(grp.get("Demand", 0), errors="coerce").fillna(0).sum()
        sum_up_to = pd.to_numeric(grp.get("Up to Prod", 0), errors="coerce").fillna(0).sum()
        sum_due = pd.to_numeric(grp.get("Due Prod", 0), errors="coerce").fillna(0).sum()
        sum_due_1 = pd.to_numeric(grp.get("Due Prod.1", 0), errors="coerce").fillna(0).sum()
        sum_last_day = pd.to_numeric(grp.get("Last Day Prod", 0), errors="coerce").fillna(0).sum()

        first_row["Item Name"] = "DT 3 IN 1 Classic Game Board Chess Set"
        first_row["Cavity"] = total_cavity
        first_row["Unit Wt"] = weighted_unit_wt
        first_row["T Counter"] = sum_a_tot
        first_row["Total Counter B"] = sum_b_tot
        first_row["A-Good"] = sum_a_good
        first_row["A-Rejec"] = sum_a_rej
        first_row["B-Good"] = sum_b_good
        if b_rej_col in first_row:
            first_row[b_rej_col] = sum_b_rej
        first_row["Demand"] = sum_demand
        first_row["Up to Prod"] = sum_up_to
        first_row["Due Prod"] = sum_due
        first_row["Due Prod.1"] = sum_due_1
        first_row["Last Day Prod"] = sum_last_day

        consolidated_rows.append(first_row)

    df_consolidated = pd.DataFrame(consolidated_rows)
    return pd.concat([df_non_chess, df_consolidated], ignore_index=True)
