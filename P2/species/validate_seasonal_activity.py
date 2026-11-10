#!/usr/bin/env python3
"""Validate seasonal fish activity evidence without creating seasonal activity scores."""
from __future__ import annotations
import argparse, csv
from pathlib import Path
from urllib.parse import urlparse

FIELDS = {
    "seasonal_evidence_id", "candidate_id", "taxon_scientific_name", "seasonal_dimension",
    "evidence_kind", "reported_season", "reported_pattern", "geographic_scope", "study_period",
    "life_stage", "method", "source_literature_id", "source_url", "confidence",
    "transferability", "model_use_status", "limitations",
}
DIMENSIONS = {"seasonal_aggregation","seasonal_nearshore_aggregation","seasonal_distribution",
              "seasonal_feeding","seasonal_activity_proxy","spawning_timing"}
KINDS = {"direct_field_observation","underwater_visual_survey","natural_history_observation",
         "fishery_catch_model","telemetry_proxy","captive_trial","taxonomic_summary", "captive_activity_observation"}

def read_csv(path: Path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))

def validate_seasonal_register(register_path: Path, candidates_path: Path, literature_path: Path):
    errors=[]
    with register_path.open(encoding="utf-8-sig", newline="") as f:
        reader=csv.DictReader(f)
        if not reader.fieldnames or not FIELDS.issubset(reader.fieldnames):
            return ["seasonal activity CSV missing required columns: "+", ".join(sorted(FIELDS-set(reader.fieldnames or [])))]
        rows=list(reader)
    candidates={r["candidate_id"]:r for r in read_csv(candidates_path)}
    literature={r["literature_record_id"]:r for r in read_csv(literature_path)}
    seen=set()
    for n,row in enumerate(rows,2):
        eid=row["seasonal_evidence_id"].strip()
        if not eid or eid in seen: errors.append(f"row {n}: seasonal_evidence_id blank or duplicated")
        seen.add(eid)
        for key in FIELDS:
            if not row.get(key,"").strip(): errors.append(f"row {n}: {key} is required")
        if row["seasonal_dimension"] not in DIMENSIONS: errors.append(f"row {n}: invalid seasonal_dimension")
        if row["evidence_kind"] not in KINDS: errors.append(f"row {n}: invalid evidence_kind")
        if row["confidence"] not in {"high","medium","low"}: errors.append(f"row {n}: invalid confidence")
        # Seasonal records remain contextual until validated East Taiwan species-level datasets exist.
        if not row["model_use_status"].startswith("context_only_"):
            errors.append(f"row {n}: seasonal evidence must remain context_only")
        parsed=urlparse(row["source_url"])
        if parsed.scheme not in {"http","https"} or not parsed.netloc:
            errors.append(f"row {n}: source_url must be HTTP(S)")
        candidate=candidates.get(row["candidate_id"])
        if not candidate: errors.append(f"row {n}: candidate_id not found")
        elif candidate.get("scientific_name","").strip()!=row["taxon_scientific_name"].strip():
            errors.append(f"row {n}: taxon_scientific_name does not match candidate register")
        source=literature.get(row["source_literature_id"])
        if not source: errors.append(f"row {n}: source_literature_id not found")
        else:
            if source.get("candidate_id","").strip()!=row["candidate_id"].strip():
                errors.append(f"row {n}: literature candidate_id mismatch")
            if source.get("taxon_scientific_name","").strip()!=row["taxon_scientific_name"].strip():
                errors.append(f"row {n}: literature taxon mismatch")
            if source.get("source_url","").strip()!=row["source_url"].strip():
                errors.append(f"row {n}: source_url does not match literature register")
            if source.get("model_use_status","").strip()!=row["model_use_status"].strip():
                errors.append(f"row {n}: model_use_status does not match literature register")
        if row["candidate_id"]=="c001" and "individual" not in row["limitations"].lower() and "鑑種" not in row["limitations"]:
            errors.append(f"row {n}: black-hair candidate requires individual identification limitation")
        if row["candidate_id"]=="c002":
            errors.append(f"row {n}: white-hair vernacular group cannot inherit species-specific seasonal evidence")
    return errors

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--seasonal-csv",type=Path,required=True)
    p.add_argument("--candidates-csv",type=Path,required=True)
    p.add_argument("--literature-csv",type=Path,required=True)
    a=p.parse_args()
    errors=validate_seasonal_register(a.seasonal_csv,a.candidates_csv,a.literature_csv)
    if errors:
        print("\\n".join(errors)); return 1
    print("Seasonal activity evidence validation passed; all records remain context-only.")
    return 0
if __name__=="__main__": raise SystemExit(main())
