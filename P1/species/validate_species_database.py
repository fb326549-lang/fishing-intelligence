#!/usr/bin/env python3
"""Validate species candidate, evidence, and ecology CSV cross-references.

Uses only Python's standard library. This checks data integrity, not biological
truth or the quality of the cited research.
"""
from __future__ import annotations
import argparse
import csv
import json
from pathlib import Path

REQUIRED = {
    "candidates": {"candidate_id", "common_name_zh", "scientific_name", "taxonomy_status"},
    "evidence": {"evidence_id", "candidate_id", "scientific_name", "source_name", "source_url", "confidence"},
    "ecology": {"ecology_record_id", "candidate_id", "scientific_name", "parameter_code",
                "parameter_value", "evidence_id", "model_use_status"},
}

def read_csv(path: Path, label: str, errors: list[str]) -> list[dict[str, str]]:
    if not path.exists():
        errors.append(f"{label}: file not found: {path}")
        return []
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            fields = set(reader.fieldnames or [])
            missing = REQUIRED[label] - fields
            if missing:
                errors.append(f"{label}: missing columns: {', '.join(sorted(missing))}")
            return list(reader)
    except (OSError, csv.Error) as exc:
        errors.append(f"{label}: cannot read CSV: {exc}")
        return []

def duplicate_ids(rows: list[dict[str, str]], field: str, label: str, errors: list[str]) -> None:
    seen: set[str] = set()
    for index, row in enumerate(rows, start=2):
        value = (row.get(field) or "").strip()
        if not value:
            errors.append(f"{label} row {index}: blank {field}")
        elif value in seen:
            errors.append(f"{label} row {index}: duplicate {field}={value}")
        seen.add(value)

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--species-dir", default="P1/species")
    parser.add_argument("--out", default="species_data_validation.json")
    args = parser.parse_args()
    base = Path(args.species_dir)
    errors: list[str] = []
    candidates = read_csv(base / "species_candidate_register.csv", "candidates", errors)
    evidence = read_csv(base / "species_evidence_register.csv", "evidence", errors)
    ecology = read_csv(base / "species_ecology_parameters.csv", "ecology", errors)

    duplicate_ids(candidates, "candidate_id", "candidates", errors)
    duplicate_ids(evidence, "evidence_id", "evidence", errors)
    duplicate_ids(ecology, "ecology_record_id", "ecology", errors)

    candidate_ids = {r.get("candidate_id", "").strip() for r in candidates}
    evidence_ids = {r.get("evidence_id", "").strip() for r in evidence}
    candidate_by_id = {r.get("candidate_id", "").strip(): r for r in candidates}

    allowed_confidence = {"high", "medium", "low"}
    for index, row in enumerate(evidence, start=2):
        confidence = (row.get("confidence") or "").strip().lower()
        if confidence not in allowed_confidence:
            errors.append(f"evidence row {index}: invalid confidence={confidence!r}")
        cid = (row.get("candidate_id") or "").strip()
        if cid and cid not in candidate_ids:
            errors.append(f"evidence row {index}: unknown candidate_id={cid}")
        if not (row.get("source_url") or "").strip():
            errors.append(f"evidence row {index}: missing source_url")

    for index, row in enumerate(ecology, start=2):
        cid = (row.get("candidate_id") or "").strip()
        eid = (row.get("evidence_id") or "").strip()
        if cid not in candidate_ids:
            errors.append(f"ecology row {index}: unknown candidate_id={cid}")
        if eid not in evidence_ids:
            errors.append(f"ecology row {index}: unknown evidence_id={eid}")
        if cid in candidate_by_id:
            candidate_scientific = (candidate_by_id[cid].get("scientific_name") or "").strip()
            ecology_scientific = (row.get("scientific_name") or "").strip()
            # Group candidates may intentionally have no single scientific name.
            if candidate_scientific and ecology_scientific and candidate_scientific != ecology_scientific:
                errors.append(
                    f"ecology row {index}: scientific_name mismatch for {cid}: "
                    f"candidate={candidate_scientific}, ecology={ecology_scientific}"
                )

    result = {
        "status": "passed" if not errors else "failed",
        "counts": {"candidates": len(candidates), "evidence_records": len(evidence),
                   "ecology_records": len(ecology)},
        "checks": ["required columns", "unique record IDs", "candidate references",
                   "evidence references", "evidence source URLs", "confidence vocabulary", "scientific-name consistency"],
        "error_count": len(errors),
        "errors": errors,
        "scope_note": "Structural validation only; does not validate taxonomy, source accuracy, or ecological claims.",
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if not errors else 1

if __name__ == "__main__":
    raise SystemExit(main())
