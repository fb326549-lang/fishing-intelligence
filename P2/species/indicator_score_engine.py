#!/usr/bin/env python3
"""Evidence-gated three-indicator fish condition model for East Taiwan.

No scores are emitted unless each indicator has fully observed, reviewed,
East-Taiwan direct-field rules and a species-specific validated weight profile.
An environmental match alone is never interpreted as fish activity or catch probability.
"""
from __future__ import annotations
import argparse, csv, json
from datetime import datetime, timedelta
from pathlib import Path

INDICATORS = ("feeding_condition", "environment_suitability", "fish_activity")
REGIONS = {
    "yilan_suao", "hualien_north", "hualien_south",
    "fengbin_shitiping", "chenggong_donghe", "taitung_south",
    "all_east_taiwan",
}
NUMERIC_FIELDS = {
    "wave_height_m", "wave_period_s", "wave_direction_deg",
    "sea_surface_temperature_c", "ocean_current_velocity_ms",
    "ocean_current_direction_deg", "wind_speed_10m_ms",
    "wind_direction_10m_deg", "tide_height_m",
    "tidal_current_velocity_ms", "tidal_current_direction_deg",
    "precipitation_mm_h", "showers_mm_h", "precipitation_probability_pct",
}
DERIVED_FIELDS = {"daylight", "month"}
RULE_FIELDS = {
    "rule_id", "candidate_id", "indicator_code", "response_group", "environment_field",
    "operator", "minimum", "maximum", "match_score", "weight",
    "region_scope", "life_stage", "evidence_id", "source_url",
    "confidence", "evidence_basis", "model_use_status",
    "reviewed_by", "reviewed_at", "limitations",
}
WEIGHT_FIELDS = {
    "candidate_id", "feeding_weight", "environment_weight", "activity_weight",
    "evidence_basis", "model_use_status", "source_ids", "reviewed_by",
    "reviewed_at", "notes",
}

def read_csv(path: Path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))

def parse_dt(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be timezone-aware ISO-8601")
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError(f"{label} must include timezone")
    return dt

def derived_features(record):
    env = record.get("environment") or {}
    values = {k: v for k, v in env.items() if k in NUMERIC_FIELDS}
    valid = parse_dt(record.get("valid_time"), "valid_time")
    values["month"] = float(valid.month)
    sunrise, sunset = env.get("sunrise"), env.get("sunset")
    if sunrise and sunset:
        rise = parse_dt(sunrise, "sunrise")
        set_ = parse_dt(sunset, "sunset")
        values["daylight"] = 1.0 if rise <= valid < set_ else 0.0
    return values

def unique_candidates(rows):
    result = {}
    for row in rows:
        cid = row.get("candidate_id", "").strip()
        if not cid:
            raise ValueError("candidate register contains blank candidate_id")
        previous = result.get(cid)
        if previous and previous.get("eligibility_gate", "") != row.get("eligibility_gate", ""):
            raise ValueError(f"candidate {cid} has conflicting eligibility_gate values")
        if not previous:
            result[cid] = row
    return [result[cid] for cid in sorted(result)]

def select_latest_forecast_vintages(records):
    latest = {}
    passthrough = []
    for record in records:
        if record.get("data_type") != "forecast":
            passthrough.append(record)
            continue
        collected = parse_dt(record.get("collected_at"), "collected_at")
        key = (record.get("region_id", ""), record.get("valid_time", ""))
        previous = latest.get(key)
        if previous is None or collected > previous[0]:
            latest[key] = (collected, record)
    return passthrough + [item[1][1] for item in sorted(latest.items())]


def load_rules(rows, candidates):
    gates = {r["candidate_id"]: r.get("eligibility_gate", "") for r in candidates}
    result, seen = [], set()
    for line, row in enumerate(rows, 2):
        rid = row.get("rule_id", "").strip()
        if not rid or rid in seen:
            raise ValueError(f"rule row {line}: rule_id blank or duplicated")
        seen.add(rid)
        # Non-approved rows are retained in the register but never score.
        if row.get("model_use_status") != "eligible_for_indicator_scoring":
            continue
        if gates.get(row.get("candidate_id")) != "verified_taxon":
            raise ValueError(f"rule {rid}: candidate taxonomy gate is not cleared")
        if row.get("evidence_basis") != "east_taiwan_direct_field":
            raise ValueError(f"rule {rid}: scoring requires East Taiwan direct field evidence")
        if row.get("confidence") not in {"high", "medium"}:
            raise ValueError(f"rule {rid}: confidence is below the scoring threshold")
        if row.get("indicator_code") not in INDICATORS:
            raise ValueError(f"rule {rid}: unknown indicator_code")
        if row.get("environment_field") not in NUMERIC_FIELDS | DERIVED_FIELDS:
            raise ValueError(f"rule {rid}: unsupported environment_field")
        if row.get("operator") not in {"between", "at_least", "at_most"}:
            raise ValueError(f"rule {rid}: unsupported operator")
        if row.get("region_scope") not in REGIONS:
            raise ValueError(f"rule {rid}: unsupported region_scope")
        if not all(row.get(k, "").strip() for k in ("response_group", "life_stage", "evidence_id", "source_url", "reviewed_by", "reviewed_at")):
            raise ValueError(f"rule {rid}: missing provenance/review fields")
        if not row["source_url"].startswith(("https://", "http://")):
            raise ValueError(f"rule {rid}: invalid source URL")
        try:
            low = float(row["minimum"]) if row.get("minimum", "").strip() else None
            high = float(row["maximum"]) if row.get("maximum", "").strip() else None
            score, weight = float(row["match_score"]), float(row["weight"])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"rule {rid}: invalid numeric field") from exc
        if not 0 <= score <= 100 or weight <= 0:
            raise ValueError(f"rule {rid}: match_score must be 0..100 and weight > 0")
        if row["operator"] == "between" and (low is None or high is None or low > high):
            raise ValueError(f"rule {rid}: invalid between range")
        if row["operator"] == "at_least" and low is None:
            raise ValueError(f"rule {rid}: minimum is required")
        if row["operator"] == "at_most" and high is None:
            raise ValueError(f"rule {rid}: maximum is required")
        row["_minimum"], row["_maximum"] = low, high
        row["_score"], row["_weight"] = score, weight
        result.append(row)
    return result

def load_weights(rows, candidates):
    gates = {r["candidate_id"]: r.get("eligibility_gate", "") for r in candidates}
    result = {}
    for line, row in enumerate(rows, 2):
        cid = row.get("candidate_id", "").strip()
        if not cid:
            raise ValueError(f"weight row {line}: candidate_id is blank")
        if row.get("model_use_status") != "eligible_for_composite_scoring":
            continue
        if gates.get(cid) != "verified_taxon":
            raise ValueError(f"weights {cid}: candidate taxonomy gate is not cleared")
        if row.get("evidence_basis") != "east_taiwan_effort_validated_catch":
            raise ValueError(f"weights {cid}: requires East Taiwan effort-validated catch validation")
        if not all(row.get(k, "").strip() for k in ("source_ids", "reviewed_by", "reviewed_at")):
            raise ValueError(f"weights {cid}: missing validation provenance")
        try:
            weights = {
                "feeding_condition": float(row["feeding_weight"]),
                "environment_suitability": float(row["environment_weight"]),
                "fish_activity": float(row["activity_weight"]),
            }
        except (TypeError, ValueError) as exc:
            raise ValueError(f"weights {cid}: invalid numeric weights") from exc
        if any(v < 0 for v in weights.values()) or abs(sum(weights.values()) - 1.0) > 1e-6:
            raise ValueError(f"weights {cid}: weights must be non-negative and sum to 1")
        if cid in result:
            raise ValueError(f"duplicate approved weight profile for {cid}")
        result[cid] = weights
    return result

def rule_matches(rule, value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if rule["operator"] == "between":
        return rule["_minimum"] <= value <= rule["_maximum"]
    if rule["operator"] == "at_least":
        return value >= rule["_minimum"]
    return value <= rule["_maximum"]

def score_indicator(candidate_id, region_id, features, rules, indicator):
    candidates = [
        r for r in rules
        if r["candidate_id"] == candidate_id
        and r["indicator_code"] == indicator
        and r["region_scope"] in {region_id, "all_east_taiwan"}
    ]
    if not candidates:
        return {"status": "insufficient_evidence", "score": "", "coverage": "0.0000", "trace": []}
    groups = {}
    for rule in candidates:
        groups.setdefault(rule["response_group"], []).append(rule)
    # A region-specific profile overrides its all-East-Taiwan fallback for that group.
    for group_id, bands in list(groups.items()):
        specific = [r for r in bands if r["region_scope"] == region_id]
        if specific:
            groups[group_id] = specific
    evaluated, missing, trace = [], [], []
    for group_id, bands in sorted(groups.items()):
        fields = {r["environment_field"] for r in bands}
        weights = {r["_weight"] for r in bands}
        if len(fields) != 1 or len(weights) != 1:
            raise ValueError(f"response group {group_id} must share one input field and one weight")
        field = next(iter(fields))
        group_weight = next(iter(weights))
        value = features.get(field)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            missing.append(group_id)
            for rule in bands:
                trace.append({
                    "response_group": group_id, "rule_id": rule["rule_id"],
                    "environment_field": field, "observed_value": value,
                    "status": "missing_or_non_numeric", "evidence_id": rule["evidence_id"],
                    "source_url": rule["source_url"],
                })
            continue
        matched = [r for r in bands if rule_matches(r, value)]
        if len(matched) > 1:
            raise ValueError(f"response group {group_id} has overlapping score bands for value {value}")
        chosen = matched[0] if matched else None
        group_score = chosen["_score"] if chosen else 0.0
        evaluated.append((group_score, group_weight))
        for rule in bands:
            trace.append({
                "response_group": group_id, "rule_id": rule["rule_id"],
                "environment_field": field, "observed_value": value,
                "status": "matched_band" if rule is chosen else "non_matching_band",
                "matched": rule is chosen, "score": group_score if rule is chosen else 0.0,
                "weight": group_weight, "evidence_id": rule["evidence_id"],
                "source_url": rule["source_url"],
            })
    total_weight = sum(next(iter({r["_weight"] for r in bands})) for bands in groups.values())
    observed_weight = sum(weight for _, weight in evaluated)
    coverage = observed_weight / total_weight if total_weight else 0.0
    # Require complete coverage; missing input must not silently inflate the score.
    if missing or not evaluated:
        return {"status": "incomplete_input", "score": "", "coverage": f"{coverage:.4f}", "trace": trace}
    score = sum(value * weight for value, weight in evaluated) / observed_weight
    return {"status": "scored", "score": f"{score:.2f}", "coverage": f"{coverage:.4f}", "trace": trace}

def assess_hour(record, candidates, rules, weights):
    region = record.get("region_id", "")
    features = derived_features(record)
    output = []
    for candidate in sorted(candidates, key=lambda x: x["candidate_id"]):
        cid = candidate["candidate_id"]
        if candidate.get("eligibility_gate") != "verified_taxon":
            output.append({
                "candidate_id": cid, "region_id": region, "valid_time": record["valid_time"],
                "data_type": record.get("data_type", ""), "model_status": "taxon_or_distribution_gate",
                "feeding_condition_score": "", "environment_suitability_score": "",
                "fish_activity_score": "", "overall_fish_condition_index": "",
                "best_hour_status": "not_established", "indicator_trace_json": "[]",
                "interpretation": "no_score_taxonomy_gate",
            })
            continue
        indicators = {
            key: score_indicator(cid, region, features, rules, key)
            for key in INDICATORS
        }
        trace = []
        for key in INDICATORS:
            trace.extend([dict(item, indicator_code=key) for item in indicators[key]["trace"]])
        profile = weights.get(cid)
        if any(indicators[k]["status"] != "scored" for k in INDICATORS):
            status = "one_or_more_indicators_unavailable"
            overall = ""
        elif not profile:
            status = "species_weights_not_validated"
            overall = ""
        else:
            overall = sum(float(indicators[k]["score"]) * profile[k] for k in INDICATORS)
            overall = f"{overall:.2f}"
            status = "scored"
        output.append({
            "candidate_id": cid, "region_id": region, "valid_time": record["valid_time"],
            "data_type": record.get("data_type", ""), "model_status": status,
            "feeding_condition_score": indicators["feeding_condition"]["score"],
            "feeding_condition_status": indicators["feeding_condition"]["status"],
            "feeding_condition_coverage": indicators["feeding_condition"]["coverage"],
            "environment_suitability_score": indicators["environment_suitability"]["score"],
            "environment_suitability_status": indicators["environment_suitability"]["status"],
            "environment_suitability_coverage": indicators["environment_suitability"]["coverage"],
            "fish_activity_score": indicators["fish_activity"]["score"],
            "fish_activity_status": indicators["fish_activity"]["status"],
            "fish_activity_coverage": indicators["fish_activity"]["coverage"],
            "overall_fish_condition_index": overall,
            "species_weights_json": json.dumps(profile or {}, ensure_ascii=False, separators=(",", ":")),
            "best_hour_status": "not_rankable" if overall == "" else "rankable",
            "indicator_trace_json": json.dumps(trace, ensure_ascii=False, separators=(",", ":")),
            "interpretation": "0_to_100_species_specific_fish_condition_index_not_catch_probability",
        })
    return output

def rank_best_hours(rows, as_of):
    if as_of.minute or as_of.second or as_of.microsecond:
        raise ValueError("as_of must be aligned to the start of an hour")
    horizons = (6, 12, 24)
    groups = {}
    output = []
    for row in rows:
        if row.get("data_type") != "forecast":
            nonforecast = dict(row, best_hour_status="not_rankable_data_type", best_hour_rank="")
            for horizon in horizons:
                nonforecast[f"best_hour_status_{horizon}h"] = "not_rankable_data_type"
                nonforecast[f"best_hour_rank_{horizon}h"] = ""
            output.append(nonforecast)
            continue
        groups.setdefault((row["candidate_id"], row["region_id"]), []).append(row)
    for key, group in groups.items():
        scored_rows = [r for r in group if r.get("overall_fish_condition_index", "") != ""]
        by_time = {r["valid_time"]: dict(r) for r in group}
        for row in group:
            row["best_hour_status"] = "outside_horizon"
            row["best_hour_rank"] = ""
            for horizon in horizons:
                row[f"best_hour_status_{horizon}h"] = "outside_horizon"
                row[f"best_hour_rank_{horizon}h"] = ""
        for horizon in horizons:
            end = as_of + timedelta(hours=horizon)
            window = [
                r for r in group
                if as_of <= parse_dt(r["valid_time"], "valid_time") < end
            ]
            scored = [r for r in window if r.get("overall_fish_condition_index", "") != ""]
            if not scored:
                for row in window:
                    row[f"best_hour_status_{horizon}h"] = "not_established"
                continue
            scored.sort(key=lambda r: (-float(r["overall_fish_condition_index"]), r["valid_time"]))
            best_time = scored[0]["valid_time"]
            ranks = {r["valid_time"]: i + 1 for i, r in enumerate(scored)}
            for row in window:
                if row.get("overall_fish_condition_index", "") == "":
                    status, rank = "unscored_hour", ""
                else:
                    status = "best_hour" if row["valid_time"] == best_time else "ranked_hour"
                    rank = str(ranks[row["valid_time"]])
                row[f"best_hour_status_{horizon}h"] = status
                row[f"best_hour_rank_{horizon}h"] = rank
        for row in group:
            row["best_hour_status"] = row["best_hour_status_6h"]
            row["best_hour_rank"] = row["best_hour_rank_6h"]
            output.append(row)
    return output

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--environment-jsonl", type=Path, required=True)
    p.add_argument("--candidates-csv", type=Path, required=True)
    p.add_argument("--rules-csv", type=Path, required=True)
    p.add_argument("--weights-csv", type=Path, required=True)
    p.add_argument("--as-of", required=True, help="timezone-aware ISO-8601 timestamp aligned to the hour")
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    records = select_latest_forecast_vintages([json.loads(x) for x in a.environment_jsonl.read_text(encoding="utf-8").splitlines() if x.strip()])
    candidates = unique_candidates(read_csv(a.candidates_csv))
    rules = load_rules(read_csv(a.rules_csv), candidates)
    weights = load_weights(read_csv(a.weights_csv), candidates)
    rows = []
    for record in records:
        rows.extend(assess_hour(record, candidates, rules, weights))
    as_of = parse_dt(a.as_of, "--as-of")
    rows = rank_best_hours(rows, as_of)
    fields = [
        "candidate_id", "region_id", "valid_time", "data_type", "model_status",
        "feeding_condition_score", "feeding_condition_status", "feeding_condition_coverage",
        "environment_suitability_score", "environment_suitability_status", "environment_suitability_coverage",
        "fish_activity_score", "fish_activity_status", "fish_activity_coverage",
        "overall_fish_condition_index", "species_weights_json", "best_hour_status", "best_hour_rank",
        "best_hour_status_6h", "best_hour_rank_6h", "best_hour_status_12h", "best_hour_rank_12h",
        "best_hour_status_24h", "best_hour_rank_24h", "indicator_trace_json", "interpretation",
    ]
    a.out.parent.mkdir(parents=True, exist_ok=True)
    with a.out.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, lineterminator="\n", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    print(f"Assessed {len(rows)} species-hour rows; scores require three validated indicators and species-specific weights.")

if __name__ == "__main__":
    main()
