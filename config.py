import re
import pandas as pd

# =========================================================
# CENTRAL MACHINE MASTER REGISTRY
# =========================================================
MACHINE_MASTER = [
    # --- FIRST FLOOR (FF) ---
    {"smart_manu": "IMM-160-6",   "position": "A1-160",      "short_name": "A1", "floor": "FF"},
    {"smart_manu": "IMM-120-20",  "position": "A2-120",      "short_name": "A2", "floor": "FF"},
    {"smart_manu": "IMM-120-28",  "position": "A3-120",      "short_name": "A3", "floor": "FF"},
    {"smart_manu": "IMM-120-29",  "position": "A4-120",      "short_name": "A4", "floor": "FF"},
    {"smart_manu": "IMM-160-7",   "position": "A5-160",      "short_name": "A5", "floor": "FF"},
    {"smart_manu": "IMM-160-12",  "position": "A6-160",      "short_name": "A6", "floor": "FF"},
    {"smart_manu": "IMM-160-48",  "position": "A7-160",      "short_name": "A7", "floor": "FF"},
    {"smart_manu": "IMM-120-11",  "position": "B1-120",      "short_name": "B1", "floor": "FF"},
    {"smart_manu": "IMM-120-15",  "position": "B2-120",      "short_name": "B2", "floor": "FF"},
    {"smart_manu": "IMM-120-14",  "position": "B3-120",      "short_name": "B3", "floor": "FF"},
    {"smart_manu": "IMM-120-75",  "position": "B4-120",      "short_name": "B4", "floor": "FF"},
    {"smart_manu": "IMM-90-8",    "position": "B5-90PC",     "short_name": "B5", "floor": "FF"},
    {"smart_manu": "IMM-90-9",    "position": "B6-90PC",     "short_name": "B6", "floor": "FF"},
    {"smart_manu": "IMM-120-32",  "position": "B7-120PC",    "short_name": "B7", "floor": "FF"},
    {"smart_manu": "IMM-120-27",  "position": "B8-120PC",    "short_name": "B8", "floor": "FF"},
    {"smart_manu": "IMM-120-4",   "position": "C1-120",      "short_name": "C1", "floor": "FF"},
    {"smart_manu": "IMM-160-17",  "position": "C2-160",      "short_name": "C2", "floor": "FF"},
    {"smart_manu": "IMM-120-22",  "position": "C3-120",      "short_name": "C3", "floor": "FF"},
    {"smart_manu": "IMM-120-46",  "position": "C4-120PC",    "short_name": "C4", "floor": "FF"},
    {"smart_manu": "IMM-90-4",    "position": "C5-90",       "short_name": "C5", "floor": "FF"},
    {"smart_manu": "IMM-120-47",  "position": "C6-120",      "short_name": "C6", "floor": "FF"},
    {"smart_manu": "IMM-160-51",  "position": "C7-160",      "short_name": "C7", "floor": "FF"},
    {"smart_manu": "IMM-160-39",  "position": "D1-160",      "short_name": "D1", "floor": "FF"},
    {"smart_manu": "IMM-160-79",  "position": "D2-160",      "short_name": "D2", "floor": "FF"},
    {"smart_manu": "IMM-160-80",  "position": "D3-160",      "short_name": "D3", "floor": "FF"},

    # --- GROUND FLOOR (GF) ---
    {"smart_manu": "IMM-280R-25", "position": "A1-280TC",    "short_name": "A1", "floor": "GF"},
    {"smart_manu": "IMM-380-5",   "position": "A2-380",      "short_name": "A2", "floor": "GF"},
    {"smart_manu": "IMM-380-81",  "position": "A3-380 (PC)", "short_name": "A3", "floor": "GF"},
    {"smart_manu": "IMM-380-80",  "position": "A4-380",      "short_name": "A4", "floor": "GF"},
    {"smart_manu": "IMM-330-4",   "position": "A5-HP-330",   "short_name": "A5", "floor": "GF"},
    {"smart_manu": "IMM-470-5",   "position": "B1-470",      "short_name": "B1", "floor": "GF"},
    {"smart_manu": "IMM-380-6",   "position": "B2-380",      "short_name": "B2", "floor": "GF"},
    {"smart_manu": "IMM-530-15",  "position": "B3-530",      "short_name": "B3", "floor": "GF"},
    {"smart_manu": "IMM-530-16",  "position": "B4-530",      "short_name": "B4", "floor": "GF"},
    {"smart_manu": "IMM-530-22",  "position": "B5-530",      "short_name": "B5", "floor": "GF"},
    {"smart_manu": "IMM-380-4",   "position": "B6-380",      "short_name": "B6", "floor": "GF"},
    {"smart_manu": "IMM-800-30",  "position": "C1-800-30",   "short_name": "C1", "floor": "GF"},
    {"smart_manu": "IMM-800-31",  "position": "C2-800-31",   "short_name": "C2", "floor": "GF"},
    {"smart_manu": "IMM-270-1",   "position": "C3-270-1",    "short_name": "C3", "floor": "GF"},
    {"smart_manu": "IMM-380-73",  "position": "C4-380-73",   "short_name": "C4", "floor": "GF"},
    {"smart_manu": "IMM-380-44",  "position": "C5-380-44",   "short_name": "C5", "floor": "GF"},
    {"smart_manu": "IMM-280R-3",  "position": "C6-280TC",    "short_name": "C6", "floor": "GF"},
    {"smart_manu": "IMM-280R-24", "position": "D1-280TC",    "short_name": "D1", "floor": "GF"},
    {"smart_manu": "IMM-250-106", "position": "D2-MA2-250",  "short_name": "D2", "floor": "GF"},
    {"smart_manu": "IMM-330-1",   "position": "D3-330-1",    "short_name": "D3", "floor": "GF"},
    {"smart_manu": "IMM-330-5",   "position": "D4-HP-330-5", "short_name": "D4", "floor": "GF"},
    {"smart_manu": "IMM-428-1",   "position": "D5-428-1",    "short_name": "D5", "floor": "GF"},
    {"smart_manu": "IMM-428-4",   "position": "D6-HP-428-4", "short_name": "D6", "floor": "GF"},
    {"smart_manu": "IMM-330-8",   "position": "D7-HP-330",   "short_name": "D7", "floor": "GF"},
    {"smart_manu": "IMM-380-90",  "position": "E1-380-90",   "short_name": "E1", "floor": "GF"},
    {"smart_manu": "IMM-380-94",  "position": "E2-380-94",   "short_name": "E2", "floor": "GF"},
    {"smart_manu": "IMM-380-88",  "position": "E3-380-88",   "short_name": "E3", "floor": "GF"},
    {"smart_manu": "IMM-380-76",  "position": "E4-380-76",   "short_name": "E4", "floor": "GF"},
    {"smart_manu": "IMM-380-62",  "position": "E5-380-62",   "short_name": "E5", "floor": "GF"},
    {"smart_manu": "IMM-380-75",  "position": "E6-380-75",   "short_name": "E6", "floor": "GF"},
    {"smart_manu": "IMM-380-92",  "position": "F1-380-92",   "short_name": "F1", "floor": "GF"},
    {"smart_manu": "IMM-380-93",  "position": "F2-380-93",   "short_name": "F2", "floor": "GF"},
    {"smart_manu": "IMM-380-98",  "position": "F3-380-98",   "short_name": "F3", "floor": "GF"},
    {"smart_manu": "IMM-380-99",  "position": "F4-380-99",   "short_name": "F4", "floor": "GF"},
    {"smart_manu": "IMM-380-101", "position": "F5-380-101",  "short_name": "F5", "floor": "GF"},
    {"smart_manu": "IMM-380-100", "position": "F6-380-100",  "short_name": "F6", "floor": "GF"},
]

# Quick Lookups
SMART_TO_POSITION = {item["smart_manu"]: item["position"] for item in MACHINE_MASTER}
POSITION_TO_SMART = {item["position"]: item["smart_manu"] for item in MACHINE_MASTER}

# =========================================================
# TYPO-RESILIENT MACHINE RESOLUTION ENGINE
# =========================================================
def resolve_machine_info(raw_input, floor=None):
    """
    Resolves raw machine input strings to a standard master record with typo resilience.
    Handles partial inputs like 'F4-380' or 'F4' resolving to 'F4-380-99' (IMM-380-99).
    """
    if not raw_input or pd.isna(raw_input):
        return None

    clean_str = str(raw_input).strip().upper()

    # Tier 1: Exact matches (Smart Manu ID, Position, or Short Name)
    for entry in MACHINE_MASTER:
        if floor and entry["floor"] != floor:
            continue
        if clean_str in [entry["smart_manu"].upper(), entry["position"].upper(), entry["short_name"].upper()]:
            return entry

    # Tier 2: Prefix matching by Short Name (e.g., 'F4-380' -> matches Short Name 'F4')
    match = re.match(r"^([A-F]\d+)", clean_str)
    if match:
        short_code = match.group(1)
        for entry in MACHINE_MASTER:
            if floor and entry["floor"] != floor:
                continue
            if entry["short_name"].upper() == short_code:
                return entry

    return None
