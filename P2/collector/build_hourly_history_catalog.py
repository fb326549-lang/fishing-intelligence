#!/usr/bin/env python3
"""Build a deterministic, replaceable catalog for archived P2 hourly JSONL files."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import tempfile
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

def parse_time(value):
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"timestamp has no timezone: {value}")
    return parsed

def atomic_write(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise

def build_catalog(archive_root: Path):
    base = archive_root / "hourly_environment"
    partitions = []
    total_records = 0
    global_regions = set()
    global_types = Counter()
    for path in sorted(base.glob("[0-9][0-9][0-9][0-9]/[0-9][0-9]/[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9].jsonl")):
        records = []
        seen_hashes = set()
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            record = json.loads(line)
            for key in ("region_id", "valid_time", "collected_at", "data_type"):
                if not record.get(key):
                    raise ValueError(f"{path}:{line_no}: missing {key}")
            valid = parse_time(record["valid_time"])
            collected = parse_time(record["collected_at"])
            records.append((record, valid, collected))
            digest = hashlib.sha256(json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
            if digest in seen_hashes:
                raise ValueError(f"{path}:{line_no}: exact duplicate record")
            seen_hashes.add(digest)
        if not records:
            continue
        region_type_counts = Counter()
        region_valid_hours = defaultdict(set)
        region_vintages = defaultdict(set)
        valid_times = []
        collected_times = []
        for record, valid, collected in records:
            region = record["region_id"]
            kind = record["data_type"]
            region_type_counts[f"{region}|{kind}"] += 1
            region_valid_hours[f"{region}|{kind}"].add(valid.isoformat())
            region_vintages[f"{region}|{kind}"].add(collected.isoformat())
            valid_times.append(valid)
            collected_times.append(collected)
            global_regions.add(region)
            global_types[kind] += 1
        partitions.append({
            "date": path.stem,
            "path": str(path.relative_to(archive_root)),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "size_bytes": path.stat().st_size,
            "record_count": len(records),
            "regions": sorted({r[0]["region_id"] for r in records}),
            "data_types": dict(sorted(Counter(r[0]["data_type"] for r in records).items())),
            "records_by_region_type": dict(sorted(region_type_counts.items())),
            "unique_valid_hours_by_region_type": {k: len(v) for k, v in sorted(region_valid_hours.items())},
            "collection_vintages_by_region_type": {k: len(v) for k, v in sorted(region_vintages.items())},
            "valid_time_min": min(valid_times).isoformat(),
            "valid_time_max": max(valid_times).isoformat(),
            "collected_at_min": min(collected_times).isoformat(),
            "collected_at_max": max(collected_times).isoformat(),
        })
        total_records += len(records)
    catalog = {
        "catalog_version": "1.0.0",
        "archive_layout": "hourly_environment/YYYY/MM/YYYY-MM-DD.jsonl",
        "partition_count": len(partitions),
        "record_count": total_records,
        "regions": sorted(global_regions),
        "data_types": dict(sorted(global_types.items())),
        "partitions": partitions,
        "notes": [
            "Counts distinguish stored records from unique valid hours; forecast vintages and observation revisions may create multiple records per valid hour.",
            "This catalog is derived metadata and may be regenerated; the underlying JSONL history is append-only.",
            "No missing hours are inferred as zero or backfilled from another region."
        ],
    }
    return catalog

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive-root", type=Path, required=True)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    catalog = build_catalog(args.archive_root)
    target = args.out or (args.archive_root / "hourly_environment" / "catalog.json")
    atomic_write(target, json.dumps(catalog, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    print(json.dumps({"catalog": str(target), "partitions": catalog["partition_count"], "records": catalog["record_count"], "regions": catalog["regions"]}, ensure_ascii=False, sort_keys=True))

if __name__ == "__main__":
    main()
