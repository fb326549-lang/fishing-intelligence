#!/usr/bin/env python3
"""Audit P2 hourly history partitions against their deterministic catalog."""
from __future__ import annotations
import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path

REQUIRED = {"schema_version", "region_id", "valid_time", "collected_at", "data_type", "source_records", "environment", "completeness", "quality"}
REGIONS = {"yilan_suao", "hualien_north", "hualien_south", "fengbin_shitiping", "chenggong_donghe", "taitung_south"}
DATA_TYPES = {"forecast", "observation", "hindcast", "derived"}

def canonical_hash(record):
    payload = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()

def audit_history(archive_root: Path):
    base = archive_root / "hourly_environment"
    catalog_path = base / "catalog.json"
    if not catalog_path.exists():
        raise ValueError("catalog.json is missing")
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    partition_paths = sorted(base.glob("[0-9][0-9][0-9][0-9]/[0-9][0-9]/[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9].jsonl"))
    catalog_by_path = {p["path"]: p for p in catalog.get("partitions", [])}
    actual_paths = {str(p.relative_to(archive_root)) for p in partition_paths}
    if actual_paths != set(catalog_by_path):
        missing = sorted(actual_paths - set(catalog_by_path))
        stale = sorted(set(catalog_by_path) - actual_paths)
        raise ValueError(f"catalog partition set mismatch; missing entries={missing}, stale entries={stale}")

    total = 0
    regions = set()
    type_counts = {}
    results = []
    for path in partition_paths:
        rel = str(path.relative_to(archive_root))
        entry = catalog_by_path[rel]
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if digest != entry.get("sha256"):
            raise ValueError(f"{rel}: SHA-256 mismatch")
        seen = set()
        count = 0
        for line_no, line in enumerate(raw.decode("utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{rel}:{line_no}: invalid JSON: {exc}") from exc
            missing = REQUIRED - set(record)
            if missing:
                raise ValueError(f"{rel}:{line_no}: missing fields {sorted(missing)}")
            if record["region_id"] not in REGIONS:
                raise ValueError(f"{rel}:{line_no}: unknown region {record['region_id']!r}")
            if record["data_type"] not in DATA_TYPES:
                raise ValueError(f"{rel}:{line_no}: invalid data_type {record['data_type']!r}")
            times = {}
            for key in ("valid_time", "collected_at"):
                parsed = datetime.fromisoformat(str(record[key]).replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    raise ValueError(f"{rel}:{line_no}: {key} has no timezone")
                times[key] = parsed
            if times["valid_time"].strftime("%Y-%m-%d") != path.stem:
                raise ValueError(f"{rel}:{line_no}: valid_time date does not match partition")
            if not isinstance(record["environment"], dict):
                raise ValueError(f"{rel}:{line_no}: environment must be an object")
            digest_record = canonical_hash(record)
            if digest_record in seen:
                raise ValueError(f"{rel}:{line_no}: exact duplicate record")
            seen.add(digest_record)
            count += 1
            regions.add(record["region_id"])
            type_counts[record["data_type"]] = type_counts.get(record["data_type"], 0) + 1
        if count != entry.get("record_count"):
            raise ValueError(f"{rel}: catalog record_count {entry.get('record_count')} != actual {count}")
        if path.stat().st_size != entry.get("size_bytes"):
            raise ValueError(f"{rel}: catalog size_bytes mismatch")
        total += count
        results.append({"path": rel, "records": count, "sha256": digest})
    if total != catalog.get("record_count"):
        raise ValueError(f"catalog total record_count {catalog.get('record_count')} != actual {total}")
    if len(partition_paths) != catalog.get("partition_count"):
        raise ValueError("catalog partition_count mismatch")
    if sorted(regions) != catalog.get("regions"):
        raise ValueError("catalog regions mismatch")
    if dict(sorted(type_counts.items())) != catalog.get("data_types"):
        raise ValueError("catalog data_types mismatch")
    return {"status": "ok", "partition_count": len(partition_paths), "record_count": total, "regions": sorted(regions), "data_types": dict(sorted(type_counts.items())), "partitions": results}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive-root", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(audit_history(args.archive_root), ensure_ascii=False, sort_keys=True))

if __name__ == "__main__":
    main()
