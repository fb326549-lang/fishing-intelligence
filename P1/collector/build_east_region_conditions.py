#!/usr/bin/env python3
"""Aggregate CWA in-situ observations into six East Taiwan planning regions."""
from __future__ import annotations
import argparse
import csv
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

REGIONS = {
    "yilan_suao": "宜蘭、蘇澳",
    "hualien_north": "花蓮北段",
    "hualien_south": "花蓮南段",
    "fengbin_shitiping": "豐濱、石梯坪",
    "chenggong_donghe": "成功、東河",
    "taitung_south": "台東南段",
}
DIRECTION_VARIABLES = {"wave_direction_deg", "wind_direction_deg", "current_direction_deg"}
VARIABLES = {
    "wave_height_m": ("WaveHeight", "m", "浪高"),
    "wave_period_s": ("WavePeriod", "s", "浪週期"),
    "wave_direction_deg": ("WaveDirection", "degree", "浪向"),
    "sea_temperature_c": ("SeaTemperature", "°C", "海溫"),
    "tide_height_m": ("TideHeight", "m", "潮位"),
    "wind_speed_ms": ("PrimaryAnemometer_WindSpeed", "m/s", "風速"),
    "wind_direction_deg": ("PrimaryAnemometer_WindDirection", "degree", "風向"),
    "current_direction_deg": ("SeaCurrent_CurrentDirection", "degree", "海流方向"),
    "current_speed_ms": ("SeaCurrent_CurrentSpeed", "m/s", "海流速度"),
    "current_speed_knots": ("SeaCurrent_CurrentSpeedInKnots", "kn", "海流速度（節）"),
}

def read_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))

def num(value):
    try:
        if value is None or str(value).strip().lower() in ("", "none", "null", "nan", "n/a", "na"):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None

def mean_value(name, values):
    if not values:
        return None
    if name in DIRECTION_VARIABLES:
        radians = [math.radians(v) for v in values]
        x = sum(math.cos(v) for v in radians) / len(radians)
        y = sum(math.sin(v) for v in radians) / len(radians)
        if abs(x) < 1e-12 and abs(y) < 1e-12:
            return None
        return round((math.degrees(math.atan2(y, x)) + 360) % 360, 1)
    return round(sum(values) / len(values), 3)

def parse_status(value):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None

def parse_properties(value):
    try:
        obj = json.loads(value or "{}")
        return obj if isinstance(obj, dict) else {}
    except (TypeError, json.JSONDecodeError):
        return {}

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", default="output/normalized/O-B0075-001.csv")
    p.add_argument("--mapping", default="P1/stations/east_region_station_mapping.csv")
    p.add_argument("--stations", default="output/cwa_stations/stations.csv")
    p.add_argument("--out", default="output/east_region")
    a = p.parse_args()
    observations, mapping = read_csv(a.input), read_csv(a.mapping)
    inventory_rows = read_csv(a.stations) if Path(a.stations).exists() else []
    inventory = {r["station_id"]: r for r in inventory_rows if r.get("station_id")}

    # Region membership is the development mapping; live CWA status and
    # per-element ObsStatus are authoritative for current availability.
    station_region = {
        r["station_id"]: r["region_id"] for r in mapping
        if r.get("station_id") and r.get("region_id") in REGIONS
    }
    active_region_stations = defaultdict(set)
    station_observed_rows = defaultdict(set)
    buckets = defaultdict(lambda: defaultdict(list))
    bucket_station_values = defaultdict(lambda: defaultdict(set))
    unmapped = set()
    inactive_or_unknown = set()

    def station_allows(sid, source_field):
        meta = inventory.get(sid)
        if not meta:
            return True  # Do not silently discard if inventory metadata is absent.
        status = parse_status(meta.get("station_status"))
        if status != 1:
            return False
        props = parse_properties(meta.get("observed_properties"))
        # Map normalized weather-element field names to inventory property names.
        property_name = source_field
        if source_field.startswith("PrimaryAnemometer_"):
            property_name = source_field.replace("PrimaryAnemometer_", "")
        if source_field.startswith("SeaCurrent_"):
            property_name = source_field.replace("SeaCurrent_", "")
        element_status = props.get(property_name)
        if element_status is None:
            return True
        return parse_status(element_status) == 1

    for row in observations:
        sid = (row.get("station_id") or "").strip()
        region = station_region.get(sid)
        timestamp = row.get("valid_time", "")
        if not region:
            if sid:
                unmapped.add(sid)
            continue
        if not timestamp:
            continue
        meta = inventory.get(sid)
        if meta and parse_status(meta.get("station_status")) != 1:
            inactive_or_unknown.add(sid)
            continue
        active_region_stations[region].add(sid)
        station_observed_rows[(region, timestamp)].add(sid)

        for outname, (source, unit, label) in VARIABLES.items():
            value = num(row.get(source))
            if value is None or not station_allows(sid, source):
                continue
            buckets[(region, timestamp)][outname].append(value)
            bucket_station_values[(region, timestamp)][outname].add(sid)

    outdir = Path(a.out)
    outdir.mkdir(parents=True, exist_ok=True)
    series = []
    for (region, timestamp), values in sorted(buckets.items()):
        row = {
            "region_id": region, "region_name": REGIONS[region],
            "valid_time": timestamp, "source": "CWA",
            "data_kind": "observed",
            "stations_reporting_any_data": len(station_observed_rows[(region, timestamp)]),
        }
        for name in VARIABLES:
            vals = values.get(name, [])
            row[name] = mean_value(name, vals)
            row[name + "_sample_count"] = len(vals)
            row[name + "_station_count"] = len(bucket_station_values[(region, timestamp)].get(name, set()))
        series.append(row)

    fields = list(dict.fromkeys(k for row in series for k in row))
    with open(outdir / "east_region_conditions.csv", "w", encoding="utf-8-sig", newline="") as f:
        if fields:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(series)

    summaries = []
    for region, name in REGIONS.items():
        mapped_ids = {sid for sid, reg in station_region.items() if reg == region}
        active_ids = active_region_stations[region]
        region_rows = [r for r in series if r["region_id"] == region]
        latest_time = max((r["valid_time"] for r in region_rows), default=None)
        latest = next((r for r in reversed(region_rows) if r["valid_time"] == latest_time), None)
        coverage = {}
        for var, (source, unit, label) in VARIABLES.items():
            # Denominator includes only mapped stations whose live metadata says
            # they are transmitting and that advertise this specific element.
            eligible = set()
            for sid in mapped_ids:
                meta = inventory.get(sid)
                if not meta or parse_status(meta.get("station_status")) != 1:
                    continue
                props = parse_properties(meta.get("observed_properties"))
                prop = source
                if source.startswith("PrimaryAnemometer_"):
                    prop = source.replace("PrimaryAnemometer_", "")
                if source.startswith("SeaCurrent_"):
                    prop = source.replace("SeaCurrent_", "")
                if parse_status(props.get(prop)) == 1:
                    eligible.add(sid)
            reporting = bucket_station_values[(region, latest_time)].get(var, set()) if latest_time else set()
            coverage[var] = {
                "label": label, "unit": unit,
                "eligible_active_stations": len(eligible),
                "stations_with_data_latest_time": len(reporting),
                "coverage_ratio": round(len(reporting) / len(eligible), 3) if eligible else None,
                "status": "available" if reporting else ("not_reported" if eligible else "no_eligible_station"),
            }
        summaries.append({
            "region_id": region, "region_name": name,
            "mapped_station_count": len(mapped_ids),
            "active_stations_with_observations": len(active_ids),
            "latest_observation_time": latest_time,
            "latest_values": {v: latest.get(v) for v in VARIABLES} if latest else {},
            "variable_coverage": coverage,
            "status": "observed" if active_ids else "no_mapped_station_observations",
        })

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_dataset": "CWA O-B0075-001", "data_kind": "observed",
        "region_definition": "P1 planning mapping; not official CWA marine zones",
        "input_observation_rows": len(observations),
        "mapped_station_ids": sorted({r.get("station_id") for r in observations} & set(station_region)),
        "unmapped_station_ids": sorted(unmapped),
        "inactive_or_unknown_mapped_station_ids": sorted(inactive_or_unknown),
        "mapped_station_ids_missing_metadata": sorted(s for s in station_region if s not in inventory),
        "regions": summaries,
        "limitations": [
            "Only mapped CWA in-situ observations are included.",
            "Missing values remain null; no zero-fill or interpolation.",
            "Coverage denominator uses live station and element status where available.",
            "Latest available observation is not a forecast.",
            "Direction values use circular means; direction is undefined when vector components cancel.",
            "Sea-current values currently represent the provider's first reported layer; layer number is retained in normalized source CSV.",
            "No fishing score or species activity is inferred.",
        ],
    }
    (outdir / "east_region_summary.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("Input rows:", len(observations), "mapped stations:", len(report["mapped_station_ids"]),
          "unmapped IDs:", len(unmapped), "inactive mapped:", len(inactive_or_unknown))
    for region in summaries:
        print(region["region_name"], "active stations", region["active_stations_with_observations"],
              "latest", region["latest_observation_time"] or "no data")

if __name__ == "__main__":
    main()
