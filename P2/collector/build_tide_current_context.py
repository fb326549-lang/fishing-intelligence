#!/usr/bin/env python3
"""Build neutral tide/current context without inferring fish response or current from tide height."""
from __future__ import annotations
import argparse, json
from pathlib import Path

ENV_FIELDS = (
    "tide_height_m", "tide_phase", "tide_turning",
    "tidal_current_velocity_ms", "tidal_current_direction_deg",
    "ocean_current_velocity_ms", "ocean_current_direction_deg",
)

def build_context(record):
    env=record.get("environment") or {}
    present={k:env.get(k) for k in ENV_FIELDS}
    tide_phase=present["tide_phase"]
    if tide_phase not in {"rising","falling","high_slack","low_slack","unknown"}:
        tide_phase="unknown"
    # Upstream may pass through a phase derived from bracketing CWA high/low
    # forecast events. Never infer it from tide height or sparse regional samples.
    # Do not infer tidal current from ocean current, or vice versa.
    tide_height=present["tide_height_m"]
    tidal_speed=present["tidal_current_velocity_ms"]
    ocean_speed=present["ocean_current_velocity_ms"]
    return {
        "schema_version":"1.0.0",
        "region_id":record.get("region_id"),
        "valid_time":record.get("valid_time"),
        "collected_at":record.get("collected_at"),
        "data_type":record.get("data_type"),
        "source_records":record.get("source_records",[]),
        "tide_height_m":tide_height,
        "tide_phase":tide_phase,
        "tide_turning":present["tide_turning"],
        "tidal_current_velocity_ms":tidal_speed,
        "tidal_current_direction_deg":present["tidal_current_direction_deg"],
        "ocean_current_velocity_ms":ocean_speed,
        "ocean_current_direction_deg":present["ocean_current_direction_deg"],
        "availability":{
            "tide_height":"available" if tide_height is not None else "missing",
            "tide_phase":"available" if tide_phase!="unknown" else "unknown",
            "tidal_current":"available" if tidal_speed is not None else "missing",
            "ocean_current":"available" if ocean_speed is not None else "missing",
        },
        "derivation":"direct_fields_with_upstream_cwa_event_derived_phase_no_height_interpolation",
        "interpretation":"neutral_hydrodynamic_context_not_fish_activity_or_catch_probability",
        "limitations":[
            "tide_height_is_not_tidal_current_velocity",
            "ocean_current_is_not_tidal_current",
            "missing_tide_phase_is_not_inferred_from_tide_height",
            "forecast_tide_phase_from_high_low_events_is_not_measured_tidal_current_or_current_slack",
            "no_species_response_or_best_fishing_time_is_inferred",
        ],
    }

def build_file(input_path:Path, output_path:Path):
    rows=[]
    with input_path.open(encoding="utf-8") as f:
        for line_no,line in enumerate(f,1):
            if not line.strip(): continue
            try: record=json.loads(line)
            except json.JSONDecodeError as exc: raise ValueError(f"line {line_no}: invalid JSON") from exc
            if not isinstance(record,dict) or not isinstance(record.get("environment"),dict):
                raise ValueError(f"line {line_no}: record/environment must be objects")
            rows.append(build_context(record))
    output_path.parent.mkdir(parents=True,exist_ok=True)
    output_path.write_text("".join(json.dumps(x,ensure_ascii=False,separators=(",",":"))+"\n" for x in rows),encoding="utf-8")
    return len(rows)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    print(f"Built {build_file(a.input,a.out)} neutral tide/current context rows.")
if __name__=="__main__": main()
