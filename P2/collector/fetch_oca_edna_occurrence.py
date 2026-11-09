#!/usr/bin/env python3
"""Fetch OCA fish-eDNA detections and preserve them as occurrence context only.

Positive eDNA detections are not fish counts, biomass, fishing catch, hourly activity,
or proof of absence when a taxon is not detected. Regional assignment is nearest-station
context only and is never presented as the exact sampling station's fishing region.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import re
import sys
import urllib.request
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

DATASET_PAGE = "https://data.gov.tw/dataset/172487"
SOURCES = [
    ("oca_edna_diving_110_113", "110-113年潛水調查魚類eDNA", "https://iocean.oca.gov.tw/oca_datahub/WebService/GetData.ashx?id=27b6c7d6-62cd-465e-b429-a5e010f7f7d8"),
    ("oca_edna_vessel_110_112", "110-112年船舶調查魚類eDNA", "https://iocean.oca.gov.tw/oca_datahub/WebService/GetData.ashx?id=3091c6ca-8fb7-4fbb-bd47-c325d7db5072"),
    ("oca_edna_mpa_110_113", "110-113年保護區站點魚類eDNA", "https://iocean.oca.gov.tw/oca_datahub/WebService/GetData.ashx?id=763b4982-caa0-4cd6-8f9c-e3ee645ec736"),
]
REGIONS = {"yilan_suao", "hualien_north", "hualien_south", "fengbin_shitiping", "chenggong_donghe", "taitung_south"}
ALIASES = {
    "station_name": ("站點名稱", "站點", "station_name", "station"),
    "latitude": ("緯度(北緯)", "緯度", "latitude", "lat"),
    "longitude": ("經度(東經)", "經度", "longitude", "lon", "lng"),
    "depth_m": ("深度(m)", "深度", "depth_m", "depth"),
    "sampled_at": ("採樣時間", "採樣日期", "sample_time", "sampling_time", "date"),
    "scientific_name": ("學名(Science Name)", "學名", "scientific_name", "science_name", "species"),
    "common_name_zh": ("中文學名", "中文名", "common_name_zh", "chinese_name"),
    "family_scientific": ("科別(Family)", "科別", "family", "family_scientific"),
    "family_zh": ("中文科別", "科中文名", "family_zh"),
    "project_type": ("所屬計畫類別", "計畫類別", "project_type", "project"),
}

def keynorm(value: str) -> str:
    return re.sub(r"[\s_\-（）()：:／/]+", "", str(value or "")).casefold()

def numeric(value):
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if not text or text.lower() in {"na", "n/a", "null", "none", "-", "未提供"}:
        return None
    try:
        number = float(text)
        return number if math.isfinite(number) else None
    except ValueError:
        return None

def parse_year_month(value: str) -> str:
    text = str(value or "").strip()
    match = re.search(r"(?<!\d)(\d{3,4})[-/.年](\d{1,2})", text)
    if not match:
        return ""
    year, month = int(match.group(1)), int(match.group(2))
    if year < 1000:
        year += 1911
    return f"{year:04d}-{month:02d}" if 1 <= month <= 12 else ""

def extract_dict_rows(value):
    if isinstance(value, list):
        if value and all(isinstance(x, dict) for x in value):
            return value
        for item in value:
            found = extract_dict_rows(item)
            if found:
                return found
    elif isinstance(value, dict):
        for key in ("data", "Data", "result", "results", "records", "items", "value"):
            if key in value:
                found = extract_dict_rows(value[key])
                if found:
                    return found
        for item in value.values():
            found = extract_dict_rows(item)
            if found:
                return found
    return []

def decode_text(payload: bytes) -> str:
    for encoding in ("utf-8-sig", "cp950", "big5"):
        try:
            return payload.decode(encoding)
        except UnicodeDecodeError:
            pass
    raise ValueError("response is neither UTF-8 nor Big5 text")

def parse_payload(payload: bytes):
    """Parse CSV, JSON, or a ZIP containing CSV/JSON files."""
    if payload.startswith(b"PK\x03\x04"):
        all_rows = []
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            for name in archive.namelist():
                if name.lower().endswith((".csv", ".json")):
                    all_rows.extend(parse_payload(archive.read(name)))
        return all_rows
    text = decode_text(payload).strip()
    if not text:
        raise ValueError("empty source payload")
    if text.startswith("{") or text.startswith("["):
        rows = extract_dict_rows(json.loads(text))
        if not rows:
            raise ValueError("JSON response contains no record array")
        return rows
    rows = list(csv.DictReader(io.StringIO(text)))
    if not rows or not any(any(str(v or "").strip() for v in row.values()) for row in rows):
        raise ValueError("CSV response contains no data rows")
    return rows

def normalize_fields(row):
    normalized = {keynorm(k): v for k, v in row.items()}
    result = {}
    for field, aliases in ALIASES.items():
        result[field] = ""
        for alias in aliases:
            found = normalized.get(keynorm(alias))
            if found is not None and str(found).strip():
                result[field] = str(found).strip()
                break
    return result

def haversine_km(lat1, lon1, lat2, lon2):
    radius = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2-lat1), math.radians(lon2-lon1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2*radius*math.asin(math.sqrt(a))

def load_region_stations(path: Path):
    stations = []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            region = (row.get("region_id") or "").strip()
            if region not in REGIONS or str(row.get("station_status", "")).strip() not in {"1", "active", "true"}:
                continue
            lat, lon = numeric(row.get("latitude")), numeric(row.get("longitude"))
            if lat is not None and lon is not None:
                stations.append({"station_id": row.get("station_id", ""), "region_id": region, "lat": lat, "lon": lon})
    if not stations:
        raise ValueError("no active six-region reference stations found")
    return stations

def nearest_region_context(lat, lon, stations, max_distance_km=35.0):
    if lat is None or lon is None:
        return "", "", None, "coordinates_missing"
    nearest = min(stations, key=lambda s: haversine_km(lat, lon, s["lat"], s["lon"]))
    distance = haversine_km(lat, lon, nearest["lat"], nearest["lon"])
    if distance > max_distance_km:
        return "", nearest["station_id"], round(distance, 3), "outside_six_region_reference_radius"
    return nearest["region_id"], nearest["station_id"], round(distance, 3), "nearest_station_context_only"

def candidate_index(path: Path):
    result = {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            sci = (row.get("scientific_name") or "").strip().casefold()
            cid = (row.get("candidate_id") or "").strip()
            if sci and cid and "spp." not in sci and "待確認" not in sci:
                result[sci] = cid
    return result

def match_candidate(scientific_name: str, candidates):
    """Exact binomials may map; slash-delimited multi-species labels stay ambiguous."""
    scientific = str(scientific_name or "").strip().casefold()
    if scientific in candidates:
        return candidates[scientific], "exact_scientific_name", ""
    if "/" in scientific:
        parts = [part.strip() for part in scientific.split("/") if part.strip()]
        if parts:
            genus = parts[0].split()[0]
            expanded = [parts[0]] + [part if " " in part else genus + " " + part for part in parts[1:]]
            possible = sorted({candidates[name] for name in expanded if name in candidates})
            if possible:
                return "", "ambiguous_multi_species_taxon", ";".join(possible)
    return "", "no_exact_candidate_match", ""

def fetch_source(url: str, timeout: int):
    request = urllib.request.Request(url, headers={"User-Agent": "fishing-intelligence/1.0 (open-data research)", "Accept": "*/*"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()

def collect(sources, stations, candidates, fetched_at):
    detections, seen = [], set()
    for dataset_id, dataset_name, url, rows in sources:
        for source_row in rows:
            fields = normalize_fields(source_row)
            scientific = fields["scientific_name"].strip()
            if not scientific:
                continue
            lat, lon, depth = numeric(fields["latitude"]), numeric(fields["longitude"]), numeric(fields["depth_m"])
            region, nearest_station, distance, mapping_status = nearest_region_context(lat, lon, stations)
            sample_time = fields["sampled_at"].strip()
            basis = parse_year_month(sample_time)
            candidate_id, candidate_match_status, possible_candidate_ids = match_candidate(scientific, candidates)
            identity = "|".join((dataset_id, fields["station_name"], sample_time, scientific, str(depth), str(lat), str(lon)))
            record_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]
            if record_id in seen:
                continue
            seen.add(record_id)
            detections.append({
                "record_id": record_id,
                "dataset_id": dataset_id,
                "dataset_name": dataset_name,
                "dataset_page": DATASET_PAGE,
                "source_url": url,
                "fetched_at_utc": fetched_at,
                "station_name": fields["station_name"],
                "latitude": lat,
                "longitude": lon,
                "depth_m": depth,
                "sampled_at": sample_time,
                "year_month": basis,
                "scientific_name": scientific,
                "common_name_zh": fields["common_name_zh"],
                "family_scientific": fields["family_scientific"],
                "family_zh": fields["family_zh"],
                "project_type": fields["project_type"],
                "candidate_id": candidate_id,
                "candidate_match_status": candidate_match_status,
                "possible_candidate_ids": possible_candidate_ids,
                "region_id": region,
                "nearest_reference_station_id": nearest_station,
                "nearest_reference_distance_km": distance,
                "region_mapping_status": mapping_status,
                "detection_type": "positive_edna_detection_record",
                "model_use_status": "context_only_edna_occurrence",
                "limitations": "eDNA positive detection is not an individual fish count, biomass, catch rate, hourly activity, or proof of absence when not detected; nearest-region mapping is contextual only.",
            })
    return detections

def build_monthly_summary(detections):
    groups = defaultdict(list)
    for row in detections:
        if row["candidate_id"] and row["year_month"]:
            groups[(row["candidate_id"], row["scientific_name"], row["region_id"], row["year_month"])].append(row)
    output = []
    for (cid, scientific, region, year_month), rows in sorted(groups.items()):
        depths = [r["depth_m"] for r in rows if r["depth_m"] is not None]
        output.append({
            "candidate_id": cid,
            "scientific_name": scientific,
            "region_id": region,
            "year_month": year_month,
            "positive_detection_record_count": len(rows),
            "distinct_station_count": len({r["station_name"] for r in rows if r["station_name"]}),
            "min_sample_depth_m": min(depths) if depths else "",
            "max_sample_depth_m": max(depths) if depths else "",
            "dataset_ids": ";".join(sorted({r["dataset_id"] for r in rows})),
            "model_use_status": "context_only_edna_occurrence",
            "interpretation_limit": "Positive detection records only; not abundance, effort-standardized prevalence, catch, activity, or absence evidence.",
        })
    return output

def build_candidate_region_context(detections):
    """Compact historical positive-detection context; never an activity or abundance score."""
    grouped = defaultdict(list)
    for row in detections:
        region = row.get("region_id", "")
        if region not in REGIONS:
            continue
        if row.get("candidate_id"):
            grouped[(row["candidate_id"], region, "exact")].append(row)
        for cid in filter(None, (row.get("possible_candidate_ids") or "").split(";")):
            grouped[(cid, region, "ambiguous")].append(row)
    merged = {}
    for (cid, region, kind), rows in sorted(grouped.items()):
        key = (cid, region)
        if key not in merged:
            merged[key] = {
                "candidate_id": cid, "region_id": region,
                "exact_positive_detection_record_count": 0,
                "ambiguous_positive_detection_record_count": 0,
                "exact_sample_month_count": 0, "exact_distinct_station_count": 0,
                "first_sampled_month": "", "last_sampled_month": "",
                "min_sample_depth_m": None, "max_sample_depth_m": None,
                "dataset_ids": set(), "ambiguous_taxon_labels": set(),
                "model_use_status": "context_only_edna_occurrence",
            }
        target = merged[key]
        target["dataset_ids"].update(r["dataset_id"] for r in rows)
        if kind == "exact":
            target["exact_positive_detection_record_count"] += len(rows)
            months = sorted({r["year_month"] for r in rows if r.get("year_month")})
            stations = {r["station_name"] for r in rows if r.get("station_name")}
            depths = [r["depth_m"] for r in rows if r.get("depth_m") is not None]
            target["exact_sample_month_count"] = len(months)
            target["exact_distinct_station_count"] = len(stations)
            target["first_sampled_month"] = months[0] if months else ""
            target["last_sampled_month"] = months[-1] if months else ""
            target["min_sample_depth_m"] = min(depths) if depths else None
            target["max_sample_depth_m"] = max(depths) if depths else None
        else:
            target["ambiguous_positive_detection_record_count"] += len(rows)
            target["ambiguous_taxon_labels"].update(r["scientific_name"] for r in rows)
    result = []
    for row in merged.values():
        row["dataset_ids"] = sorted(row["dataset_ids"])
        row["ambiguous_taxon_labels"] = sorted(row["ambiguous_taxon_labels"])
        result.append(row)
    return sorted(result, key=lambda x: (x["region_id"], x["candidate_id"]))


def write_outputs(out_dir: Path, detections, summary, region_context, fetched_at, reference_regions=None):
    out_dir.mkdir(parents=True, exist_ok=True)
    active_regions = sorted(set(reference_regions or ()))
    coverage = {
        "region_ids": sorted(REGIONS),
        "active_reference_regions": active_regions,
        "regions_without_active_reference_stations": sorted(REGIONS - set(active_regions)),
        "assignment_method": "nearest_active_reference_station_within_35km",
        "interpretation": "Nearest-station region is geographic context only; it is not proof that the sample belongs to a fishing spot or that every region has equal reference coverage.",
    }
    with (out_dir / "edna_occurrence_context.jsonl").open("w", encoding="utf-8", newline="") as handle:
        for row in detections:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    fields = ["candidate_id", "scientific_name", "region_id", "year_month", "positive_detection_record_count", "distinct_station_count", "min_sample_depth_m", "max_sample_depth_m", "dataset_ids", "model_use_status", "interpretation_limit"]
    with (out_dir / "edna_species_monthly_summary.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(summary)
    manifest = {
        "schema_version": 1,
        "source": "OCA 110-113 Taiwan adjacent waters fish eDNA survey",
        "dataset_page": DATASET_PAGE,
        "generated_at_utc": fetched_at,
        "detection_record_count": len(detections),
        "exact_candidate_record_count": sum(bool(r["candidate_id"]) for r in detections),
        "ambiguous_taxon_record_count": sum(r["candidate_match_status"] == "ambiguous_multi_species_taxon" for r in detections),
        "unmatched_taxon_record_count": sum(r["candidate_match_status"] == "no_exact_candidate_match" for r in detections),
        "nearest_region_context_record_count": sum(r["region_mapping_status"] == "nearest_station_context_only" for r in detections),
        "candidate_month_region_summary_count": len(summary),
        "candidate_region_context_count": len(region_context),
        "regional_reference_coverage": coverage,
        "interpretation": "Positive eDNA detections provide occurrence context only. They do not measure fish abundance, catch rate, fishing activity, or absence.",
        "source_datasets": [{"dataset_id": x[0], "name": x[1], "url": x[2]} for x in SOURCES],
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    context_payload = {
        "schema_version": 1,
        "source": "OCA 110-113 Taiwan adjacent waters fish eDNA survey",
        "dataset_page": DATASET_PAGE,
        "generated_at_utc": fetched_at,
        "regional_reference_coverage": coverage,
        "interpretation": "Historical positive eDNA occurrence context only; not abundance, current presence, catch rate, activity, or absence.",
        "records": region_context,
    }
    (out_dir / "edna_candidate_region_context.json").write_text(
        json.dumps(context_payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8"
    )
    return manifest

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mapping", type=Path, required=True)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=int, default=45)
    args = parser.parse_args()
    stations, candidates = load_region_stations(args.mapping), candidate_index(args.candidates)
    fetched_at = datetime.now(timezone.utc).isoformat()
    source_rows = []
    for dataset_id, name, url in SOURCES:
        payload = fetch_source(url, args.timeout_seconds)
        source_rows.append((dataset_id, name, url, parse_payload(payload)))
    detections = collect(source_rows, stations, candidates, fetched_at)
    if not detections:
        raise SystemExit("No normalized eDNA detections found; refusing to publish an empty dataset.")
    summary = build_monthly_summary(detections)
    region_context = build_candidate_region_context(detections)
    manifest = write_outputs(args.out_dir, detections, summary, region_context, fetched_at, reference_regions={s['region_id'] for s in stations})
    print(
        f"eDNA occurrence context built: {len(detections)} positive records; "
        f"{manifest['exact_candidate_record_count']} exact-candidate records; "
        f"{manifest['ambiguous_taxon_record_count']} ambiguous multi-species records; "
        f"{len(summary)} candidate/month/region summaries; "
        f"{len(region_context)} compact candidate-region context rows."
    )
    print("All records remain context_only_edna_occurrence; no activity/catch scores are produced.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
