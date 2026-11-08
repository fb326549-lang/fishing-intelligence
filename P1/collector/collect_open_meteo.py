#!/usr/bin/env python3
"""Local, free-tier-friendly Open-Meteo snapshot collector.

This is a P1 prototype: it preserves provider responses and emits normalized
CSV rows. It does not write to a database, claim in-situ measurements, or
supply exact fishing-spot forecasts. Config coordinates are planning centers.
"""
from __future__ import annotations
import argparse, csv, json, time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import requests

MARINE_FIELDS = [
    "sea_surface_temperature", "ocean_current_velocity",
    "ocean_current_direction", "wave_height", "wave_direction", "wave_period"
]
WEATHER_CURRENT = [
    "temperature_2m", "relative_humidity_2m", "precipitation",
    "pressure_msl", "wind_speed_10m", "wind_direction_10m",
    "wind_gusts_10m", "cloud_cover"
]
WEATHER_HOURLY = [
    "precipitation_probability", "precipitation", "pressure_msl",
    "temperature_2m", "relative_humidity_2m", "wind_speed_10m",
    "wind_direction_10m", "wind_gusts_10m", "cloud_cover"
]
TIMEOUT = 30
HEADERS = {"User-Agent": "FishingIntelligence-P1/0.1 (personal research)"}

def get_json(url: str, params: dict[str, Any]) -> dict[str, Any]:
    response = requests.get(url, params=params, timeout=TIMEOUT, headers=HEADERS)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("Provider response is not a JSON object")
    return payload

def write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

def normalize_hourly(location_id: str, payload: dict[str, Any], fetched_at: str,
                     source: str, kind: str) -> list[dict[str, Any]]:
    hourly = payload.get("hourly") or {}
    times = hourly.get("time") or []
    rows: list[dict[str, Any]] = []
    units = payload.get("hourly_units") or {}
    for i, valid_time in enumerate(times):
        for variable, values in hourly.items():
            if variable == "time" or not isinstance(values, list):
                continue
            value = values[i] if i < len(values) else None
            rows.append({
                "location_id": location_id, "variable_code": variable,
                "value": value, "unit": units.get(variable),
                "valid_time": valid_time, "fetched_at": fetched_at,
                "source": source, "data_kind": kind,
                "quality_status": "missing" if value is None else "unchecked"
            })
    return rows

def normalize_current(location_id: str, payload: dict[str, Any], fetched_at: str,
                      source: str) -> list[dict[str, Any]]:
    current = payload.get("current") or {}
    units = payload.get("current_units") or {}
    valid_time = current.get("time")
    rows: list[dict[str, Any]] = []
    for variable, value in current.items():
        if variable == "time":
            continue
        rows.append({
            "location_id": location_id, "variable_code": variable,
            "value": value, "unit": units.get(variable),
            "valid_time": valid_time, "fetched_at": fetched_at,
            "source": source, "data_kind": "modelled",
            "quality_status": "missing" if value is None else "unchecked"
        })
    return rows

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--out", default="data")
    parser.add_argument("--delay", type=float, default=2.0,
                        help="seconds between location requests; keep conservative")
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    out = Path(args.out)
    run_time = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    fetched_at = datetime.now(timezone.utc).isoformat()
    all_rows: list[dict[str, Any]] = []
    manifest = {"run_id": run_time, "fetched_at": fetched_at, "locations": []}

    for location in config["locations"]:
        lat, lon = location["latitude"], location["longitude"]
        common = {"latitude": lat, "longitude": lon,
                  "timezone": config.get("timezone", "Asia/Taipei")}
        marine_params = {
            **common, "current": ",".join(MARINE_FIELDS),
            "hourly": ",".join(MARINE_FIELDS),
            "forecast_days": int(config.get("forecast_days", 2))
        }
        weather_params = {
            **common, "current": ",".join(WEATHER_CURRENT),
            "hourly": ",".join(WEATHER_HOURLY),
            "forecast_days": int(config.get("forecast_days", 2))
        }
        entry = {"id": location["id"], "name": location["name"],
                 "latitude": lat, "longitude": lon, "status": "ok"}
        try:
            marine = get_json(config["marine_base_url"], marine_params)
            time.sleep(max(0, args.delay))
            weather = get_json(config["forecast_base_url"], weather_params)
            folder = out / run_time
            folder.mkdir(parents=True, exist_ok=True)
            (folder / f'{location["id"]}_marine_raw.json').write_text(
                json.dumps(marine, ensure_ascii=False, indent=2), encoding="utf-8")
            (folder / f'{location["id"]}_weather_raw.json').write_text(
                json.dumps(weather, ensure_ascii=False, indent=2), encoding="utf-8")
            all_rows += normalize_current(location["id"], marine, fetched_at,
                                          "open-meteo-marine",)
            all_rows += normalize_hourly(location["id"], marine, fetched_at,
                                          "open-meteo-marine", "forecast_or_model")
            all_rows += normalize_current(location["id"], weather, fetched_at,
                                          "open-meteo-forecast")
            all_rows += normalize_hourly(location["id"], weather, fetched_at,
                                          "open-meteo-forecast", "forecast")
            entry["raw_files"] = [
                f'{location["id"]}_marine_raw.json',
                f'{location["id"]}_weather_raw.json'
            ]
        except Exception as exc:
            entry["status"] = "error"
            entry["error"] = str(exc)
        manifest["locations"].append(entry)
        time.sleep(max(0, args.delay))

    folder = out / run_time
    folder.mkdir(parents=True, exist_ok=True)
    write_rows(folder / "environmental_data.csv", all_rows)
    (folder / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Run: {run_time}; normalized rows: {len(all_rows)}")
    print(f"Output: {folder.resolve()}")
    print("Note: Open-Meteo marine/weather outputs are model/forecast products, not local in-situ observations.")
    return 0 if all(x["status"] == "ok" for x in manifest["locations"]) else 1

if __name__ == "__main__":
    raise SystemExit(main())
