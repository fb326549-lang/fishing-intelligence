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

CWA_TIDE_URL = "https://opendata.cwa.gov.tw/dataset/forecast/F-A0021-001"
TIDE_SLACK_WINDOW_MINUTES = 30


def parse_cwa_tide_time(value: str):
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=ZoneInfo("Asia/Taipei"))


def build_tide_phase_index(csv_path: Path):
    """Index explicit CWA high/low forecast events by mapped region and location."""
    grouped = defaultdict(lambda: defaultdict(list))
    with csv_path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError("CWA tide forecast CSV is empty")
    for row in rows:
        region = (row.get("region_id") or "").strip()
        location = (row.get("location_id") or "").strip()
        when = parse_cwa_tide_time(row.get("valid_time"))
        tide = (row.get("tide") or "").strip()
        kind = "high" if tide in {"滿潮", "高潮"} else "low" if tide in {"乾潮", "低潮"} else None
        if not region or region not in REGIONS or not location or when is None or kind is None:
            continue
        grouped[region][location].append((when, kind, (row.get("fetched_at_utc") or "").strip()))
    if not grouped:
        raise ValueError("No mapped CWA high/low tide events found")
    for locations in grouped.values():
        for location, events in locations.items():
            by_time = {}
            for event in events:
                when, kind = event[0], event[1]
                fetched_at = event[2] if len(event) > 2 else ""
                by_time.setdefault(when, {"kinds": set(), "fetched_at": []})
                by_time[when]["kinds"].add(kind)
                if fetched_at:
                    by_time[when]["fetched_at"].append(fetched_at)
            locations[location] = [
                (when, next(iter(value["kinds"])), max(value["fetched_at"]) if value["fetched_at"] else None)
                for when, value in sorted(by_time.items())
                if len(value["kinds"]) == 1
            ]
    return grouped


def tide_phase_for_location(events, target):
    if not events:
        return None
    previous = [event for event in events if event[0] <= target]
    following = [event for event in events if event[0] >= target]
    nearest = min(events, key=lambda event: abs((event[0] - target).total_seconds()))
    if abs((nearest[0] - target).total_seconds()) <= TIDE_SLACK_WINDOW_MINUTES * 60:
        return "high_slack" if nearest[1] == "high" else "low_slack"
    if not previous or not following:
        return None
    prev_kind, next_kind = previous[-1][1], following[0][1]
    if prev_kind == "low" and next_kind == "high":
        return "rising"
    if prev_kind == "high" and next_kind == "low":
        return "falling"
    return None


def regional_tide_phase(tide_index, region, target):
    locations = tide_index.get(region) or {}
    phases = [tide_phase_for_location(events, target) for events in locations.values()]
    if not phases or any(phase is None for phase in phases) or len(set(phases)) != 1:
        return None, None, len(locations)
    phase = phases[0]
    return phase, phase in {"high_slack", "low_slack"}, len(locations)


def build_forecast_rows(csv_path: Path, forecast_dir: Path, timezone_name: str, tide_phase_index=None):
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
        tide_flags = []
        tide_source_record = None
        if tide_phase_index is not None:
            phase, turning, location_count = regional_tide_phase(
                tide_phase_index, region, parse_dt(valid, timezone_name)
            )
            env["tide_phase"] = phase
            env["tide_turning"] = turning
            tide_flags.append("tide_phase_based_on_predicted_high_low_events_not_measured_current")
            if phase is None:
                tide_flags.append("cwa_tide_phase_unavailable_or_region_locations_disagree")
            else:
                tide_flags.append("tide_phase_derived_from_cwa_high_low_forecast_events")
            if location_count:
                retrieved_at = max(
                    (event[2] for locations in tide_phase_index.get(region, {}).values()
                     for event in locations if len(event) > 2 and event[2]),
                    default=None,
                )
                tide_source_record = {
                    "source_id": "CWA",
                    "dataset": "F-A0021-001",
                    "url": CWA_TIDE_URL,
                    **({"retrieved_at": parse_cwa_tide_time(retrieved_at).isoformat()} if retrieved_at and parse_cwa_tide_time(retrieved_at) else {}),
                }
        code = env.get("weather_code")
        env["thunderstorm_risk"] = thunderstorm_risk(code)
        env["sunrise"] = parse_dt(sun["sunrise"], timezone_name).isoformat() if sun.get("sunrise") else None
        env["sunset"] = parse_dt(sun["sunset"], timezone_name).isoformat() if sun.get("sunset") else None
        expected = len(MARINE_MAP) + len(WEATHER_MAP) + 3 + (2 if tide_phase_index is not None else 0)
        available = sum(v is not None and not (k == "thunderstorm_risk" and v == "unknown") for k, v in env.items())
        source_records = list(item["source_records"].values())
        if tide_source_record is not None:
            source_records.append(tide_source_record)
        output.append({
            "schema_version": "1.0.0", "region_id": region,
            "valid_time": item["valid_time"],
            "collected_at": parse_dt(item["collected_at"], "UTC").isoformat(),
            "data_type": "forecast",
            "source_records": source_records,
            "environment": env,
            "completeness": {"available_fields": available, "expected_fields": expected, "ratio": round(available / expected, 6)},
            "quality": {
                "status": "good" if available == expected else "partial",
                "confidence": "unknown",
                "flags": sorted(item["quality_flags"]) + (["sunrise_sunset_missing"] if not sun.get("sunrise") or not sun.get("sunset") else []) + tide_flags,
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
    parser.add_argument("--cwa-tide-forecast-csv", type=Path, help="Mapped CWA F-A0021-001 high/low tide forecast events.")
    args = parser.parse_args()
    tide_index = build_tide_phase_index(args.cwa_tide_forecast_csv) if args.cwa_tide_forecast_csv else None
    records = build_forecast_rows(args.forecast_csv, args.forecast_dir, args.timezone, tide_index)
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
        "note": "CWA tide height remains separate from current velocity. Forecast tide phase, when available, is derived from bracketing official high/low events; no tide height or tidal current is interpolated.",
    }, ensure_ascii=False))

if __name__ == "__main__":
    main()
