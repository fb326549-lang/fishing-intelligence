#!/usr/bin/env python3
"""Export mapped CWA high/low tide events as a compact PWA feed.

Heights remain separated by datum. This feed contains forecast turning events,
not continuous observed tide heights or tidal-current velocity.
"""
from __future__ import annotations
import argparse, csv, json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

REGIONS = {"yilan_suao", "hualien_north", "hualien_south", "fengbin_shitiping", "chenggong_donghe", "taitung_south"}

def number(value):
    if value is None or str(value).strip() == "":
        return None
    try:
        return float(value) if "." in str(value) else int(value)
    except (TypeError, ValueError):
        return None

def build_payload(rows, generated_at=None):
    grouped = defaultdict(dict)
    excluded = 0
    for row in rows:
        region = str(row.get("region_id") or "").strip()
        location_id = str(row.get("location_id") or "").strip()
        valid_time = str(row.get("valid_time") or "").strip()
        tide = str(row.get("tide") or "").strip()
        lat, lon = number(row.get("latitude")), number(row.get("longitude"))
        if region not in REGIONS or not location_id or not valid_time or tide not in {"滿潮", "高潮", "乾潮", "低潮"} or lat is None or lon is None:
            excluded += 1
            continue
        try:
            datetime.fromisoformat(valid_time.replace("Z", "+00:00"))
        except ValueError:
            excluded += 1
            continue
        location = grouped[location_id].setdefault("location", {
            "location_id": location_id,
            "location_name": str(row.get("location_name") or location_id),
            "latitude": lat,
            "longitude": lon,
            "region_id": region,
            "events": [],
        })
        if location["region_id"] != region or location["latitude"] != lat or location["longitude"] != lon:
            raise ValueError(f"Conflicting location metadata for {location_id}")
        event = {
            "valid_time": valid_time,
            "tide": "滿潮" if tide in {"滿潮", "高潮"} else "乾潮",
            "height_above_local_msl_cm": number(row.get("height_above_local_msl_cm")),
            "height_above_chart_datum_cm": number(row.get("height_above_chart_datum_cm")),
            "height_above_twvd_cm": number(row.get("height_above_twvd_cm")),
            "tide_range": str(row.get("tide_range") or ""),
        }
        location["events"].append(event)
    locations = []
    for item in grouped.values():
        location = item["location"]
        unique = {(e["valid_time"], e["tide"]): e for e in location["events"]}
        location["events"] = sorted(unique.values(), key=lambda e: e["valid_time"])
        locations.append(location)
    locations.sort(key=lambda x: (x["region_id"], x["location_name"], x["location_id"]))
    if not locations:
        raise ValueError("No mapped CWA tide forecast locations to publish")
    return {
        "schema_version": 1,
        "source": "CWA F-A0021-001",
        "generated_at_utc": generated_at or datetime.now(timezone.utc).isoformat(),
        "timezone": "Asia/Taipei",
        "regions": sorted(REGIONS),
        "location_count": len(locations),
        "event_count": sum(len(x["events"]) for x in locations),
        "excluded_event_row_count": excluded,
        "interpretation": "Official high/low tide forecast events only. Heights retain separate local MSL, chart datum, and TWVD fields; this is not continuous tide observation or tidal-current velocity.",
        "locations": locations,
    }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    with args.input.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    payload = build_payload(rows)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(json.dumps({"status": "published", "locations": payload["location_count"], "events": payload["event_count"], "excluded_rows": payload["excluded_event_row_count"]}, ensure_ascii=False))

if __name__ == "__main__":
    main()
