#!/usr/bin/env python3
"""Pivot variable-level 6/12/24h forecast values into six regional records.

This is a presentation/analysis layer only: no blending with CWA observations,
no interpolation, and no invented values. Missing variables remain blank and
are reflected in explicit completeness fields.
"""
from __future__ import annotations
import argparse, csv, json
from pathlib import Path

VARIABLES = {
    "wave_height_m": "wave_height",
    "wave_direction_deg": "wave_direction",
    "wave_period_s": "wave_period",
    "sea_surface_temperature_c": "sea_surface_temperature",
    "sea_level_height_msl_m": "sea_level_height_msl",
    "ocean_current_velocity_ms": "ocean_current_velocity",
    "ocean_current_direction_deg": "ocean_current_direction",
    "wind_speed_10m_ms": "wind_speed_10m",
    "wind_direction_10m_deg": "wind_direction_10m",
}
MARINE = {
    "wave_height_m": "wave_height",
    "wave_direction_deg": "wave_direction",
    "wave_period_s": "wave_period",
    "sea_surface_temperature_c": "sea_surface_temperature",
    "sea_level_height_msl_m": "sea_level_height_msl",
    "ocean_current_velocity_ms": "ocean_current_velocity",
    "ocean_current_direction_deg": "ocean_current_direction",
}
WEATHER = {
    "wind_speed_10m_ms": "wind_speed_10m",
    "wind_direction_10m_deg": "wind_direction_10m",
}

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True)
    p.add_argument("--out", required=True)
    a = p.parse_args()
    with open(a.input, encoding="utf-8-sig", newline="") as f:
        source_rows = list(csv.DictReader(f))
    if not source_rows:
        raise SystemExit("Horizon CSV is empty.")

    grouped = {}
    for row in source_rows:
        key = (row["location_id"], row["location_name"], int(row["horizon_hours"]))
        grouped.setdefault(key, {})[row["variable_code"]] = row

    output = []
    for (region_id, region_name, horizon), values in sorted(grouped.items()):
        record = {
            "region_id": region_id,
            "region_name": region_name,
            "horizon_hours": horizon,
            "target_time": next(iter(values.values()))["target_time"],
            "marine_valid_time": "",
            "weather_valid_time": "",
        }
        available = 0
        marine_available = 0
        weather_available = 0
        missing = []
        for output_name, variable in VARIABLES.items():
            item = values.get(variable)
            valid = bool(item and item["quality_status"] == "available")
            record[output_name] = item["value"] if valid else ""
            if valid:
                available += 1
                if variable in MARINE.values():
                    marine_available += 1
                    record["marine_valid_time"] = item["selected_valid_time"]
                if variable in WEATHER.values():
                    weather_available += 1
                    record["weather_valid_time"] = item["selected_valid_time"]
            else:
                missing.append(output_name)
        record["available_variable_count"] = available
        record["expected_variable_count"] = len(VARIABLES)
        record["data_completeness_pct"] = round(available / len(VARIABLES) * 100, 1)
        record["marine_available_count"] = marine_available
        record["marine_expected_count"] = len(MARINE)
        record["weather_available_count"] = weather_available
        record["weather_expected_count"] = len(WEATHER)
        record["missing_variables"] = ";".join(missing)
        record["data_kind"] = "forecast/modelled"
        output.append(record)

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(output[0].keys()))
        writer.writeheader()
        writer.writerows(output)

    summary = {
        "regional_records": len(output),
        "regions": len({r["region_id"] for r in output}),
        "horizons_hours": sorted({r["horizon_hours"] for r in output}),
        "average_completeness_pct": round(sum(r["data_completeness_pct"] for r in output) / len(output), 1),
        "records_with_missing_variables": sum(bool(r["missing_variables"]) for r in output),
        "data_kind": "forecast/modelled",
        "note": "Completeness is the fraction of nine selected forecast variables available; it is not a forecast accuracy score.",
    }
    out.with_name("regional_forecast_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
