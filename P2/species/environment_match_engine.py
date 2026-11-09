#!/usr/bin/env python3
"""Evidence-gated environmental match engine. Scores are not fish activity or catch probability."""
from __future__ import annotations
import argparse
import csv
import json
from pathlib import Path

RULE_FIELDS = {
    "rule_id", "candidate_id", "environment_field", "operator", "minimum", "maximum",
    "match_score", "weight", "region_scope", "life_stage", "evidence_id", "source_url",
    "confidence", "evidence_basis", "model_use_status", "reviewed_by", "reviewed_at",
}
ALLOWED_ENV_FIELDS = {
    "wave_height_m", "wave_period_s", "wave_direction_deg",
    "sea_surface_temperature_c", "ocean_current_velocity_ms",
    "ocean_current_direction_deg", "wind_speed_10m_ms", "wind_direction_10m_deg",
    "tide_height_m", "tidal_current_velocity_ms", "tidal_current_direction_deg",
    "precipitation_mm_h", "showers_mm_h", "precipitation_probability_pct",
}
ALLOWED_OPERATORS = {"between", "at_least", "at_most"}
ALLOWED_REGIONS = {
    "yilan_suao", "hualien_north", "hualien_south",
    "fengbin_shitiping", "chenggong_donghe", "taitung_south",
    "all_east_taiwan",
}
BLOCKED_TAXON_GATES = {
    "black_hair_alias_requires_morphological_species_check",
    "white_hair_is_kyphosus_genus_group_species_identification_required",
    "regional_occurrence_conflict_requires_review",
}

def read_csv(path: Path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))

def load_rules(path: Path):
    rows = read_csv(path)
    if not rows:
        return []
    if not RULE_FIELDS.issubset(rows[0]):
        raise ValueError("rules CSV missing required columns: " + ", ".join(sorted(RULE_FIELDS - set(rows[0]))))
    seen = set()
    rules = []
    for line, row in enumerate(rows, 2):
        rid = row["rule_id"].strip()
        if not rid or rid in seen:
            raise ValueError(f"rules row {line}: rule_id is blank or duplicated")
        seen.add(rid)
        # Unreviewed, indirect, or context-only evidence is never allowed to score.
        if row["model_use_status"] != "eligible_for_environment_scoring":
            continue
        if row["evidence_basis"] != "east_taiwan_direct_field":
            continue
        if row["confidence"] not in {"high", "medium"}:
            continue
        if not row["evidence_id"].strip() or not row["source_url"].startswith(("https://", "http://")):
            raise ValueError(f"rules row {line}: approved rule requires evidence_id and HTTP(S) source_url")
        if not row["reviewed_by"].strip() or not row["reviewed_at"].strip():
            raise ValueError(f"rules row {line}: approved rule requires reviewer and review date")
        if row["environment_field"] not in ALLOWED_ENV_FIELDS:
            raise ValueError(f"rules row {line}: unsupported environment_field")
        if row["operator"] not in ALLOWED_OPERATORS:
            raise ValueError(f"rules row {line}: unsupported operator")
        if row["region_scope"] not in ALLOWED_REGIONS:
            raise ValueError(f"rules row {line}: unsupported region_scope")
        try:
            score, weight = float(row["match_score"]), float(row["weight"])
            low = float(row["minimum"]) if row["minimum"].strip() else None
            high = float(row["maximum"]) if row["maximum"].strip() else None
        except ValueError as exc:
            raise ValueError(f"rules row {line}: numeric rule fields are invalid") from exc
        if not 0 <= score <= 100 or weight <= 0:
            raise ValueError(f"rules row {line}: match_score must be 0..100 and weight > 0")
        if row["operator"] == "between" and (low is None or high is None or low > high):
            raise ValueError(f"rules row {line}: between requires minimum <= maximum")
        if row["operator"] == "at_least" and low is None:
            raise ValueError(f"rules row {line}: at_least requires minimum")
        if row["operator"] == "at_most" and high is None:
            raise ValueError(f"rules row {line}: at_most requires maximum")
        row["_score"], row["_weight"] = score, weight
        row["_minimum"], row["_maximum"] = low, high
        rules.append(row)
    return rules

def gate_for(candidate_id: str, candidates: dict):
    return candidates.get(candidate_id, {}).get("eligibility_gate", "unregistered_candidate")

def matches(rule, value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if rule["operator"] == "between":
        return rule["_minimum"] <= value <= rule["_maximum"]
    if rule["operator"] == "at_least":
        return value >= rule["_minimum"]
    return value <= rule["_maximum"]

def evaluate(environment_records, candidate_rows, rules):
    candidates = {r["candidate_id"]: r for r in candidate_rows}
    results = []
    for env in environment_records:
        region = env.get("region_id", "")
        env_values = env.get("environment") or {}
        for cid, candidate in sorted(candidates.items()):
            gate = gate_for(cid, candidates)
            if gate in BLOCKED_TAXON_GATES or gate != "verified_taxon":
                results.append({
                    "candidate_id": cid, "region_id": region, "valid_time": env.get("valid_time", ""),
                    "status": "taxon_or_distribution_gate", "environment_match_score": "",
                    "rule_coverage": "0", "rules_matched": "0", "rules_evaluated": "0", "rules_applicable": "0",
                    "reason": "candidate identity or regional occurrence is not cleared",
                    "interpretation": "not_fish_activity_or_catch_probability",
                })
                continue
            applicable = [r for r in rules if r["candidate_id"] == cid and r["region_scope"] in {region, "all_east_taiwan"}]
            if not applicable:
                results.append({
                    "candidate_id": cid, "region_id": region, "valid_time": env.get("valid_time", ""),
                    "status": "insufficient_evidence", "environment_match_score": "",
                    "rule_coverage": "0", "rules_matched": "0", "rules_applicable": "0",
                    "reason": "no approved East Taiwan direct-field response rules",
                    "interpretation": "not_fish_activity_or_catch_probability",
                })
                continue
            evaluated = []
            missing = []
            for rule in applicable:
                value = env_values.get(rule["environment_field"])
                if value is None:
                    missing.append(rule["rule_id"])
                    continue
                result = matches(rule, value)
                if result is None:
                    missing.append(rule["rule_id"])
                else:
                    evaluated.append((rule, result))
            total_weight = sum(r["_weight"] for r in applicable)
            observed_weight = sum(r["_weight"] for r, _ in evaluated)
            coverage = observed_weight / total_weight if total_weight else 0
            if not evaluated:
                status, score = "insufficient_environment_data", ""
                reason = "all applicable rule input fields are missing or non-numeric"
            else:
                score = sum((r["_score"] if matched else 0.0) * r["_weight"] for r, matched in evaluated) / observed_weight
                status = "scored" if not missing else "partial_environment_data"
                reason = "explicit reviewed response rules only; non-matching conditions contribute zero; missing rules are excluded and coverage is reported"
            results.append({
                "candidate_id": cid, "region_id": region, "valid_time": env.get("valid_time", ""),
                "status": status, "environment_match_score": "" if score == "" else f"{score:.2f}",
                "rule_coverage": f"{coverage:.4f}", "rules_matched": str(sum(1 for _, matched in evaluated if matched)),
                "rules_evaluated": str(len(evaluated)), "rules_applicable": str(len(applicable)), "reason": reason,
                "interpretation": "environment_match_only_not_fish_activity_or_catch_probability",
            })
    return results

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--environment-jsonl", type=Path, required=True)
    parser.add_argument("--candidates-csv", type=Path, required=True)
    parser.add_argument("--rules-csv", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    environments = [json.loads(line) for line in args.environment_jsonl.read_text(encoding="utf-8").splitlines() if line.strip()]
    results = evaluate(environments, read_csv(args.candidates_csv), load_rules(args.rules_csv))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    fields = ["candidate_id", "region_id", "valid_time", "status", "environment_match_score", "rule_coverage", "rules_matched", "rules_evaluated", "rules_applicable", "reason", "interpretation"]
    with args.out.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(results)
    print(f"Evaluated {len(results)} candidate-region-time rows; no unapproved evidence was used.")

if __name__ == "__main__":
    main()
