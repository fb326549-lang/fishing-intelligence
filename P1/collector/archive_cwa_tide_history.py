#!/usr/bin/env python3
"""Append immutable CWA tide observations and forecast vintages to JSONL history.

Observation revisions are retained only when the value changes. Forecast rows
are keyed by their issue/fetch time so later forecast updates never overwrite
earlier vintages. The caller supplies a persistent history directory checked
out from the dedicated tide-history branch.
"""
from __future__ import annotations
import argparse, csv, hashlib, json
from datetime import datetime, timezone
from pathlib import Path

def read_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))

def load_keys(path, key_fields):
    keys = set()
    if not path.exists():
        return keys
    with path.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                keys.add(tuple(str(row.get(k, "")) for k in key_fields))
            except (json.JSONDecodeError, TypeError):
                raise SystemExit(f"History file contains invalid JSON: {path}")
    return keys

def append_jsonl(path, rows):
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--observations", required=True)
    p.add_argument("--forecasts", required=True)
    p.add_argument("--pairing", required=True)
    p.add_argument("--history-dir", required=True)
    p.add_argument("--snapshot-id", required=True)
    p.add_argument("--collected-at", default=datetime.now(timezone.utc).isoformat())
    a = p.parse_args()

    pairs = read_csv(a.pairing)
    matched = [r for r in pairs if r.get("matching_status") == "matched"]
    station_ids = {r["station_id"] for r in matched}
    location_ids = {r["location_id"] for r in matched}
    if not station_ids or not location_ids:
        raise SystemExit("No explicitly matched station/location pairs in pairing file.")

    obs_rows = read_csv(a.observations)
    forecast_rows = read_csv(a.forecasts)
    obs_path = Path(a.history_dir) / "observed_tides.jsonl"
    forecast_path = Path(a.history_dir) / "forecast_vintages.jsonl"
    runs_path = Path(a.history_dir) / "collection_runs.jsonl"

    obs_keys = load_keys(obs_path, ("station_id", "valid_time", "TideHeight"))
    new_obs = []
    for r in obs_rows:
        if r.get("station_id") not in station_ids or not r.get("valid_time"):
            continue
        value = r.get("TideHeight")
        if value is None or not str(value).strip():
            continue
        key = (str(r.get("station_id", "")), str(r.get("valid_time", "")), str(value))
        if key in obs_keys:
            continue
        row = {
            "dataset_id": "O-B0075-001", "source": "CWA", "data_kind": "observed",
            "station_id": r.get("station_id"), "station_name": r.get("station_name"),
            "latitude": r.get("latitude"), "longitude": r.get("longitude"),
            "valid_time": r.get("valid_time"), "TideHeight": value,
            "snapshot_id": a.snapshot_id, "collected_at": a.collected_at,
            "revision_key": hashlib.sha256("|".join(key).encode()).hexdigest(),
        }
        new_obs.append(row)
        obs_keys.add(key)

    # Each forecast issue is a separate vintage; do not overwrite earlier runs.
    forecast_keys = load_keys(forecast_path, (
        "snapshot_id", "location_id", "valid_time", "tide"
    ))
    new_forecasts = []
    for r in forecast_rows:
        if r.get("location_id") not in location_ids or not r.get("valid_time"):
            continue
        key = (a.snapshot_id, str(r.get("location_id", "")),
               str(r.get("valid_time", "")), str(r.get("tide", "")))
        if key in forecast_keys:
            continue
        row = {
            "dataset_id": "F-A0021-001", "source": "CWA", "data_kind": "forecast_vintage",
            "location_id": r.get("location_id"), "location_name": r.get("location_name"),
            "region_id": r.get("region_id"), "valid_time": r.get("valid_time"),
            "tide": r.get("tide"),
            "height_above_twvd_cm": r.get("height_above_twvd_cm"),
            "height_above_local_msl_cm": r.get("height_above_local_msl_cm"),
            "height_above_chart_datum_cm": r.get("height_above_chart_datum_cm"),
            "forecast_fetched_at_utc": r.get("fetched_at_utc"),
            "snapshot_id": a.snapshot_id, "collected_at": a.collected_at,
        }
        new_forecasts.append(row)
        forecast_keys.add(key)

    append_jsonl(obs_path, new_obs)
    append_jsonl(forecast_path, new_forecasts)
    run = {
        "snapshot_id": a.snapshot_id, "collected_at": a.collected_at,
        "observation_rows_seen": len(obs_rows),
        "forecast_rows_seen": len(forecast_rows),
        "new_observation_revisions": len(new_obs),
        "new_forecast_vintage_events": len(new_forecasts),
        "matched_station_count": len(station_ids),
        "matched_forecast_location_count": len(location_ids),
        "observation_history_records": len(obs_keys),
        "forecast_history_records": len(forecast_keys),
        "observation_file": obs_path.name,
        "forecast_file": forecast_path.name,
    }
    append_jsonl(runs_path, [run])
    summary = {
        "schema_version": 1, "updated_at": a.collected_at,
        "observation_history_records": len(obs_keys),
        "forecast_vintage_records": len(forecast_keys),
        "collection_run_count": sum(1 for line in runs_path.open(encoding="utf-8") if line.strip()),
        "matched_station_ids": sorted(station_ids),
        "matched_forecast_location_ids": sorted(location_ids),
        "latest_run": run,
        "policy": [
            "CWA observed TideHeight records are appended when station/time/value is new.",
            "Changed observed values are retained as revisions; earlier values are not overwritten.",
            "Each forecast collection run is retained as a distinct vintage using snapshot_id.",
            "Only explicitly paired mainland tide stations and forecast locations are archived.",
            "All vertical datum fields are preserved separately; do not mix them.",
            "No interpolation, regional averaging, or catch probability is generated.",
        ],
    }
    Path(a.history_dir, "history_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(run, ensure_ascii=False))

if __name__ == "__main__":
    main()
