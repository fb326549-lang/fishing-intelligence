#!/usr/bin/env python3
"""Normalize CWA O-B0075 marine observations into CSV without inventing units."""
from __future__ import annotations
import argparse,csv,json
from pathlib import Path

def clean(v):
    if v in (None,"None",""): return None
    return v

def flatten(prefix,obj,out):
    if isinstance(obj,dict):
        for k,v in obj.items(): flatten(f"{prefix}_{k}" if prefix else k,v,out)
    elif isinstance(obj,list):
        out[prefix]=json.dumps(obj,ensure_ascii=False)
    else:
        out[prefix]=clean(obj)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input",default="output/cwa_marine")
    p.add_argument("--stations",default="output/cwa_stations/stations.csv")
    p.add_argument("--out",default="output/normalized")
    a=p.parse_args()
    inp,out=Path(a.input),Path(a.out); out.mkdir(parents=True,exist_ok=True)
    station_map={}
    sp=Path(a.stations)
    if sp.exists():
        with sp.open(encoding="utf-8-sig",newline="") as f:
            for r in csv.DictReader(f): station_map[r.get("station_id")]=r
    summary=[]
    for dataset in ("O-B0075-001","O-B0075-002"):
        data=json.loads((inp/f"{dataset}.json").read_text(encoding="utf-8"))
        if str(data.get("Success")).lower()!="true":
            raise SystemExit(f"{dataset}: provider response is not Success=true")
        rows=[]
        locations=data.get("Records",{}).get("SeaSurfaceObs",{}).get("Location",[])
        for loc in locations:
            sid=str((loc.get("Station") or {}).get("StationID",""))
            meta=station_map.get(sid,{})
            for obs in (loc.get("StationObsTimes") or {}).get("StationObsTime",[]):
                row={"dataset_id":dataset,"station_id":sid,
                     "station_name":meta.get("station_name"),
                     "latitude":meta.get("latitude"),"longitude":meta.get("longitude"),
                     "county":meta.get("county"),"valid_time":obs.get("DateTime"),
                     "data_kind":"observed","source":"CWA"}
                elements = obs.get("WeatherElements",{})
                flatten("",elements,row)
                # Sea currents are nested by measurement layer; expose layer-1
                # fields as separate columns while preserving the original JSON.
                current_layers = elements.get("SeaCurrents",{}).get("Layer",[])
                if isinstance(current_layers,dict): current_layers=[current_layers]
                if isinstance(current_layers,list) and current_layers:
                    layer = current_layers[0]
                    for key in ("LayerNumber","CurrentDirection","CurrentDirectionDescription","CurrentSpeed","CurrentSpeedInKnots"):
                        if key in layer: row[f"SeaCurrent_{key}"]=layer[key]
                rows.append(row)
        if rows:
            fields=list(dict.fromkeys(k for r in rows for k in r))
            with (out/f"{dataset}.csv").open("w",encoding="utf-8-sig",newline="") as f:
                w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)
        summary.append({"dataset_id":dataset,"stations":len(locations),
                        "observation_rows":len(rows),"csv":f"{dataset}.csv"})
    (out/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    for x in summary: print(f'{x["dataset_id"]}: {x["stations"]} stations, {x["observation_rows"]} observation rows')
    print("Units are intentionally left as supplied/unspecified; inspect CWA field definitions before conversion.")

if __name__=="__main__": main()
