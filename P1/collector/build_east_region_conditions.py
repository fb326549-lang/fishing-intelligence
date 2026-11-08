#!/usr/bin/env python3
"""Aggregate CWA in-situ marine observations into six East Taiwan planning regions."""
import argparse, csv, json, math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

REGIONS = {
    "yilan_suao": "宜蘭、蘇澳", "hualien_north": "花蓮北段",
    "hualien_south": "花蓮南段", "fengbin_shitiping": "豐濱、石梯坪",
    "chenggong_donghe": "成功、東河", "taitung_south": "台東南段",
}
DIRECTION_VARIABLES = {"wave_direction_deg", "wind_direction_deg", "current_direction_deg"}
VARIABLES = {
    "wave_height_m": ("WaveHeight", "m", "浪高"),
    "wave_period_s": ("WavePeriod", "s", "浪週期"),
    "wave_direction_deg": ("WaveDirection", "degree", "浪向"),
    "sea_temperature_c": ("SeaTemperature", "°C", "海溫"),
    "tide_height_m": ("TideHeight", "m", "潮位"),
    "wind_speed_ms": ("PrimaryAnemometer_WindSpeed", "m/s", "風速"),
    "wind_direction_deg": ("PrimaryAnemometer_WindDirection", "degree", "風向"),
    "current_direction_deg": ("SeaCurrent_CurrentDirection", "degree", "海流方向"),
    "current_speed_ms": ("SeaCurrent_CurrentSpeed", "m/s", "海流速度"),
    "current_speed_knots": ("SeaCurrent_CurrentSpeedInKnots", "kn", "海流速度（節）"),
}

def read_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))

def num(value):
    try:
        if value is None or str(value).strip().lower() in ("", "none", "null", "nan", "n/a"):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None

def mean_value(name, values):
    if not values:
        return None
    if name in DIRECTION_VARIABLES:
        radians = [math.radians(v) for v in values]
        x = sum(math.cos(v) for v in radians) / len(radians)
        y = sum(math.sin(v) for v in radians) / len(radians)
        if abs(x) < 1e-12 and abs(y) < 1e-12:
            return None
        return round((math.degrees(math.atan2(y, x)) + 360) % 360, 1)
    return round(sum(values) / len(values), 3)

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", default="output/normalized/O-B0075-001.csv")
    p.add_argument("--mapping", default="P1/stations/east_region_station_mapping.csv")
    p.add_argument("--stations", default="output/cwa_stations/stations.csv")
    p.add_argument("--out", default="output/east_region")
    a = p.parse_args()
    observations, mapping = read_csv(a.input), read_csv(a.mapping)
    station_region = {r["station_id"]: r["region_id"] for r in mapping
                      if r.get("station_id") and r.get("region_id") in REGIONS}
    inventory = {r["station_id"]: r for r in read_csv(a.stations)} if Path(a.stations).exists() else {}
    buckets = defaultdict(lambda: defaultdict(list))
    region_stations, variable_stations, unmapped = defaultdict(set), defaultdict(lambda: defaultdict(set)), set()
    for row in observations:
        sid, region, timestamp = row.get("station_id", ""), station_region.get(row.get("station_id", "")), row.get("valid_time", "")
        if not region:
            if sid: unmapped.add(sid)
            continue
        if not timestamp: continue
        region_stations[region].add(sid)
        for outname, (source, unit, label) in VARIABLES.items():
            value = num(row.get(source))
            if value is not None:
                buckets[(region, timestamp)][outname].append(value)
                variable_stations[region][outname].add(sid)
    outdir = Path(a.out); outdir.mkdir(parents=True, exist_ok=True)
    series = []
    for (region, timestamp), values in sorted(buckets.items()):
        r = {"region_id": region, "region_name": REGIONS[region], "valid_time": timestamp, "source": "CWA", "data_kind": "observed"}
        for name in VARIABLES:
            vals = values.get(name, [])
            r[name] = mean_value(name, vals)
            r[name+"_sample_count"] = len(vals)
        series.append(r)
    fields = list(dict.fromkeys(k for r in series for k in r))
    with open(outdir/"east_region_conditions.csv", "w", encoding="utf-8-sig", newline="") as f:
        if fields:
            w=csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(series)
    summaries=[]
    for region, name in REGIONS.items():
        ids=region_stations[region]
        region_rows=[r for r in series if r["region_id"]==region]
        latest_time=max((r["valid_time"] for r in region_rows), default=None)
        latest=next((r for r in reversed(region_rows) if r["valid_time"]==latest_time), None)
        coverage={}
        for var, (source, unit, label) in VARIABLES.items():
            count=len(variable_stations[region][var])
            coverage[var]={"label":label,"unit":unit,"stations_with_data":count,
                           "stations_with_any_observation":len(ids),
                           "coverage_ratio":round(count/len(ids),3) if ids else None}
        summaries.append({"region_id":region,"region_name":name,
            "mapped_stations_with_observations":len(ids),"latest_observation_time":latest_time,
            "latest_values":{v:latest.get(v) for v in VARIABLES} if latest else {},
            "variable_coverage":coverage,
            "status":"observed" if ids else "no_mapped_station_observations"})
    report={"generated_at":datetime.now(timezone.utc).isoformat(),
        "source_dataset":"CWA O-B0075-001","data_kind":"observed",
        "region_definition":"P1 planning mapping; not official CWA marine zones",
        "input_observation_rows":len(observations),
        "mapped_station_ids":sorted(set(r.get("station_id") for r in observations)&set(station_region)),
        "unmapped_station_ids":sorted(unmapped),
        "mapped_station_ids_missing_metadata":sorted(s for s in station_region if s not in inventory),
        "regions":summaries,
        "limitations":["Only mapped CWA in-situ observations are included.",
        "Missing values remain null; no zero-fill or interpolation.",
        "Coverage is station-based and variable-specific, not a guarantee of full spatial coverage.",
        "Latest available observation is not a forecast.",
        "Direction values use circular means; direction is undefined when vector components cancel.",
        "No fishing score or species activity is inferred."]}
    (outdir/"east_region_summary.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print("Input rows:",len(observations),"mapped stations:",len(report["mapped_station_ids"]),"unmapped IDs:",len(unmapped))
    for r in summaries: print(r["region_name"],"stations",r["mapped_stations_with_observations"],"latest",r["latest_observation_time"] or "no data")

if __name__=="__main__": main()
