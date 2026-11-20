#!/usr/bin/env python3
"""Compare observed captive-feeding points without turning them into field scores.

This research helper compares exact measured temperature points for the same
macroalga in L052. It never interpolates, extrapolates, or emits an FCI.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

DEFAULT_REGISTER = Path(__file__).with_name("southern_drummer_response_curve_observations.csv")
EXPECTED_TAXON = "c036"
ELIGIBLE_STATUS = "context_only_captive_feeding"


def load_temperature_observations(path: Path = DEFAULT_REGISTER) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    observations = []
    seen = set()
    for row in rows:
        if row.get("candidate_id") != EXPECTED_TAXON or row.get("source_literature_id") != "L052":
            continue
        if row.get("indicator_code") != "feeding_condition" or row.get("environment_field") != "sea_surface_temperature_c":
            continue
        if row.get("model_use_status") != ELIGIBLE_STATUS:
            raise ValueError(f"{row.get('response_curve_id')}: L052 points must remain context-only")
        if row.get("observed_response_unit") != "% body weight/day":
            raise ValueError(f"{row.get('response_curve_id')}: unsupported response unit")
        point_id, group = row.get("response_curve_id", ""), row.get("response_group", "")
        try:
            temperature, rate = float(row["condition_value"]), float(row["observed_response"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"{point_id}: temperature and response must be numeric") from exc
        if not math.isfinite(temperature) or not math.isfinite(rate) or rate < 0:
            raise ValueError(f"{point_id}: temperature/rate must be finite and rate non-negative")
        key = (group, temperature)
        if not point_id or not group or key in seen:
            raise ValueError(f"{point_id}: missing identity or duplicate group-temperature point")
        if not row.get("source_url", "").startswith("https://"):
            raise ValueError(f"{point_id}: missing traceable source URL")
        seen.add(key)
        observations.append({
            "response_curve_id": point_id, "candidate_id": EXPECTED_TAXON,
            "response_group": group, "temperature_c": temperature,
            "feeding_rate_percent_body_weight_per_day": rate,
            "evidence_id": row["source_literature_id"], "source_url": row["source_url"],
            "model_use_status": row["model_use_status"],
            "transferability": row["transferability"], "limitations": row["limitations"],
        })
    if not observations:
        raise ValueError("no eligible L052 context observations found")
    return observations


def compare_observed_points(observations: list[dict], response_group: str,
                            reference_temperature_c: float, comparison_temperature_c: float) -> dict:
    """Return a descriptive ratio for two exact points; never infer between them."""
    if not math.isfinite(reference_temperature_c) or not math.isfinite(comparison_temperature_c):
        raise ValueError("temperatures must be finite")
    group_points = [p for p in observations if p["response_group"] == response_group]
    exact = lambda temperature: next((p for p in group_points if p["temperature_c"] == temperature), None)
    reference, comparison = exact(reference_temperature_c), exact(comparison_temperature_c)
    result = {
        "candidate_id": EXPECTED_TAXON, "response_group": response_group,
        "reference_temperature_c": reference_temperature_c,
        "comparison_temperature_c": comparison_temperature_c,
        "evidence_basis": "observed_points_from_japanese_captive_trial",
        "model_use_status": ELIGIBLE_STATUS, "transferability": "low_for_east_taiwan",
        "is_fci_score": False, "is_fishing_probability": False,
        "interpolation_performed": False, "extrapolation_performed": False,
    }
    if reference is None or comparison is None:
        return {**result, "status": "no_exact_observed_point", "reference_rate": None,
                "comparison_rate": None,
                "reference_point_id": reference["response_curve_id"] if reference else None,
                "comparison_point_id": comparison["response_curve_id"] if comparison else None,
                "rate_ratio_reference_over_comparison": None}
    ref_rate = reference["feeding_rate_percent_body_weight_per_day"]
    cmp_rate = comparison["feeding_rate_percent_body_weight_per_day"]
    ratio = ref_rate / cmp_rate if cmp_rate else None
    return {**result, "status": "observed_point_comparison", "reference_rate": ref_rate,
            "comparison_rate": cmp_rate, "response_unit": "% body weight/day",
            "reference_point_id": reference["response_curve_id"],
            "comparison_point_id": comparison["response_curve_id"],
            "rate_ratio_reference_over_comparison": round(ratio, 6) if ratio is not None else None,
            "evidence_ids": sorted({reference["evidence_id"], comparison["evidence_id"]}),
            "source_urls": sorted({reference["source_url"], comparison["source_url"]}),
            "limitations": sorted({reference["limitations"], comparison["limitations"]})}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--response-group", required=True,
                        choices=("macroalgae_sst_sargassum", "macroalgae_sst_eisenia"))
    parser.add_argument("--reference-temperature-c", type=float, required=True)
    parser.add_argument("--comparison-temperature-c", type=float, required=True)
    parser.add_argument("--observations-csv", type=Path, default=DEFAULT_REGISTER)
    args = parser.parse_args()
    observations = load_temperature_observations(args.observations_csv)
    result = compare_observed_points(observations, args.response_group,
                                    args.reference_temperature_c, args.comparison_temperature_c)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
