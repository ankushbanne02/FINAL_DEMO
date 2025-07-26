import streamlit as st
import pandas as pd
from datetime import datetime

def all_parcels_view(df: pd.DataFrame) -> None:
    # ── 1. Helpers ──────────────────────────────────────────────────
    def iso_to_hms(iso_ts: str | None) -> str:
        """Return HH:MM:SS for a valid ISO string, else '—'."""
        if isinstance(iso_ts, str):
            try:
                return datetime.fromisoformat(iso_ts).strftime("%H:%M:%S")
            except ValueError:
                pass
        return "—"

    def stringify_barcodes(lst) -> str:
        """Show every barcode as‑is, or '—' if empty / bad."""
        if not isinstance(lst, list) or not lst:
            return "—"
        return ", ".join(str(b) for b in lst)

    def extract_report(events: list, status: str) -> str:
        """Return raw log text based on lifecycle status."""
        if not isinstance(events, list):
            return "—"
        match status:
            case "sorted":
                types = {"UnverifiedSortReport", "VerifiedSortReport"}
            case "deregistered":
                types = {"ItemDeRegister"}
            case "open":
                types = {"ItemInstruction"}
            case _:
                return "—"

        logs = [ev["raw"] for ev in events if ev.get("type") in types and "raw" in ev]
        return "\n".join(logs) if logs else "—"

    # ── 2. Extract status and registered time first ─────────────────
    df["status"] = df["lifeCycle"].apply(lambda x: x.get("status", "—") if isinstance(x, dict) else "—")
    df["registeredAt"] = df["lifeCycle"].apply(lambda x: x.get("registeredAt", None) if isinstance(x, dict) else None)

    # ── 3. Build main table ─────────────────────────────────────────
    tbl = pd.DataFrame({
        "Time":        df["registeredAt"].apply(iso_to_hms),
        "Status":      df["status"],
        "HOSTID":      df["hostId"],
        "BARCODES":    df["barcodes"].apply(stringify_barcodes),
        "LOCATION":    df["location"].fillna("—"),
        "DESTINATION": df["destination"].fillna("—"),
    })

    # ── 4. Add Report column with raw logs ──────────────────────────
    tbl["Report"] = df.apply(
        lambda row: extract_report(row.get("events", []), row.get("status", "")),
        axis=1
    )

    # ── 5. Filters ──────────────────────────────────────────────────
    filter_targets = ["Status", "LOCATION", "DESTINATION"]
    filters = {col: "All" for col in filter_targets}

    cols = st.columns(len(tbl.columns))
    for col_name, col_widget in zip(tbl.columns, cols):
        with col_widget:
            if col_name in filter_targets:
                options = ["All"] + sorted(tbl[col_name].dropna().unique())
                filters[col_name] = st.selectbox(
                    f"{col_name} filter", options, index=0,
                    label_visibility="collapsed", key=f"{col_name.lower()}_filter"
                )
            else:
                st.markdown("&nbsp;", unsafe_allow_html=True)

    # ── 6. Apply filters ────────────────────────────────────────────
    for col_name, choice in filters.items():
        if choice != "All":
            tbl = tbl[tbl[col_name] == choice]

    # ── 7. Display table ────────────────────────────────────────────
    st.dataframe(tbl, use_container_width=True)

    # ── 8. CSS tweak for compact select boxes ───────────────────────
  
    st.markdown(
    """
    <style>
    div[data-baseweb="select"] {
        width: 60%;
        font-size: 0.8rem;
        padding-left: 20px; /* 👈 add left padding */
    }
    </style>
    """,
    unsafe_allow_html=True
)

