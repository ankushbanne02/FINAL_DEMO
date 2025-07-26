import re
import json
from collections import defaultdict

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
RAW_BODY = re.compile(r'\): (.*?)(?: \[\]$)')
LOC_PAT = re.compile(r'\b\d{4}\.\d{4}\.\d{4}\.B\d{2}\b')

# --- Main parser ---------------------------------------------------
def parse_log(text: str) -> list[dict]:
    parcels = {}
    pending_registers = {}

    for line in text.splitlines():
        body_m = RAW_BODY.search(line)
        if not body_m:
            continue

        parts = body_m.group(1).strip().split("|")
        if len(parts) < 6 or ID_MAP.get(parts[3], "").startswith("Watchdog"):
            continue

        msg_code = parts[3]
        msg = ID_MAP.get(msg_code, f"Type{msg_code}")

        try:
            pic = int(parts[4])
        except ValueError:
            continue

        host_id = parts[5].strip()

        # Extract timestamp from the message body (parts[2]), ensure ms format
        try:
            raw_ts = parts[2]  # Example: 2025-05-13T07:46:40.306Z
            ts_clean = raw_ts.split("T")[1].replace("Z", "")  # => "07:46:40.306"
            iso_ts = f"2025-05-13T{ts_clean}"
        except:
            continue

        # Handle ItemRegister (with or without hostId)
        if msg == "ItemRegister":
            if host_id:
                if host_id not in parcels:
                    parcels[host_id] = {
                        "pic": pic,
                        "hostId": host_id,
                        "barcodes": [],
                        "barcode_count": 0,
                        "location": None,
                        "destination": None,
                        "lifeCycle": {"registeredAt": iso_ts, "closedAt": None, "status": "open"},
                        "barcodeErr": False,
                        "events": [],
                        "volume_data": {
                            "length": None, "width": None, "height": None,
                            "box_volume": None, "real_volume": None
                        }
                    }
                parcels[host_id]["events"].append({
                    "ts": iso_ts,
                    "type": msg,
                    "raw": "|".join(parts)
                })
            else:
                pending_registers[pic] = iso_ts
            continue

        if not host_id:
            continue  # Can't proceed without hostId in other messages

        if host_id not in parcels:
            parcels[host_id] = {
                "pic": pic,
                "hostId": host_id,
                "barcodes": [],
                "barcode_count": 0,
                "location": None,
                "destination": None,
                "lifeCycle": {"registeredAt": None, "closedAt": None, "status": "open"},
                "barcodeErr": False,
                "events": [],
                "volume_data": {
                    "length": None, "width": None, "height": None,
                    "box_volume": None, "real_volume": None
                }
            }

        parcel = parcels[host_id]

        # Register time from cached register
        if msg == "ItemInstruction" and parcel["lifeCycle"]["registeredAt"] is None:
            if pic in pending_registers:
                parcel["lifeCycle"]["registeredAt"] = pending_registers[pic]
                del pending_registers[pic]
            else:
                parcel["lifeCycle"]["registeredAt"] = iso_ts

        if not parcel["location"]:
            loc_m = LOC_PAT.search("|".join(parts))
            if loc_m:
                parcel["location"] = loc_m.group(0)

        if msg == "ItemInstruction":
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
            parcel["lifeCycle"]["closedAt"] = iso_ts

        parcel["events"].append({
            "ts": iso_ts,
            "type": msg,
            "raw": "|".join(parts)
        })

    for parcel_data in parcels.values():
        parcel_data["barcode_count"] = len(parcel_data["barcodes"])

    return list(parcels.values())

# --- Run as script --------------------------------------------------
if __name__ == "__main__":
    input_file = "logs.txt"
    output_file = "parsed_output.json"

    with open(input_file, "r", encoding="utf-8") as f:
        log_text = f.read()

    parsed_data = parse_log(log_text)

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(parsed_data, f, ensure_ascii=False, indent=2)

    print(f"✅ Parsed data saved to {output_file}")
