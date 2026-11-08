#!/usr/bin/env python3
"""Fetch CWA buoy/tide station metadata (O-B0076-001).

This is a raw-data download dataset, so use CWA's file API rather than the
REST datastore endpoint. Keep CWA_AUTHORIZATION in a GitHub Actions secret.
"""
from __future__ import annotations
import argparse, csv, json, os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET
import requests

ENDPOINT = "https://opendata.cwa.gov.tw/fileapi/v1/opendataapi/O-B0076-001"

def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]

def xml_to_obj(element: ET.Element) -> Any:
    children = list(element)
    if not children:
        return (element.text or "").strip()
    result = {}
    for child in children:
        key = local_name(child.tag)
        value = xml_to_obj(child)
        if key in result:
            if not isinstance(result[key], list):
                result[key] = [result[key]]
            result[key].append(value)
        else:
            result[key] = value
    return result

def find_location_nodes(obj: Any):
    if isinstance(obj, dict):
        if isinstance(obj.get("Station"), dict):
            yield obj
        for value in obj.values():
            yield from find_location_nodes(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from find_location_nodes(value)

def as_text(value):
    if isinstance(value, (str, int, float)):
        return value
    return None

def flatten_station(location: dict[str, Any]):
    station = location.get("Station") or {}
    status = location.get("StationObsStatus") or {}
    props = {}
    observed = status.get("ObservedProperties") or {}
    if isinstance(observed, dict):
        for name, detail in observed.items():
            if isinstance(detail, dict):
                props[name] = as_text(detail.get("ObsStatus"))
    def nested(name, key):
        value = station.get(name) or {}
        return value.get(key) if isinstance(value, dict) else None
    return {
        "station_id": as_text(station.get("StationID")),
        "station_name": as_text(station.get("StationName")),
        "station_name_en": as_text(station.get("StationNameEN")),
        "longitude": as_text(station.get("StationLongitude")),
        "latitude": as_text(station.get("StationLatitude")),
        "station_type": as_text(station.get("StationAttribute")),
        "station_address": as_text(station.get("StationAddress")),
        "county": nested("County", "CountyName"),
        "town": nested("Town", "TownName"),
        "area": nested("Area", "AreaName"),
        "station_status": as_text(status.get("StationStatus")),
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
    response = requests.get(
        ENDPOINT,
        params={"Authorization": token, "format": "JSON"},
        timeout=30,
        headers={"User-Agent": "FishingIntelligence-P1/0.2"}
    )
    if response.status_code >= 400:
        # Do not print the request URL: it contains the credential.
        raise SystemExit(f"CWA download failed: HTTP {response.status_code}. Check dataset download route, authorization and access.")
    content_type = response.headers.get("Content-Type", "").lower()
    body = response.content
    try:
        if "json" in content_type or body.lstrip().startswith((b"{", b"[")):
            payload = response.json()
        else:
            root = ET.fromstring(body)
            payload = xml_to_obj(root)
    except Exception as exc:
        raise SystemExit(f"CWA response could not be parsed ({type(exc).__name__}). Check the dataset's supported format.")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "O-B0076-001_raw_response.txt").write_bytes(body)
    rows = [flatten_station(loc) for loc in find_location_nodes(payload)]
    unique = {row["station_id"]: row for row in rows if row["station_id"]}
    rows = sorted(unique.values(), key=lambda x: (x["county"] or "", x["station_name"] or ""))
    if not rows:
        raise SystemExit("Download succeeded but no station records matched the expected schema; inspect raw response before changing the parser.")
    with (out / "stations.csv").open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Stations parsed: {len(rows)}")
    print(f"Raw response saved: {(out / 'O-B0076-001_raw_response.txt').name}")
    print(f"CSV saved: {(out / 'stations.csv').name}")
    print("Review station_status and observed_properties; 0 means no observation, 1 transmitting, 2 stopped, blank means no return.")

if __name__ == "__main__":
    main()
