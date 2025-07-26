import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, time

def parcel_search_view(df):
    search_mode = st.radio("Search by", ["Host ID", "Barcode"], horizontal=True)
    search_input = st.text_input(f"Enter {search_mode}")
    if not search_input:
        return

    try:
        if search_mode == "Host ID":
            result = df[df["hostId"] == search_input]
        elif search_mode == "Barcode":
            result = df[df["barcodes"].apply(lambda barcodes: search_input in (barcodes or []))]

        if result.empty:
            st.warning(f"{search_mode} not found.")
            return

        for idx, parcel in result.iterrows():
            volume = parcel.get("volume_data") or {}

            volume_info = {
                "Length (cm)": volume.get("length") or "—",
                "Width (cm)": volume.get("width") or "—",
                "Height (cm)": volume.get("height") or "—",
                "Box Volume (cm³)": volume.get("box_volume") or "—",
                "Real Volume (cm³)": volume.get("real_volume") or "—"
            }

            lifecycle = parcel.get("lifeCycle") or {}
            registered_at = lifecycle.get("registeredAt") or "—"

            parcel_summary = {
                "PIC": parcel.get("pic"),
                "Host ID": parcel.get("hostId"),
                "Barcodes": parcel.get("barcodes"),
                "Location": parcel.get("location"),
                "Destination": parcel.get("destination"),
                "Registered At": registered_at,
                "Volume Data": volume_info,
                "Lifecycle": lifecycle,
                "Barcode Error": parcel.get("barcodeErr"),
                "Recirculation Count": parcel.get("recirculationCount", 0)
            }

            st.subheader("📦 Parcel Information")
            st.json(parcel_summary)

            # ── Event timeline ──
            ev = pd.DataFrame(parcel.get("events") or [])
            if ev.empty:
                st.info("No event data available.")
                continue

            ev = ev[ev["type"] != "Lifecycle"]

            # Convert HH:MM:SS to datetime (for plotting)
            ev["ts"] = ev["ts"].apply(lambda t: datetime.strptime(t, "%H:%M:%S"))
            ev = ev.sort_values("ts")

            # Duration and Finish
            buffer_sec = 2
            ev["finish"] = ev["ts"].shift(-1)
            ev["finish"] = ev["finish"].fillna(ev["ts"] + pd.Timedelta(seconds=buffer_sec))
            ev["duration_s"] = (ev["finish"] - ev["ts"]).dt.total_seconds().clip(lower=0)
            ev["time"] = ev["ts"].dt.strftime("%H:%M:%S")

            st.subheader("📋 Event Log")
            st.dataframe(
                ev[["time", "type", "duration_s"]].rename(columns={
                    "time": "Time",
                    "type": "Type",
                    "duration_s": "Duration (s)"
                }),
                use_container_width=True,
                hide_index=True,
            )

            fig = px.timeline(
                ev,
                x_start="ts",
                x_end="finish",
                y=["Parcel"] * len(ev),
                color="type",
                hover_data=["type", "time", "duration_s"]
            )
            fig.update_layout(
                title="Parcel Event Timeline",
                xaxis_title="Time",
                yaxis_title="",
                height=300,
                showlegend=True
            )
            st.plotly_chart(fig, use_container_width=True)

    except Exception as e:
        st.error(f"Error: {e}")
