#!/usr/bin/env python3
"""Evaluate immutable CWA tide forecast vintages against observed tide extrema.

Only explicitly paired mainland stations are evaluated. Each forecast vintage
is scored against later observed extrema; lead time is calculated from the
forecast fetch timestamp, never from the observation collection timestamp.
"""
from __future__ import annotations
import argparse, csv, json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median

REGIONS = {
    "yilan_suao": "宜蘭、蘇澳",
    "hualien_north": "花蓮北段",
    "hualien_south": "花蓮南段",
    "fengbin_shitiping": "豐濱、石梯坪",
    "chenggong_donghe": "成功、東河",
    "taitung_south": "台東南段",
}
LEAD_BUCKETS = [
    (0, 6, "00-06h"), (6, 12, "06-12h"), (12, 24, "12-24h"),
    (24, 48, "24-48h"), (48, float("inf"), "48h+"),
]

def parse_time(value):
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt
    except (TypeError, ValueError):
        return None

def number(value):
    try:
        if value is None or str(value).strip().lower() in {"", "none", "null", "nan", "n/a"}:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None

def read_jsonl(path):
    rows = []
    if not path.exists():
        return rows
    with path.open(encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise SystemExit(f"Invalid JSON in {path}:{line_no}: {exc}")
            if not isinstance(row, dict):
                raise SystemExit(f"Expected JSON object in {path}:{line_no}")
            rows.append(row)
    return rows

def lead_bucket(hours):
    for lower, upper, label in LEAD_BUCKETS:
        if lower <= hours < upper:
            return label
    return None

def observed_series(rows):
    # For corrected values at the same station/time, use the latest archived revision.
    latest = {}
    for row in rows:
        t = parse_time(row.get("valid_time"))
        h = number(row.get("TideHeight"))
        if t is None or h is None:
            continue
        key = t
        revision_time = parse_time(row.get("collected_at")) or datetime.min.replace(tzinfo=timezone.utc)
        previous = latest.get(key)
        if previous is None or revision_time >= previous[0]:
            latest[key] = (revision_time, h)
    points = sorted((t, value[1]) for t, value in latest.items())
    extrema = []
    for i in range(1, len(points) - 1):
        prev_h, h, next_h = points[i - 1][1], points[i][1], points[i + 1][1]
        if h >= prev_h and h >= next_h and (h > prev_h or h > next_h):
            extrema.append({"time": points[i][0], "height_m": h, "kind": "high"})
        elif h <= prev_h and h <= next_h and (h < prev_h or h < next_h):
            extrema.append({"time": points[i][0], "height_m": h, "kind": "low"})
    intervals = [
        (points[i][0] - points[i-1][0]).total_seconds() / 60
        for i in range(1, len(points)) if points[i][0] > points[i-1][0]
    ]
    return points, extrema, median(intervals) if intervals else None

def kind_of(value):
    value = str(value or "").strip()
    if value in {"滿潮", "高潮"}:
        return "high"
    if value in {"乾潮", "低潮"}:
        return "low"
    return None

def score_snapshot(forecasts, extrema, max_delta_minutes, pair, snapshot_id):
    candidates = []
    for fi, forecast in enumerate(forecasts):
        ft = parse_time(forecast.get("valid_time"))
        issue = parse_time(forecast.get("forecast_fetched_at_utc") or forecast.get("collected_at"))
        kind = kind_of(forecast.get("tide"))
        height_cm = number(forecast.get("height_above_twvd_cm"))
        if ft is None or issue is None or kind is None or height_cm is None:
            continue
        lead_hours = (ft - issue).total_seconds() / 3600
        # Never score a forecast issued at or after its target event.
        if lead_hours <= 0:
            continue
        bucket = lead_bucket(lead_hours)
        if bucket is None:
            continue
        for oi, observed in enumerate(extrema):
            if observed["kind"] != kind:
                continue
            delta = (observed["time"] - ft).total_seconds() / 60
            if abs(delta) <= max_delta_minutes:
                candidates.append((abs(delta), fi, oi, delta, lead_hours, bucket, height_cm / 100.0))
    candidates.sort(key=lambda x: (x[0], x[1], x[2]))
    used_f, used_o, matches = set(), set(), []
    for abs_delta, fi, oi, delta, lead_hours, bucket, forecast_m in candidates:
        if fi in used_f or oi in used_o:
            continue
        used_f.add(fi)
        used_o.add(oi)
        f, o = forecasts[fi], extrema[oi]
        error = o["height_m"] - forecast_m
        matches.append({
            "snapshot_id": snapshot_id,
            "station_id": pair["station_id"], "station_name": pair.get("station_name", ""),
            "location_id": pair["location_id"], "location_name": pair.get("location_name", ""),
            "region_id": pair["region_id"], "region_name": REGIONS[pair["region_id"]],
            "pair_distance_m": pair.get("distance_m", ""),
            "tide_type": f.get("tide"),
            "forecast_issue_time_utc": (parse_time(f.get("forecast_fetched_at_utc") or f.get("collected_at"))).isoformat(),
            "forecast_time": f["valid_time"],
            "observed_extremum_time": o["time"].isoformat(),
            "lead_time_hours": round(lead_hours, 2), "lead_time_bucket": bucket,
            "forecast_height_twvd_m": round(forecast_m, 3),
            "observed_height_twvd_m": round(o["height_m"], 3),
            "signed_height_error_observed_minus_forecast_m": round(error, 3),
            "absolute_height_error_m": round(abs(error), 3),
            "signed_timing_error_observed_minus_forecast_minutes": round(delta, 1),
            "absolute_timing_error_minutes": round(abs_delta, 1),
            "height_datum": "TWVD2001",
            "observation_dataset": "O-B0075-001", "forecast_dataset": "F-A0021-001",
        })
    return matches, len(used_f)

def aggregate(matches):
    groups = defaultdict(list)
    for row in matches:
        keys = [
            ("overall", "all", "all"),
            ("station", row["station_id"], row["lead_time_bucket"]),
            ("region", row["region_id"], row["lead_time_bucket"]),
            ("tide_type", row["tide_type"], row["lead_time_bucket"]),
            ("station_tide", row["station_id"] + "|" + row["tide_type"], row["lead_time_bucket"]),
        ]
        for dimension, entity, bucket in keys:
            groups[(dimension, entity, bucket)].append(row)
    output = []
    for (dimension, entity, bucket), rows in sorted(groups.items()):
        h = [r["absolute_height_error_m"] for r in rows]
        t = [r["absolute_timing_error_minutes"] for r in rows]
        output.append({
            "dimension": dimension, "entity": entity, "lead_time_bucket": bucket,
            "matched_event_count": len(rows),
            "mae_height_m": round(mean(h), 3),
            "median_absolute_height_error_m": round(median(h), 3),
            "mae_timing_minutes": round(mean(t), 1),
            "median_absolute_timing_error_minutes": round(median(t), 1),
            "first_forecast_time": min(r["forecast_time"] for r in rows),
            "last_forecast_time": max(r["forecast_time"] for r in rows),
        })
    return output

def write_csv(path, rows, fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--history-dir", required=True)
    p.add_argument("--out-dir", required=True)
    p.add_argument("--max-delta-minutes", type=int, default=120)
    a = p.parse_args()
    if a.max_delta_minutes < 0:
        raise SystemExit("max-delta-minutes must be non-negative.")
    root = Path(a.history_dir)
    observations = read_jsonl(root / "observed_tides.jsonl")
    forecasts = read_jsonl(root / "forecast_vintages.jsonl")
    if not observations or not forecasts:
        raise SystemExit("Historical observations and forecast vintages must both be non-empty.")

    pair_path = Path(__file__).resolve().parents[1] / "stations" / "cwa_tide_observation_forecast_pairing.csv"
    with pair_path.open(encoding="utf-8-sig", newline="") as f:
        pairings = list(csv.DictReader(f))
    pairs = [r for r in pairings if r.get("matching_status") == "matched"]
    obs_by_station = defaultdict(list)
    forecasts_by_snapshot_location = defaultdict(list)
    for row in observations:
        obs_by_station[row.get("station_id", "")].append(row)
    for row in forecasts:
        forecasts_by_snapshot_location[(row.get("snapshot_id", ""), row.get("location_id", ""))].append(row)

    all_matches, coverage = [], []
    for pair in pairs:
        distance = number(pair.get("distance_m"))
        if (pair.get("region_id") not in REGIONS or distance is None or distance > 500
                or pair.get("comparison_datum") != "TWVD2001"):
            raise SystemExit(f"Invalid matched station/location pair: {pair}")
        points, extrema, sampling = observed_series(obs_by_station.get(pair["station_id"], []))
        if not points:
            coverage.append({"station_id": pair["station_id"], "status": "no_observations",
                             "observation_samples": 0, "observed_extrema": 0,
                             "forecast_vintages_seen": 0, "matched_events": 0})
            continue
        snapshot_ids = sorted({
            snapshot for snapshot, location in forecasts_by_snapshot_location
            if location == pair["location_id"]
        })
        station_matches = []
        candidate_count = 0
        for snapshot_id in snapshot_ids:
            rows = forecasts_by_snapshot_location[(snapshot_id, pair["location_id"])]
            # Only evaluate events whose target time is within the observed series coverage.
            rows = [r for r in rows if (parse_time(r.get("valid_time")) is not None
                    and points[0][0] <= parse_time(r["valid_time"]) <= points[-1][0])]
            candidate_count += len(rows)
            matches, _ = score_snapshot(rows, extrema, a.max_delta_minutes, pair, snapshot_id)
            station_matches.extend(matches)
        all_matches.extend(station_matches)
        coverage.append({
            "station_id": pair["station_id"], "station_name": pair.get("station_name", ""),
            "location_id": pair["location_id"], "region_id": pair["region_id"],
            "pair_distance_m": int(distance), "status": "matched" if station_matches else "no_verified_event_yet",
            "observation_samples": len(points), "median_sampling_interval_minutes": sampling,
            "observed_extrema": len(extrema), "forecast_vintages_seen": len(snapshot_ids),
            "forecast_events_in_observation_window": candidate_count,
            "matched_events": len(station_matches),
        })

    summaries = aggregate(all_matches)
    out = Path(a.out_dir)
    event_fields = [
        "snapshot_id", "station_id", "station_name", "location_id", "location_name",
        "region_id", "region_name", "pair_distance_m", "tide_type",
        "forecast_issue_time_utc", "forecast_time", "observed_extremum_time",
        "lead_time_hours", "lead_time_bucket", "forecast_height_twvd_m",
        "observed_height_twvd_m", "signed_height_error_observed_minus_forecast_m",
        "absolute_height_error_m", "signed_timing_error_observed_minus_forecast_minutes",
        "absolute_timing_error_minutes", "height_datum", "observation_dataset", "forecast_dataset",
    ]
    summary_fields = [
        "dimension", "entity", "lead_time_bucket", "matched_event_count", "mae_height_m",
        "median_absolute_height_error_m", "mae_timing_minutes",
        "median_absolute_timing_error_minutes", "first_forecast_time", "last_forecast_time",
    ]
    write_csv(out / "event_matches.csv", all_matches, event_fields)
    write_csv(out / "accuracy_by_lead.csv", summaries, summary_fields)
    result = {
        "schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_kind": "historical_forecast_verification",
        "observation_dataset": "O-B0075-001", "forecast_dataset": "F-A0021-001",
        "height_datum": "TWVD2001",
        "observation_history_records": len(observations),
        "forecast_vintage_records": len(forecasts),
        "forecast_snapshot_count": len({r.get("snapshot_id") for r in forecasts}),
        "matched_event_count": len(all_matches),
        "station_coverage": coverage,
        "accuracy_groups": summaries,
        "limitations": [
            "Only the six explicitly paired mainland station/location pairs are evaluated.",
            "Observed extrema are derived from sampled hourly/irregular observations; timing precision is limited by actual sample spacing.",
            "Forecast issue time comes from the recorded CWA fetch timestamp. Forecasts issued at or after the target event are excluded.",
            "Each forecast vintage is a separate lead-time sample; the same observed extremum may verify multiple vintages by design.",
            "Only forecast events inside the observed history time range are eligible; future forecasts remain unverified until observations arrive.",
            "MAE is descriptive and must not be treated as a calibrated confidence score until sample counts and multi-day coverage are sufficient.",
            "No interpolation, regional averaging, fish activity score, or catch probability is generated.",
        ],
        "interpretation": "Insufficient evidence" if len(all_matches) < 30 else "Preliminary; review sample coverage before use",
    }
    (out / "analysis_summary.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "observation_history_records": len(observations),
        "forecast_vintage_records": len(forecasts),
        "forecast_snapshot_count": result["forecast_snapshot_count"],
        "matched_event_count": len(all_matches),
        "interpretation": result["interpretation"],
        "output_dir": str(out),
    }, ensure_ascii=False))

if __name__ == "__main__":
    main()
