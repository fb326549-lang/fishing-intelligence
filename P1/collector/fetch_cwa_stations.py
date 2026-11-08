#!/usr/bin/env python3
"""Fetch CWA buoy/tide station metadata with a private API token.

Set CWA_AUTHORIZATION in the shell environment. Never put the token in this
repository, config files, browser JavaScript, or logs.
"""
from __future__ import annotations
import argparse, csv, json, os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import requests

ENDPOINT = "https://opendata.cwa.gov.tw/api/v1/rest/datastore/O-B0076-001"

def find_station_nodes(obj: Any):
    if isinstance(obj, dict):
        if "StationID" in obj and ("StationName" in obj or "StationNameEN" in obj):
            yield obj
        for value in obj.values():
            yield from find_station_nodes(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from find_station_nodes(value)

def find_status_node(obj: Any):
    if isinstance(obj, dict):
        if "StationStatus" in obj or "ObservedProperties" in obj:
            yield obj
        for value in obj.values():
            yield from find_status_node(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from find_status_node(value)

def flatten_station(station: dict[str, Any], status: dict[str, Any] | None):
    def val(key):
        value = station.get(key)
        return value if value not in ("", None) else None
    props = {}
    if status:
        for node in find_status_node(status):
            observed = node.get("ObservedProperties")
            if isinstance(observed, dict):
                for name, detail in observed.items():
                    if isinstance(detail, dict):
                        props[name] = detail.get("ObsStatus")
    return {
        "station_id": val("StationID"),
        "station_name": val("StationName"),
        "station_name_en": val("StationNameEN"),
        "longitude": val("StationLongitude"),
        "latitude": val("StationLatitude"),
        "station_type": val("StationAttribute"),
        "station_address": val("StationAddress"),
        "county": (station.get("County") or {}).get("CountyName"),
        "town": (station.get("Town") or {}).get("TownName"),
        "area": (station.get("Area") or {}).get("AreaName"),
        "station_status": (status or {}).get("StationStatus"),
        "observed_properties": json.dumps(props, ensure_ascii=False),
        "metadata_checked_at": datetime.now(timezone.utc).isoformat()
    }

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="data/cwa_stations")
    args = p.parse_args()
    token = os.environ.get("CWA_AUTHORIZATION")
    if not token:
        raise SystemExit("Missing CWA_AUTHORIZATION environment variable.")
    response = requests.get(ENDPOINT, params={"Authorization": token, "format": "JSON"},
                            timeout=30, headers={"User-Agent": "FishingIntelligence-P1/0.1"})
    response.raise_for_status()
    payload = response.json()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "O-B0076-001_raw.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    status_nodes = list(find_status_node(payload))
    rows = []
    for station in find_station_nodes(payload):
        sid = station.get("StationID")
        related = next((x for x in status_nodes if x.get("StationID") == sid), None)
        rows.append(flatten_station(station, related))
    # Deduplicate station records by station ID, preserving first occurrence.
    unique = {row["station_id"]: row for row in rows if row["station_id"]}
    rows = sorted(unique.values(), key=lambda x: (x["county"] or "", x["station_name"] or ""))
    if rows:
        with (out / "stations.csv").open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    print(f"Stations parsed: {len(rows)}")
    print(f"Raw response: {(out / 'O-B0076-001_raw.json').resolve()}")
    print(f"CSV: {(out / 'stations.csv').resolve()}")
    print("Check station_status and observed_properties; empty/0/2 do not mean live observations.")
if __name__ == "__main__":
    main()
