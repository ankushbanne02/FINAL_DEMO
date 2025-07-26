import re
import json
from collections import defaultdict
from datetime import datetime

# --- Message-type mapping ------------------------------------------
ID_MAP = {
    "1": "ItemRegister",
    "2": "ItemPropertiesUpdate",
    "3": "ItemInstruction",
    "5": "UnverifiedSortReport",
    "6": "VerifiedSortReport",
    "7": "ItemDeRegister",
    "98": "WatchdogReply",
    "99": "WatchdogRequest",
}

# --- Regex helpers -------------------------------------------------
LOG_TS = re.compile(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),(\d{3})')
RAW_BODY = re.compile(r'\): (.*?)(?: \[\]$)')
LOC_PAT = re.compile(r'\b\d{4}\.\d{4}\.\d{4}\.B\d{2}\b') 

# --- Main parser ---------------------------------------------------
def parse_log(text: str) -> list[dict]:
    parcels = defaultdict(lambda: {
        "pic": None,
        "hostId": None,
        "barcodes": [],
        "barcode_count": 0,
        "location": None,
        "destination": None,
        "lifeCycle": {"registeredAt": None, "closedAt": None, "status": "open"},
        "barcodeErr": False,
        "events": [],
        "volume_data": {
            "length": None,
            "width": None,
            "height": None,
            "box_volume": None,
            "real_volume": None
        }
    })

    for line in text.splitlines():
        ts_m, body_m = LOG_TS.search(line), RAW_BODY.search(line)
        if not (ts_m and body_m):
            continue

        ts_iso = datetime.strptime(
            f"{ts_m.group(1)}.{ts_m.group(2)}", "%Y-%m-%d %H:%M:%S.%f"
        ).isoformat()

        parts = body_m.group(1).strip().split("|")
        if len(parts) < 6 or ID_MAP.get(parts[3], "").startswith("Watchdog"):
            continue

        try:
            pic = int(parts[4])
        except ValueError:
            continue

        host_id = parts[5].strip()
        if not host_id:
            continue

        parcel = parcels[host_id]
        parcel["pic"] = pic
        parcel["hostId"] = host_id

        msg = ID_MAP.get(parts[3], f"Type{parts[3]}")

        if not parcel["location"]:
            loc_m = LOC_PAT.search("|".join(parts))
            if loc_m:
                parcel["location"] = loc_m.group(0)

        if msg == "ItemRegister":
            parcel["lifeCycle"]["registeredAt"] = (
                parcel["lifeCycle"]["registeredAt"] or ts_iso
            )

        elif msg == "ItemInstruction":
            # ✅ Set registeredAt only if not already set
            if parcel["lifeCycle"]["registeredAt"] is None:
                parcel["lifeCycle"]["registeredAt"] = ts_iso

            if len(parts) >= 7:
                parcel["location"] = parcel["location"] or parts[6]
            if len(parts) >= 8:
                parcel["destination"] = parcel["destination"] or parts[7]

        elif msg == "ItemPropertiesUpdate":
            if len(parts) >= 7:
                parcel["location"] = parcel["location"] or parts[6]

            def add_valid_barcode(barcode_str, barcode_list):
                if barcode_str and barcode_str.startswith("0]C") and barcode_str not in barcode_list:
                    barcode_list.append(barcode_str)

            def process_barcode_field(field_content, barcode_list):
                if field_content:
                    for pb in field_content.split('@'):
                        if not pb.startswith("0]C"):
                            pb = pb.lstrip("0")
                        add_valid_barcode(pb, barcode_list)

            if len(parts) >= 9:
                process_barcode_field(parts[8], parcel["barcodes"])

            if len(parts) >= 10:
                semis = parts[9].split(";")
                if len(semis) >= 3:
                    process_barcode_field(semis[2], parcel["barcodes"])
                if semis and semis[0] != "6":
                    parcel["barcodeErr"] = True

            if len(parts) >= 13:
                volume_semis = parts[12].split(';')
                if len(volume_semis) >= 7:
                    try: parcel["volume_data"]["length"] = float(volume_semis[2])
                    except: pass
                    try: parcel["volume_data"]["width"] = float(volume_semis[3])
                    except: pass
                    try: parcel["volume_data"]["height"] = float(volume_semis[4])
                    except: pass
                    try: parcel["volume_data"]["box_volume"] = float(volume_semis[5])
                    except: pass
                    try: parcel["volume_data"]["real_volume"] = float(volume_semis[6])
                    except: pass

        elif msg == "VerifiedSortReport":
            parcel["lifeCycle"]["status"] = "sorted"

        elif msg == "ItemDeRegister":
            if parcel["lifeCycle"]["status"] != "sorted":
                parcel["lifeCycle"]["status"] = "deregistered"
            parcel["lifeCycle"]["closedAt"] = ts_iso

        parcel["events"].append({
            "ts": ts_iso,
            "type": msg,
            "raw": "|".join(parts)
        })

    for parcel_data in parcels.values():
        parcel_data["barcode_count"] = len(parcel_data["barcodes"])

    return list(parcels.values())


if __name__ == "__main__":
    input_file = "logs.txt"  # Replace with your actual log file name
    output_file = "parsed_output.json"

    with open(input_file, "r", encoding="utf-8") as f:
        log_text = f.read()

    parsed_data = parse_log(log_text)

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(parsed_data, f, ensure_ascii=False, indent=2)

    print(f"Parsed data saved to {output_file}")
