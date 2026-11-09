#!/usr/bin/env python3
"""Publish the P2 hourly outlook and optional historical eDNA context for the PWA."""
from __future__ import annotations
import argparse,csv,json
from datetime import datetime,timezone
from pathlib import Path

def build_payload(rows, edna_context=None, generated_at=None, species_context=None):
    if not rows:
        raise ValueError("Refusing to publish an empty P2 outlook")
    as_ofs={r.get("as_of","") for r in rows}
    if len(as_ofs)!=1 or not next(iter(as_ofs)):
        raise ValueError("P2 outlook must contain exactly one as_of timestamp")
    regions=sorted({r.get("region_id","") for r in rows if r.get("region_id")})
    horizons=sorted({r.get("horizon_hours","") for r in rows},key=int)
    if horizons!=["6","12","24"]:
        raise ValueError(f"Expected all 6/12/24-hour horizons; got {horizons}")
    context = edna_context or {
        "schema_version": 1,
        "generated_at_utc": None,
        "interpretation": "No historical eDNA context has been published; this is not evidence of absence.",
        "records": [],
    }
    if context.get("schema_version") != 1 or not isinstance(context.get("records"), list):
        raise ValueError("eDNA occurrence context schema is invalid")
    for row in context["records"]:
        if row.get("model_use_status") != "context_only_edna_occurrence":
            raise ValueError("eDNA context cannot be promoted to an activity-scoring record")
        for field in ("exact_positive_detection_record_count","ambiguous_positive_detection_record_count"):
            if not isinstance(row.get(field), int) or row[field] < 0:
                raise ValueError(f"invalid eDNA context count: {field}")
    ecology = species_context or {
        "schema_version": 1,
        "generated_at": None,
        "record_count": 0,
        "interpretation": "No species ecology context catalog is available; this is not evidence of absence.",
        "records": [],
    }
    if ecology.get("schema_version") != 1 or not isinstance(ecology.get("records"), list):
        raise ValueError("species ecology context schema is invalid")
    for record in ecology["records"]:
        if not record.get("candidate_id") or not record.get("parameter_code") or not record.get("source_url"):
            raise ValueError("species ecology context record is missing candidate, parameter or provenance")
    return {
        "schema_version":1,
        "source":"fishing-intelligence-p2.6",
        "generated_at":generated_at or datetime.now(timezone.utc).isoformat(),
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
        "edna_occurrence_context":context,
        "species_ecology_context":ecology,
        "rows":rows
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--edna-context-json",type=Path)
    p.add_argument("--species-context-json",type=Path)
    a=p.parse_args()
    with a.input.open(encoding="utf-8-sig",newline="") as f:
        rows=list(csv.DictReader(f))
    context=None
    if a.edna_context_json and a.edna_context_json.exists():
        context=json.loads(a.edna_context_json.read_text(encoding="utf-8"))
    species_context=None
    if a.species_context_json and a.species_context_json.exists():
        species_context=json.loads(a.species_context_json.read_text(encoding="utf-8"))
    payload=build_payload(rows,context,species_context=species_context)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(payload,ensure_ascii=False,separators=(",",":"))+"\n",encoding="utf-8")
    print(f"Published {len(rows)} hourly outlook records and {len(payload['edna_occurrence_context']['records'])} historical eDNA candidate-region context records.")
if __name__=="__main__":main()
