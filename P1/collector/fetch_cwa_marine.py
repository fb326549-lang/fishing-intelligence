#!/usr/bin/env python3
"""Download CWA 48-hour and 30-day buoy/tide observations.

The REST datastore API is documented by CWA for O-B0075-001 and O-B0075-002.
Credentials are read only from CWA_AUTHORIZATION and are never printed.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE = "https://opendata.cwa.gov.tw/api/v1/rest/datastore"
DATASETS = ("O-B0075-001", "O-B0075-002")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="output/cwa_marine")
    parser.add_argument("--delay", type=float, default=1.5)
    args = parser.parse_args()

    token = os.environ.get("CWA_AUTHORIZATION")
    if not token:
        raise SystemExit("Missing CWA_AUTHORIZATION secret.")

    output_dir = Path(args.out)
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "datasets": [],
    }
    session = requests.Session()
    session.headers.update({"User-Agent": "FishingIntelligence-P1/0.4"})

    for dataset in DATASETS:
        try:
            response = session.get(
                f"{BASE}/{dataset}",
                params={"Authorization": token, "format": "JSON"},
                timeout=45,
            )
            if response.status_code >= 400:
                raise RuntimeError(f"HTTP {response.status_code}")

            payload = response.json()
            # CWA's live response uses capitalized "Success"; tolerate the
            # lower-case spelling as well, but never silently accept false.
            success_flag = payload.get("Success", payload.get("success"))
            if success_flag is not None and str(success_flag).strip().lower() not in {
                "true", "1"
            }:
                raise RuntimeError(
                    f"CWA API application-level failure: Success={success_flag}"
                )
            if not isinstance(payload, dict) or "Records" not in payload:
                raise RuntimeError("CWA response is missing the Records object.")

            output_path = output_dir / f"{dataset}.json"
            output_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            manifest["datasets"].append({
                "dataset_id": dataset,
                "status": "downloaded",
                "bytes": output_path.stat().st_size,
                "file": output_path.name,
                "top_level_keys": list(payload.keys()),
            })
        except Exception as exc:
            manifest["datasets"].append({
                "dataset_id": dataset,
                "status": "error",
                "error": str(exc),
            })
        time.sleep(max(0, args.delay))

    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    for item in manifest["datasets"]:
        status = item["status"]
        detail = (
            f' ({item.get("bytes", 0)} bytes)'
            if status == "downloaded"
            else f' ({item.get("error", "error")})'
        )
        print(f'{item["dataset_id"]}: {status}{detail}')

    if any(item["status"] != "downloaded" for item in manifest["datasets"]):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
