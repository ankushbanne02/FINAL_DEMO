import streamlit as st

def sorted_parcels_view(df):
    good = df[df.lifeCycle.apply(lambda x: x["status"]) == "sorted"]
    st.dataframe(good[["pic", "barcodeErr"]], use_container_width=True)
