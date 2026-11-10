#!/usr/bin/env python3
"""Validate traceable species activity evidence; no activity or catch scores are produced."""
from __future__ import annotations
import argparse, csv
from pathlib import Path
from urllib.parse import urlparse

FIELDS = {
    "activity_evidence_id", "candidate_id", "taxon_scientific_name", "activity_dimension",
    "evidence_kind", "activity_measure", "reported_pattern", "time_basis", "geographic_scope",
    "study_period", "sample_size", "life_stage", "method", "source_literature_id", "source_url",
    "confidence", "transferability", "model_use_status", "limitations",
}
DIMENSIONS = {"occurrence_record","diel_activity","diel_feeding","seasonal_aggregation","seasonal_distribution","spawning_timing","feeding_activity","movement_activity","diel_activity_proxy","tide_associated_behavior","current_associated_distribution"}
KINDS = {"verified_museum_specimen","direct_field_observation","telemetry_proxy","captive_feeding_trial","fishery_catch_model","taxonomic_summary","larval_field_survey"}
CONTEXT_ONLY = {"context_only_northern_taiwan_field_study","context_only_taxonomic_database","context_only_captive_feeding","context_only_western_taiwan_fishery_model","context_only_external_region","context_only_western_taiwan_fishery_model","context_only_east_taiwan_occurrence"}

def read_csv(path: Path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))

def validate_activity_register(register_path: Path, candidates_path: Path, literature_path: Path):
    errors=[]
    with register_path.open(encoding="utf-8-sig", newline="") as f:
        reader=csv.DictReader(f)
        if not reader.fieldnames or not FIELDS.issubset(reader.fieldnames):
            return ["activity evidence CSV missing required columns: "+", ".join(sorted(FIELDS-set(reader.fieldnames or [])))]
        rows=list(reader)
    candidates={r["candidate_id"]:r for r in read_csv(candidates_path)}
    literature={r["literature_record_id"]:r for r in read_csv(literature_path)}
    seen=set()
    for n,row in enumerate(rows,2):
        aid=row["activity_evidence_id"].strip()
        if not aid or aid in seen: errors.append(f"row {n}: activity_evidence_id blank or duplicated")
        seen.add(aid)
        for key in FIELDS-{"sample_size"}:
            if not row.get(key,"").strip(): errors.append(f"row {n}: {key} is required")
        if row["activity_dimension"] not in DIMENSIONS: errors.append(f"row {n}: invalid activity_dimension")
        if row["evidence_kind"] not in KINDS: errors.append(f"row {n}: invalid evidence_kind")
        if row["confidence"] not in {"high","medium","low"}: errors.append(f"row {n}: invalid confidence")
        # P2.4.1 is evidence organization only. No row may become a scoring rule.
        if row["model_use_status"] not in CONTEXT_ONLY: errors.append(f"row {n}: activity evidence must remain context-only")
        parsed=urlparse(row["source_url"])
        if parsed.scheme not in {"http","https"} or not parsed.netloc: errors.append(f"row {n}: source_url must be HTTP(S)")
        candidate=candidates.get(row["candidate_id"])
        if not candidate: errors.append(f"row {n}: candidate_id not found")
        elif candidate.get("scientific_name","").strip()!=row["taxon_scientific_name"].strip():
            errors.append(f"row {n}: taxon_scientific_name does not match candidate register")
        source=literature.get(row["source_literature_id"])
        if not source: errors.append(f"row {n}: source_literature_id not found")
        else:
            if source.get("candidate_id","").strip()!=row["candidate_id"].strip(): errors.append(f"row {n}: literature candidate_id mismatch")
            if source.get("source_url","").strip()!=row["source_url"].strip(): errors.append(f"row {n}: source_url does not match literature register")
            if source.get("model_use_status","").strip()!=row["model_use_status"].strip(): errors.append(f"row {n}: model_use_status does not match literature register")
        if row["candidate_id"]=="c001" and "individual" not in row["limitations"].lower() and "鑑種" not in row["limitations"]:
            errors.append(f"row {n}: black-hair candidate requires individual identification limitation")
    return errors

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--activity-csv",type=Path,required=True)
    p.add_argument("--candidates-csv",type=Path,required=True)
    p.add_argument("--literature-csv",type=Path,required=True)
    a=p.parse_args()
    errors=validate_activity_register(a.activity_csv,a.candidates_csv,a.literature_csv)
    if errors:
        print("\n".join(errors)); return 1
    print("Species activity evidence validation passed; all records remain context-only.")
    return 0
if __name__=="__main__": raise SystemExit(main())
