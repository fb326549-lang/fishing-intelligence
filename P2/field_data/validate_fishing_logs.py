#!/usr/bin/env python3
"""Validate paired fishing-session and catch-event ground-truth CSV files."""
from __future__ import annotations
import argparse,csv,json
from datetime import datetime
from pathlib import Path

REGIONS={"yilan_suao","hualien_north","hualien_south","fengbin_shitiping","chenggong_donghe","taitung_south"}
CONFIDENCE={"high","medium","low","unconfirmed"}
SESSION_REQUIRED={"session_id","started_at_local","region_id","method","effort_minutes","catch_count"}
CATCH_REQUIRED={"catch_id","session_id","caught_at_local","common_name_reported","species_identification_confidence","count"}

def read_csv(path):
    with path.open(encoding="utf-8-sig",newline="") as f:
        reader=csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError(f"{path}: missing CSV header")
        return reader.fieldnames,list(reader)

def integer(value,field,line,minimum=0):
    try: n=int(value)
    except (TypeError,ValueError): raise ValueError(f"{field} at row {line} must be an integer")
    if str(n)!=str(value).strip() or n<minimum: raise ValueError(f"{field} at row {line} must be >= {minimum}")
    return n

def timestamp(value,field,line):
    try: dt=datetime.fromisoformat(value.replace("Z","+00:00"))
    except Exception: raise ValueError(f"{field} at row {line} must be ISO 8601")
    if dt.tzinfo is None or dt.utcoffset() is None: raise ValueError(f"{field} at row {line} must include timezone")
    return dt

def validate(session_path:Path,catch_path:Path):
    sh,sessions=read_csv(session_path); ch,catches=read_csv(catch_path)
    errors=[]
    for field in SESSION_REQUIRED:
        if field not in sh: errors.append(f"session CSV missing column: {field}")
    for field in CATCH_REQUIRED:
        if field not in ch: errors.append(f"catch CSV missing column: {field}")
    if errors: return errors
    session_map={}
    for line,row in enumerate(sessions,2):
        sid=(row.get("session_id") or "").strip()
        if not sid: errors.append(f"session row {line}: session_id is required"); continue
        if sid in session_map: errors.append(f"session row {line}: duplicate session_id {sid}"); continue
        try:
            start=timestamp(row["started_at_local"],"started_at_local",line)
            end=timestamp(row["ended_at_local"],"ended_at_local",line) if (row.get("ended_at_local") or "").strip() else None
            if end and end<start: raise ValueError(f"ended_at_local at row {line} precedes start")
            if row["region_id"] not in REGIONS: raise ValueError(f"unknown region_id at row {line}")
            if not (row.get("method") or "").strip(): raise ValueError(f"method at row {line} is required")
            effort=integer(row["effort_minutes"],"effort_minutes",line,1)
            total=integer(row["catch_count"],"catch_count",line,0)
            session_map[sid]={"start":start,"end":end,"catch_count":total,"event_count":0,"event_total":0}
        except ValueError as e: errors.append(str(e))
    seen=set()
    for line,row in enumerate(catches,2):
        cid=(row.get("catch_id") or "").strip(); sid=(row.get("session_id") or "").strip()
        if not cid: errors.append(f"catch row {line}: catch_id is required"); continue
        if cid in seen: errors.append(f"catch row {line}: duplicate catch_id {cid}"); continue
        seen.add(cid)
        session=session_map.get(sid)
        if not session: errors.append(f"catch row {line}: unknown session_id {sid}"); continue
        try:
            caught=timestamp(row["caught_at_local"],"caught_at_local",line)
            if caught<session["start"] or (session["end"] and caught>session["end"]):
                raise ValueError(f"caught_at_local at row {line} is outside session interval")
            if not (row.get("common_name_reported") or "").strip(): raise ValueError(f"common_name_reported at row {line} is required")
            if row.get("species_identification_confidence") not in CONFIDENCE: raise ValueError(f"invalid species_identification_confidence at row {line}")
            count=integer(row["count"],"count",line,1)
            session["event_count"]+=1;session["event_total"]+=count
        except ValueError as e: errors.append(str(e))
    for sid,s in session_map.items():
        if s["catch_count"]!=s["event_total"]:
            errors.append(f"session {sid}: catch_count={s['catch_count']} but catch-event counts sum to {s['event_total']}")
    if not sessions: errors.append("session CSV contains no sessions")
    return errors

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--sessions",type=Path,required=True)
    p.add_argument("--catches",type=Path,required=True)
    a=p.parse_args(); errors=validate(a.sessions,a.catches)
    if errors:
        print(json.dumps({"valid":False,"errors":errors},ensure_ascii=False,indent=2));raise SystemExit(1)
    print(json.dumps({"valid":True,"message":"Fishing sessions and catch events are consistent. Zero-catch sessions are retained."},ensure_ascii=False))
if __name__=="__main__":main()
