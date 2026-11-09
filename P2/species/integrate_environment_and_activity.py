#!/usr/bin/env python3
"""Join environmental match results with activity/seasonal evidence without inventing activity scores."""
from __future__ import annotations
import argparse, csv, json
from pathlib import Path

def read_csv(path):
    with path.open(encoding="utf-8-sig",newline="") as f:
        return list(csv.DictReader(f))

def unique_candidates(rows):
    result={}
    for row in rows:
        cid=row.get("candidate_id","").strip()
        if not cid: raise ValueError("candidate register contains blank candidate_id")
        gate=row.get("eligibility_gate","").strip()
        if cid in result and result[cid]["eligibility_gate"]!=gate:
            raise ValueError(f"candidate {cid} has conflicting eligibility_gate values")
        result[cid]=row
    return result

def index_matches(rows):
    indexed={}
    for row in rows:
        key=(row.get("candidate_id",""),row.get("region_id",""),row.get("valid_time",""))
        if key in indexed: raise ValueError(f"duplicate environment match result: {key}")
        indexed[key]=row
    return indexed

def build_integrated_rows(environments,candidate_rows,match_rows,activity_rows,seasonal_rows):
    candidates=unique_candidates(candidate_rows)
    matches=index_matches(match_rows)
    activity_by={cid:[] for cid in candidates}
    seasonal_by={cid:[] for cid in candidates}
    for row in activity_rows:
        if row.get("candidate_id") in activity_by: activity_by[row["candidate_id"]].append(row)
    for row in seasonal_rows:
        if row.get("candidate_id") in seasonal_by: seasonal_by[row["candidate_id"]].append(row)
    output=[]
    for env in environments:
        region=env.get("region_id","")
        valid=env.get("valid_time","")
        for cid,candidate in sorted(candidates.items()):
            match=matches.get((cid,region,valid))
            gate=candidate.get("eligibility_gate","")
            arows=activity_by[cid]
            srows=seasonal_by[cid]
            if gate!="verified_taxon":
                activity_status="taxon_or_distribution_gate"
                activity_reason="candidate identity or regional occurrence is not cleared"
            else:
                east_direct=[r for r in arows+srows
                    if r.get("transferability","").startswith("east_taiwan_direct")
                    and r.get("model_use_status","").startswith("eligible_for_activity")]
                if east_direct:
                    activity_status="direct_evidence_requires_activity_rule_review"
                    activity_reason="East Taiwan direct evidence exists but no approved activity scoring rule is defined by this integration"
                elif arows or srows:
                    activity_status="context_only_evidence_available"
                    activity_reason="available evidence is external-region, non-target life-stage, descriptive, or otherwise context-only"
                else:
                    activity_status="insufficient_east_taiwan_activity_evidence"
                    activity_reason="no traceable activity or seasonal evidence for this candidate"
            output.append({
                "candidate_id":cid,
                "common_name_zh":candidate.get("common_name_zh",""),
                "scientific_name":candidate.get("scientific_name",""),
                "region_id":region,
                "valid_time":valid,
                "data_type":env.get("data_type",""),
                "taxon_gate":gate,
                "environment_match_status":match.get("status","missing_environment_match_result") if match else "missing_environment_match_result",
                "environment_match_score":match.get("environment_match_score","") if match else "",
                "environment_rule_coverage":match.get("rule_coverage","") if match else "",
                "activity_evidence_status":activity_status,
                "activity_evidence_count":str(len(arows)),
                "seasonal_evidence_count":str(len(srows)),
                "activity_evidence_ids":";".join(sorted(r.get("activity_evidence_id","") for r in arows if r.get("activity_evidence_id"))),
                "seasonal_evidence_ids":";".join(sorted(r.get("seasonal_evidence_id","") for r in srows if r.get("seasonal_evidence_id"))),
                "activity_reason":activity_reason,
                "activity_score":"",
                "catch_probability":"",
                "best_fishing_window_status":"not_established",
                "interpretation":"environment_match_is_not_fish_activity_or_catch_probability",
            })
    return output

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--environment-jsonl",type=Path,required=True)
    p.add_argument("--candidates-csv",type=Path,required=True)
    p.add_argument("--environment-match-csv",type=Path,required=True)
    p.add_argument("--activity-csv",type=Path,required=True)
    p.add_argument("--seasonal-csv",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    env=[]
    for n,line in enumerate(a.environment_jsonl.read_text(encoding="utf-8").splitlines(),1):
        if line.strip():
            try: env.append(json.loads(line))
            except json.JSONDecodeError as exc: raise ValueError(f"environment JSONL line {n}: invalid JSON") from exc
    rows=build_integrated_rows(env,read_csv(a.candidates_csv),read_csv(a.environment_match_csv),
        read_csv(a.activity_csv),read_csv(a.seasonal_csv))
    fields=["candidate_id","common_name_zh","scientific_name","region_id","valid_time","data_type","taxon_gate",
        "environment_match_status","environment_match_score","environment_rule_coverage","activity_evidence_status",
        "activity_evidence_count","seasonal_evidence_count","activity_evidence_ids","seasonal_evidence_ids",
        "activity_reason","activity_score","catch_probability","best_fishing_window_status","interpretation"]
    a.out.parent.mkdir(parents=True,exist_ok=True)
    with a.out.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields,lineterminator="\n");w.writeheader();w.writerows(rows)
    print(f"Integrated {len(rows)} candidate-region-hour rows; activity scores and catch probabilities remain unassigned.")
if __name__=="__main__": main()
