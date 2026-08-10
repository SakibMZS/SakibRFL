import streamlit as st

st.set_page_config(
    page_title="SMS Module | Plastic-3 Console",
    page_icon="📱",
    layout="wide",
)

# ---------------------------------------------------------
# ACCESS CONTROL: STRICT CHECK FOR APP.PY DATA
# ---------------------------------------------------------
if not st.session_state.get("dashboard_ready", False) or "df_data_raw" not in st.session_state:
    st.error("🔒 **Access Denied / No Active Session**")
    st.caption("Please upload First Floor (FF) and Ground Floor (GF) production files in the main console first.")
    
    if st.button("⬅️ Back to Main Console", type="primary"):
        st.switch_page("app.py")
        
    st.stop()  # Strictly stops execution here; page acts dead without app.py data

# ---------------------------------------------------------
# BLANK SMS MODULE WINDOW (LOADS ONLY WHEN DATA EXISTS)
# ---------------------------------------------------------
# Load custom styles if present
import os
if os.path.exists("style.css"):
    with open("style.css") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

# Access shared app.py dataframe safely
df_shared = st.session_state["df_data_raw"]

col_title, col_nav = st.columns([4, 1], vertical_alignment="center")
with col_title:
    st.title("📱 **SMS MODULE**")
    st.caption(f"Connected to Active Session | Parsed Records: {len(df_shared):,}")

with col_nav:
    if st.button("⬅️ Main Console", use_container_width=True):
        st.switch_page("app.py")

st.divider()

# Blank workspace container for upcoming functionality
st.info("🛠️ SMS Module initialized. Ready for functional buildout.")
