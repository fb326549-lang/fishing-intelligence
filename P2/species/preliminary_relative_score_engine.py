#!/usr/bin/env python3
"""Transparent, low-confidence relative fish outlook from existing P2 inputs.

This is an explicitly exploratory heuristic, not a calibrated biological model.
It converts recorded qualitative diel evidence to coarse index points, ranks the
available wave and wind forecast within each region, and gives equal interim
weight to the three indicators. It never emits a catch probability.
"""
from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timedelta
from pathlib import Path

from indicator_score_engine import parse_dt, read_csv, select_latest_forecast_vintages

TARGETS = {"c036", "c003", "c004", "c001"}
PHASES = ("dawn", "day", "dusk", "night")
WEIGHTS = {"feeding_condition": 1 / 3, "environment_suitability": 1 / 3, "fish_activity": 1 / 3}
MODEL_VERSION = "preliminary-relative-1.2"


def load_profiles(path: Path):
    result = {}
    for row in read_csv(path):
        cid = row["candidate_id"]
        if cid not in TARGETS or cid in result:
            raise ValueError(f"unexpected or duplicate preliminary profile: {cid}")
        for key in ("feeding_phase_points", "activity_phase_points"):
            profile = json.loads(row[key])
            if set(profile) != set(PHASES) or any(v is not None and not 0 <= float(v) <= 100 for v in profile.values()):
                raise ValueError(f"{cid}: {key} must define dawn/day/dusk/night points in 0..100 or null when unsupported")
            row["_" + key] = {k: None if v is None else float(v) for k, v in profile.items()}
        weight = float(row["weight_each"])
        if abs(weight - 1 / 3) > 1e-5:
            raise ValueError(f"{cid}: preliminary weights must document the equal-weight convention")
        row["_weight"] = weight
        row["_urls"] = [u for u in row["source_urls"].split(";") if u.startswith("https://")]
        if not row["_urls"]:
            raise ValueError(f"{cid}: at least one traceable source URL is required")
        result[cid] = row
    if set(result) != TARGETS:
        raise ValueError(f"preliminary profiles must cover exactly {sorted(TARGETS)}")
    return result


def unique_candidates(rows):
    found = {}
    for row in rows:
        cid = row.get("candidate_id", "")
        if cid in TARGETS:
            previous = found.get(cid)
            if previous and previous.get("eligibility_gate", "") != row.get("eligibility_gate", ""):
                raise ValueError(f"conflicting taxonomy gates for {cid}")
            if not previous:
                found[cid] = row
    if set(found) != TARGETS:
        raise ValueError(f"candidate source missing target IDs: {sorted(TARGETS - set(found))}")
    return found


def phase_for(record):
    env = record.get("environment") or {}
    sunrise, sunset = env.get("sunrise"), env.get("sunset")
    if not sunrise or not sunset:
        return "unknown", False
    valid = parse_dt(record["valid_time"], "valid_time")
    rise, setting = parse_dt(sunrise, "sunrise"), parse_dt(sunset, "sunset")
    twilight = timedelta(minutes=90)
    if rise - twilight <= valid < rise + twilight:
        return "dawn", True
    if setting - twilight <= valid < setting + twilight:
        return "dusk", True
    if rise + twilight <= valid < setting - twilight:
        return "day", True
    return "night", True


def percentile_scores(records, field, lower_is_better=True):
    grouped = {}
    for r in records:
        value = (r.get("environment") or {}).get(field)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            grouped.setdefault(r.get("region_id", ""), []).append((r["valid_time"], float(value)))
    scores = {}
    for region, values in grouped.items():
        ordered = sorted(values, key=lambda item: (item[1], item[0]))
        if len(ordered) == 1 or ordered[0][1] == ordered[-1][1]:
            scores.update({(region, time): 50.0 for time, _ in ordered})
            continue
        n = len(ordered)
        for rank, (time, _) in enumerate(ordered):
            percentile = 100.0 * rank / (n - 1)
            scores[(region, time)] = 100.0 - percentile if lower_is_better else percentile
    return scores


def build_rows(records, candidate_rows, profiles, as_of):
    candidates = unique_candidates(candidate_rows)
    forecasts = [r for r in records if r.get("data_type") == "forecast"
                 and as_of <= parse_dt(r.get("valid_time"), "valid_time") < as_of + timedelta(hours=24)]
    wave_scores = percentile_scores(forecasts, "wave_height_m")
    wind_scores = percentile_scores(forecasts, "wind_speed_10m_ms")
    rows = []
    for record in sorted(forecasts, key=lambda r: (r.get("region_id", ""), r.get("valid_time", ""))):
        region, valid_time = record.get("region_id", ""), record["valid_time"]
        env = record.get("environment") or {}
        phase, solar_available = phase_for(record)
        env_parts = [x for x in (wave_scores.get((region, valid_time)), wind_scores.get((region, valid_time))) if x is not None]
        env_score = round(sum(env_parts) / len(env_parts), 2) if env_parts else None
        env_coverage = len(env_parts) / 4  # wave, wind, SST and current are the planned environment inputs.
        for cid in sorted(TARGETS):
            profile, candidate = profiles[cid], candidates[cid]
            feeding_profile = profile["_feeding_phase_points"]
            activity_profile = profile["_activity_phase_points"]
            feeding = feeding_profile.get(phase)
            activity = activity_profile.get(phase)
            coverage_phase = 0.25 if solar_available else 0.0  # time phase is one of four planned feeding/activity inputs.
            indicators = {"feeding_condition": feeding, "environment_suitability": env_score, "fish_activity": activity}
            if any(value is None for value in indicators.values()):
                overall = None
                if not solar_available:
                    status = "preliminary_incomplete_solar_input"
                elif feeding is None or activity is None:
                    status = "insufficient_species_specific_evidence"
                else:
                    status = "preliminary_incomplete_environment_input"
            else:
                overall = round(sum(float(indicators[k]) * WEIGHTS[k] for k in WEIGHTS), 2)
                status = "preliminary_scored"
            trace = [
                {"indicator_code": "feeding_condition", "phase": phase, "score": feeding,
                 "evidence_ids": profile["feeding_source_ids"].split(";"), "source_urls": profile["_urls"],
                 "evidence_class": profile["evidence_class"], "limitation": profile["limitations"]},
                {"indicator_code": "environment_suitability", "score": env_score,
                 "inputs_used": {k: env.get(k) for k in ("wave_height_m", "wind_speed_10m_ms")},
                 "input_ranks": {"wave_height_m": wave_scores.get((region, valid_time)), "wind_speed_10m_ms": wind_scores.get((region, valid_time))},
                 "coverage": env_coverage, "excluded_unvalidated_inputs": ["sea_surface_temperature_c", "ocean_current_velocity_ms", "tide_height_m"]},
                {"indicator_code": "fish_activity", "phase": phase, "score": activity,
                 "evidence_ids": profile["activity_source_ids"].split(";"), "source_urls": profile["_urls"],
                 "evidence_class": profile["evidence_class"], "limitation": profile["limitations"]},
                {"indicator_code": "composite", "weights": WEIGHTS if overall is not None else {},
                 "weight_basis": ("provisional_equal_weight_convention_not_empirically_calibrated" if overall is not None
                                  else "not_applicable_no_composite_score"),
                 "model_version": MODEL_VERSION},
            ]
            row = {
                "candidate_id": cid, "common_name_zh": candidate.get("common_name_zh", ""),
                "scientific_name": candidate.get("scientific_name", profile["scientific_name"]),
                "region_id": region, "valid_time": valid_time, "data_type": "forecast",
                "model_status": status,
                "feeding_condition_score": "" if feeding is None else f"{feeding:.2f}", "feeding_condition_status": "preliminary_proxy_low_confidence" if feeding is not None else ("insufficient_species_specific_evidence" if solar_available else "missing_sunrise_sunset"),
                "feeding_condition_coverage": f"{coverage_phase:.4f}",
                "environment_suitability_score": "" if env_score is None else f"{env_score:.2f}",
                "environment_suitability_status": "preliminary_relative_sea_state_proxy" if env_score is not None else "missing_environment_inputs",
                "environment_suitability_coverage": f"{env_coverage:.4f}",
                "fish_activity_score": "" if activity is None else f"{activity:.2f}", "fish_activity_status": "preliminary_diel_evidence_proxy_low_confidence" if activity is not None else ("insufficient_species_specific_evidence" if solar_available else "missing_sunrise_sunset"),
                "fish_activity_coverage": f"{coverage_phase:.4f}",
                "overall_fish_condition_index": "" if overall is None else f"{overall:.2f}",
                "species_weights_json": json.dumps(WEIGHTS if overall is not None else {}, separators=(",", ":")),
                "model_confidence": "low", "model_version": MODEL_VERSION,
                "best_hour_status": "not_rankable", "best_hour_rank": "",
                "indicator_trace_json": json.dumps(trace, ensure_ascii=False, separators=(",", ":")),
                "interpretation": "preliminary_species_relative_fish_condition_index_not_catch_probability",
            }
            rows.append(row)
    rank_best_hours(rows, as_of)
    return rows


def rank_best_hours(rows, as_of):
    for row in rows:
        for horizon in (6, 12, 24):
            row[f"best_hour_status_{horizon}h"] = "outside_horizon"
            row[f"best_hour_rank_{horizon}h"] = ""
    for horizon in (6, 12, 24):
        groups = {}
        for row in rows:
            valid = parse_dt(row["valid_time"], "valid_time")
            if as_of <= valid < as_of + timedelta(hours=horizon):
                groups.setdefault((row["candidate_id"], row["region_id"]), []).append(row)
        for group in groups.values():
            ranked = sorted((r for r in group if r["overall_fish_condition_index"]),
                            key=lambda r: (-float(r["overall_fish_condition_index"]), r["valid_time"]))
            ranks = {r["valid_time"]: i + 1 for i, r in enumerate(ranked)}
            best_time = ranked[0]["valid_time"] if ranked else None
            for row in group:
                row[f"best_hour_status_{horizon}h"] = ("best_hour" if row["valid_time"] == best_time else "ranked_hour") if row["overall_fish_condition_index"] else "unscored_hour"
                row[f"best_hour_rank_{horizon}h"] = str(ranks.get(row["valid_time"], ""))
    for row in rows:
        row["best_hour_status"] = row.get("best_hour_status_6h", "outside_horizon")
        row["best_hour_rank"] = row.get("best_hour_rank_6h", "")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--environment-jsonl", type=Path, required=True)
    parser.add_argument("--candidates-csv", type=Path, required=True)
    parser.add_argument("--profiles-csv", type=Path, default=Path(__file__).with_name("preliminary_relative_score_profiles.csv"))
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    records = select_latest_forecast_vintages([json.loads(line) for line in args.environment_jsonl.read_text(encoding="utf-8").splitlines() if line.strip()])
    rows = build_rows(records, read_csv(args.candidates_csv), load_profiles(args.profiles_csv), parse_dt(args.as_of, "--as-of"))
    fields = ["candidate_id", "common_name_zh", "scientific_name", "region_id", "valid_time", "data_type", "model_status",
              "feeding_condition_score", "feeding_condition_status", "feeding_condition_coverage", "environment_suitability_score",
              "environment_suitability_status", "environment_suitability_coverage", "fish_activity_score", "fish_activity_status",
              "fish_activity_coverage", "overall_fish_condition_index", "species_weights_json", "model_confidence", "model_version",
              "best_hour_status", "best_hour_rank", "best_hour_status_6h", "best_hour_rank_6h", "best_hour_status_12h", "best_hour_rank_12h",
              "best_hour_status_24h", "best_hour_rank_24h", "indicator_trace_json", "interpretation"]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print({"rows": len(rows), "scored_rows": sum(bool(r["overall_fish_condition_index"]) for r in rows), "model_version": MODEL_VERSION, "confidence": "low"})


if __name__ == "__main__":
    main()
