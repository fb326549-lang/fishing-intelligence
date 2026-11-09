#!/usr/bin/env python3
"""Collect independent Open-Meteo marine and atmospheric hourly forecasts.

All records are model-derived, never CWA in-situ observations. Marine and
weather requests fail independently so one provider endpoint cannot suppress
the other. Raw responses and per-product status are retained for audit.
"""
from __future__ import annotations
import argparse, csv, json, time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

MARINE_FIELDS = [
    "wave_height", "wave_direction", "wave_period",
    "wind_wave_height", "wind_wave_direction", "wind_wave_period",
    "swell_wave_height", "swell_wave_direction", "swell_wave_period",
    "sea_surface_temperature", "sea_level_height_msl",
    "ocean_current_velocity", "ocean_current_direction",
]
WEATHER_FIELDS = [
    "temperature_2m", "relative_humidity_2m", "precipitation",
    "precipitation_probability", "showers", "weather_code", "pressure_msl", "wind_speed_10m",
    "wind_direction_10m", "wind_gusts_10m", "cloud_cover",
]
TIMEOUT = 45
HEADERS = {"User-Agent": "FishingIntelligence-P1/0.3 (research; https://github.com/fb326549-lang/fishing-intelligence)"}

def request_json(session: requests.Session, url: str, params: dict[str, Any]) -> dict[str, Any]:
    response = session.get(url, params=params, timeout=TIMEOUT)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict) or payload.get("error"):
        reason = payload.get("reason", "not a JSON object") if isinstance(payload, dict) else "not an object"
        raise ValueError(f"Invalid provider response: {reason}")
    hourly = payload.get("hourly")
    if not isinstance(hourly, dict) or not isinstance(hourly.get("time"), list):
        raise ValueError("Provider response missing hourly.time array")
    return payload

def normalize_hourly(location: dict[str, Any], payload: dict[str, Any], fetched_at: str,
                     source: str, kind: str) -> list[dict[str, Any]]:
    hourly = payload["hourly"]
    times = hourly["time"]
    units = payload.get("hourly_units") or {}
    rows = []
    for variable, values in hourly.items():
        if variable == "time":
            continue
        if not isinstance(values, list) or len(values) != len(times):
            raise ValueError(f"{location['id']} {variable}: time/value length mismatch")
        for valid_time, value in zip(times, values):
            rows.append({
                "location_id": location["id"], "location_name": location["name"],
                "requested_latitude": location["latitude"], "requested_longitude": location["longitude"],
                "grid_latitude": payload.get("latitude"), "grid_longitude": payload.get("longitude"),
                "variable_code": variable, "value": value, "unit": units.get(variable),
                "valid_time": valid_time, "fetched_at": fetched_at,
                "source": source, "data_kind": kind,
                "quality_status": "missing" if value is None else "unchecked",
                "model_selection": "Best Match",
                "generationtime_ms": payload.get("generationtime_ms"),
            })
    return rows

def save_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--out", default="output/open_meteo")
    parser.add_argument("--delay", type=float, default=1.0)
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    locations = config.get("locations", [])
    if not locations:
        raise SystemExit("Config contains no locations")

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    fetched_at = datetime.now(timezone.utc).isoformat()
    folder = Path(args.out) / run_id
    folder.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    retry_policy = Retry(
        total=4,
        connect=4,
        read=3,
        status=3,
        backoff_factor=1.0,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        respect_retry_after_header=True,
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry_policy, pool_connections=8, pool_maxsize=8)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update(HEADERS)
    rows: list[dict[str, Any]] = []
    manifest = {
        "run_id": run_id, "fetched_at": fetched_at, "provider": "Open-Meteo",
        "data_kind": "forecast/modelled",
        "attribution": "Open-Meteo and the underlying model providers; see https://open-meteo.com/en/docs/marine-weather-api",
        "locations": [],
    }

    for location in locations:
        lat, lon = float(location["latitude"]), float(location["longitude"])
        common = {
            "latitude": lat, "longitude": lon,
            "timezone": config.get("timezone", "Asia/Taipei"),
            "forecast_days": int(config.get("forecast_days", 2)),
            "wind_speed_unit": "ms", "timeformat": "iso8601",
        }
        entry: dict[str, Any] = {
            "id": location["id"], "name": location["name"],
            "marine": {"status": "not_attempted"},
            "weather": {"status": "not_attempted"},
        }

        # Marine forecast is independent from atmospheric forecast.
        try:
            marine_params = {
                **common, "hourly": ",".join(MARINE_FIELDS),
                "cell_selection": "sea",
            }
            marine = request_json(session, config["marine_base_url"], marine_params)
            save_json(folder / f"{location['id']}_marine_raw.json", marine)
            rows.extend(normalize_hourly(
                location, marine, fetched_at, "open-meteo-marine", "modelled"
            ))
            marine_hourly = marine["hourly"]
            marine_counts = {
                name: sum(value is not None for value in values)
                for name, values in marine_hourly.items()
                if name != "time" and isinstance(values, list)
            }
            marine_partial = any(count == 0 for count in marine_counts.values())
            entry["marine"] = {
                "status": "partial" if marine_partial else "success",
                "request_status": "success",
                "grid": {"latitude": marine.get("latitude"), "longitude": marine.get("longitude")},
                "variables": list(marine_hourly.keys()),
                "units": marine.get("hourly_units", {}),
                "hour_count": len(marine_hourly["time"]),
                "available_value_counts": marine_counts,
                "missing_variables": [name for name, count in marine_counts.items() if count == 0],
            }
        except Exception as exc:
            entry["marine"] = {"status": "error", "error": str(exc)}
        time.sleep(max(0.0, args.delay))

        # Atmospheric forecast still runs even when marine request failed.
        try:
            weather_params = {**common, "hourly": ",".join(WEATHER_FIELDS), "daily": "sunrise,sunset"}
            weather = request_json(session, config["forecast_base_url"], weather_params)
            save_json(folder / f"{location['id']}_weather_raw.json", weather)
            rows.extend(normalize_hourly(
                location, weather, fetched_at, "open-meteo-forecast", "forecast"
            ))
            weather_hourly = weather["hourly"]
            weather_counts = {
                name: sum(value is not None for value in values)
                for name, values in weather_hourly.items()
                if name != "time" and isinstance(values, list)
            }
            weather_partial = any(count == 0 for count in weather_counts.values())
            entry["weather"] = {
                "status": "partial" if weather_partial else "success",
                "request_status": "success",
                "grid": {"latitude": weather.get("latitude"), "longitude": weather.get("longitude")},
                "variables": list(weather_hourly.keys()),
                "units": weather.get("hourly_units", {}),
                "hour_count": len(weather_hourly["time"]),
                "available_value_counts": weather_counts,
                "missing_variables": [name for name, count in weather_counts.items() if count == 0],
            }
        except Exception as exc:
            entry["weather"] = {"status": "error", "error": str(exc)}

        entry["status"] = (
            "success" if entry["marine"]["status"] == "success" and entry["weather"]["status"] == "success"
            else "partial" if entry["marine"]["status"] in ("success", "partial") or entry["weather"]["status"] in ("success", "partial")
            else "error"
        )
        manifest["locations"].append(entry)
        time.sleep(max(0.0, args.delay))

    if rows:
        fields = list(dict.fromkeys(key for row in rows for key in row))
        with (folder / "environmental_forecast.csv").open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

    manifest["normalized_rows"] = len(rows)
    manifest["successful_locations"] = sum(item["status"] == "success" for item in manifest["locations"])
    manifest["partial_locations"] = sum(item["status"] == "partial" for item in manifest["locations"])
    manifest["failed_locations"] = sum(item["status"] == "error" for item in manifest["locations"])
    manifest["marine_successes"] = sum(item["marine"]["status"] == "success" for item in manifest["locations"])
    manifest["marine_partial"] = sum(item["marine"]["status"] == "partial" for item in manifest["locations"])
    manifest["weather_successes"] = sum(item["weather"]["status"] == "success" for item in manifest["locations"])
    manifest["weather_partial"] = sum(item["weather"]["status"] == "partial" for item in manifest["locations"])
    save_json(folder / "manifest.json", manifest)

    print(f"Run {run_id}: rows={len(rows)}")
    print(f"Locations full={manifest['successful_locations']}, partial={manifest['partial_locations']}, failed={manifest['failed_locations']}")
    print(f"Marine full={manifest['marine_successes']}, partial={manifest['marine_partial']}; weather full={manifest['weather_successes']}, partial={manifest['weather_partial']}")
    print("All Open-Meteo records are forecast/modelled data, not in-situ observations.")
    return 0 if manifest["failed_locations"] == 0 else 1

if __name__ == "__main__":
    raise SystemExit(main())
