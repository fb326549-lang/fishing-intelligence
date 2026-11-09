#!/usr/bin/env python3
"""Build an evidence-gap matrix for priority East Taiwan target species.

This is a research planning register only. It never manufactures response values.
"""
from __future__ import annotations
import argparse
import csv
from pathlib import Path

PRIORITY = {
    "c001": "black_hair_alias_requires_morphological_species_check",
    "c002": "white_hair_is_kyphosus_genus_group_species_identification_required",
    "c003": "verified_taxon",
    "c004": "verified_taxon",
    "c027": "verified_taxon",
    "c028": "verified_taxon",
    "c029": "verified_taxon",
    "c030": "regional_occurrence_conflict_requires_review",
    "c036": "verified_taxon",
    "c037": "verified_taxon",
}
DOMAINS = [
    ("temperature_range", "temperature_response"),
    ("wave_preference", "wave_response"),
    ("current_preference", "ocean_current_response"),
    ("tide_response", "tide_response"),
    ("wind_sensitivity", "wind_response"),
    ("activity_period", "activity_period"),
    ("salinity_preference", "salinity_response"),
]
FIELDS = [
    "candidate_id", "common_name_zh", "scientific_name", "response_domain",
    "parameter_code", "evidence_status", "eligibility_gate",
    "existing_parameter_codes", "evidence_ids", "literature_record_ids", "literature_use_status", "source_urls",
    "research_requirement", "model_use_policy",
]

def read_rows(path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))

def build_matrix(candidate_path: Path, ecology_path: Path, evidence_path: Path, literature_path: Path):
    candidates = {r["candidate_id"]: r for r in read_rows(candidate_path)}
    ecology = read_rows(ecology_path)
    evidence = read_rows(evidence_path)
    evidence_by_id = {r["evidence_id"]: r for r in evidence if r.get("evidence_id")}
    literature = read_rows(literature_path)
    result = []
    for candidate_id, gate in PRIORITY.items():
        candidate = candidates.get(candidate_id)
        if not candidate:
            raise ValueError(f"priority candidate not found: {candidate_id}")
        species_ecology = [r for r in ecology if r.get("candidate_id") == candidate_id]
        codes = sorted({r.get("parameter_code", "") for r in species_ecology if r.get("parameter_code")})
        evidence_ids = sorted({r.get("evidence_id", "") for r in species_ecology if r.get("evidence_id")})
        candidate_evidence = [r for r in evidence if r.get("candidate_id") == candidate_id]
        if not evidence_ids:
            evidence_ids = sorted({r.get("evidence_id", "") for r in candidate_evidence if r.get("evidence_id")})
        urls = sorted({evidence_by_id[eid].get("source_url", "") for eid in evidence_ids if eid in evidence_by_id and evidence_by_id[eid].get("source_url")})
        for domain, code in DOMAINS:
            literature_code = {"temperature_range":"temperature_response","wave_preference":"wave_response","current_preference":"ocean_current_response","tide_response":"tide_response","wind_sensitivity":"wind_response","activity_period":"activity_period","salinity_preference":"salinity_response"}[domain]
            domain_literature = [r for r in literature if r.get("candidate_id") == candidate_id and r.get("parameter_code") == literature_code]
            literature_ids = sorted({r.get("literature_record_id", "") for r in domain_literature if r.get("literature_record_id")})
            literature_urls = {r.get("source_url", "") for r in domain_literature if r.get("source_url")}
            if gate.startswith("white_hair"):
                status = "species_identification_required"
            elif gate.startswith("regional_occurrence"):
                status = "regional_evidence_gate"
            elif domain_literature:
                status = "external_literature_found_context_only"
            elif code in codes:
                status = "existing_parameter_requires_scope_and_source_review"
            else:
                status = "evidence_gap"
            result.append({
                "candidate_id": candidate_id,
                "common_name_zh": candidate.get("common_name_zh", ""),
                "scientific_name": candidate.get("scientific_name", ""),
                "response_domain": domain,
                "parameter_code": code,
                "evidence_status": status,
                "eligibility_gate": gate,
                "existing_parameter_codes": ";".join(codes),
                "evidence_ids": ";".join(evidence_ids),
                "literature_record_ids": ";".join(literature_ids),
                "literature_use_status": ";".join(sorted({r.get("model_use_status", "") for r in domain_literature if r.get("model_use_status")})),
                "source_urls": ";".join(sorted(set(urls) | literature_urls)),
                "research_requirement": "Find direct species-specific evidence for response direction/range, study region, season, life stage, method and uncertainty; do not infer a numeric threshold from habitat/depth descriptions.",
                "model_use_policy": "not_model_eligible_until_direct_response_evidence_reviewed",
            })
    return result

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--ecology", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--literature", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    rows = build_matrix(args.candidates, args.ecology, args.evidence, args.literature)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(f"Built {len(rows)} evidence-gap rows for {len(PRIORITY)} priority candidates; no response values inferred.")

if __name__ == "__main__":
    main()
