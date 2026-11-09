#!/usr/bin/env python3
"""Build a compact, source-labelled CWA regional observation snapshot for the PWA."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

REGION_ORDER = [
    "yilan_suao",
    "hualien_north",
    "hualien_south",
    "fengbin_shitiping",
    "chenggong_donghe",
    "taitung_south",
]


def read_summary(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Cannot read regional summary {path}: {exc}")
    if not isinstance(data, dict) or not isinstance(data.get("regions"), list):
        raise SystemExit(f"Invalid regional summary schema: {path}")
    by_id = {}
    for row in data["regions"]:
        region_id = row.get("region_id")
        if not region_id or region_id in by_id:
            raise SystemExit(f"Missing or duplicate region_id in {path}: {region_id}")
        by_id[region_id] = row
    missing = sorted(set(REGION_ORDER) - set(by_id))
    extra = sorted(set(by_id) - set(REGION_ORDER))
    if missing or extra:
        raise SystemExit(f"Region set mismatch in {path}; missing={missing}, extra={extra}")
    return {key: by_id[key] for key in REGION_ORDER}


def compact_region(row: dict, scope: str) -> dict:
    mapped = int(row.get("mapped_station_count") or 0)
    stations = int(row.get("stations_with_observations") or 0)
    status = row.get("status", "unknown")
    coverage_status = (
        "no_cwa_station_coverage" if mapped == 0
        else "no_observations_in_window" if stations == 0
        else "observations_available"
    )
    return {
        "data_kind": "observed",
        "temporal_scope": scope,
        "latest_observation_time": row.get("latest_observation_time"),
        "mapped_station_count": mapped,
        "stations_with_observations": stations,
        "latest_values": row.get("latest_values") or {},
        "variable_coverage": row.get("variable_coverage") or {},
        "status": status,
        "coverage_status": coverage_status,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--observed-48h", required=True)
    parser.add_argument("--observed-30d", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--generated-at", default=datetime.now(timezone.utc).isoformat())
    args = parser.parse_args()

    short = read_summary(Path(args.observed_48h))
    long = read_summary(Path(args.observed_30d))
    regions = {}
    for region_id in REGION_ORDER:
        name = short[region_id].get("region_name") or long[region_id].get("region_name") or region_id
        if long[region_id].get("region_name") and name != long[region_id].get("region_name"):
            raise SystemExit(f"Region name mismatch between 48h and 30d summaries: {region_id}")
        regions[region_id] = {
            "region_name": name,
            "observed_48h": compact_region(short[region_id], "rolling_48_hour"),
            "observed_30d": compact_region(long[region_id], "rolling_30_day"),
        }

    result = {
        "schema_version": 1,
        "source": "CWA",
        "data_kind": "regional_in_situ_observations",
        "generated_at": args.generated_at,
        "region_order": REGION_ORDER,
        "regions": regions,
        "limitations": [
            "Region IDs are P1 planning zones, not official CWA marine forecast boundaries.",
            "Regional values are means of mapped stations reporting at the same valid time; they are not point measurements at the user's exact fishing location.",
            "Missing variables remain null and must not be interpreted as zero.",
            "The 30-day dataset is a rolling historical window, not a forecast and not 30 independent samples per daily refresh.",
            "No CWA station is currently mapped to hualien_south; that region is explicitly marked no_cwa_station_coverage.",
            "These observations are separate from Open-Meteo model forecasts and must not be blended without retaining source and valid time.",
        ],
    }
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\\n", encoding="utf-8")
    print(json.dumps({
        "output": str(output),
        "region_count": len(regions),
        "hualien_south_48h_status": regions["hualien_south"]["observed_48h"]["coverage_status"],
        "hualien_south_30d_status": regions["hualien_south"]["observed_30d"]["coverage_status"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
