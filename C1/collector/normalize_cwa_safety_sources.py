#!/usr/bin/env python3
"""Normalize official CWA warnings and marine hazard monitors to six regions.

County-wide warnings are expanded conservatively to all planning subregions
inside that county. Point marine monitors are mapped only to their documented
station region; no spatial extrapolation is performed.
"""
from __future__ import annotations
import argparse,csv,json
from datetime import datetime,timedelta,timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import sys
import xml.etree.ElementTree as ET
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from safety_decision import REGIONS,decide_region

TZ=ZoneInfo("Asia/Taipei")
COUNTY_REGIONS={
 "宜蘭縣":["yilan_suao"],
 "花蓮縣":["hualien_north","hualien_south","fengbin_shitiping"],
 "臺東縣":["chenggong_donghe","taitung_south"],
}
TOWN_REGIONS={
 "宜蘭縣頭城鎮":"yilan_suao","宜蘭縣蘇澳鎮":"yilan_suao",
 "花蓮縣新城鄉":"hualien_north","花蓮縣秀林鄉":"hualien_north",
 "花蓮縣花蓮市":"hualien_north","花蓮縣吉安鄉":"hualien_south",
 "花蓮縣壽豐鄉":"hualien_south","花蓮縣豐濱鄉":"fengbin_shitiping",
 "臺東縣長濱鄉":"chenggong_donghe","臺東縣成功鎮":"chenggong_donghe",
 "臺東縣東河鄉":"chenggong_donghe","臺東縣臺東市":"taitung_south",
 "臺東縣卑南鄉":"taitung_south","臺東縣太麻里鄉":"taitung_south",
 "臺東縣大武鄉":"taitung_south","臺東縣達仁鄉":"taitung_south",
}
MARINE_STATIONS={
 "宜蘭":"yilan_suao","蘇澳":"yilan_suao","蘇澳浮標":"yilan_suao",
 "花蓮":"hualien_north","花蓮浮標":"hualien_north",
 "成功":"chenggong_donghe","成功浮球":"chenggong_donghe",
 "臺東":"taitung_south","台東":"taitung_south","臺東浮標":"taitung_south",
}
COVERAGE={
 "O-B0069-001":["yilan_suao","hualien_north","chenggong_donghe","taitung_south"],
 "O-B0070-001":["yilan_suao","hualien_north","chenggong_donghe","taitung_south"],
}
def one(value):
 return value if isinstance(value,list) else ([] if value is None else [value])
def local(tag):
 return tag.rsplit("}",1)[-1]
def child(node,name):
 if node is None:return None
 for x in list(node):
  if local(x.tag)==name:return x
 return None
def text_child(node,name,default=""):
 x=child(node,name)
 return (x.text or "").strip() if x is not None else default
def parse_time(value):
 if not value:return None
 d=datetime.fromisoformat(str(value).replace("Z","+00:00"))
 return d.replace(tzinfo=TZ) if d.tzinfo is None else d
def iso(value):
 d=parse_time(value)
 return d.isoformat() if d else None
def regions_for_area(name):
 name=(name or "").strip().replace("臺","台")
 # Restore canonical prefixes for exact matching; tolerate CWA traditional variants.
 normalized=name.replace("台東","臺東")
 for town,region in TOWN_REGIONS.items():
  if normalized==town:return [region]
 for county,regions in COUNTY_REGIONS.items():
  if normalized==county or normalized.startswith(county+"(") or normalized.startswith(county+"（"):
   return list(regions)
 for town,region in TOWN_REGIONS.items():
  if normalized.startswith(town):return [region]
 return []
def alert_type(phenomena,headline=""):
 s=(phenomena+" "+headline)
 if "颱風" in s:return "typhoon"
 if "巨浪" in s:return "high_wave"
 if "長浪" in s:return "long_wave"
 if "暴潮" in s:return "storm_surge"
 if "大潮" in s:return "large_tide"
 if "強風" in s or "強風" in headline:return "strong_wind_land"
 if "雷" in s:return "thunderstorm"
 if any(x in s for x in ("豪雨","大雨","降雨")):return "heavy_rain"
 return "other"
def severity_from_text(value,kind):
 s=str(value or "")
 if kind in {"typhoon","high_wave","storm_surge"}:return "extreme"
 if "巨浪" in s or "暴潮警戒" in s:return "severe"
 if "注意" in s or "長浪" in s or "強風" in s:return "moderate"
 return "unknown"
def make_alert(dataset,alert_id,kind,regions,start,end,collected,message,source_url,severity="moderate",status="active",area=None):
 return {"schema_version":"1.0.0","alert_id":alert_id,"source_id":"CWA_OPENDATA","dataset_id":dataset,"source_url":source_url,"region_ids":sorted(set(regions)),"alert_type":kind,"severity":severity,"status":status,"issued_at":collected,"effective_start":start,"effective_end":end,"collected_at":collected,"message":message,"affected_area":area}
def warning_records(dataset,payload,collected):
 out=[]; records=payload.get("records",payload.get("Records",{}))
 if dataset=="W-C0033-001":
  for loc in one(records.get("location",records.get("Location"))):
   county=loc.get("locationName","")
   regions=regions_for_area(county)
   hazards=loc.get("hazardConditions",{}).get("hazards",[])
   for h in one(hazards):
    info=h.get("info",{}) if isinstance(h,dict) else {}
    vt=h.get("validTime",{}) if isinstance(h,dict) else {}
    kind=alert_type(str(info.get("phenomena","")))
    if kind=="other":continue
    start=iso(vt.get("startTime")) or collected
    end=iso(vt.get("endTime")) or collected
    if regions:
     out.append(make_alert(dataset,f"{dataset}:{county}:{kind}",kind,regions,start,end,collected,str(info.get("phenomena","官方警報")), "https://opendata.cwa.gov.tw/dataset/all/"+dataset, "moderate","active",county))
 elif dataset=="W-C0033-002":
  for rec in one(records.get("record",records.get("Record"))):
   info=rec.get("datasetInfo",{})
   vt=info.get("validTime",{})
   hazards=rec.get("hazardConditions",{}).get("hazards",{}).get("hazard",[])
   for h in one(hazards):
    hi=h.get("info",{})
    names=one(hi.get("affectedAreas",{}).get("location"))
    areas=[x.get("locationName","") for x in names if isinstance(x,dict)]
    regions=sorted({r for a in areas for r in regions_for_area(a)})
    kind=alert_type(str(hi.get("phenomena","")),str(info.get("datasetDescription","")))
    if kind=="other":continue
    start=iso(vt.get("startTime")) or collected;end=iso(vt.get("endTime")) or collected
    if regions:
     msg=rec.get("contents",{}).get("content",{}).get("contentText","").strip() or str(hi.get("phenomena",""))
     out.append(make_alert(dataset,f"{dataset}:{info.get('datasetDescription','')}:{kind}",kind,regions,start,end,collected,msg,"https://opendata.cwa.gov.tw/dataset/all/"+dataset,"moderate","active","、".join(areas)))
 else:
  for info in one(records.get("info",records.get("Info"))):
   areas=one(info.get("area"))
   regions=sorted({r for a in areas if isinstance(a,dict) for r in regions_for_area(a.get("areaDesc",""))})
   kind=alert_type(str(info.get("event","")),str(info.get("headline","")))
   if kind=="other":continue
   start=iso(info.get("onset") or info.get("effective")) or collected
   end=iso(info.get("expires")) or collected
   sev=severity_from_text(str(info.get("severity",""))+" "+str(info.get("headline","")),kind)
   if regions:
    out.append(make_alert(dataset,f"{dataset}:{info.get('event','')}:{info.get('headline','')}",kind,regions,start,end,collected,str(info.get("description") or info.get("headline") or info.get("event")),str(info.get("web") or "https://opendata.cwa.gov.tw/dataset/all/"+dataset),sev,"active","、".join(a.get("areaDesc","") for a in areas if isinstance(a,dict))))
 return out
def cap_alerts(path,collected):
 out=[];root=ET.parse(path).getroot()
 status=text_child(root,"status","Actual");msg_type=text_child(root,"msgType","Alert")
 for info in [x for x in list(root) if local(x.tag)=="info"]:
  event=text_child(info,"event","颱風")
  kind=alert_type(event)
  start=text_child(info,"onset") or text_child(info,"effective") or collected
  end=text_child(info,"expires") or collected
  regions=[]
  area_names=[]
  for area in [x for x in list(info) if local(x.tag)=="area"]:
   name=text_child(area,"areaDesc")
   area_names.append(name);regions.extend(regions_for_area(name))
  if not regions:continue
  active_status="cancelled" if msg_type.lower()=="cancel" or status.lower()=="cancelled" else "active"
  out.append(make_alert("W-C0034-001",text_child(root,"identifier","CWA-TYPHOON"),"typhoon",regions,iso(start),iso(end),collected,text_child(info,"headline",event),"https://opendata.cwa.gov.tw/dataset/all/W-C0034-001","extreme",active_status,"、".join(area_names)))
 return out
def marine_alerts(dataset,payload,collected):
 root=payload.get("cwaopendata",{})
 resources=root.get("Resources",{}).get("Resource",{})
 data=resources.get("Data",{})
 obs=one(data.get("SeaSurfaceObs"))
 out=[];covered=set(COVERAGE[dataset])
 for entry in obs:
  loc=entry.get("Location",{}) if isinstance(entry,dict) else {}
  name=loc.get("StationName","")
  region=MARINE_STATIONS.get(name)
  if not region:continue
  times=loc.get("StationObsTimes",{}).get("StationObsTime",{})
  if isinstance(times,list):times=times[-1] if times else {}
  start=iso(times.get("StartTime")) or collected
  end_time=parse_time(times.get("EndTime")) or parse_time(collected)
  # These products summarize the previous 8 hours and update hourly. Keep
  # the observation current only until the next expected hourly refresh.
  end=(end_time+timedelta(hours=1)).isoformat()
  el=times.get("WeatherElements",{})
  warning=str(el.get("WarningStatus",""))
  if dataset=="O-B0070-001":
   if "巨浪" in warning:
    kind,sev="high_wave","extreme"
   elif "長浪" in warning:
    kind,sev="long_wave","moderate"
   else:continue
  else:
   if "暴潮警戒" in warning:
    kind,sev="storm_surge","extreme"
   elif "大潮注意" in warning:
    kind,sev="large_tide","moderate"
   else:continue
  value=el.get("MaximumWaveHeight") if dataset=="O-B0070-001" else el.get("MaximumTideHeight")
  msg=f"{name}測站過去8小時監測：{warning}；最大值 {value if value is not None else '無資料'}"
  out.append(make_alert(dataset,f"{dataset}:{name}:{warning}",kind,[region],start,end,collected,msg,"https://opendata.cwa.gov.tw/dataset/observation/"+dataset,sev,"active",name))
 return out,sorted(covered)
def main():
 p=argparse.ArgumentParser();p.add_argument("--input",type=Path,required=True);p.add_argument("--out",type=Path,required=True);p.add_argument("--as-of");a=p.parse_args()
 manifest=json.loads((a.input/"manifest.json").read_text(encoding="utf-8"))
 collected=iso(a.as_of) if a.as_of else datetime.now(timezone.utc).isoformat()
 status={}
 for item in manifest["datasets"]:
  status[item["dataset_id"]]={"status":"ok" if item["status"]=="ok" else "error","collected_at":item.get("collected_at"),"region_coverage":{r:True for r in REGIONS}}
 alerts=[]
 for ds in ("W-C0033-001","W-C0033-002","W-C0033-003","W-C0033-006"):
  item=next(x for x in manifest["datasets"] if x["dataset_id"]==ds)
  if item["status"]=="ok":
   alerts.extend(warning_records(ds,json.loads((a.input/item["file"]).read_text(encoding="utf-8")),item["collected_at"]))
 item=next(x for x in manifest["datasets"] if x["dataset_id"]=="W-C0034-001")
 if item["status"]=="ok":alerts.extend(cap_alerts(a.input/item["file"],item["collected_at"]))
 for ds in ("O-B0069-001","O-B0070-001"):
  item=next(x for x in manifest["datasets"] if x["dataset_id"]==ds)
  for r in COVERAGE[ds]:status[ds]["region_coverage"][r]=False
  if item["status"]=="ok":
   marine,covered=marine_alerts(ds,json.loads((a.input/item["file"]).read_text(encoding="utf-8")),item["collected_at"])
   alerts.extend(marine)
   for r in covered:status[ds]["region_coverage"][r]=True
 # Deduplicate repeated hazard representations while retaining source provenance.
 unique={}
 for x in alerts:
  key=(x["dataset_id"],x["alert_id"],tuple(x["region_ids"]))
  unique[key]=x
 alerts=list(unique.values())
 decisions={"schema_version":"1.0.0","as_of":collected,"regions":{r:decide_region(r,alerts,status,parse_time(collected)) for r in REGIONS}}
 a.out.mkdir(parents=True,exist_ok=True)
 for name,obj in (("alerts.json",alerts),("source_status.json",status),("safety_decisions.json",decisions)):
  (a.out/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
 print(json.dumps({"alert_count":len(alerts),"region_states":{r:v["state"] for r,v in decisions["regions"].items()}},ensure_ascii=False))
if __name__=="__main__":main()
