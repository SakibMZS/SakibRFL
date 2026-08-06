import pandas as pd
import streamlit as st

st.set_page_config(page_title="Excel Dashboard", layout="wide")
st.title("📊 Excel Data Summary")

uploaded_file = st.file_uploader("Upload your Excel file", type=["xlsx", "xls"])

if uploaded_file is not None:
    # Read Excel file
    df = pd.read_excel(uploaded_file)

    st.success("File uploaded successfully!")

    # Display basic metrics
    col1, col2 = st.columns(2)
    col1.metric("Total Rows", df.shape[0])
    col2.metric("Total Columns", df.shape[1])

    # Display Data Table
    st.subheader("Data Preview")
    st.dataframe(df)
