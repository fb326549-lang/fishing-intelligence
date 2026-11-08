#!/usr/bin/env python3
"""Collect Open-Meteo marine + atmospheric forecasts for six planning regions.

All records are model-derived, never CWA in-situ observations. Raw provider
JSON is retained. Forecast timestamps are local Asia/Taipei when configured.
"""
from __future__ import annotations
import argparse, csv, json, time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import requests

MARINE_FIELDS = [
    "wave_height", "wave_direction", "wave_period", "wave_peak_period",
    "wind_wave_height", "wind_wave_direction", "wind_wave_period",
    "swell_wave_height", "swell_wave_direction", "swell_wave_period",
    "sea_surface_temperature", "sea_level_height_msl",
    "ocean_current_velocity", "ocean_current_direction",
]
WEATHER_FIELDS = [
    "temperature_2m", "relative_humidity_2m", "precipitation",
    "precipitation_probability", "pressure_msl", "wind_speed_10m",
    "wind_direction_10m", "wind_gusts_10m", "cloud_cover",
]
TIMEOUT = 45
HEADERS = {"User-Agent": "FishingIntelligence-P1/0.2 (research; https://github.com/fb326549-lang/fishing-intelligence)"}

def request_json(session: requests.Session, url: str, params: dict[str, Any]) -> dict[str, Any]:
    response = session.get(url, params=params, timeout=TIMEOUT)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict) or payload.get("error"):
        raise ValueError(f"Invalid provider response: {payload.get('reason', 'not a JSON object') if isinstance(payload, dict) else 'not an object'}")
    if "hourly" not in payload:
        raise ValueError("Provider response missing hourly data")
    return payload

def normalize_hourly(location: dict[str, Any], payload: dict[str, Any], fetched_at: str,
                     source: str, kind: str) -> list[dict[str, Any]]:
    hourly = payload["hourly"]
    times = hourly.get("time") or []
    units = payload.get("hourly_units") or {}
    rows = []
    for variable, values in hourly.items():
        if variable == "time" or not isinstance(values, list):
            continue
        if len(values) != len(times):
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
                "model_or_provider": "Open-Meteo Best Match",
            })
    return rows

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--config", required=True)
    p.add_argument("--out", default="output/open_meteo")
    p.add_argument("--delay", type=float, default=1.0)
    a = p.parse_args()
    config = json.loads(Path(a.config).read_text(encoding="utf-8"))
    locations = config.get("locations", [])
    if not locations:
        raise SystemExit("Config contains no locations")
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    fetched_at = datetime.now(timezone.utc).isoformat()
    folder = Path(a.out) / run_id
    folder.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers.update(HEADERS)
    rows: list[dict[str, Any]] = []
    manifest: dict[str, Any] = {
        "run_id": run_id, "fetched_at": fetched_at,
        "provider": "Open-Meteo", "data_kind": "forecast/modelled",
        "attribution": "Open-Meteo; underlying marine/weather model providers vary by variable and model selection.",
        "documentation": "https://open-meteo.com/en/docs/marine-weather-api",
        "locations": [],
    }
    for location in locations:
        lat, lon = float(location["latitude"]), float(location["longitude"])
        common = {"latitude": lat, "longitude": lon,
                  "timezone": config.get("timezone", "Asia/Taipei"),
                  "forecast_days": int(config.get("forecast_days", 2)),
                  "wind_speed_unit": "ms", "timeformat": "iso8601"}
        entry = {"id": location["id"], "name": location["name"], "status": "ok"}
        try:
            marine_params = {**common, "hourly": ",".join(MARINE_FIELDS),
                             "current": ",".join(MARINE_FIELDS),
                             "cell_selection": "sea"}
            marine = request_json(session, config["marine_base_url"], marine_params)
            (folder / f"{location['id']}_marine_raw.json").write_text(
                json.dumps(marine, ensure_ascii=False, indent=2), encoding="utf-8")
            rows.extend(normalize_hourly(location, marine, fetched_at,
                                         "open-meteo-marine", "modelled"))
            entry["marine_grid"] = {"latitude": marine.get("latitude"), "longitude": marine.get("longitude")}
            entry["marine_hourly_variables"] = list((marine.get("hourly") or {}).keys())
            time.sleep(max(0.0, a.delay))
            weather_params = {**common, "hourly": ",".join(WEATHER_FIELDS),
                              "current": ",".join(WEATHER_FIELDS)}
            weather = request_json(session, config["forecast_base_url"], weather_params)
            (folder / f"{location['id']}_weather_raw.json").write_text(
                json.dumps(weather, ensure_ascii=False, indent=2), encoding="utf-8")
            rows.extend(normalize_hourly(location, weather, fetched_at,
                                         "open-meteo-forecast", "forecast"))
            entry["weather_grid"] = {"latitude": weather.get("latitude"), "longitude": weather.get("longitude")}
            entry["weather_hourly_variables"] = list((weather.get("hourly") or {}).keys())
        except Exception as exc:
            entry["status"] = "error"
            entry["error"] = str(exc)
        manifest["locations"].append(entry)
        time.sleep(max(0.0, a.delay))
    if rows:
        fields = list(dict.fromkeys(k for row in rows for k in row))
        with (folder / "environmental_forecast.csv").open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
    manifest["normalized_rows"] = len(rows)
    manifest["successful_locations"] = sum(x["status"] == "ok" for x in manifest["locations"])
    (folder / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Run {run_id}: {manifest['successful_locations']}/{len(locations)} locations; {len(rows)} normalized rows")
    print("All Open-Meteo records are forecast/modelled data, not in-situ observations.")
    return 0 if manifest["successful_locations"] == len(locations) else 1

if __name__ == "__main__":
    raise SystemExit(main())
