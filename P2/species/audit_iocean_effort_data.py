#!/usr/bin/env python3
"""Audit whether an iOcean export contains time and effort fields for radar use.

This reports schema completeness only. It never calculates CPUE, fish scores,
or treats an absent catch record as a zero-catch fishing trip.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
from collections import Counter
from datetime import date, datetime
from pathlib import Path

REQUIRED_FIELDS = (
    "ID", "Fishing_Time", "People_Count", "WGS84X", "WGS84Y",
    "Species_Name", "Name_Code", "Fishing_Count", "Fishing_Length", "Type_Name",
)
METADATA_ROWS = {
    "Fishing_Time": {"垂釣時間", "Fishing time"},
    "People_Count": {"同行人數", "People count"},
    "WGS84X": {"經度", "Longitude"},
    "WGS84Y": {"緯度", "Latitude"},
}
EFFORT_HEADER_TOKENS = ("hour", "duration", "時數", "小時", "分鐘", "作釣時間")


def _blank(value: str | None) -> bool:
    return value is None or not value.strip()


def _is_export_metadata_row(row: dict[str, str | None]) -> bool:
    """The official export includes one translated-label row after its header."""
    return all(row.get(field, "").strip() in labels for field, labels in METADATA_ROWS.items())


def _time_kind(value: str | None) -> str:
    if _blank(value):
        return "missing"
    candidate = value.strip()
    try:
        date.fromisoformat(candidate)
        return "date_only"
    except ValueError:
        pass
    try:
        parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
    except ValueError:
        return "unparseable"
    return "datetime_with_clock" if any((parsed.hour, parsed.minute, parsed.second)) or "T" in candidate or " " in candidate else "date_only"


def _number_kind(value: str | None) -> str:
    if _blank(value):
        return "missing"
    try:
        number = float(value)
    except ValueError:
        return "invalid"
    if not math.isfinite(number):
        return "invalid"
    if number < 0:
        return "negative"
    if number == 0:
        return "zero"
    return "positive"


def audit_rows(fieldnames: list[str] | None, source_rows: list[dict[str, str | None]]) -> dict:
    headers = [name.strip() for name in (fieldnames or [])]
    rows = [row for row in source_rows if not _is_export_metadata_row(row)]
    completeness = {}
    for field in REQUIRED_FIELDS:
        if field not in headers:
            completeness[field] = {"present": 0, "missing": len(rows), "field_available": False}
        else:
            present = sum(not _blank(row.get(field)) for row in rows)
            completeness[field] = {
                "present": present,
                "missing": len(rows) - present,
                "field_available": True,
            }

    time_counts = Counter(_time_kind(row.get("Fishing_Time")) for row in rows)
    catch_counts = Counter(_number_kind(row.get("Fishing_Count")) for row in rows)
    people_counts = Counter(_number_kind(row.get("People_Count")) for row in rows)
    ids = [row.get("ID", "").strip() for row in rows if not _blank(row.get("ID"))]
    id_counts = Counter(ids)
    duration_fields = [
        name for name in headers
        if any(token in re.sub(r"[\s_\-]", "", name).casefold() for token in EFFORT_HEADER_TOKENS)
    ]
    has_clock_time = time_counts["datetime_with_clock"] > 0
    has_zero_catch = catch_counts["zero"] > 0
    duration_completeness = {}
    for field in duration_fields:
        values = [row.get(field) for row in rows]
        kinds = Counter(_number_kind(value) for value in values)
        duration_completeness[field] = {
            "present": len(rows) - kinds["missing"],
            "missing": kinds["missing"],
            "positive": kinds["positive"],
            "invalid_or_nonpositive": len(rows) - kinds["positive"] - kinds["missing"],
        }
    complete_positive_duration = bool(rows) and any(
        counts["missing"] == 0 and counts["positive"] == len(rows)
        for counts in duration_completeness.values()
    )
    complete_positive_people = bool(rows) and people_counts["positive"] == len(rows)
    has_reported_zero_with_effort = has_zero_catch and complete_positive_duration and complete_positive_people
    supports_hourly_effort = has_clock_time and has_reported_zero_with_effort
    return {
        "schema_version": 1,
        "source_kind": "iOcean_fishing_report_export",
        "record_rows": len(rows),
        "fieldnames": headers,
        "required_field_completeness": completeness,
        "fishing_time_value_kinds": dict(sorted(time_counts.items())),
        "people_count_value_kinds": dict(sorted(people_counts.items())),
        "fishing_count_value_kinds": dict(sorted(catch_counts.items())),
        "nonblank_report_ids": len(ids),
        "unique_report_ids": len(id_counts),
        "report_ids_repeated_across_species_rows": sum(count > 1 for count in id_counts.values()),
        "candidate_effort_duration_fields": duration_fields,
        "duration_field_completeness": duration_completeness,
        "has_datetime_with_clock": has_clock_time,
        "has_explicit_zero_catch_rows": has_zero_catch,
        "has_reported_zero_catch_with_complete_effort": has_reported_zero_with_effort,
        "has_fields_for_person_hour_cpue_screen": has_reported_zero_with_effort,
        "has_fields_for_hourly_effort_screen": supports_hourly_effort,
        "interpretation": "schema_audit_only_not_cpue_or_fish_condition_score",
        "limitations": [
            "Blank Fishing_Count is not a zero-catch record.",
            "A report ID repeated across species rows is not assumed to be a duplicate trip.",
            "People_Count alone is not angler-hour effort.",
        ],
    }


def audit_csv(path: Path) -> dict:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        result = audit_rows(reader.fieldnames, rows)
    raw = path.read_bytes()
    result["source_filename"] = path.name
    result["source_size_bytes"] = len(raw)
    result["source_sha256"] = hashlib.sha256(raw).hexdigest()
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="Downloaded iOcean CSV export")
    parser.add_argument("--out", type=Path, required=True, help="Write schema audit JSON")
    args = parser.parse_args()
    result = audit_csv(args.input)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"Audited {result['record_rows']} iOcean rows; "
        f"clock_times={result['fishing_time_value_kinds'].get('datetime_with_clock', 0)}, "
        f"explicit_zero_catch={result['fishing_count_value_kinds'].get('zero', 0)}, "
        f"person_hour_effort_fields_present={result['has_fields_for_person_hour_cpue_screen']}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
