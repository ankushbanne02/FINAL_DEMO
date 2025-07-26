import re
import json
from collections import defaultdict
from datetime import datetime

# ── Message‑type mapping ────────────────────────────────────────────
ID_MAP = {
    "1":  "ItemRegister",
    "2":  "ItemPropertiesUpdate",
    "3":  "ItemInstruction",
    "5":  "UnverifiedSortReport",
    "6":  "VerifiedSortReport",
    "7":  "ItemDeRegister",
    "98": "WatchdogReply",
    "99": "WatchdogRequest",
}

# ── Regex helpers ───────────────────────────────────────────────────
LOG_TS   = re.compile(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),(\d{3})')
RAW_BODY = re.compile(r'\): (.*?)(?: \[\]$)')
LOC_PAT  = re.compile(r'\b\d{4}\.\d{4}\.\d{4}\.B\d{2}\b')   # chute/station code

# ── Main parser ─────────────────────────────────────────────────────
def parse_log(text: str):
    """
    Parse entire raw log text → list[dict] (one dict per PIC).
    Dict schema:
        pic, hostId, barcodes[], location, destination,
        lifeCycle{registeredAt, closedAt, status}, barcodeErr, events[].
    """
    parcels = defaultdict(lambda: {
        "pic": None,
        "hostId": None,
        "barcodes": [],           # list of every barcode seen
        "location": None,
        "destination": None,
        "lifeCycle": {"registeredAt": None, "closedAt": None, "status": "open"},
        "barcodeErr": False,
        "events": []
    })

    for line in text.splitlines():
        # timestamp & body extraction
        ts_m, body_m = LOG_TS.search(line), RAW_BODY.search(line)
        if not (ts_m and body_m):
            continue

        ts_iso = datetime.strptime(
            f"{ts_m.group(1)}.{ts_m.group(2)}", "%Y-%m-%d %H:%M:%S.%f"
        ).isoformat()

        parts = body_m.group(1).strip().split("|")
        if len(parts) < 5 or ID_MAP.get(parts[3], "").startswith("Watchdog"):
            continue

        # PIC must be int
        try:
            pic = int(parts[4])
        except ValueError:
            continue

        parcel = parcels[pic]
        parcel["pic"] = pic
        msg = ID_MAP.get(parts[3], f"Type{parts[3]}")

        # universal location fallback
        if not parcel["location"]:
            loc_m = LOC_PAT.search("|".join(parts))
            if loc_m:
                parcel["location"] = loc_m.group(0)

        # ── message‑specific handling ─────────────────────────────
        if msg == "ItemRegister":
            parcel["lifeCycle"]["registeredAt"] = (
                parcel["lifeCycle"]["registeredAt"] or ts_iso
            )

        elif msg == "ItemInstruction":
            # …| PIC | HOSTID | LOCATION | DESTINATION |…
            if len(parts) >= 7:
                parcel["hostId"]   = parcel["hostId"]   or parts[5]
                parcel["location"] = parcel["location"] or parts[6]
            if len(parts) >= 8:
                parcel["destination"] = parcel["destination"] or parts[7]

        elif msg == "ItemPropertiesUpdate":
            # layout sample: |…| field6=location | field8=longBarcode | field9=status;BCode;Loc
            if len(parts) >= 7:
                parcel["location"] = parcel["location"] or parts[6]

            # primary barcode (field8)
            if len(parts) >= 9:
                bc = parts[8].lstrip("0")
                if bc and bc not in parcel["barcodes"]:
                    parcel["barcodes"].append(bc)

            # secondary barcode in semicolon block (field9)
            if len(parts) >= 10:
                semis = parts[9].split(";")
                if len(semis) >= 3:
                    bc2 = semis[2]
                    if bc2 and bc2 not in parcel["barcodes"]:
                        parcel["barcodes"].append(bc2)
                # status flag
                if semis and semis[0] != "6":
                    parcel["barcodeErr"] = True

        elif msg == "VerifiedSortReport":
            parcel["lifeCycle"]["status"] = "sorted"

        elif msg == "ItemDeRegister":
            if parcel["lifeCycle"]["status"] != "sorted":
                parcel["lifeCycle"]["status"] = "deregistered"
            parcel["lifeCycle"]["closedAt"] = ts_iso

        # store raw event
        parcel["events"].append({"ts": ts_iso, "type": msg, "raw": "|".join(parts)})

    # defaultdict → list[dict]
    return list(parcels.values())


# ── Replace this with actual log string ─────────────────────────────
text = """\
2025-07-19 11:45:10,123 INFO (Thread-1): |S|2|2027756|1|460|LOC1|BARCODE123|6;BCode;1234.5678.0000.B01| []
2025-07-19 11:45:11,456 INFO (Thread-1): |S|3|2027756|3|460|HOST123|1234.5678.0000.B02|DEST123| []
2025-07-19 11:45:12,789 INFO (Thread-1): |S|6|2027756|6|460| []
2025-07-19 11:45:13,789 INFO (Thread-1): |S|7|2027756|7|460| []
"""

# ── Save raw log to logs.txt ────────────────────────────────────────
with open("logs.txt", "w", encoding="utf-8") as txt_file:
    txt_file.write(text)

# ── Parse logs and save JSON ────────────────────────────────────────
parsed_data = parse_log(text)

with open("parcels.json", "w", encoding="utf-8") as json_file:
    json.dump(parsed_data, json_file, indent=2)

print("✔ Saved logs to logs.txt and parsed output to parcels.json")
