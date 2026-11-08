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
EXPECTED_VARIABLES = 9

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
            if expected != EXPECTED_VARIABLES:
                errors.append(f"regional row {index}: expected_variable_count={expected}, expected {EXPECTED_VARIABLES}")
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

    missing_pairs = expected_pairs - seen
    if missing_pairs:
        errors.append(f"missing {len(missing_pairs)} region/horizon combinations")
    if len(horizons) != len(REGIONS) * len(HORIZONS) * EXPECTED_VARIABLES:
        errors.append(
            f"horizon CSV row count {len(horizons)} does not equal "
            f"{len(REGIONS) * len(HORIZONS) * EXPECTED_VARIABLES}"
        )
    for index, row in enumerate(horizons, start=2):
        if row.get("data_kind") not in ("forecast", "modelled", "forecast/modelled"):
            errors.append(f"horizon row {index}: unexpected data_kind={row.get('data_kind')!r}")
        if row.get("quality_status") == "available" and row.get("value") in ("", None):
            errors.append(f"horizon row {index}: available value is blank")
        if row.get("quality_status") != "available" and row.get("value") not in ("", None):
            errors.append(f"horizon row {index}: missing status has nonblank value")

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
