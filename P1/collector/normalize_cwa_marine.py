#!/usr/bin/env python3
"""Normalize CWA O-B0075 marine observations into CSV without inventing units.

Sea-current measurements are depth/layered. Keep one row per station/time
observation, preserve the provider's original nested JSON, and expose every
reported layer in stable, explicit columns. Missing provider sentinels such as
"None" are represented as empty CSV cells, not as valid measurements.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


def clean(value: Any) -> Any:
    """Convert provider missing-value sentinels to null; preserve real values."""
    if value is None:
        return None
    if isinstance(value, str) and value.strip().lower() in {
        "", "none", "null", "nan", "n/a", "na"
    }:
        return None
    return value


def clean_nested(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: clean_nested(item) for key, item in value.items()}
    if isinstance(value, list):
        return [clean_nested(item) for item in value]
    return clean(value)


def flatten(prefix: str, obj: Any, out: dict[str, Any]) -> None:
    if isinstance(obj, dict):
        for key, value in obj.items():
            flatten(f"{prefix}_{key}" if prefix else key, value, out)
    elif isinstance(obj, list):
        out[prefix] = json.dumps(obj, ensure_ascii=False)
    else:
        out[prefix] = clean(obj)


def as_layer_list(sea_currents: Any) -> list[dict[str, Any]]:
    """Handle CWA Layer as object/list and tolerate repeated SeaCurrents nodes."""
    if sea_currents is None:
        return []
    sources = sea_currents if isinstance(sea_currents, list) else [sea_currents]
    layers: list[dict[str, Any]] = []
    for source in sources:
        if not isinstance(source, dict):
            continue
        raw = source.get("Layer", [])
        if isinstance(raw, dict):
            raw = [raw]
        if isinstance(raw, list):
            layers.extend(item for item in raw if isinstance(item, dict))
    return layers


def layer_label(layer: dict[str, Any], index: int) -> str:
    number = clean(layer.get("LayerNumber"))
    if number is None:
        return str(index)
    return str(number).strip().replace(" ", "_")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="output/cwa_marine")
    parser.add_argument("--stations", default="output/cwa_stations/stations.csv")
    parser.add_argument("--out", default="output/normalized")
    args = parser.parse_args()

    input_dir, output_dir = Path(args.input), Path(args.out)
    output_dir.mkdir(parents=True, exist_ok=True)

    station_map: dict[str, dict[str, str]] = {}
    station_path = Path(args.stations)
    if station_path.exists():
        with station_path.open(encoding="utf-8-sig", newline="") as handle:
            for record in csv.DictReader(handle):
                station_id = record.get("station_id")
                if station_id:
                    station_map[station_id] = record

    summaries = []
    for dataset in ("O-B0075-001", "O-B0075-002"):
        source_path = input_dir / f"{dataset}.json"
        payload = json.loads(source_path.read_text(encoding="utf-8"))
        if str(payload.get("Success", "")).lower() != "true":
            raise SystemExit(f"{dataset}: provider response is not Success=true")

        locations = (
            payload.get("Records", {})
            .get("SeaSurfaceObs", {})
            .get("Location", [])
        )
        rows: list[dict[str, Any]] = []
        total_layers = 0
        for location in locations:
            station = location.get("Station") or {}
            station_id = str(station.get("StationID", ""))
            metadata = station_map.get(station_id, {})
            observations = (
                location.get("StationObsTimes", {}).get("StationObsTime", []) or []
            )
            for observation in observations:
                row: dict[str, Any] = {
                    "dataset_id": dataset,
                    "station_id": station_id,
                    "station_name": metadata.get("station_name"),
                    "latitude": metadata.get("latitude"),
                    "longitude": metadata.get("longitude"),
                    "county": metadata.get("county"),
                    "valid_time": observation.get("DateTime"),
                    "data_kind": "observed",
                    "source": "CWA",
                }
                elements = observation.get("WeatherElements", {}) or {}
                flatten("", elements, row)

                sea_currents = elements.get("SeaCurrents")
                layers = as_layer_list(sea_currents)
                total_layers += len(layers)
                # Preserve the provider's complete nested current payload.
                if sea_currents is not None:
                    row["SeaCurrents_Raw"] = json.dumps(
                        clean_nested(sea_currents), ensure_ascii=False
                    )
                row["SeaCurrent_LayerCount"] = len(layers)
                row["SeaCurrent_LayerNumbers"] = json.dumps(
                    [clean(layer.get("LayerNumber")) for layer in layers],
                    ensure_ascii=False,
                ) if layers else None

                for index, layer in enumerate(layers, start=1):
                    label = layer_label(layer, index)
                    for field in (
                        "LayerNumber",
                        "CurrentDirection",
                        "CurrentDirectionDescription",
                        "CurrentSpeed",
                        "CurrentSpeedInKnots",
                    ):
                        value = clean(layer.get(field))
                        row[f"SeaCurrent_Layer_{label}_{field}"] = value
                        # Backward-compatible first-layer aliases for existing consumers.
                        if index == 1:
                            row[f"SeaCurrent_{field}"] = value
                rows.append(row)

        if rows:
            fields = list(dict.fromkeys(key for record in rows for key in record))
            with (output_dir / f"{dataset}.csv").open(
                "w", encoding="utf-8-sig", newline=""
            ) as handle:
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows)

        summaries.append({
            "dataset_id": dataset,
            "stations": len(locations),
            "observation_rows": len(rows),
            "observations_with_current_layers": sum(
                1 for row in rows if row.get("SeaCurrent_LayerCount", 0) > 0
            ),
            "reported_current_layer_records": total_layers,
            "csv": f"{dataset}.csv",
        })

    (output_dir / "summary.json").write_text(
        json.dumps(summaries, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    for summary in summaries:
        print(
            f'{summary["dataset_id"]}: {summary["stations"]} stations, '
            f'{summary["observation_rows"]} observations, '
            f'{summary["observations_with_current_layers"]} with current layers, '
            f'{summary["reported_current_layer_records"]} layer records'
        )
    print(
        "Provider missing values are blank; current direction/speed remain in "
        "provider-supplied units. Verify field definitions before conversion."
    )


if __name__ == "__main__":
    main()
