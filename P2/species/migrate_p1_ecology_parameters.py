#!/usr/bin/env python3
"""Evidence-preserving migration from P1 ecology rows to the P2 response register.

No ecological values are inferred or converted. Original parameter codes,
values, units, geographic scope, confidence and use status are retained.
"""
from __future__ import annotations
import argparse
import csv
from pathlib import Path

FIELDS = [
    "response_record_id", "candidate_id", "parameter_code", "parameter_value",
    "unit", "life_stage", "geographic_scope", "habitat_scope", "evidence_id",
    "source_url", "confidence", "model_use_status", "notes",
]

def read_csv(path: Path):
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))

def migrate(ecology_path: Path, evidence_path: Path):
    ecology = read_csv(ecology_path)
    evidence = read_csv(evidence_path)
    evidence_by_id = {}
    for row in evidence:
        evidence_id = row.get("evidence_id", "").strip()
        if not evidence_id:
            continue
        if evidence_id in evidence_by_id:
            prior = evidence_by_id[evidence_id]
            if prior.get("source_url") != row.get("source_url") or prior.get("candidate_id") != row.get("candidate_id"):
                raise ValueError(f"Conflicting evidence register entries for {evidence_id}")
        evidence_by_id[evidence_id] = row

    output = []
    errors = []
    for line, row in enumerate(ecology, start=2):
        evidence_id = row.get("evidence_id", "").strip()
        evidence_row = evidence_by_id.get(evidence_id)
        if not evidence_row:
            errors.append(f"ecology row {line}: evidence_id {evidence_id!r} not found")
            continue
        if evidence_row.get("candidate_id") != row.get("candidate_id"):
            errors.append(f"ecology row {line}: candidate_id mismatch for {evidence_id}")
            continue
        source_url = evidence_row.get("source_url", "").strip()
        if not source_url.startswith(("https://", "http://")):
            errors.append(f"ecology row {line}: evidence {evidence_id} has no HTTP(S) source_url")
            continue
        required = ("ecology_record_id", "candidate_id", "parameter_code", "parameter_value", "unit_or_format", "confidence", "model_use_status")
        missing = [key for key in required if not row.get(key, "").strip()]
        if missing:
            errors.append(f"ecology row {line}: missing {', '.join(missing)}")
            continue
        notes = row.get("limitations", "").strip()
        source_type = row.get("source_type", "").strip()
        note_parts = [x for x in (notes, f"source_type={source_type}" if source_type else "", "life_stage and habitat_scope were not separately specified in the P1 source record") if x]
        output.append({
            "response_record_id": row["ecology_record_id"],
            "candidate_id": row["candidate_id"],
            "parameter_code": row["parameter_code"],
            "parameter_value": row["parameter_value"],
            "unit": row["unit_or_format"],
            "life_stage": "not_specified",
            "geographic_scope": row.get("geographic_scope", "").strip() or "not_specified",
            "habitat_scope": "not_separately_specified",
            "evidence_id": evidence_id,
            "source_url": source_url,
            "confidence": row["confidence"],
            "model_use_status": row["model_use_status"],
            "notes": "; ".join(note_parts),
        })
    if errors:
        raise ValueError("\n".join(errors))
    return output

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ecology-csv", type=Path, required=True)
    parser.add_argument("--evidence-csv", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    rows = migrate(args.ecology_csv, args.evidence_csv)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(f"Migrated {len(rows)} evidence-linked ecology records; no values inferred.")

if __name__ == "__main__":
    main()
