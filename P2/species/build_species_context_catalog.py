#!/usr/bin/env python3
"""Build a source-linked species ecology context catalog; never create fishing scores."""
from __future__ import annotations
import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path

CATEGORY_MAP = {
    "habitat": "habitat", "substrate": "habitat", "juvenile_habitat": "habitat",
    "reported_depth_min": "depth", "reported_depth_max": "depth",
    "typical_depth_min": "depth", "typical_depth_max": "depth",
    "typical_habitat_depth_min": "depth", "typical_habitat_depth_max": "depth",
    "activity_water_layer": "activity", "diel_activity": "activity",
    "vertical_movement": "activity", "aggregation": "activity",
    "social_behavior": "activity", "juvenile_aggregation": "activity",
    "adult_aggregation": "activity", "foraging_aggregation": "activity",
    "adult_social_behavior": "activity", "juvenile_social_behavior": "activity",
    "nocturnal_social_behavior": "activity", "movement_behavior": "activity",
    "sex_specific_social_behavior": "activity",
    "diet": "feeding", "feeding": "feeding", "foraging_behavior": "feeding",
    "seasonal_diet": "feeding", "juvenile_diet": "feeding", "adult_diet": "feeding",
    "spawning_period": "reproduction", "reproductive_behavior": "reproduction",
    "sex_change": "reproduction",
    "regional_fishery_season": "fishery", "fishery_occurrence": "fishery",
}
REQUIRED_ECOLOGY = {
    "ecology_record_id", "candidate_id", "scientific_name", "parameter_code",
    "parameter_value", "unit_or_format", "geographic_scope", "evidence_id",
    "confidence", "model_use_status", "limitations",
}

def read_csv(path: Path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))

def build_catalog(candidates_path: Path, ecology_path: Path, evidence_path: Path):
    candidates = {r["candidate_id"]: r for r in read_csv(candidates_path)}
    evidence = {r["evidence_id"]: r for r in read_csv(evidence_path) if r.get("evidence_id")}
    with ecology_path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = REQUIRED_ECOLOGY - set(reader.fieldnames or [])
        if missing:
            raise ValueError("ecology register missing fields: " + ", ".join(sorted(missing)))
        ecology = list(reader)
    records = []
    for row in ecology:
        cid = row.get("candidate_id", "").strip()
        eid = row.get("evidence_id", "").strip()
        if cid not in candidates:
            raise ValueError(f"unknown candidate_id {cid!r} in {row.get('ecology_record_id')}")
        source = evidence.get(eid)
        if not source or not source.get("source_url"):
            raise ValueError(f"missing traceable evidence/source URL for {row.get('ecology_record_id')}")
        if not row.get("model_use_status", "").strip():
            raise ValueError(f"missing model_use_status for {row.get('ecology_record_id')}")
        candidate = candidates[cid]
        records.append({
            "ecology_record_id": row.get("ecology_record_id", ""),
            "candidate_id": cid,
            "common_name_zh": candidate.get("common_name_zh", ""),
            "scientific_name": row.get("scientific_name", "") or candidate.get("scientific_name", ""),
            "taxonomy_status": candidate.get("taxonomy_status", ""),
            "category": CATEGORY_MAP.get(row.get("parameter_code", ""), "other"),
            "parameter_code": row.get("parameter_code", ""),
            "parameter_value": row.get("parameter_value", ""),
            "unit_or_format": row.get("unit_or_format", ""),
            "geographic_scope": row.get("geographic_scope", ""),
            "evidence_id": eid,
            "source_name": source.get("source_name", ""),
            "source_url": source.get("source_url", ""),
            "confidence": row.get("confidence", ""),
            "model_use_status": row.get("model_use_status", ""),
            "limitations": row.get("limitations", ""),
        })
    records.sort(key=lambda r: (r["candidate_id"], r["category"], r["parameter_code"], r["ecology_record_id"]))
    return {
        "schema_version": 1,
        "source": "P1 evidence-linked species ecology register",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "interpretation": "Species-level natural-history context only; not current presence, local fish abundance, fishing-depth advice, activity score, catch probability, or best fishing time.",
        "record_count": len(records),
        "records": records,
    }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--ecology", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    payload = build_catalog(args.candidates, args.ecology, args.evidence)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"Built {payload['record_count']} traceable species ecology context records; no fishing scores inferred.")

if __name__ == "__main__":
    main()
