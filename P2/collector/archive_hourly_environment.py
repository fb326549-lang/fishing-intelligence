#!/usr/bin/env python3
"""Append normalized hourly environment records to date-partitioned history.

Records are immutable snapshots. Forecast vintages and observation revisions
are retained; exact duplicate JSON records are ignored. No record is overwritten.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import tempfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path

REQUIRED = {"schema_version", "region_id", "valid_time", "collected_at", "data_type", "source_records", "environment", "completeness", "quality"}
ALLOWED_TYPES = {"forecast", "observation", "hindcast", "derived"}

def canonical(record):
    return json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

def record_hash(record):
    return hashlib.sha256(canonical(record).encode("utf-8")).hexdigest()

def validate_record(record, line_no):
    missing = REQUIRED - set(record)
    if missing:
        raise ValueError(f"input line {line_no}: missing keys {sorted(missing)}")
    if record["data_type"] not in ALLOWED_TYPES:
        raise ValueError(f"input line {line_no}: unsupported data_type {record['data_type']!r}")
    for key in ("valid_time", "collected_at"):
        value = datetime.fromisoformat(str(record[key]).replace("Z", "+00:00"))
        if value.tzinfo is None:
            raise ValueError(f"input line {line_no}: {key} must include timezone")
    if not isinstance(record["environment"], dict):
        raise ValueError(f"input line {line_no}: environment must be an object")

def read_input(path):
    partitions = defaultdict(list)
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        record = json.loads(line)
        validate_record(record, line_no)
        day = datetime.fromisoformat(record["valid_time"].replace("Z", "+00:00")).date().isoformat()
        partitions[day].append(record)
    return partitions

def atomic_write(path, content):
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

def archive(input_path: Path, archive_root: Path):
    partitions = read_input(input_path)
    total_added = total_duplicates = 0
    summary = []
    for day, incoming in sorted(partitions.items()):
        year, month, _ = day.split("-")
        target = archive_root / "hourly_environment" / year / month / f"{day}.jsonl"
        existing = []
        seen = set()
        if target.exists():
            for line_no, line in enumerate(target.read_text(encoding="utf-8").splitlines(), 1):
                if not line.strip():
                    continue
                record = json.loads(line)
                validate_record(record, line_no)
                digest = record_hash(record)
                if digest not in seen:
                    seen.add(digest)
                    existing.append(record)
        added = 0
        for record in incoming:
            digest = record_hash(record)
            if digest in seen:
                total_duplicates += 1
                continue
            seen.add(digest)
            existing.append(record)
            added += 1
        existing.sort(key=lambda r: (r["valid_time"], r["region_id"], r["data_type"], r["collected_at"], record_hash(r)))
        atomic_write(target, "".join(canonical(r) + "\n" for r in existing))
        total_added += added
        summary.append({"date": day, "path": str(target.relative_to(archive_root)), "records_added": added, "records_total": len(existing)})
    return {"input_records": sum(map(len, partitions.values())), "records_added": total_added, "exact_duplicates_skipped": total_duplicates, "partitions": summary}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--archive-root", type=Path, required=True)
    args = parser.parse_args()
    result = archive(args.input, args.archive_root)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))

if __name__ == "__main__":
    main()
