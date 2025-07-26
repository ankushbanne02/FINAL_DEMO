import streamlit as st

def deregistered_parcels_view(df):
    bad = df[df.lifeCycle.apply(lambda x: x["status"]) == "deregistered"]
    st.dataframe(bad[["pic", "barcodeErr"]], use_container_width=True)
