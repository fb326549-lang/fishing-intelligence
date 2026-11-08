#!/usr/bin/env python3
"""Collect and normalize CWA one-month tide forecasts (F-A0021-001).

The provider publishes high/low tide event times and heights. Heights remain
in the provider's centimetre datums; no conversion or fishing score is inferred.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

DATASET_ID = "F-A0021-001"
ENDPOINT = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/{DATASET_ID}"
FIELDS = [
    "dataset_id", "source", "data_kind", "location_id", "location_name",
    "latitude", "longitude", "date", "lunar_date", "tide_range",
    "valid_time", "tide", "height_above_twvd_cm",
    "height_above_local_msl_cm", "height_above_chart_datum_cm",
    "region_id", "fetched_at_utc",
]


def pick(obj: Any, name: str, default=None):
    if not isinstance(obj, dict):
        return default
    target = name.casefold()
    for key, value in obj.items():
        if str(key).casefold() == target:
            return value
    return default


def as_list(value: Any) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def number(value: Any):
    if value is None or str(value).strip().lower() in {"", "none", "null", "nan", "n/a", "na"}:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def find_locations(obj: Any):
    """Find location records in CWA JSON without assuming wrapper capitalization."""
    if isinstance(obj, dict):
        if pick(obj, "LocationId") is not None and pick(obj, "TimePeriods") is not None:
            yield obj
            return
        for value in obj.values():
            yield from find_locations(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from find_locations(value)


def normalize(payload: dict, fetched_at: str) -> list[dict]:
    success = pick(payload, "success")
    if success is not None and str(success).strip().lower() not in {"true", "1"}:
        raise ValueError(f"CWA application-level failure: Success={success}")

    locations = list(find_locations(payload))
    rows: list[dict] = []
    for location in locations:
        location_id = pick(location, "LocationId")
        periods = pick(location, "TimePeriods", {}) or {}
        for daily in as_list(pick(periods, "Daily")):
            heights_date = pick(daily, "Date")
            for event in as_list(pick(daily, "Time")):
                tide_heights = pick(event, "TideHeights", {}) or {}
                rows.append({
                    "dataset_id": DATASET_ID,
                    "source": "CWA",
                    "data_kind": "forecast",
                    "location_id": location_id,
                    "location_name": pick(location, "LocationName"),
                    "latitude": number(pick(location, "Latitude")),
                    "longitude": number(pick(location, "Longitude")),
                    "date": heights_date,
                    "lunar_date": pick(daily, "LunarDate"),
                    "tide_range": pick(daily, "TideRange"),
                    "valid_time": pick(event, "DateTime"),
                    "tide": pick(event, "Tide"),
                    "height_above_twvd_cm": number(pick(tide_heights, "AboveTWVD")),
                    "height_above_local_msl_cm": number(pick(tide_heights, "AboveLocalMSL")),
                    "height_above_chart_datum_cm": number(pick(tide_heights, "AboveChartDatum")),
                    # Intentionally blank until a reviewed CWA-location-to-P1-region
                    # mapping exists. Do not infer a fishing region from county alone.
                    "region_id": "",
                    "fetched_at_utc": fetched_at,
                })

    if not rows:
        raise ValueError("No F-A0021 tide event records matched the documented Location/TimePeriods schema.")
    if any(not row["location_id"] or not row["valid_time"] for row in rows):
        raise ValueError("Tide forecast contains an event without location_id or valid_time.")
    return sorted(rows, key=lambda row: (row["location_id"], row["valid_time"]))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="output/cwa_tides")
    args = parser.parse_args()

    token = os.environ.get("CWA_AUTHORIZATION")
    if not token:
        raise SystemExit("Missing CWA_AUTHORIZATION secret.")

    response = requests.get(
        ENDPOINT,
        params={"Authorization": token, "format": "JSON"},
        timeout=60,
        headers={"User-Agent": "FishingIntelligence-P1/0.5"},
    )
    if response.status_code >= 400:
        raise SystemExit(f"CWA tide forecast request failed: HTTP {response.status_code}. Check authorization and dataset access.")
    try:
        payload = response.json()
    except ValueError as exc:
        raise SystemExit("CWA tide forecast response is not valid JSON.") from exc
    if not isinstance(payload, dict):
        raise SystemExit("CWA tide forecast response has an unexpected top-level type.")

    fetched_at = datetime.now(timezone.utc).isoformat()
    try:
        rows = normalize(payload, fetched_at)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{DATASET_ID}_raw.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    with (out / f"{DATASET_ID}.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    summary = {
        "dataset_id": DATASET_ID,
        "source": "CWA",
        "data_kind": "forecast",
        "fetched_at_utc": fetched_at,
        "event_rows": len(rows),
        "unique_locations": len({row["location_id"] for row in rows}),
        "tide_height_unit": "cm",
        "region_mapping_status": "pending_reviewed_location_mapping",
        "limitations": [
            "This dataset contains forecast high/low tide events, not continuous observed tide levels.",
            "Height datums are kept separate: TWVD, local mean sea level, and chart datum.",
            "P1 region_id is blank until an explicit reviewed mapping is created.",
            "No interpolation between high/low events and no fishing score are generated.",
        ],
    }
    (out / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
