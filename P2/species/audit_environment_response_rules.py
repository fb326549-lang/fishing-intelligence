#!/usr/bin/env python3
"""Audit environment-response rules and explain why each rule is or is not score-eligible."""
from __future__ import annotations
import argparse
import csv
from pathlib import Path
from urllib.parse import urlparse

from environment_match_engine import ALLOWED_ENV_FIELDS, ALLOWED_OPERATORS, ALLOWED_REGIONS

FIELDS = [
    "rule_id", "candidate_id", "eligibility_gate", "environment_field", "operator",
    "minimum", "maximum", "match_score", "weight", "region_scope", "life_stage",
    "evidence_id", "source_url", "confidence", "evidence_basis", "model_use_status",
    "reviewed_by", "reviewed_at", "audit_status", "rejection_reasons",
]

def read_csv(path: Path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))

def audit_rules(rule_rows, candidate_rows):
    gates = {}
    for row in candidate_rows:
        cid = row.get("candidate_id", "").strip()
        gate = row.get("eligibility_gate", "").strip()
        if not cid:
            raise ValueError("candidate register contains blank candidate_id")
        if cid in gates and gates[cid] != gate:
            raise ValueError(f"candidate {cid} has conflicting eligibility_gate values")
        gates[cid] = gate

    results = []
    seen = set()
    for line, row in enumerate(rule_rows, 2):
        reasons = []
        rid = row.get("rule_id", "").strip()
        cid = row.get("candidate_id", "").strip()
        if not rid:
            reasons.append("missing_rule_id")
        elif rid in seen:
            reasons.append("duplicate_rule_id")
        seen.add(rid)
        gate = gates.get(cid, "unregistered_candidate")
        if gate != "verified_taxon":
            reasons.append("candidate_taxonomy_or_distribution_gate")
        if row.get("model_use_status") != "eligible_for_environment_scoring":
            reasons.append("model_use_status_not_approved")
        if row.get("evidence_basis") != "east_taiwan_direct_field":
            reasons.append("evidence_not_direct_east_taiwan_field")
        if row.get("confidence") not in {"high", "medium"}:
            reasons.append("confidence_below_required_level")
        if row.get("environment_field") not in ALLOWED_ENV_FIELDS:
            reasons.append("unsupported_environment_field")
        if row.get("operator") not in ALLOWED_OPERATORS:
            reasons.append("unsupported_operator")
        if row.get("region_scope") not in ALLOWED_REGIONS:
            reasons.append("unsupported_region_scope")
        if not row.get("life_stage", "").strip():
            reasons.append("missing_life_stage")
        if not row.get("evidence_id", "").strip():
            reasons.append("missing_evidence_id")
        parsed = urlparse(row.get("source_url", "").strip())
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            reasons.append("invalid_source_url")
        if not row.get("reviewed_by", "").strip():
            reasons.append("missing_reviewer")
        if not row.get("reviewed_at", "").strip():
            reasons.append("missing_review_date")

        try:
            score = float(row.get("match_score", ""))
            if not 0 <= score <= 100:
                reasons.append("match_score_out_of_range")
        except (TypeError, ValueError):
            reasons.append("invalid_match_score")
        try:
            weight = float(row.get("weight", ""))
            if weight <= 0:
                reasons.append("weight_must_be_positive")
        except (TypeError, ValueError):
            reasons.append("invalid_weight")

        try:
            low = float(row["minimum"]) if row.get("minimum", "").strip() else None
            high = float(row["maximum"]) if row.get("maximum", "").strip() else None
            operator = row.get("operator")
            if operator == "between" and (low is None or high is None or low > high):
                reasons.append("invalid_between_range")
            elif operator == "at_least" and low is None:
                reasons.append("missing_minimum")
            elif operator == "at_most" and high is None:
                reasons.append("missing_maximum")
        except (TypeError, ValueError):
            reasons.append("invalid_numeric_range")

        result = {field: row.get(field, "") for field in FIELDS}
        result["eligibility_gate"] = gate
        result["audit_status"] = "approved_for_scoring" if not reasons else "excluded"
        result["rejection_reasons"] = ";".join(sorted(set(reasons)))
        results.append(result)
    return results

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rules-csv", type=Path, required=True)
    parser.add_argument("--candidates-csv", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    rows = audit_rules(read_csv(args.rules_csv), read_csv(args.candidates_csv))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    approved = sum(row["audit_status"] == "approved_for_scoring" for row in rows)
    excluded = len(rows) - approved
    print(f"Audited {len(rows)} environment response rules: {approved} approved, {excluded} excluded.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
