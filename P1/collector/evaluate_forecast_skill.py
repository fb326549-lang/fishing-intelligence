#!/usr/bin/env python3
"""Evaluate archived Open-Meteo forecast vintages against time-aligned CWA observations.

This is a retrospective verification layer, not a live fish-activity score.
Only same-region, same-valid-hour forecast/observation pairs are compared.
"""
from __future__ import annotations
import argparse
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

VARIABLES = {
    "wave_height_m": "wave_height_m",
    "wave_period_s": "wave_period_s",
    "sea_surface_temperature_c": "sea_surface_temperature_c",
    "wind_speed_ms": "wind_speed_10m_ms",
    "wind_direction_deg": "wind_direction_10m_deg",
    "current_speed_ms": "ocean_current_velocity_ms",
    "current_direction_deg": "ocean_current_direction_deg",
}
DIRECTION_VARIABLES = {"wind_direction_deg", "current_direction_deg"}
LEAD_BANDS = ((0, 6, "0-6h"), (6, 12, "6-12h"), (12, 24, "12-24h"), (24, 48, "24-48h"), (48, float("inf"), "48h+"))

def parse_time(value, label="timestamp"):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} is required")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} is not valid ISO-8601: {value!r}") from exc
    if result.tzinfo is None:
        raise ValueError(f"{label} must include a timezone offset")
    return result.astimezone(timezone.utc)

def numeric(value):
    if value is None or value == "":
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None

def absolute_error(forecast, observed, circular=False):
    difference = abs(forecast - observed)
    return min(difference, 360.0 - difference) if circular else difference

def lead_band(hours):
    for lower, upper, label in LEAD_BANDS:
        if lower <= hours < upper:
            return label
    return "unknown"

def load_archive(archive_root):
    base = archive_root / "hourly_environment"
    observations = {}
    forecasts = defaultdict(list)
    files = sorted(base.glob("[0-9][0-9][0-9][0-9]/[0-9][0-9]/[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9].jsonl"))
    for path in files:
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                region = row["region_id"]
                valid = parse_time(row["valid_time"], f"{path}:{line_no} valid_time")
                collected = parse_time(row["collected_at"], f"{path}:{line_no} collected_at")
                kind = row["data_type"]
                environment = row.get("environment")
                if not isinstance(environment, dict):
                    raise ValueError(f"{path}:{line_no}: environment must be an object")
            except (KeyError, json.JSONDecodeError) as exc:
                raise ValueError(f"{path}:{line_no}: malformed archive record: {exc}") from exc
            key = (region, valid)
            if kind == "observation":
                current = observations.get(key)
                if current is None or collected > current[0]:
                    observations[key] = (collected, row)
            elif kind == "forecast" and collected <= valid:
                forecasts[key].append((collected, row))
    return observations, forecasts, len(files)

def build_verification(archive_root, minimum_pairs=5):
    observations, forecasts, partition_count = load_archive(archive_root)
    per_variable = defaultdict(list)
    matched_forecast_keys = set()
    matched_hours = set()
    for key, vintage_rows in forecasts.items():
        observation_entry = observations.get(key)
        if observation_entry is None:
            continue
        observed = observation_entry[1].get("environment", {})
        for collected, forecast_row in vintage_rows:
            lead_hours = (parse_time(forecast_row["valid_time"]) - collected).total_seconds() / 3600
            if lead_hours < 0:
                continue
            forecast_env = forecast_row.get("environment", {})
            vintage_matched = False
            for metric, field in VARIABLES.items():
                fv = numeric(forecast_env.get(field))
                ov = numeric(observed.get(field))
                if fv is None or ov is None:
                    continue
                error = absolute_error(fv, ov, metric in DIRECTION_VARIABLES)
                per_variable[metric].append({
                    "region_id": key[0],
                    "valid_time": forecast_row["valid_time"],
                    "forecast_collected_at": forecast_row["collected_at"],
                    "observation_collected_at": observation_entry[0].isoformat(),
                    "lead_hours": round(lead_hours, 3),
                    "lead_band": lead_band(lead_hours),
                    "forecast": fv,
                    "observed": ov,
                    "absolute_error": error,
                    "signed_error": ((fv - ov + 180) % 360 - 180) if metric in DIRECTION_VARIABLES else fv - ov,
                })
                vintage_matched = True
            if vintage_matched:
                matched_forecast_keys.add((key[0], key[1], collected))
                matched_hours.add(key)
    summaries = {}
    for metric, pairs in sorted(per_variable.items()):
        errors = [p["absolute_error"] for p in pairs]
        signed = [p["signed_error"] for p in pairs]
        bands = {}
        for _, _, label in LEAD_BANDS:
            selected = [p["absolute_error"] for p in pairs if p["lead_band"] == label]
            if selected:
                bands[label] = {
                    "sample_count": len(selected),
                    "mae": round(sum(selected) / len(selected), 4),
                }
        enough = len(errors) >= minimum_pairs
        summaries[metric] = {
            "sample_count": len(errors),
            "status": "exploratory_metrics" if enough else "insufficient_sample",
            "mae": round(sum(errors) / len(errors), 4) if errors else None,
            "rmse": round(math.sqrt(sum(x*x for x in errors) / len(errors)), 4) if errors else None,
            "mean_bias": round(sum(signed) / len(signed), 4) if signed else None,
            "lead_bands": bands,
        }
    matched_variable_pairs = sum(item["sample_count"] for item in summaries.values())
    variables_with_metrics = sum(item["status"] == "exploratory_metrics" for item in summaries.values())
    if not matched_hours:
        verification_status = "awaiting_time_aligned_observations"
    elif not matched_variable_pairs:
        verification_status = "matched_hours_without_comparable_variables"
    elif variables_with_metrics:
        verification_status = "exploratory_metrics_available"
    else:
        verification_status = "exploratory_pairs_below_minimum_sample"
    return {
        "schema_version": "1.0.0",
        "status": verification_status,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "method": "exact_region_and_valid_hour_join_latest_observation_revision_all_archived_forecast_vintages",
        "archive_partition_count": partition_count,
        "observation_valid_hours_available": len(observations),
        "forecast_valid_hours_with_vintages": len(forecasts),
        "forecast_vintages_considered": sum(len(items) for items in forecasts.values()),
        "forecast_observation_hour_pairs": len(matched_hours),
        "forecast_vintages_with_any_comparable_variable": len(matched_forecast_keys),
        "matched_variable_pairs": matched_variable_pairs,
        "variables_with_exploratory_metrics": variables_with_metrics,
        "minimum_pairs_for_exploratory_metrics": minimum_pairs,
        "variables": summaries,
        "limitations": [
            "Only exact same-region and same-valid-hour pairs are compared; no nearest-time substitution or interpolation.",
            "All archived forecast vintages are retained, so repeated valid hours represent different forecast lead times, not independent observations.",
            "CWA regional station aggregates are not point measurements at a fishing location.",
            "MAE and RMSE describe historical paired errors only; they do not guarantee future accuracy or local nearshore accuracy.",
            "Direction errors use the shortest circular angular distance.",
            "Variables with fewer than the minimum sample count are marked insufficient_sample.",
        ],
    }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--minimum-pairs", type=int, default=5)
    args = parser.parse_args()
    if args.minimum_pairs < 1:
        parser.error("--minimum-pairs must be at least 1")
    result = build_verification(args.archive_root, args.minimum_pairs)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": "generated",
        "forecast_observation_hour_pairs": result["forecast_observation_hour_pairs"],
        "forecast_vintages_with_any_comparable_variable": result["forecast_vintages_with_any_comparable_variable"],
        "variables_with_metrics": sum(v["status"] == "exploratory_metrics" for v in result["variables"].values()),
        "out": str(args.out),
    }, ensure_ascii=False, sort_keys=True))

if __name__ == "__main__":
    main()
