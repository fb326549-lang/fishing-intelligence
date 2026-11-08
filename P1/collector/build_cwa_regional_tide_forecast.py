#!/usr/bin/env python3
"""Build six-region CWA tide forecast event output from an explicit reviewed map.

Keeps each CWA location's high/low events separate. It does not average tide
heights across locations, interpolate between events, or infer catch scores.
"""
from __future__ import annotations
import argparse, csv, json
from collections import Counter, defaultdict
from pathlib import Path

REGIONS = {
    "yilan_suao": "宜蘭、蘇澳",
    "hualien_north": "花蓮北段",
    "hualien_south": "花蓮南段",
    "fengbin_shitiping": "豐濱、石梯坪",
    "chenggong_donghe": "成功、東河",
    "taitung_south": "台東南段",
}
REQUIRED = {"location_id", "location_name", "latitude", "longitude", "region_id",
            "mapping_status", "mapping_basis", "notes"}

def read_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True)
    p.add_argument("--mapping", required=True)
    p.add_argument("--out", required=True)
    a = p.parse_args()
    tide_rows, map_rows = read_csv(a.input), read_csv(a.mapping)
    if not tide_rows:
        raise SystemExit("Tide forecast input is empty.")
    if not map_rows or not REQUIRED.issubset(map_rows[0]):
        raise SystemExit("Tide mapping is empty or missing required columns.")

    mapping = {}
    for row in map_rows:
        lid = row["location_id"].strip()
        if not lid:
            raise SystemExit("Mapping contains a blank location_id.")
        if lid in mapping:
            raise SystemExit(f"Duplicate location_id in mapping: {lid}")
        status, region = row["mapping_status"], row["region_id"].strip()
        if status == "mapped" and region not in REGIONS:
            raise SystemExit(f"Mapped location {lid} has unsupported region_id: {region}")
        if status != "mapped" and region:
            raise SystemExit(f"Non-mapped location {lid} must have blank region_id.")
        mapping[lid] = row

    available_locations = {r["location_id"] for r in tide_rows}
    missing_from_feed = sorted(set(mapping) - available_locations)
    unexpected_rows = []
    output, unmapped_ids = [], set()
    region_location_counts = Counter()
    region_event_counts = Counter()
    for row in tide_rows:
        m = mapping.get(row["location_id"])
        if not m or m["mapping_status"] != "mapped":
            unmapped_ids.add(row["location_id"])
            continue
        if row["location_name"] != m["location_name"]:
            unexpected_rows.append(row["location_id"])
            raise SystemExit(f"Location name mismatch for {row['location_id']}: mapping='{m['location_name']}', feed='{row['location_name']}'")
        region = m["region_id"]
        out = dict(row)
        out.update({
            "region_id": region,
            "region_name": REGIONS[region],
            "mapping_status": m["mapping_status"],
            "mapping_basis": m["mapping_basis"],
            "mapping_notes": m["notes"],
        })
        output.append(out)
        region_location_counts[region] += 0
        region_event_counts[region] += 1

    # Count unique locations per region, not event rows.
    for region in REGIONS:
        region_location_counts[region] = len({r["location_id"] for r in output if r["region_id"] == region})
    out_path = Path(a.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(output[0].keys()) if output else list(tide_rows[0].keys()) + [
        "region_name", "mapping_status", "mapping_basis", "mapping_notes"
    ]
    with out_path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(output)
    summary = {
        "source": "CWA", "dataset_id": "F-A0021-001", "data_kind": "forecast",
        "mapped_event_rows": len(output),
        "mapped_unique_locations": len({r["location_id"] for r in output}),
        "unmapped_or_excluded_location_count": len(unmapped_ids),
        "mapping_locations_missing_from_feed": missing_from_feed,
        "regions": [
            {"region_id": rid, "region_name": name,
             "location_count": region_location_counts[rid],
             "event_count": region_event_counts[rid],
             "status": "available" if region_event_counts[rid] else "no_mapped_tide_locations"}
            for rid, name in REGIONS.items()
        ],
        "limitations": [
            "High/low tide forecast events only; not continuous tide observations.",
            "Events remain separated by CWA location; no regional mean tide height is calculated.",
            "No interpolation between events and no extrapolation to unmapped locations.",
            "Unmapped and offshore-island locations are excluded from the six mainland regions.",
            "Height datums remain separate and values remain in centimetres.",
            "Regional membership is an explicit P1 planning mapping, not an official CWA zone.",
        ],
    }
    out_path.with_name("regional_tide_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))

if __name__ == "__main__":
    main()
