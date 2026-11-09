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


def archive_regional_series(csv_path, history_dir, filename, source_dataset, scope, snapshot_id, collected_at):
    """Append unique region/time/value revisions from a CWA regional series."""
    source_rows = read_csv(Path(csv_path))
    if not source_rows:
        raise SystemExit(f"Regional observation file is empty: {csv_path}")
    history_path = Path(history_dir) / filename
    keys = load_keys(history_path, ("region_id", "valid_time", "revision_key"))
    additions = []
    for source in source_rows:
        region_id = str(source.get("region_id", "")).strip()
        valid_time = str(source.get("valid_time", "")).strip()
        if not region_id or not valid_time:
            continue
        canonical = json.dumps(source, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        revision_key = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        key = (region_id, valid_time, revision_key)
        if key in keys:
            continue
        row = dict(source)
        row.update({
            "archive_scope": scope,
            "source_dataset": source_dataset,
            "snapshot_id": snapshot_id,
            "collected_at": collected_at,
            "revision_key": revision_key,
        })
        additions.append(row)
        keys.add(key)
    append_jsonl(history_path, additions)
    return {"file": filename, "records_seen": len(source_rows),
            "new_revisions": len(additions), "history_records": len(keys)}

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--observations", required=True)
    p.add_argument("--forecasts", required=True)
    p.add_argument("--pairing", required=True)
    p.add_argument("--history-dir", required=True)
    p.add_argument("--snapshot-id", required=True)
    p.add_argument("--collected-at", default=datetime.now(timezone.utc).isoformat())
    p.add_argument("--regional-48h", help="Six-region O-B0075-001 rolling 48-hour series CSV.")
    p.add_argument("--regional-30d", help="Six-region O-B0075-002 rolling 30-day series CSV.")
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

    forecast_location_ids = {r.get("location_id") for r in forecast_rows if r.get("region_id")}
    if not forecast_location_ids:
        raise SystemExit("No mapped six-region CWA tide forecast locations to archive.")

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
        if r.get("location_id") not in forecast_location_ids or not r.get("valid_time"):
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

    regional_48h = (
        archive_regional_series(a.regional_48h, a.history_dir,
                                "regional_marine_observations_48h.jsonl",
                                "O-B0075-001", "rolling_48_hour", a.snapshot_id, a.collected_at)
        if a.regional_48h else {"file": "regional_marine_observations_48h.jsonl",
                                "records_seen": 0, "new_revisions": 0,
                                "history_records": len(load_keys(Path(a.history_dir) / "regional_marine_observations_48h.jsonl",
                                                                  ("region_id", "valid_time", "revision_key")))}
    )
    regional_30d = (
        archive_regional_series(a.regional_30d, a.history_dir,
                                "regional_marine_observations_30d.jsonl",
                                "O-B0075-002", "rolling_30_day", a.snapshot_id, a.collected_at)
        if a.regional_30d else {"file": "regional_marine_observations_30d.jsonl",
                                "records_seen": 0, "new_revisions": 0,
                                "history_records": len(load_keys(Path(a.history_dir) / "regional_marine_observations_30d.jsonl",
                                                                  ("region_id", "valid_time", "revision_key")))}
    )
    run = {
        "snapshot_id": a.snapshot_id, "collected_at": a.collected_at,
        "observation_rows_seen": len(obs_rows),
        "forecast_rows_seen": len(forecast_rows),
        "new_observation_revisions": len(new_obs),
        "new_forecast_vintage_events": len(new_forecasts),
        "regional_48h_records_seen": regional_48h["records_seen"],
        "new_regional_48h_revisions": regional_48h["new_revisions"],
        "regional_48h_history_records": regional_48h["history_records"],
        "regional_30d_records_seen": regional_30d["records_seen"],
        "new_regional_30d_revisions": regional_30d["new_revisions"],
        "regional_30d_history_records": regional_30d["history_records"],
        "matched_station_count": len(station_ids),
        "matched_forecast_location_count": len(location_ids),
        "archived_forecast_location_count": len(forecast_location_ids),
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
        "regional_48h_history_records": regional_48h["history_records"],
        "regional_30d_history_records": regional_30d["history_records"],
        "collection_run_count": sum(1 for line in runs_path.open(encoding="utf-8") if line.strip()),
        "matched_station_ids": sorted(station_ids),
        "matched_forecast_location_ids": sorted(location_ids),
        "archived_forecast_location_ids": sorted(forecast_location_ids),
        "latest_run": run,
        "regional_marine_files": {
            "rolling_48_hour": regional_48h["file"],
            "rolling_30_day": regional_30d["file"],
        },
        "policy": [
            "CWA observed TideHeight records are appended when station/time/value is new.",
            "Changed observed values are retained as revisions; earlier values are not overwritten.",
            "Each forecast collection run is retained as a distinct vintage using snapshot_id.",
            "Only explicitly paired mainland tide stations and forecast locations are archived.",
            "All vertical datum fields are preserved separately; do not mix them.",
            "Regional marine observations are archived as region/time/value revisions; identical daily repeats are deduplicated and changed values are retained.",
            "The rolling 30-day regional feed is a historical context source; its records are not treated as 30 independent days of new samples.",
            "No interpolation, regional averaging, or catch probability is generated.",
        ],
    }
    Path(a.history_dir, "history_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(run, ensure_ascii=False))

if __name__ == "__main__":
    main()
