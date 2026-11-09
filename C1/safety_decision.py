#!/usr/bin/env python3
"""Evidence-gated regional safety decision. No alert is never a safety clearance."""
import argparse,json
from datetime import datetime
from pathlib import Path
REGIONS=("yilan_suao","hualien_north","hualien_south","fengbin_shitiping","chenggong_donghe","taitung_south")
REQUIRED_SOURCES=("W-C0033-001","W-C0033-002","W-C0033-003","W-C0033-006","W-C0034-001","O-B0069-001","O-B0070-001")
HIGH_RISK_TYPES={"typhoon","high_wave","storm_surge"}
def parse_time(value):
    if not isinstance(value,str): return None
    try:
        d=datetime.fromisoformat(value.replace("Z","+00:00"))
        return d if d.tzinfo else None
    except ValueError: return None
def validate_alert(a):
    errors=[]
    required=("schema_version","alert_id","source_id","dataset_id","source_url","region_ids","alert_type","severity","status","issued_at","effective_start","effective_end","collected_at","message")
    errors += ["missing "+k for k in required if k not in a]
    if a.get("schema_version")!="1.0.0": errors.append("schema_version must be 1.0.0")
    if a.get("source_id") not in ("CWA_OPENDATA","CWA_OCEAN_PLATFORM"): errors.append("invalid source_id")
    if not str(a.get("source_url","")).startswith("https://"): errors.append("source_url must be HTTPS")
    if not isinstance(a.get("region_ids"),list) or any(x not in REGIONS for x in a.get("region_ids",[])): errors.append("invalid region_ids")
    if a.get("alert_type") not in {"typhoon","strong_wind_land","heavy_rain","thunderstorm","long_wave","high_wave","storm_surge","cold_surge","large_tide","marine_warning","other"}: errors.append("invalid alert_type")
    if a.get("severity") not in {"extreme","severe","moderate","minor","unknown"}: errors.append("invalid severity")
    if a.get("status") not in {"active","cancelled","expired","unknown"}: errors.append("invalid status")
    for k in ("issued_at","effective_start","effective_end","collected_at"):
        if parse_time(a.get(k)) is None: errors.append(k+" must be timezone-aware ISO-8601")
    start,end=parse_time(a.get("effective_start")),parse_time(a.get("effective_end"))
    if start and end and end<start: errors.append("effective_end precedes effective_start")
    return errors
def decide_region(region_id,alerts,source_status,now,max_age_minutes=90):
    if region_id not in REGIONS: raise ValueError("unknown region_id: "+region_id)
    valid=[];issues=[]
    for a in alerts:
        err=validate_alert(a)
        if err: issues.append(err); continue
        if region_id not in a["region_ids"] or a["status"]!="active": continue
        if parse_time(a["effective_start"])<=now<=parse_time(a["effective_end"]): valid.append(a)
    missing=[];stale=[]
    for dataset in REQUIRED_SOURCES:
        s=source_status.get(dataset,{})
        if s.get("status")!="ok": missing.append(dataset); continue
        t=parse_time(s.get("collected_at"))
        if t is None or t>now or (now-t).total_seconds()>max_age_minutes*60: stale.append(dataset)
    unmapped=[a for a in alerts if a.get("unmapped_area")]
    if any(a["alert_type"] in HIGH_RISK_TYPES for a in valid): state="high_risk"
    elif valid: state="warning"
    elif missing or stale or issues or unmapped: state="insufficient_data"
    else: state="no_active_alerts_reported"
    reasons=[a["alert_type"]+": "+a["message"] for a in valid]
    if missing: reasons.append("來源未取得："+", ".join(missing))
    if stale: reasons.append("來源逾時或時間無效："+", ".join(stale))
    if issues: reasons.append("有警報資料未通過格式驗證，不可忽略")
    if unmapped: reasons.append("有未映射影響範圍，需人工確認")
    if state=="no_active_alerts_reported": reasons.append("已查核來源未回報有效警特報；不代表海面安全，也不排除突發長浪")
    return {"schema_version":"1.0.0","region_id":region_id,"as_of":now.isoformat(),"state":state,"safety_clearance":False,"active_alert_count":len(valid),"active_alerts":[a["alert_id"] for a in valid],"missing_sources":missing,"stale_sources":stale,"validation_issue_count":len(issues),"reasoning":reasons,"mandatory_notice":"本結果不是安全許可；出發前仍須確認現場海況、岸際公告、管制區及裝備。"}
def main():
    p=argparse.ArgumentParser();p.add_argument("--alerts-json",type=Path,required=True);p.add_argument("--source-status-json",type=Path,required=True);p.add_argument("--as-of",required=True);p.add_argument("--out",type=Path,required=True);a=p.parse_args()
    now=parse_time(a.as_of)
    if now is None: raise SystemExit("--as-of must be timezone-aware ISO-8601")
    alerts=json.loads(a.alerts_json.read_text(encoding="utf-8"));status=json.loads(a.source_status_json.read_text(encoding="utf-8"))
    out={"schema_version":"1.0.0","as_of":now.isoformat(),"regions":{r:decide_region(r,alerts,status,now) for r in REGIONS}}
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"regions":len(out["regions"]),"states":{k:v["state"] for k,v in out["regions"].items()}},ensure_ascii=False))
if __name__=="__main__": main()
