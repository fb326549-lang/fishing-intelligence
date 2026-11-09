#!/usr/bin/env python3
"""Validate six-region Open-Meteo forecast output and report partial coverage."""
from __future__ import annotations
import argparse
import csv
import json
from pathlib import Path

REGIONS = {
    "yilan_suao", "hualien_north", "hualien_south",
    "fengbin_shitiping", "chenggong_donghe", "taitung_south",
}
HORIZONS = {6, 12, 24}
REGIONAL_VARIABLES = 9
SOURCE_VARIABLES = {
    "wave_height", "wave_direction", "wave_period",
    "wind_wave_height", "wind_wave_direction", "wind_wave_period",
    "swell_wave_height", "swell_wave_direction", "swell_wave_period",
    "sea_surface_temperature", "sea_level_height_msl",
    "ocean_current_velocity", "ocean_current_direction",
    "temperature_2m", "relative_humidity_2m", "precipitation",
    "precipitation_probability", "showers", "weather_code", "pressure_msl", "wind_speed_10m",
    "wind_direction_10m", "wind_gusts_10m", "cloud_cover",
}

def load_csv(path: Path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", required=True)
    parser.add_argument("--out", default="forecast_validation.json")
    args = parser.parse_args()
    folder = Path(args.directory)
    errors, warnings = [], []
    horizon_path = folder / "forecast_horizons_6_12_24.csv"
    regional_path = folder / "regional_forecast_conditions_6_12_24.csv"
    manifest_path = folder / "manifest.json"
    for path in (horizon_path, regional_path, manifest_path):
        if not path.exists():
            errors.append(f"missing required file: {path.name}")
    if errors:
        result = {"status": "failed", "errors": errors, "warnings": warnings}
        Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False))
        return 1

    horizons = load_csv(horizon_path)
    regional = load_csv(regional_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected_pairs = {(region, horizon) for region in REGIONS for horizon in HORIZONS}
    seen = set()
    for index, row in enumerate(regional, start=2):
        try:
            pair = (row["region_id"], int(row["horizon_hours"]))
        except (KeyError, ValueError):
            errors.append(f"regional row {index}: invalid region/horizon")
            continue
        if pair in seen:
            errors.append(f"regional row {index}: duplicate region/horizon {pair}")
        seen.add(pair)
        if pair not in expected_pairs:
            errors.append(f"regional row {index}: unexpected region/horizon {pair}")
        if row.get("data_kind") != "forecast/modelled":
            errors.append(f"regional row {index}: data_kind must be forecast/modelled")
        try:
            available = int(row["available_variable_count"])
            expected = int(row["expected_variable_count"])
            pct = float(row["data_completeness_pct"])
            if expected != REGIONAL_VARIABLES:
                errors.append(f"regional row {index}: expected {REGIONAL_VARIABLES} regional variables, got {expected}")
            if not 0 <= available <= expected:
                errors.append(f"regional row {index}: invalid available count {available}")
            calculated = round(available / expected * 100, 1) if expected else 0
            if pct != calculated:
                errors.append(f"regional row {index}: completeness mismatch {pct} != {calculated}")
            missing = [x for x in (row.get("missing_variables") or "").split(";") if x]
            if len(missing) != expected - available:
                errors.append(f"regional row {index}: missing variable list/count mismatch")
        except (KeyError, ValueError, ZeroDivisionError):
            errors.append(f"regional row {index}: invalid completeness fields")

    if seen != expected_pairs:
        errors.append(f"regional output does not contain exactly {len(expected_pairs)} region/horizon combinations")

    source_groups = {}
    for index, row in enumerate(horizons, start=2):
        try:
            key = (row["location_id"], int(row["horizon_hours"]))
            variable = row["variable_code"]
        except (KeyError, ValueError):
            errors.append(f"horizon row {index}: invalid location/horizon/variable key")
            continue
        source_groups.setdefault(key, set())
        if variable in source_groups[key]:
            errors.append(f"horizon row {index}: duplicate variable {variable} for {key}")
        source_groups[key].add(variable)
        if row.get("data_kind") not in ("forecast", "modelled", "forecast/modelled"):
            errors.append(f"horizon row {index}: unexpected data_kind={row.get('data_kind')!r}")
        if row.get("quality_status") == "available" and row.get("value") in ("", None):
            errors.append(f"horizon row {index}: available value is blank")
        if row.get("quality_status") != "available" and row.get("value") not in ("", None):
            errors.append(f"horizon row {index}: missing status has nonblank value")

    if set(source_groups) != expected_pairs:
        errors.append("source horizon CSV does not contain exactly all six-region/three-horizon groups")
    for key, variables in source_groups.items():
        if variables != SOURCE_VARIABLES:
            errors.append(f"source group {key}: expected {len(SOURCE_VARIABLES)} unique variables, found {len(variables)}")

    locations = manifest.get("locations", [])
    marine_partial = [x.get("id") for x in locations if x.get("marine", {}).get("status") == "partial"]
    marine_errors = [x.get("id") for x in locations if x.get("marine", {}).get("status") == "error"]
    weather_errors = [x.get("id") for x in locations if x.get("weather", {}).get("status") == "error"]
    if marine_partial:
        warnings.append("Marine forecast partial coverage: " + ", ".join(marine_partial))
    if marine_errors:
        warnings.append("Marine forecast errors: " + ", ".join(marine_errors))
    if weather_errors:
        warnings.append("Weather forecast errors: " + ", ".join(weather_errors))
    if len(locations) != len(REGIONS):
        errors.append(f"manifest has {len(locations)} locations; expected {len(REGIONS)}")

    result = {
        "status": "passed" if not errors else "failed",
        "regions_expected": len(REGIONS),
        "regional_records": len(regional),
        "horizon_variable_rows": len(horizons),
        "region_horizon_combinations": len(seen),
        "source_variables_per_region_horizon": len(SOURCE_VARIABLES),
        "marine_partial_locations": marine_partial,
        "marine_error_locations": marine_errors,
        "weather_error_locations": weather_errors,
        "error_count": len(errors),
        "errors": errors,
        "warnings": warnings,
        "scope_note": "Structural and completeness validation only; not a forecast-accuracy assessment.",
    }
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if not errors else 1

if __name__ == "__main__":
    raise SystemExit(main())
