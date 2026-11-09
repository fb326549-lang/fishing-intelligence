#!/usr/bin/env python3
"""Summarize 6/12/24-hour forecast windows without claiming best fishing times."""
from __future__ import annotations
import argparse, csv, json
from datetime import datetime, timedelta
from pathlib import Path

HORIZONS=(6,12,24)
REGIONS=("yilan_suao","hualien_north","hualien_south","fengbin_shitiping","chenggong_donghe","taitung_south")

def parse_dt(value,label):
    if not isinstance(value,str) or not value.strip():
        raise ValueError(f"{label} must be a timezone-aware ISO-8601 datetime")
    try: dt=datetime.fromisoformat(value.replace("Z","+00:00"))
    except ValueError as exc: raise ValueError(f"{label} is not valid ISO-8601") from exc
    if dt.tzinfo is None: raise ValueError(f"{label} must include a timezone offset")
    return dt

def read_csv(path):
    with path.open(encoding="utf-8-sig",newline="") as f: return list(csv.DictReader(f))

def select_forecast_vintages(records,as_of):
    selected={}
    for n,record in enumerate(records,1):
        if record.get("data_type")!="forecast": continue
        valid=parse_dt(record.get("valid_time"),f"record {n} valid_time")
        collected=parse_dt(record.get("collected_at"),f"record {n} collected_at")
        if collected>as_of or valid<as_of: continue
        key=(record.get("region_id",""),valid.isoformat())
        current=selected.get(key)
        if current is None or collected>current[0]:
            selected[key]=(collected,record)
    return [v[1] for _,v in sorted(selected.items(),key=lambda x:(x[0][0],x[0][1]))]

def index_integrated(rows):
    result={}
    for row in rows:
        key=(row.get("candidate_id",""),row.get("region_id",""),row.get("valid_time",""),row.get("data_type",""))
        if key in result: raise ValueError(f"duplicate integrated assessment row: {key}")
        result[key]=row
    return result

def build_window_summaries(records,candidate_rows,integrated_rows,as_of):
    if as_of.minute or as_of.second or as_of.microsecond:
        raise ValueError("--as-of must be aligned to the start of an hour")
    forecast=select_forecast_vintages(records,as_of)
    integrated=index_integrated(integrated_rows)
    candidates={}
    for row in candidate_rows:
        cid=row.get("candidate_id","")
        if not cid: raise ValueError("candidate register contains blank candidate_id")
        if cid in candidates and candidates[cid].get("eligibility_gate")!=row.get("eligibility_gate"):
            raise ValueError(f"candidate {cid} has conflicting eligibility_gate values")
        candidates[cid]=row
    by_region={}
    for row in forecast: by_region.setdefault(row.get("region_id",""),[]).append(row)
    output=[]
    for region in REGIONS:
        region_rows=by_region.get(region,[])
        for hours in HORIZONS:
            end=as_of+timedelta(hours=hours)
            window=[r for r in region_rows if as_of<=parse_dt(r["valid_time"],"valid_time")<end]
            # Tide phases are hydrodynamic context only, not a fish-activity score.
            phase_counts={phase:0 for phase in ("rising","falling","high_slack","low_slack")}
            turning_hours=0
            for record in window:
                env=record.get("environment") or {}
                phase=env.get("tide_phase")
                if phase in phase_counts:
                    phase_counts[phase]+=1
                if env.get("tide_turning") is True:
                    turning_hours+=1
            phase_known=sum(phase_counts.values())
            phase_missing=len(window)-phase_known
            forecast_missing=hours-len(window)
            # Keep one record per hour after forecast vintage selection; absent hours remain absent.
            for cid,candidate in sorted(candidates.items()):
                joined=[integrated.get((cid,region,r.get("valid_time",""),"forecast")) for r in window]
                joined=[r for r in joined if r is not None]
                scores=[]
                for row in joined:
                    value=row.get("environment_match_score","")
                    if value not in (None,""):
                        try: scores.append(float(value))
                        except ValueError: pass
                statuses=sorted({r.get("activity_evidence_status","") for r in joined if r.get("activity_evidence_status")})
                if "taxon_or_distribution_gate" in statuses:
                    activity_status="taxon_or_distribution_gate"
                elif "context_only_evidence_available" in statuses:
                    activity_status="context_only_evidence_available"
                elif "direct_evidence_requires_activity_rule_review" in statuses:
                    activity_status="direct_evidence_requires_activity_rule_review"
                elif "insufficient_east_taiwan_activity_evidence" in statuses:
                    activity_status="insufficient_east_taiwan_activity_evidence"
                else:
                    activity_status="missing_activity_assessment"
                if not window:
                    env_status="no_forecast_records"
                elif not scores:
                    statuses_env={r.get("environment_match_status","") for r in joined}
                    if statuses_env and statuses_env=={"insufficient_evidence"}: env_status="insufficient_evidence"
                    elif statuses_env and statuses_env=={"taxon_or_distribution_gate"}: env_status="taxon_or_distribution_gate"
                    else: env_status="environment_match_unavailable"
                elif len(scores)<hours or len(window)<hours:
                    env_status="partial_environment_match_coverage"
                else:
                    env_status="environment_match_summary_available"
                evidence_ids=sorted({x for r in joined for x in r.get("activity_evidence_ids","").split(";") if x})
                occurrence_ids=sorted({x for r in joined for x in r.get("occurrence_evidence_ids","").split(";") if x})
                seasonal_ids=sorted({x for r in joined for x in r.get("seasonal_evidence_ids","").split(";") if x})
                def collect_evidence_context(field):
                    by_id={}
                    for integrated_row in joined:
                        raw_context=integrated_row.get(field,"")
                        if not raw_context:
                            continue
                        try:
                            contexts=json.loads(raw_context)
                        except (TypeError,ValueError) as exc:
                            raise ValueError(f"invalid {field} for {cid}/{region}: {exc}") from exc
                        if not isinstance(contexts,list):
                            raise ValueError(f"{field} must contain a JSON array")
                        for context in contexts:
                            if not isinstance(context,dict) or not context.get("id"):
                                raise ValueError(f"{field} entries must be objects with an id")
                            evidence_id=context["id"]
                            previous=by_id.get(evidence_id)
                            if previous is not None and previous!=context:
                                raise ValueError(f"conflicting {field} metadata for evidence {evidence_id}")
                            by_id[evidence_id]=context
                    return [by_id[key] for key in sorted(by_id)]
                activity_context=collect_evidence_context("activity_evidence_context_json")
                occurrence_context=collect_evidence_context("occurrence_evidence_context_json")
                seasonal_context=collect_evidence_context("seasonal_evidence_context_json")
                rule_trace_by_hour={}
                for integrated_row in joined:
                    raw_trace=integrated_row.get("rule_evidence_trace_json","")
                    if not raw_trace:
                        continue
                    try:
                        trace_items=json.loads(raw_trace)
                    except (TypeError,ValueError) as exc:
                        raise ValueError(f"invalid rule_evidence_trace_json for {cid}/{region}: {exc}") from exc
                    if not isinstance(trace_items,list):
                        raise ValueError("rule_evidence_trace_json must contain a JSON array")
                    for item in trace_items:
                        if not isinstance(item,dict) or not item.get("rule_id"):
                            raise ValueError("rule trace entries must be objects with a rule_id")
                        key=(item["rule_id"],item.get("valid_time",""))
                        previous=rule_trace_by_hour.get(key)
                        if previous is not None and previous!=item:
                            raise ValueError(f"conflicting rule trace metadata for {key}")
                        rule_trace_by_hour[key]=item
                rule_trace=[rule_trace_by_hour[key] for key in sorted(rule_trace_by_hour)]
                output.append({
                    "candidate_id":cid,"common_name_zh":candidate.get("common_name_zh",""),
                    "scientific_name":candidate.get("scientific_name",""),"region_id":region,
                    "as_of":as_of.isoformat(),"horizon_hours":str(hours),"window_end":end.isoformat(),
                    "forecast_hour_count":str(len(window)),"expected_hour_count":str(hours),
                    "forecast_coverage":f"{len(window)/hours:.4f}",
                    "tide_phase_rising_hours":str(phase_counts["rising"]),
                    "tide_phase_falling_hours":str(phase_counts["falling"]),
                    "tide_phase_high_slack_hours":str(phase_counts["high_slack"]),
                    "tide_phase_low_slack_hours":str(phase_counts["low_slack"]),
                    "tide_phase_known_hour_count":str(phase_known),
                    "tide_phase_missing_hour_count":str(phase_missing),
                    "tide_phase_missing_forecast_hour_count":str(forecast_missing),
                    "tide_phase_coverage":f"{phase_known/hours:.4f}",
                    "tide_turning_hour_count":str(turning_hours),
                    "environment_match_hour_count":str(len(scores)),"environment_match_status":env_status,
                    "environment_match_mean":f"{sum(scores)/len(scores):.2f}" if scores else "",
                    "environment_match_min":f"{min(scores):.2f}" if scores else "",
                    "environment_match_max":f"{max(scores):.2f}" if scores else "",
                    "activity_evidence_status":activity_status,
                    "activity_evidence_ids":";".join(evidence_ids),
                    "activity_evidence_context_json":json.dumps(activity_context,ensure_ascii=False,separators=(",",":")),
                    "occurrence_evidence_context_json":json.dumps(occurrence_context,ensure_ascii=False,separators=(",",":")),
                    "occurrence_evidence_count":str(len(occurrence_ids)),
                    "occurrence_evidence_ids":";".join(occurrence_ids),
                    "seasonal_evidence_ids":";".join(seasonal_ids),
                    "seasonal_evidence_context_json":json.dumps(seasonal_context,ensure_ascii=False,separators=(",",":")),
                    "rule_evidence_trace_json":json.dumps(rule_trace,ensure_ascii=False,separators=(",",":")),
                    "activity_score":"","catch_probability":"","best_fishing_window_status":"not_established",
                    "interpretation":"forecast_environment_summary_not_fish_activity_or_catch_probability",
                })
    return output

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--environment-jsonl",type=Path,required=True)
    p.add_argument("--candidates-csv",type=Path,required=True)
    p.add_argument("--integrated-csv",type=Path,required=True)
    p.add_argument("--as-of",required=True,help="timezone-aware ISO-8601 timestamp aligned to the hour")
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    records=[json.loads(x) for x in a.environment_jsonl.read_text(encoding="utf-8").splitlines() if x.strip()]
    rows=build_window_summaries(records,read_csv(a.candidates_csv),read_csv(a.integrated_csv),parse_dt(a.as_of,"--as-of"))
    fields=["candidate_id","common_name_zh","scientific_name","region_id","as_of","horizon_hours","window_end",
        "forecast_hour_count","expected_hour_count","forecast_coverage",
        "tide_phase_rising_hours","tide_phase_falling_hours","tide_phase_high_slack_hours","tide_phase_low_slack_hours",
        "tide_phase_known_hour_count","tide_phase_missing_hour_count","tide_phase_missing_forecast_hour_count",
        "tide_phase_coverage","tide_turning_hour_count","environment_match_hour_count",
        "environment_match_status","environment_match_mean","environment_match_min","environment_match_max",
        "activity_evidence_status","activity_evidence_ids","activity_evidence_context_json",
        "occurrence_evidence_count","occurrence_evidence_ids","occurrence_evidence_context_json",
        "seasonal_evidence_ids","seasonal_evidence_context_json","rule_evidence_trace_json","activity_score",
        "catch_probability","best_fishing_window_status","interpretation"]
    a.out.parent.mkdir(parents=True,exist_ok=True)
    with a.out.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields,lineterminator="\n");w.writeheader();w.writerows(rows)
    print(f"Built {len(rows)} 6/12/24-hour candidate-region summaries; best fishing windows remain unestablished.")
if __name__=="__main__": main()
