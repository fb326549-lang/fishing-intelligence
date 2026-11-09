#!/usr/bin/env python3
"""Derive neutral solar-time context from hourly environment records; never infer fish activity."""
from __future__ import annotations
import argparse, json
from datetime import datetime
from pathlib import Path

def parse_dt(value):
    if not isinstance(value,str) or not value.strip(): return None
    try:
        dt=datetime.fromisoformat(value.replace("Z","+00:00"))
        return dt if dt.tzinfo is not None else None
    except ValueError:
        return None

def build_context(record, twilight_window_minutes=60):
    valid=parse_dt(record.get("valid_time"))
    sunrise=parse_dt((record.get("environment") or {}).get("sunrise"))
    sunset=parse_dt((record.get("environment") or {}).get("sunset"))
    base={
        "schema_version":"1.0.0",
        "region_id":record.get("region_id",""),
        "valid_time":record.get("valid_time",""),
        "data_type":record.get("data_type",""),
        "source_records":record.get("source_records",[]),
        "twilight_window_minutes":twilight_window_minutes,
        "derivation":"solar_phase_from_source_sunrise_sunset",
        "interpretation":"neutral_time_context_not_fish_activity_or_catch_probability",
    }
    if not valid or not sunrise or not sunset:
        return {**base,"solar_phase":"unknown","minutes_from_sunrise":None,"minutes_to_sunset":None,"status":"insufficient_solar_time_data"}
    if valid.tzinfo != sunrise.tzinfo or valid.tzinfo != sunset.tzinfo:
        # Compare instants safely, but preserve the source timezone in original strings.
        pass
    from_sunrise=(valid-sunrise).total_seconds()/60
    to_sunset=(sunset-valid).total_seconds()/60
    if abs(from_sunrise)<=twilight_window_minutes:
        phase="dawn"
    elif abs(to_sunset)<=twilight_window_minutes:
        phase="dusk"
    elif from_sunrise>twilight_window_minutes and to_sunset>twilight_window_minutes:
        phase="daylight"
    else:
        phase="night"
    return {**base,"solar_phase":phase,"minutes_from_sunrise":round(from_sunrise,1),
            "minutes_to_sunset":round(to_sunset,1),"status":"derived"}

def build_file(input_path: Path, output_path: Path, twilight_window_minutes=60):
    if twilight_window_minutes<0 or twilight_window_minutes>180:
        raise ValueError("twilight window must be between 0 and 180 minutes")
    rows=[]
    for line_no,line in enumerate(input_path.read_text(encoding="utf-8").splitlines(),1):
        if not line.strip(): continue
        try: record=json.loads(line)
        except json.JSONDecodeError as exc: raise ValueError(f"line {line_no}: invalid JSON") from exc
        rows.append(build_context(record,twilight_window_minutes))
    output_path.parent.mkdir(parents=True,exist_ok=True)
    output_path.write_text("".join(json.dumps(r,ensure_ascii=False,separators=(",",":"))+"\n" for r in rows),encoding="utf-8")
    return len(rows)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--twilight-window-minutes",type=int,default=60)
    a=p.parse_args()
    print(f"Built {build_file(a.input,a.out,a.twilight_window_minutes)} neutral solar-time context rows.")
if __name__=="__main__": main()
