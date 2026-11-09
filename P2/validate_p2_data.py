#!/usr/bin/env python3
"""Dependency-free structural validation for P2 hourly records and species parameters."""
from __future__ import annotations
import argparse, csv, json, math
from datetime import datetime
from pathlib import Path

REGIONS = {"yilan_suao","hualien_north","hualien_south","fengbin_shitiping","chenggong_donghe","taitung_south"}
DATA_TYPES = {"forecast","observation","hindcast","derived"}
CONFIDENCE = {"high","medium","low","unknown"}
PARAMETER_CODES = {"temperature_range","depth_range","habitat","wave_preference","current_preference","tide_response","wind_sensitivity","activity_period","salinity_preference"}

def iso(value):
    if not isinstance(value,str): return False
    try: datetime.fromisoformat(value.replace("Z","+00:00")); return True
    except ValueError: return False

def validate_environment(record):
    errors=[]
    required={"schema_version","region_id","valid_time","collected_at","data_type","source_records","completeness","quality"}
    missing=required-record.keys()
    if missing: errors.append("missing required fields: "+", ".join(sorted(missing)))
    if record.get("schema_version")!="1.0.0": errors.append("unsupported schema_version")
    if record.get("region_id") not in REGIONS: errors.append("invalid region_id")
    for key in ("valid_time","collected_at"):
        if not iso(record.get(key)): errors.append(key+" must be ISO-8601 datetime")
    if record.get("data_type") not in DATA_TYPES: errors.append("invalid data_type")
    sources=record.get("source_records")
    if not isinstance(sources,list) or not sources: errors.append("source_records must be a non-empty list")
    else:
        for i,s in enumerate(sources):
            if not all(isinstance(s.get(k),str) and s[k].strip() for k in ("source_id","dataset","url")): errors.append(f"source_records[{i}] requires source_id, dataset, url")
    env=record.get("environment",{})
    if not isinstance(env,dict): errors.append("environment must be an object"); env={}
    numeric={"wave_height_m":(0,None),"wave_period_s":(0,None),"wave_direction_deg":(0,360),"sea_surface_temperature_c":(-2,40),"ocean_current_velocity_ms":(0,None),"ocean_current_direction_deg":(0,360),"wind_speed_10m_ms":(0,None),"wind_direction_10m_deg":(0,360),"tidal_current_velocity_ms":(0,None),"tidal_current_direction_deg":(0,360),"precipitation_mm_h":(0,None),"showers_mm_h":(0,None),"precipitation_probability_pct":(0,100)}
    for key,(lo,hi) in numeric.items():
        v=env.get(key)
        if v is not None and (isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or (lo is not None and (v<lo if key not in ("wave_period_s",) else v<=lo)) or (hi is not None and v>=hi)):
            errors.append(f"environment.{key} has invalid value")
    weather_code=env.get("weather_code")
    if weather_code is not None and (isinstance(weather_code,bool) or not isinstance(weather_code,int) or weather_code<0): errors.append("environment.weather_code must be a non-negative integer or null")
    if env.get("tide_phase") not in (None,"rising","falling","high_slack","low_slack","unknown"): errors.append("invalid tide_phase")
    if env.get("thunderstorm_risk") not in (None,"none","low","moderate","high","unknown"): errors.append("invalid thunderstorm_risk")
    for key in ("tide_turning",):
        if env.get(key) is not None and not isinstance(env[key],bool): errors.append(f"environment.{key} must be boolean or null")
    for key in ("sunrise","sunset"):
        if env.get(key) is not None and not iso(env[key]): errors.append(f"environment.{key} must be ISO-8601 datetime or null")
    # Tide height is a water-level observation; it is never treated as current speed.
    comp=record.get("completeness",{})
    if not isinstance(comp,dict) or not all(k in comp for k in ("available_fields","expected_fields","ratio")): errors.append("completeness requires available_fields, expected_fields, ratio")
    else:
        a,e,r=comp["available_fields"],comp["expected_fields"],comp["ratio"]
        if not isinstance(a,int) or not isinstance(e,int) or e<1 or a<0 or a>e or not isinstance(r,(int,float)) or abs(r-a/e)>0.001: errors.append("completeness counts and ratio inconsistent")
    q=record.get("quality",{})
    if not isinstance(q,dict) or q.get("status") not in {"good","degraded","partial","invalid"} or q.get("confidence") not in CONFIDENCE: errors.append("quality status/confidence invalid")
    return errors

def validate_species_csv(path):
    errors=[]
    required={"response_record_id","candidate_id","parameter_code","parameter_value","unit","life_stage","geographic_scope","habitat_scope","evidence_id","source_url","confidence","model_use_status","notes"}
    with path.open(encoding="utf-8-sig",newline="") as f:
        reader=csv.DictReader(f)
        if not reader.fieldnames or not required.issubset(reader.fieldnames): return ["species parameter CSV missing required columns"]
        for n,row in enumerate(reader,2):
            for key in ("response_record_id","candidate_id","parameter_code","parameter_value","evidence_id","source_url","confidence","model_use_status"):
                if not row.get(key,"").strip(): errors.append(f"row {n}: {key} is required; use blank only for unpopulated template, not submitted records")
            if row.get("parameter_code") and row["parameter_code"] not in PARAMETER_CODES: errors.append(f"row {n}: unknown parameter_code")
            if row.get("confidence") and row["confidence"] not in CONFIDENCE-{"unknown"}: errors.append(f"row {n}: invalid confidence")
            if row.get("source_url") and not row["source_url"].startswith(("https://","http://")): errors.append(f"row {n}: source_url must be HTTP(S)")
    return errors

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--environment-jsonl",type=Path)
    p.add_argument("--species-csv",type=Path)
    a=p.parse_args(); errors=[]
    if not a.environment_jsonl and not a.species_csv: p.error("provide at least one input")
    if a.environment_jsonl:
        for n,line in enumerate(a.environment_jsonl.read_text(encoding="utf-8").splitlines(),1):
            if not line.strip(): continue
            try: errors += [f"{a.environment_jsonl}:{n}: {e}" for e in validate_environment(json.loads(line))]
            except json.JSONDecodeError as e: errors.append(f"{a.environment_jsonl}:{n}: invalid JSON: {e}")
    if a.species_csv: errors += [f"{a.species_csv}: {e}" for e in validate_species_csv(a.species_csv)]
    if errors:
        print("\n".join(errors)); return 1
    print("P2 data validation passed"); return 0
if __name__=="__main__": raise SystemExit(main())
