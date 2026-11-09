#!/usr/bin/env python3
"""Normalize hourly Open-Meteo forecasts and CWA observations into P2 JSONL.

Forecast and observation records are kept separate. No temporal interpolation,
regional substitution, tide-phase inference, or tide-height/current conversion.
"""
from __future__ import annotations
import argparse, csv, json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

REGIONS = {"yilan_suao", "hualien_north", "hualien_south", "fengbin_shitiping", "chenggong_donghe", "taitung_south"}
MARINE_MAP = {
    "wave_height": ("wave_height_m", float),
    "wave_period": ("wave_period_s", float),
    "wave_direction": ("wave_direction_deg", float),
    "sea_surface_temperature": ("sea_surface_temperature_c", float),
    "sea_level_height_msl": ("sea_level_height_msl_m", float),
    "ocean_current_velocity": ("ocean_current_velocity_ms", float),
    "ocean_current_direction": ("ocean_current_direction_deg", float),
}
WEATHER_MAP = {
    "wind_speed_10m": ("wind_speed_10m_ms", float),
    "wind_direction_10m": ("wind_direction_10m_deg", float),
    "precipitation": ("precipitation_mm_h", float),
    "showers": ("showers_mm_h", float),
    "precipitation_probability": ("precipitation_probability_pct", float),
    "weather_code": ("weather_code", int),
}
MARINE_URL = "https://marine-api.open-meteo.com/v1/marine"
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"
CWA_URLS = {
    "O-B0075-001": "https://opendata.cwa.gov.tw/dataset/observation/O-B0075-001",
    "O-B0075-002": "https://opendata.cwa.gov.tw/dataset/observation/O-B0075-002",
}

def parse_dt(value: str, timezone_name: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=ZoneInfo(timezone_name))

def number(value, cast=float):
    if value is None or str(value).strip().lower() in {"", "none", "null", "nan", "n/a"}:
        return None
    try:
        return cast(value)
    except (TypeError, ValueError):
        return None

def thunderstorm_risk(code):
    if code is None:
        return "unknown"
    # WMO weather interpretation codes 95, 96 and 99 denote thunderstorms.
    return "high" if code in {95, 96, 99} else "none"

def read_daily_sunrise_sunset(forecast_dir: Path, region_id: str):
    path = forecast_dir / f"{region_id}_weather_raw.json"
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    daily = payload.get("daily") or {}
    result = {}
    dates = daily.get("time") or []
    sunrises, sunsets = daily.get("sunrise") or [], daily.get("sunset") or []
    for i, day in enumerate(dates):
        result[day] = {
            "sunrise": sunrises[i] if i < len(sunrises) else None,
            "sunset": sunsets[i] if i < len(sunsets) else None,
        }
    return result

def build_forecast_rows(csv_path: Path, forecast_dir: Path, timezone_name: str):
    grouped = {}
    with csv_path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise ValueError("Forecast CSV is empty")
    for row in rows:
        region = row.get("location_id")
        if region not in REGIONS:
            raise ValueError(f"Unknown forecast region: {region}")
        valid = parse_dt(row["valid_time"], timezone_name)
        key = (region, valid.isoformat())
        item = grouped.setdefault(key, {
            "region_id": region, "valid_time": valid.isoformat(),
            "collected_at": row["fetched_at"], "environment": {},
            "source_records": {}, "quality_flags": set(),
        })
        fetched = parse_dt(row["fetched_at"], "UTC")
        if fetched > parse_dt(item["collected_at"], "UTC"):
            item["collected_at"] = row["fetched_at"]
        code = row.get("variable_code")
        mapping = MARINE_MAP.get(code) or WEATHER_MAP.get(code)
        if not mapping:
            continue
        field, cast = mapping
        item["environment"][field] = number(row.get("value"), cast)
        source = row.get("source") or "Open-Meteo"
        if source == "open-meteo-marine":
            dataset, url = "marine-api", MARINE_URL
        else:
            dataset, url = "forecast-api", WEATHER_URL
        item["source_records"][dataset] = {
            "source_id": "Open-Meteo", "dataset": dataset, "url": url,
            "retrieved_at": row["fetched_at"],
        }
        if row.get("value") in ("", None):
            item["quality_flags"].add(f"missing_{field}")
    output = []
    for (region, valid), item in sorted(grouped.items()):
        day = parse_dt(valid, timezone_name).date().isoformat()
        sun = read_daily_sunrise_sunset(forecast_dir, region).get(day, {})
        env = item["environment"]
        code = env.get("weather_code")
        env["thunderstorm_risk"] = thunderstorm_risk(code)
        env["sunrise"] = parse_dt(sun["sunrise"], timezone_name).isoformat() if sun.get("sunrise") else None
        env["sunset"] = parse_dt(sun["sunset"], timezone_name).isoformat() if sun.get("sunset") else None
        expected = len(MARINE_MAP) + len(WEATHER_MAP) + 3
        available = sum(v is not None and not (k == "thunderstorm_risk" and v == "unknown") for k, v in env.items())
        output.append({
            "schema_version": "1.0.0", "region_id": region,
            "valid_time": item["valid_time"],
            "collected_at": parse_dt(item["collected_at"], "UTC").isoformat(),
            "data_type": "forecast",
            "source_records": list(item["source_records"].values()),
            "environment": env,
            "completeness": {"available_fields": available, "expected_fields": expected, "ratio": round(available / expected, 6)},
            "quality": {
                "status": "good" if available == expected else "partial",
                "confidence": "unknown",
                "flags": sorted(item["quality_flags"]) + (["sunrise_sunset_missing"] if not sun.get("sunrise") or not sun.get("sunset") else []),
            },
        })
    return output

def build_cwa_rows(jsonl_path: Path):
    # Keep the latest collected revision for each region/valid-time pair.
    selected = {}
    for line_no, line in enumerate(jsonl_path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        region = row.get("region_id")
        if region not in REGIONS:
            continue
        valid = row.get("valid_time")
        collected = row.get("collected_at")
        if not valid or not collected:
            continue
        key = (region, valid)
        if key not in selected or parse_dt(collected, "UTC") > parse_dt(selected[key]["collected_at"], "UTC"):
            selected[key] = row
    output = []
    for (region, valid), row in sorted(selected.items()):
        env = {}
        for src, dest in (
            ("wave_height_m", "wave_height_m"),
            ("wave_period_s", "wave_period_s"),
            ("wave_direction_deg", "wave_direction_deg"),
            ("sea_temperature_c", "sea_surface_temperature_c"),
            ("tide_height_m", "tide_height_m"),
            ("current_speed_ms", "ocean_current_velocity_ms"),
            ("current_direction_deg", "ocean_current_direction_deg"),
            ("wind_speed_ms", "wind_speed_10m_ms"),
            ("wind_direction_deg", "wind_direction_10m_deg"),
        ):
            env[dest] = number(row.get(src))
        # Current measurements are marine currents, not specifically tidal currents.
        available = sum(v is not None for v in env.values())
        archive_scope = row.get("archive_scope", "")
        dataset = row.get("source_dataset") or "regional-marine-aggregate"
        source_url = CWA_URLS.get(dataset, "https://opendata.cwa.gov.tw/")
        output.append({
            "schema_version": "1.0.0", "region_id": region,
            "valid_time": parse_dt(valid, "Asia/Taipei").isoformat(),
            "collected_at": parse_dt(row["collected_at"], "UTC").isoformat(),
            "data_type": "observation",
            "source_records": [{
                "source_id": "CWA", "dataset": dataset,
                "url": source_url,
                "retrieved_at": parse_dt(row["collected_at"], "UTC").isoformat(),
                "source_record_id": row.get("revision_key") or row.get("snapshot_id"),
            }],
            "environment": env,
            "completeness": {"available_fields": available, "expected_fields": 9, "ratio": round(available / 9, 6)},
            "quality": {
                "status": "good" if available == 9 else "partial",
                "confidence": "unknown",
                "flags": ["regional_station_aggregate", "latest_revision_selected"],
            },
        })
    return output

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--forecast-csv", type=Path, required=True)
    parser.add_argument("--forecast-dir", type=Path, required=True, help="Directory containing *_weather_raw.json files")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--timezone", default="Asia/Taipei")
    parser.add_argument("--cwa-observations-jsonl", type=Path)
    args = parser.parse_args()
    records = build_forecast_rows(args.forecast_csv, args.forecast_dir, args.timezone)
    if args.cwa_observations_jsonl:
        records.extend(build_cwa_rows(args.cwa_observations_jsonl))
    records.sort(key=lambda r: (r["region_id"], r["valid_time"], r["data_type"]))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    print(json.dumps({
        "output": str(args.out), "records": len(records),
        "forecast_records": sum(r["data_type"] == "forecast" for r in records),
        "observation_records": sum(r["data_type"] == "observation" for r in records),
        "regions": sorted({r["region_id"] for r in records}),
        "note": "CWA tide height remains separate from current velocity; no tide-phase interpolation is performed.",
    }, ensure_ascii=False))

if __name__ == "__main__":
    main()
