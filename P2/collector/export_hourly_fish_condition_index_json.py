#!/usr/bin/env python3
"""Export the explicitly preliminary hourly relative fish index for the PWA."""
from __future__ import annotations
import argparse, csv, json
from datetime import datetime, timedelta, timezone
from pathlib import Path

REGIONS = [
    "yilan_suao", "hualien_north", "hualien_south",
    "fengbin_shitiping", "chenggong_donghe", "taitung_south",
]

def number(value):
    if value in (None, ""):
        return None
    return float(value)

def integer(value):
    if value in (None, ""):
        return None
    return int(value)

def json_value(value, fallback):
    if not value:
        return fallback
    parsed = json.loads(value)
    return parsed

def export_index(input_path: Path, output_path: Path, as_of: str):
    as_of_dt = datetime.fromisoformat(as_of.replace("Z", "+00:00"))
    if as_of_dt.tzinfo is None:
        raise ValueError("--as-of must include timezone")
    if as_of_dt.minute or as_of_dt.second or as_of_dt.microsecond:
        raise ValueError("--as-of must be aligned to the start of an hour")
    with input_path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    normalized = []
    for row in rows:
        if row.get("data_type") != "forecast" or row.get("region_id") not in REGIONS:
            continue
        valid = datetime.fromisoformat(row["valid_time"].replace("Z", "+00:00"))
        if not as_of_dt <= valid < as_of_dt + timedelta(hours=24):
            continue
        if row.get("model_version") != "preliminary-relative-1.1" or row.get("model_confidence") != "low":
            raise ValueError("FCI export requires preliminary-relative-1.1 rows marked low confidence")
        normalized.append({
            "candidate_id": row.get("candidate_id", ""),
            "common_name_zh": row.get("common_name_zh", ""),
            "scientific_name": row.get("scientific_name", ""),
            "region_id": row.get("region_id", ""),
            "valid_time": row.get("valid_time", ""),
            "data_type": "forecast",
            "model_status": row.get("model_status", ""),
            "model_confidence": row.get("model_confidence", "low"),
            "model_version": row.get("model_version", "preliminary-relative-1.1"),
            "feeding_condition_score": number(row.get("feeding_condition_score")),
            "feeding_condition_status": row.get("feeding_condition_status", "insufficient_evidence"),
            "feeding_condition_coverage": number(row.get("feeding_condition_coverage")),
            "environment_suitability_score": number(row.get("environment_suitability_score")),
            "environment_suitability_status": row.get("environment_suitability_status", "insufficient_evidence"),
            "environment_suitability_coverage": number(row.get("environment_suitability_coverage")),
            "fish_activity_score": number(row.get("fish_activity_score")),
            "fish_activity_status": row.get("fish_activity_status", "insufficient_evidence"),
            "fish_activity_coverage": number(row.get("fish_activity_coverage")),
            "overall_fish_condition_index": number(row.get("overall_fish_condition_index")),
            "species_weights": json_value(row.get("species_weights_json", ""), {}),
            "best_hour_status_6h": row.get("best_hour_status_6h", "not_established"),
            "best_hour_rank_6h": integer(row.get("best_hour_rank_6h")),
            "best_hour_status_12h": row.get("best_hour_status_12h", "not_established"),
            "best_hour_rank_12h": integer(row.get("best_hour_rank_12h")),
            "best_hour_status_24h": row.get("best_hour_status_24h", "not_established"),
            "best_hour_rank_24h": integer(row.get("best_hour_rank_24h")),
            "indicator_trace": json_value(row.get("indicator_trace_json", ""), []),
            "interpretation": "preliminary_species_relative_fish_condition_index_not_catch_probability",
        })
    output = {
        "schema_version": 1,
        "source": "fishing-intelligence-fci-preliminary-1.1",
        "generated_at": datetime.now(timezone(timedelta(hours=8))).isoformat(),
        "as_of": as_of_dt.isoformat(),
        "regions": REGIONS,
        "horizons_hours": [6, 12, 24],
        "rows": normalized,
        "model_note": "Preliminary low-confidence relative index. It combines qualitative diel evidence, within-region relative wave/wind ranks and equal interim indicator weights; it is not validated against East Taiwan catch data and is not a catch probability. Missing prey, habitat-specific response, current and tide effects are not inferred.",
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print({"rows": len(normalized), "scored_rows": sum(r["overall_fish_condition_index"] is not None for r in normalized),
           "regions": len(REGIONS), "horizons_hours": [6, 12, 24]})

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--as-of", required=True)
    a = p.parse_args()
    export_index(a.input, a.out, a.as_of)

if __name__ == "__main__":
    main()
