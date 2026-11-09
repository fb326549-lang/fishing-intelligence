#!/usr/bin/env python3
"""Fetch CWA official weather alerts and coastal hazard observations.

Raw responses are preserved before validation so schema changes remain
inspectable. No county warning is silently treated as a sea-area clearance.
"""
from __future__ import annotations
import argparse, json, os, time, hashlib
from datetime import datetime, timezone
from pathlib import Path
import xml.etree.ElementTree as ET
import requests

REST = "https://opendata.cwa.gov.tw/api/v1/rest/datastore"
FILE = "https://opendata.cwa.gov.tw/fileapi/v1/opendataapi"
REST_DATASETS = ("W-C0033-001", "W-C0033-002", "W-C0033-003", "W-C0033-006")
FILE_DATASETS = {"W-C0034-001": "CAP", "O-B0069-001": "JSON", "O-B0070-001": "JSON"}
USER_AGENT = "FishingIntelligence-C1/1.0"

def utc_now():
    return datetime.now(timezone.utc).isoformat()

def validate_json_payload(payload, dataset):
    if not isinstance(payload, dict):
        raise ValueError("JSON root must be an object")
    success = payload.get("Success", payload.get("success"))
    if success is not None and str(success).strip().lower() not in {"true", "1"}:
        raise ValueError("provider application-level success flag is false")
    if "Records" not in payload and "records" not in payload:
        raise ValueError("JSON response has no Records object; schema may have changed")
    return payload

def validate_cap_payload(body):
    try:
        root = ET.fromstring(body)
    except ET.ParseError as exc:
        raise ValueError("CAP response is not parseable XML") from exc
    if root.tag.rsplit("}", 1)[-1].lower() != "alert":
        raise ValueError("CAP XML root is not alert")
    return root

def fetch_one(session, dataset, kind, token, outdir, timeout=45):
    collected = utc_now()
    url = f"{REST}/{dataset}" if kind == "REST_JSON" else f"{FILE}/{dataset}"
    params = {"format": "JSON"} if kind == "REST_JSON" else {"format": kind}
    params["Authorization"] = token
    raw_name = f"{dataset}.raw"
    try:
        response = session.get(url, params=params, timeout=timeout, allow_redirects=True)
        if response.status_code >= 400:
            raise RuntimeError(f"HTTP {response.status_code}")
        body = response.content
        # Save the exact bytes before parsing; useful when provider schema changes.
        (outdir / raw_name).write_bytes(body)
        if kind == "CAP":
            validate_cap_payload(body)
            extension = "cap"
        else:
            payload = response.json()
            try:
                payload = validate_json_payload(payload, dataset)
            except ValueError as exc:
                keys = ",".join(str(k) for k in payload.keys()) if isinstance(payload, dict) else type(payload).__name__
                raise ValueError(f"{exc}; top_level={keys}") from exc
            body = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
            extension = "json"
        target = outdir / f"{dataset}.{extension}"
        target.write_bytes(body)
        return {
            "dataset_id": dataset, "status": "ok", "collected_at": collected,
            "file": target.name, "bytes": len(body),
            "sha256": hashlib.sha256(body).hexdigest(),
            "content_type": response.headers.get("Content-Type", ""),
        }
    except Exception as exc:
        # Never print request URLs: file API query strings contain credentials.
        return {
            "dataset_id": dataset, "status": "error", "collected_at": collected,
            "error": f"{type(exc).__name__}: {str(exc).split('?')[0][:360]}",
            "raw_file": raw_name if (outdir / raw_name).exists() else None,
        }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="output/c1_safety_sources")
    parser.add_argument("--delay", type=float, default=1.2)
    args = parser.parse_args()
    token = os.environ.get("CWA_AUTHORIZATION")
    if not token:
        raise SystemExit("Missing CWA_AUTHORIZATION secret.")
    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json, application/xml, text/xml, */*"})
    configs = [(d, "REST_JSON") for d in REST_DATASETS] + list(FILE_DATASETS.items())
    results = []
    for dataset, kind in configs:
        results.append(fetch_one(session, dataset, kind, token, outdir))
        time.sleep(max(0, args.delay))
    manifest = {
        "schema_version": "1.0.0", "collector": "FishingIntelligence-C1",
        "collected_at": utc_now(), "datasets": results,
        "note": "Raw-source collection only. A successful download is not equivalent to a regional safety clearance."
    }
    (outdir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for item in results:
        detail = f' — {item.get("error")}' if item["status"] != "ok" else ""
        print(f'{item["dataset_id"]}: {item["status"]}{detail}')
    if any(item["status"] != "ok" for item in results):
        raise SystemExit("One or more official safety sources failed; fail closed.")

if __name__ == "__main__":
    main()
