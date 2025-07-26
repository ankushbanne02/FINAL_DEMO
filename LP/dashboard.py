import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
from collections import Counter
from hlc_parser import parse_log

from views.parcel_search import parcel_search_view
from views.all_parcels import all_parcels_view

# ── Streamlit UI Setup ─────────────────────────────────────────────
st.set_page_config(page_title="Vanderlande Parcel Dashboard", layout="wide")
st.title("📦 Vanderlande Parcel Dashboard")

# ── File Upload ────────────────────────────────────────────────────
uploaded = st.file_uploader("Upload raw Log File in .txt format", type="txt")
if not uploaded:
    st.info("Upload Raw Log file.")
    st.stop()

text = uploaded.read().decode("utf-8")
with st.spinner("Parsing log…"):
    lifecycles = parse_log(text)
    df = pd.DataFrame(lifecycles)

# ── Metrics Calculation ────────────────────────────────────────────
total = len(df)
sorted_cnt = (df.lifeCycle.apply(lambda x: x["status"]) == "sorted").sum()
dereg_cnt = (df.lifeCycle.apply(lambda x: x["status"]) == "deregistered").sum()
barcode_err = df.barcodeErr.sum()

def cycle_s(lc):
    try:
        if isinstance(lc["registeredAt"], str) and isinstance(lc["closedAt"], str):
            return (
                datetime.fromisoformat(lc["closedAt"])
                - datetime.fromisoformat(lc["registeredAt"])
            ).total_seconds()
    except Exception:
        return None

df["cycle_time"] = df.lifeCycle.apply(cycle_s)
cycle_vals = df["cycle_time"].dropna()
avg_cycle = sum(cycle_vals) / len(cycle_vals) if len(cycle_vals) else 0

registered_times = [
    datetime.fromisoformat(l["registeredAt"])
    for l in df.lifeCycle
    if isinstance(l["registeredAt"], str)
]

closed_or_registered_times = [
    datetime.fromisoformat(l["closedAt"]) if isinstance(l["closedAt"], str)
    else datetime.fromisoformat(l["registeredAt"]) if isinstance(l["registeredAt"], str)
    else None
    for l in df.lifeCycle
]
closed_or_registered_times = [dt for dt in closed_or_registered_times if dt]

if registered_times and closed_or_registered_times:
    first_ts = min(registered_times)
    last_ts = max(closed_or_registered_times)
    duration = (last_ts - first_ts).total_seconds()
    tph = total / (duration / 3600) if duration > 0 else 0
else:
    tph = 0

# ── Dashboard Metrics ──────────────────────────────────────────────
c1, c2, c3 = st.columns(3)
with c1:
    st.metric("Total Parcels", total)
    st.metric("% Sorted", f"{sorted_cnt / total * 100:.1f}%" if total else "0%")
with c2:
    st.metric("% Barcode Err", f"{barcode_err / total * 100:.1f}%" if total else "0%")
    st.metric("% Deregistered", f"{dereg_cnt / total * 100:.1f}%" if total else "0%")
with c3:
    st.metric("Avg Cycle (s)", f"{avg_cycle:.1f}")
    st.metric("Throughput (tph)", f"{tph:.1f}")

st.divider()

# ── Tabs ───────────────────────────────────────────────────────────
tab1, tab2, tab3 = st.tabs(["🔍 Parcel Search", "📦 All Parcels", "📊 Report"])

with tab1:
    parcel_search_view(df)

with tab2:
    all_parcels_view(df)

with tab3:
    st.subheader("📊 Message Type Summary")
    st.write("Breakdown of log messages by type:")

    # Flatten all events from all parcels
    all_events = sum(df["events"].tolist(), [])

    # Count each message type
    type_counts = Counter(event["type"] for event in all_events)

    # Label map
    display_mapping = {
        "ItemRegister": "1: Item Register Host PIC Request",
        "ItemInstruction": "3: Item Register Host PIC Reply",
        "ItemPropertiesUpdate": "2: Destination Request",
        "UnverifiedSortReport": "5: Unverfied Sort Report",
        "VerifiedSortReport": "6: Verified Sort Report",
        "ItemDeRegister": "7: De-Register",
        "RecirculationUpdate": "8: Recirculation Update"
    }

    # Build report table
    rows = []
    for msg_type, label in display_mapping.items():
        count = type_counts.get(msg_type, 0)
        rows.append({"Message ID": label, "Count": count})

    report_df = pd.DataFrame(rows)

    st.dataframe(report_df, use_container_width=False)
