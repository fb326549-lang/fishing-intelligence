#!/usr/bin/env python3
"""Publish the P2.4.6 CSV outlook as a compact, versioned JSON document for the PWA."""
from __future__ import annotations
import argparse,csv,json
from datetime import datetime,timezone
from pathlib import Path

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    with a.input.open(encoding="utf-8-sig",newline="") as f:
        rows=list(csv.DictReader(f))
    if not rows:
        raise SystemExit("Refusing to publish an empty P2 outlook")
    as_ofs={r.get("as_of","") for r in rows}
    if len(as_ofs)!=1 or not next(iter(as_ofs)):
        raise SystemExit("P2 outlook must contain exactly one as_of timestamp")
    regions=sorted({r.get("region_id","") for r in rows if r.get("region_id")})
    horizons=sorted({r.get("horizon_hours","") for r in rows},key=int)
    if horizons!=["6","12","24"]:
        raise SystemExit(f"Expected all 6/12/24-hour horizons; got {horizons}")
    payload={
        "schema_version":1,
        "source":"fishing-intelligence-p2.4.6",
        "generated_at":datetime.now(timezone.utc).isoformat(),
        "as_of":next(iter(as_ofs)),
        "regions":regions,
        "horizons_hours":[6,12,24],
        "record_count":len(rows),
        "model_limits":{
            "environment_match":"only evidence-approved rules; currently no approved East Taiwan numeric response rules",
            "activity_score":None,
            "catch_probability":None,
            "best_fishing_window":"not_established",
            "safety_assessment":"not_included; consult official marine warnings and local conditions"
        },
        "rows":rows
    }
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(payload,ensure_ascii=False,separators=(",",":"))+"\n",encoding="utf-8")
    print(f"Published {len(rows)} P2.4.6 records for {len(regions)} regions and horizons {','.join(horizons)}")
if __name__=="__main__":main()
