#!/usr/bin/env python3
"""Create a source-separated six-region environmental comparison.

CWA observations and Open-Meteo model forecasts are never averaged together.
This report checks spatial/temporal availability and writes paired values
where both sources exist, preserving each source's own timestamp and type.
"""
from __future__ import annotations
import argparse, csv, json
from pathlib import Path

COMPARE = {
    "wave_height_m": ("wave_height_m", "wave_height"),
    "wave_period_s": ("wave_period_s", "wave_period"),
    "wave_direction_deg": ("wave_direction_deg", "wave_direction"),
    "sea_temperature_c": ("sea_temperature_c", "sea_surface_temperature"),
    "wind_speed_ms": ("wind_speed_ms", "wind_speed_10m"),
    "wind_direction_deg": ("wind_direction_deg", "wind_direction_10m"),
    "current_speed_ms": ("current_speed_ms", "ocean_current_velocity"),
    "current_direction_deg": ("current_direction_deg", "ocean_current_direction"),
}
def load(path):
    with open(path,encoding="utf-8-sig",newline="") as f: return list(csv.DictReader(f))
def num(x):
    try: return float(x) if x not in (None,"","None","null") else None
    except (TypeError,ValueError): return None
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--observed",required=True)
    p.add_argument("--forecast",required=True)
    p.add_argument("--out",required=True)
    a=p.parse_args()
    obs=load(a.observed); fc=load(a.forecast)
    # Latest CWA observation per region/variable; forecast rows remain horizon-specific.
    latest={}
    for r in obs:
        key=(r["region_id"],r["valid_time"])
        if key not in latest or r["valid_time"]>latest[key]["valid_time"]: latest[key]=r
    latest_by_region={}
    for r in latest.values():
        rid=r["region_id"]
        if rid not in latest_by_region or r["valid_time"]>latest_by_region[rid]["valid_time"]:
            latest_by_region[rid]=r
    output=[]
    for f in fc:
        rid=f["region_id"]
        o=latest_by_region.get(rid,{})
        row={"region_id":rid,"region_name":f["region_name"],
             "horizon_hours":f["horizon_hours"],"forecast_target_time":f["target_time"],
             "cwa_observation_time":o.get("valid_time"),"cwa_data_kind":"observed" if o else "no_observation",
             "forecast_data_kind":"forecast/modelled"}
        comparable=0; matched=0
        for label,(okey,fkey) in COMPARE.items():
            ov=num(o.get(okey)); fv=num(f.get(fkey))
            row["cwa_"+label]=ov
            row["forecast_"+label]=fv
            row[label+"_both_available"]=bool(ov is not None and fv is not None)
            comparable+=1
            matched+=int(ov is not None and fv is not None)
        row["paired_variable_count"]=matched
        row["comparison_variable_count"]=comparable
        row["paired_completeness_pct"]=round(matched/comparable*100,1)
        output.append(row)
    out=Path(a.out);out.parent.mkdir(parents=True,exist_ok=True)
    if output:
        with out.open("w",encoding="utf-8-sig",newline="") as f:
            w=csv.DictWriter(f,fieldnames=list(output[0]));w.writeheader();w.writerows(output)
    summary={"forecast_records":len(fc),"comparison_records":len(output),
        "regions":len({r["region_id"] for r in output}),
        "records_with_any_paired_values":sum(r["paired_variable_count"]>0 for r in output),
        "records_without_cwa_observation":sum(r["cwa_data_kind"]=="no_observation" for r in output),
        "policy":"CWA observations and Open-Meteo forecasts remain separate; no blending or substitution.",
        "limitations":["Latest CWA observation may not be time-aligned to forecast target.",
        "Paired completeness measures fields present, not forecast accuracy.",
        "Only identical/compatible units should be compared; provider units are retained in source outputs."]}
    out.with_name("source_comparison_summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(summary,ensure_ascii=False))
if __name__=="__main__":main()
