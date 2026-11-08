#!/usr/bin/env python3
"""Download CWA 48-hour and 30-day buoy/tide observations.

The REST datastore API is documented by CWA for O-B0075-001 and O-B0075-002.
Credentials are read only from CWA_AUTHORIZATION and are never printed.
"""
from __future__ import annotations
import argparse, json, os, time
from datetime import datetime, timezone
from pathlib import Path
import requests

BASE = "https://opendata.cwa.gov.tw/api/v1/rest/datastore"
DATASETS = ("O-B0075-001", "O-B0075-002")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="output/cwa_marine")
    parser.add_argument("--delay", type=float, default=1.5)
    args = parser.parse_args()
    token = os.environ.get("CWA_AUTHORIZATION")
    if not token:
        raise SystemExit("Missing CWA_AUTHORIZATION secret.")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    manifest = {"fetched_at": datetime.now(timezone.utc).isoformat(), "datasets": []}
    session = requests.Session()
    session.headers.update({"User-Agent": "FishingIntelligence-P1/0.3"})
    for dataset in DATASETS:
        try:
            response = session.get(
                f"{BASE}/{dataset}",
                params={"Authorization": token, "format": "JSON"},
                timeout=45
            )
            if response.status_code >= 400:
                raise RuntimeError(f"HTTP {response.status_code}")
            payload = response.json()
            # CWA may return an application-level error in a successful HTTP response.
            success = str(payload.get("success", "")).lower()
            if success == "false":
                raise RuntimeError("CWA API returned success=false")
            path = out / f"{dataset}.json"
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            manifest["datasets"].append({
                "dataset_id": dataset, "status": "downloaded",
                "bytes": path.stat().st_size, "file": path.name,
                "top_level_keys": list(payload.keys())
            })
        except Exception as exc:
            manifest["datasets"].append({
                "dataset_id": dataset, "status": "error",
                "error": str(exc)
            })
        time.sleep(max(0, args.delay))
    (out / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    for item in manifest["datasets"]:
        print(f'{item["dataset_id"]}: {item["status"]}' +
              (f' ({item.get("bytes", 0)} bytes)' if item["status"] == "downloaded" else f' ({item.get("error", "error")})'))
    if any(x["status"] != "downloaded" for x in manifest["datasets"]):
        raise SystemExit(1)

if __name__ == "__main__":
    main()
