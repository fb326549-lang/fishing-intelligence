#!/usr/bin/env python3
"""Publish station-level CWA marine observations grouped into the six fishing regions.

This is an observation feed, not a forecast or a fishing/safety score. It only
uses active, explicitly mapped stations and preserves provider values without
guessing wave-field names or units.
"""
from __future__ import annotations
import argparse,csv,json
from datetime import datetime,timezone
from pathlib import Path

REGIONS=("yilan_suao","hualien_north","hualien_south","fengbin_shitiping","chenggong_donghe","taitung_south")
DATASETS=("O-B0075-001","O-B0075-002")

def as_list(value):
    if value is None:return []
    return value if isinstance(value,list) else [value]

def clean(value):
    if value is None:return None
    if isinstance(value,str) and value.strip().lower() in {"","none","null","nan","n/a","-"}:return None
    return value

def parse_time(value):
    if not isinstance(value,str):return None
    try:
        d=datetime.fromisoformat(value.replace("Z","+00:00"))
        return d if d.tzinfo else None
    except ValueError:return None

def flatten(value,prefix=""):
    out={}
    if isinstance(value,dict):
        for key,item in value.items():
            name=f"{prefix}.{key}" if prefix else str(key)
            out.update(flatten(item,name))
    elif isinstance(value,list):
        out[prefix]=value
    else:
        out[prefix]=clean(value)
    return out

def load_station_map(path):
    result={}
    with Path(path).open(encoding="utf-8-sig",newline="") as handle:
        for row in csv.DictReader(handle):
            if row.get("region_id") not in REGIONS or str(row.get("station_status","")).strip()!="1":
                continue
            sid=str(row.get("station_id","")).strip()
            if sid: result[sid]={**row,"station_id":sid}
    return result

def dataset_locations(payload):
    records=payload.get("Records",{})
    obs=records.get("SeaSurfaceObs",{}) if isinstance(records,dict) else {}
    return as_list(obs.get("Location") if isinstance(obs,dict) else None)

def collect_dataset(path,dataset,station_map):
    payload=json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload,dict):raise ValueError(f"{dataset}: JSON root must be object")
    flag=payload.get("Success",payload.get("success"))
    if flag is not None and str(flag).strip().lower() not in {"true","1"}:
        raise ValueError(f"{dataset}: provider success flag is false")
    if not isinstance(payload.get("Records"),dict):
        raise ValueError(f"{dataset}: missing Records")
    found={sid:[] for sid in station_map}
    unknown=[]
    for location in dataset_locations(payload):
        if not isinstance(location,dict):continue
        station=location.get("Station") or {}
        sid=str(station.get("StationID","")).strip()
        if sid not in station_map:
            if sid:unknown.append(sid)
            continue
        times=location.get("StationObsTimes",{}).get("StationObsTime",[])
        for obs in as_list(times):
            if not isinstance(obs,dict):continue
            when=obs.get("DateTime") or obs.get("DataTime")
            dt=parse_time(when)
            if dt is None:continue
            elements=obs.get("WeatherElements") or {}
            found[sid].append({
                "observed_at":dt.isoformat(),
                "observed_at_epoch":dt.timestamp(),
                "weather_elements":elements,
                "flattened":flatten(elements),
            })
    for sid in found:
        found[sid].sort(key=lambda x:x["observed_at_epoch"])
    return found,sorted(set(unknown))

def summarize_region(region,station_map,latest48,history30,as_of_epoch):
    stations=[]
    for sid,meta in station_map.items():
        if meta["region_id"]!=region:continue
        recent=latest48.get(sid,[])
        history=history30.get(sid,[])
        latest=recent[-1] if recent else None
        age_minutes=round((as_of_epoch-latest["observed_at_epoch"])/60,1) if latest else None
        freshness="fresh" if age_minutes is not None and 0 <= age_minutes <= 180 else ("stale" if age_minutes is not None else "no_recent_observation")
        stations.append({
            "station_id":sid,"station_name":meta.get("station_name"),
            "station_type":meta.get("role"),"county":meta.get("county"),
            "latitude":float(meta["latitude"]) if meta.get("latitude") else None,
            "longitude":float(meta["longitude"]) if meta.get("longitude") else None,
            "latest_observation":latest,
            "observations_48h":len(recent),
            "observations_30d":len(history),
            "history_30d_latest_at":history[-1]["observed_at"] if history else None,
            "latest_age_minutes":age_minutes,
            "status":freshness,
        })
    valid=[s for s in stations if s["latest_observation"]]
    fresh=[s for s in stations if s["status"]=="fresh"]
    valid.sort(key=lambda s:s["latest_observation"]["observed_at_epoch"],reverse=True)
    coverage="observed" if fresh else ("stale" if valid else "no_recent_observation")
    return {
        "region_id":region,"station_count":len(stations),
        "stations_with_recent_observation":len(valid),
        "stations_with_fresh_observation":len(fresh),
        "coverage_status":coverage,
        "freshness_threshold_minutes":180,
        "stations":stations,
    }

def build_snapshot(input_dir,station_csv,as_of=None):
    input_dir=Path(input_dir)
    station_map=load_station_map(station_csv)
    data={};unknown={}
    for ds in DATASETS:
        data[ds],unknown[ds]=collect_dataset(input_dir/f"{ds}.json",ds,station_map)
    now=parse_time(as_of) if as_of else datetime.now(timezone.utc)
    if now is None:raise ValueError("--as-of must be timezone-aware ISO-8601")
    regions={r:summarize_region(r,station_map,data[DATASETS[0]],data[DATASETS[1]],now.timestamp()) for r in REGIONS}
    statuses={}
    for ds in DATASETS:
        n=sum(len(v) for v in data[ds].values())
        statuses[ds]={"status":"ok" if n else "empty","station_count":sum(bool(v) for v in data[ds].values()),"observation_count":n,"unmapped_station_ids":unknown[ds]}
    return {
        "schema_version":"1.0.0","source":"CWA_OPENDATA","data_kind":"observations_not_forecast",
        "generated_at":now.isoformat(),"dataset_status":statuses,
        "regions":regions,
        "interpretation_limits":[
            "These are station observations, not a forecast for the whole fishing region.",
            "No station measurement is spatially extrapolated to another coast or subregion.",
            "Provider values and nested field names are preserved; units must follow CWA field metadata.",
            "A latest 48-hour observation older than 180 minutes is marked stale, not current.",
            "Missing or stale station observations are not interpreted as calm sea or safe conditions.",
            "This feed does not calculate fish activity, catch probability, or a safety clearance."
        ]
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input",required=True);p.add_argument("--stations",required=True)
    p.add_argument("--out",required=True);p.add_argument("--as-of")
    a=p.parse_args()
    result=build_snapshot(a.input,a.stations,a.as_of)
    out=Path(a.out);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"regions":len(result["regions"]),"stations_with_observations":sum(r["stations_with_recent_observation"] for r in result["regions"].values()),"datasets":result["dataset_status"]},ensure_ascii=False))
if __name__=="__main__":main()
