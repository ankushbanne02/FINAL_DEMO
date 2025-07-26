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
LOC_PAT = re.compile(r'\b\d{4}\.\d{4}\.\d{4}\.B\d{2}\b') # chute/station code

# --- Main parser ---------------------------------------------------
def parse_log(text: str):
    parcels = defaultdict(lambda: {
        "pic": None,
        "hostId": None,
        "barcodes": [],
        "barcode_count": 0,  # Retained from your previous code
        "location": None,
        "destination": None,
        "lifeCycle": {"registeredAt": None, "closedAt": None, "status": "open"},
        "barcodeErr": False,
        "events": [],
        # --- ADDED NEW KEY: volume_data ---
        "volume_data": {
            "length": None,
            "width": None,
            "height": None,
            "box_volume": None,  # Corresponds to 'Calculated Volume' in the document
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
            if len(parts) >= 7:
                parcel["location"] = parcel["location"] or parts[6]
            if len(parts) >= 8:
                parcel["destination"] = parcel["destination"] or parts[7]

        elif msg == "ItemPropertiesUpdate":
            if len(parts) >= 7:
                parcel["location"] = parcel["location"] or parts[6]

            # Define a helper function to validate and add barcodes
            def add_valid_barcode(barcode_str, parcel_barcodes_list):
                # A barcode is considered valid if it starts with "0]C"
                if barcode_str and barcode_str.startswith("0]C") and barcode_str not in parcel_barcodes_list:
                    parcel_barcodes_list.append(barcode_str)

            # Helper to process a potential barcode string (which might contain multiple barcodes separated by '@')
            def process_barcode_field(field_content, barcode_list):
                if field_content:
                    # Split by '@' to handle concatenated barcodes
                    potential_barcodes = field_content.split('@')
                    for pb in potential_barcodes:
                        # Apply lstrip("0") ONLY IF it's not a "0]C" barcode and seems like a numerical ID
                        if not pb.startswith("0]C"):
                            pb = pb.lstrip("0")
                        add_valid_barcode(pb, barcode_list)

            # Try to extract barcode(s) from parts[8]
            if len(parts) >= 9:
                process_barcode_field(parts[8], parcel["barcodes"])

            # Try to extract barcode(s) from parts[9] (semicolon-separated), specifically semis[2]
            if len(parts) >= 10:
                semis = parts[9].split(";")
                if len(semis) >= 3:
                    process_barcode_field(semis[2], parcel["barcodes"])
                
                # Check for barcode error based on the first semi-colon part
                if semis and semis[0] != "6":
                    parcel["barcodeErr"] = True
            
            # --- MODIFIED: Volume Data Extraction from ItemPropertiesUpdate message ---
            # Based on the user's provided log line example, the volume data is in parts[12],
            # which is itself a semicolon-separated string.
            if len(parts) >= 13: # Ensure parts[12] exists
                volume_data_str = parts[12]
                volume_semis = volume_data_str.split(';')

                if len(volume_semis) >= 7: # Ensure enough sub-parts for length, width, height, box, real volume
                    try:
                        parcel["volume_data"]["length"] = float(volume_semis[2])
                    except (ValueError, IndexError):
                        pass
                    try:
                        parcel["volume_data"]["width"] = float(volume_semis[3])
                    except (ValueError, IndexError):
                        pass
                    try:
                        parcel["volume_data"]["height"] = float(volume_semis[4])
                    except (ValueError, IndexError):
                        pass
                    try:
                        parcel["volume_data"]["box_volume"] = float(volume_semis[5])
                    except (ValueError, IndexError):
                        pass
                    try:
                        parcel["volume_data"]["real_volume"] = float(volume_semis[6])
                    except (ValueError, IndexError):
                        pass
            # --- END MODIFIED ---

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
    
    # After processing all lines, iterate through parcels to set barcode_count
    for parcel_data in parcels.values():
        parcel_data["barcode_count"] = len(parcel_data["barcodes"])

    return list(parcels.values())

# --- Main execution ------------------------------------------------
if __name__ == "__main__":
    input_file = input("Enter the log file name (e.g., log.txt): ").strip()
    output_file = input_file.replace(".txt", ".json")

    try:
        with open(input_file, "r", encoding="utf-8") as f:
            log_text = f.read()

        parsed_data = parse_log(log_text)

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(parsed_data, f, indent=4)

        print(f"\n✅ Parsed data saved to '{output_file}'")
    except FileNotFoundError:
        print(f"Error: The file '{input_file}' was not found.")
    except Exception as e:
        print(f"An error occurred: {e}")