#!/usr/bin/env python3
"""Audit archived hourly marine-data coverage without imputing missing regions."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

DEFAULT_REGIONS = (
    "yilan_suao",
    "hualien_north",
    "hualien_south",
    "fengbin_shitiping",
    "chenggong_donghe",
    "taitung_south",
)
DATA_TYPES = ("forecast", "observation")


def audit_catalog(catalog: dict, expected_regions=DEFAULT_REGIONS) -> dict:
    if not isinstance(catalog, dict):
        raise ValueError("catalog must be a JSON object")
    partitions = catalog.get("partitions")
    if not isinstance(partitions, list):
        raise ValueError("catalog.partitions must be an array")

    totals = {
        region: {
            kind: {"record_count": 0, "unique_valid_hours": 0, "collection_vintages": 0}
            for kind in DATA_TYPES
        }
        for region in expected_regions
    }

    for index, partition in enumerate(partitions):
        if not isinstance(partition, dict):
            raise ValueError(f"partition {index} must be an object")
        records = partition.get("records_by_region_type", {})
        unique_hours = partition.get("unique_valid_hours_by_region_type", {})
        vintages = partition.get("collection_vintages_by_region_type", {})
        for region in expected_regions:
            for kind in DATA_TYPES:
                key = f"{region}|{kind}"
                for source, field in (
                    (records, "record_count"),
                    (unique_hours, "unique_valid_hours"),
                    (vintages, "collection_vintages"),
                ):
                    value = source.get(key, 0)
                    if not isinstance(value, int) or value < 0:
                        raise ValueError(
                            f"partition {index} {field} for {key} must be a non-negative integer"
                        )
                    totals[region][kind][field] += value

    regions = []
    for region, by_type in totals.items():
        forecast = by_type["forecast"]
        observation = by_type["observation"]
        if forecast["record_count"] and observation["record_count"]:
            status = "forecast_and_observation_present"
        elif forecast["record_count"]:
            status = "forecast_only_observation_missing"
        elif observation["record_count"]:
            status = "observation_only_forecast_missing"
        else:
            status = "no_data"
        regions.append({
            "region_id": region,
            "status": status,
            "forecast": forecast,
            "observation": observation,
        })

    missing_observations = [
        item["region_id"] for item in regions
        if item["observation"]["record_count"] == 0
    ]
    missing_forecasts = [
        item["region_id"] for item in regions
        if item["forecast"]["record_count"] == 0
    ]
    return {
        "schema_version": "1.0.0",
        "source": "p2-history hourly_environment/catalog.json",
        "interpretation": (
            "Coverage audit only. Record counts and unique valid hours are reported as stored; "
            "missing hours are not inferred, interpolated, or filled from another region. "
            "Presence does not imply sufficient sample size or measurement quality."
        ),
        "expected_region_count": len(expected_regions),
        "partition_count": len(partitions),
        "regions_with_forecast_and_observation": sum(
            item["status"] == "forecast_and_observation_present" for item in regions
        ),
        "regions_missing_observations": missing_observations,
        "regions_missing_forecasts": missing_forecasts,
        "all_expected_regions_have_observations": not missing_observations,
        "all_expected_regions_have_forecasts": not missing_forecasts,
        "regions": regions,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--expected-regions",
        default=",".join(DEFAULT_REGIONS),
        help="Comma-separated region IDs; defaults to the six East Taiwan project regions.",
    )
    parser.add_argument(
        "--require-all-observations",
        action="store_true",
        help="Return exit code 2 when any expected region has no archived observations.",
    )
    args = parser.parse_args()
    expected = tuple(item.strip() for item in args.expected_regions.split(",") if item.strip())
    if not expected or len(set(expected)) != len(expected):
        parser.error("--expected-regions must contain unique, non-empty region IDs")

    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
    result = audit_catalog(catalog, expected)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "regions_with_forecast_and_observation": result["regions_with_forecast_and_observation"],
        "regions_missing_observations": result["regions_missing_observations"],
        "regions_missing_forecasts": result["regions_missing_forecasts"],
        "out": str(args.out),
    }, ensure_ascii=False, sort_keys=True))
    if args.require_all_observations and result["regions_missing_observations"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
