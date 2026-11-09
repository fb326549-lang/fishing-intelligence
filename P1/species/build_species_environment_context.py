#!/usr/bin/env python3
"""Build evidence-gated species/environment context; never invent catch odds.

This first engine release deliberately does not emit activity scores or catch
probabilities. Existing ecology records describe broad habitat/depth context,
not validated species-specific responses to hourly waves, currents or SST.
"""
from __future__ import annotations
import argparse
import csv
import json
from pathlib import Path

ELIGIBLE_TAXON_STATUS = "verified_taxon"
ELIGIBLE_REGIONAL_STATUS = "regional_distribution_documented"
ENVIRONMENT_FIELDS = {
    "wave_height_m": "wave_height_m",
    "wave_period_s": "wave_period_s",
    "sea_surface_temperature_c": "sea_surface_temperature_c",
    "sea_level_height_msl_m": "sea_level_height_msl_m",
    "ocean_current_velocity_ms": "ocean_current_velocity_ms",
    "wind_speed_10m_ms": "wind_speed_10m_ms",
    "wind_direction_10m_deg": "wind_direction_10m_deg",
}
MODEL_VERSION = "0.1.0-evidence-gated"

def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))

def as_number(value: str | None):
    if value in (None, "", "None", "null"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--species-dir", default="P1/species")
    parser.add_argument("--regional-forecast", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    species_dir = Path(args.species_dir)
    candidates = read_csv(species_dir / "species_candidate_register.csv")
    evidence = read_csv(species_dir / "species_evidence_register.csv")
    ecology = read_csv(species_dir / "species_ecology_parameters.csv")
    forecasts = read_csv(Path(args.regional_forecast))

    evidence_by_candidate: dict[str, list[dict[str, str]]] = {}
    for item in evidence:
        evidence_by_candidate.setdefault(item["candidate_id"], []).append(item)
    ecology_by_candidate: dict[str, list[dict[str, str]]] = {}
    for item in ecology:
        ecology_by_candidate.setdefault(item["candidate_id"], []).append(item)

    # Protected species may be present in the ecological reference database,
    # but must never enter the target-fishing context output.
    protected_ids = {
        item.get("candidate_id", "")
        for item in ecology
        if item.get("parameter_code") == "conservation_status"
        and any(
            marker in item.get("parameter_value", "").lower()
            for marker in ("prohibited to catch", "protected wildlife", "保育類", "禁止垂釣")
        )
    }
    protected_candidates = [
        item for item in candidates if item.get("candidate_id") in protected_ids
    ]
    eligible = [
        item for item in candidates
        if item.get("taxonomy_status") == ELIGIBLE_TAXON_STATUS
        and item.get("regional_evidence_status") == ELIGIBLE_REGIONAL_STATUS
        and item.get("scientific_name", "").strip()
        and item.get("candidate_id") not in protected_ids
    ]

    output = []
    for forecast in forecasts:
        region = forecast.get("region_id", "")
        horizon = forecast.get("horizon_hours", "")
        for fish in eligible:
            cid = fish["candidate_id"]
            ev = evidence_by_candidate.get(cid, [])
            eco = ecology_by_candidate.get(cid, [])
            habitat_parameters = [
                x for x in eco
                if x.get("parameter_code") == "habitat"
                and x.get("model_use_status") == "eligible_as_species_context"
            ]
            habitat_values = sorted({
                part.strip()
                for item in habitat_parameters
                for part in item.get("parameter_value", "").split(";")
                if part.strip()
            })
            context = {
                key: as_number(forecast.get(source_key))
                for key, source_key in ENVIRONMENT_FIELDS.items()
            }
            available = sum(value is not None for value in context.values())
            output.append({
                "region_id": region,
                "horizon_hours": horizon,
                "target_time": forecast.get("target_time", ""),
                "candidate_id": cid,
                "common_name_zh": fish.get("common_name_zh", ""),
                "scientific_name": fish.get("scientific_name", ""),
                "fishery_group": fish.get("fishery_group", ""),
                "regional_evidence_status": fish.get("regional_evidence_status", ""),
                "taxonomy_status": fish.get("taxonomy_status", ""),
                "evidence_record_count": len(ev),
                "evidence_ids": ";".join(x.get("evidence_id", "") for x in ev),
                "best_evidence_confidence": (
                    "high" if any(x.get("confidence") == "high" for x in ev)
                    else "medium" if any(x.get("confidence") == "medium" for x in ev)
                    else "low" if ev else "none"
                ),
                "habitat_context": ";".join(habitat_values),
                "habitat_evidence_ids": ";".join(
                    x.get("evidence_id", "") for x in habitat_parameters
                ),
                "environment_context_json": json.dumps(context, ensure_ascii=False, sort_keys=True),
                "environment_available_count": available,
                "environment_expected_count": len(ENVIRONMENT_FIELDS),
                "environment_completeness_pct": round(available / len(ENVIRONMENT_FIELDS) * 100, 1),
                "environment_score": "",
                "activity_score": "",
                "feeding_score": "",
                "catch_probability": "",
                "model_readiness": "insufficient_species_specific_response_parameters",
                "result_type": "species_and_environment_context_only",
                "model_name": "evidence_gated_species_context",
                "model_version": MODEL_VERSION,
                "limitations": (
                    "East Taiwan distribution is not proof of presence at this exact region or spot; "
                    "habitat/depth descriptions are not fishing recommendations; "
                    "no validated species-specific response thresholds or catch logs are available; "
                    "no activity score or catch probability is calculated."
                ),
            })

    if not output:
        raise SystemExit("No eligible species with verified taxonomy and East Taiwan distribution evidence.")
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    fields = list(output[0])
    with out.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(output)
    summary = {
        "status": "generated_context_only",
        "model_version": MODEL_VERSION,
        "eligible_species": len(eligible),
        "excluded_protected_species": [
            {
                "candidate_id": item.get("candidate_id", ""),
                "common_name_zh": item.get("common_name_zh", ""),
                "reason": "protected_species_not_target_eligible",
            }
            for item in protected_candidates
        ],
        "forecast_region_horizon_records": len(forecasts),
        "output_records": len(output),
        "activity_scores_generated": 0,
        "catch_probabilities_generated": 0,
        "reason_scores_withheld": "No validated species-specific environmental response parameters or local effort/catch dataset.",
        "scope_note": "This is an evidence-linked context layer, not a fish activity forecast.",
    }
    out.with_name("species_environment_context_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
