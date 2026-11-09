#!/usr/bin/env python3
"""Compare CWA high/low tide forecasts with nearby CWA tide observations.

Only explicitly paired station/location combinations are evaluated. Observed
TideHeight is metres relative to TWVD2001; forecast AboveTWVD is cm for mainland stations.
Hourly observed local extrema are matched to forecast events within a stated
time tolerance. This is a limited diagnostic, not a complete forecast score.
"""
from __future__ import annotations
import argparse, csv, json, math
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import median, mean

REGIONS = {
    "yilan_suao": "宜蘭、蘇澳",
    "hualien_north": "花蓮北段",
    "hualien_south": "花蓮南段",
    "fengbin_shitiping": "豐濱、石梯坪",
    "chenggong_donghe": "成功、東河",
    "taitung_south": "台東南段",
}

def read_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))

def num(value):
    try:
        if value is None or str(value).strip().lower() in {"", "none", "null", "nan", "n/a"}:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None

def parse_time(value):
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None

def tide_kind(value):
    value = (value or "").strip()
    if value in {"滿潮", "高潮"}:
        return "high"
    if value in {"乾潮", "低潮"}:
        return "low"
    return None

def find_observed_extrema(rows):
    points = []
    for row in rows:
        t = parse_time(row.get("valid_time"))
        h = num(row.get("TideHeight"))
        if t is not None and h is not None:
            points.append((t, h))
    points.sort(key=lambda x: x[0])
    extrema = []
    for i in range(1, len(points) - 1):
        prev_h, h, next_h = points[i - 1][1], points[i][1], points[i + 1][1]
        if h >= prev_h and h >= next_h and (h > prev_h or h > next_h):
            extrema.append({"time": points[i][0], "height_m": h, "kind": "high"})
        elif h <= prev_h and h <= next_h and (h < prev_h or h < next_h):
            extrema.append({"time": points[i][0], "height_m": h, "kind": "low"})
    intervals = [
        (points[i][0] - points[i - 1][0]).total_seconds() / 60
        for i in range(1, len(points))
        if points[i][0] > points[i - 1][0]
    ]
    sampling_minutes = median(intervals) if intervals else None
    return points, extrema, sampling_minutes

def match_events(forecasts, extrema, max_delta_minutes):
    """Match only forecasts issued strictly before their target tide event."""
    candidates = []
    for fi, forecast in enumerate(forecasts):
        ft = parse_time(forecast.get("valid_time"))
        issue_raw = (
            forecast.get("forecast_fetched_at_utc")
            or forecast.get("fetched_at_utc")
            or forecast.get("collected_at")
        )
        issue = parse_time(issue_raw)
        kind = tide_kind(forecast.get("tide"))
        height_cm = num(forecast.get("height_above_twvd_cm"))
        if ft is None or issue is None or kind is None or height_cm is None:
            continue
        lead_hours = (ft - issue).total_seconds() / 3600
        # A forecast issued at/after its target event is not a forecast skill sample.
        if lead_hours <= 0:
            continue
        for oi, observed in enumerate(extrema):
            if observed["kind"] != kind:
                continue
            delta = (observed["time"] - ft).total_seconds() / 60
            if abs(delta) <= max_delta_minutes:
                candidates.append((abs(delta), fi, oi, delta, height_cm / 100.0, issue, lead_hours))
    candidates.sort(key=lambda x: x[0])
    used_f, used_o, matches = set(), set(), []
    for abs_delta, fi, oi, delta, forecast_m, issue, lead_hours in candidates:
        if fi in used_f or oi in used_o:
            continue
        used_f.add(fi)
        used_o.add(oi)
        f, o = forecasts[fi], extrema[oi]
        error = o["height_m"] - forecast_m
        matches.append({
            "forecast_issue_time_utc": issue.isoformat(),
            "forecast_time": f["valid_time"],
            "lead_time_hours": round(lead_hours, 2),
            "observed_extremum_time": o["time"].isoformat(),
            "tide_type": f["tide"],
            "forecast_above_twvd_m": round(forecast_m, 3),
            "observed_tide_height_m": round(o["height_m"], 3),
            "height_error_observed_minus_forecast_m": round(error, 3),
            "absolute_height_error_m": round(abs(error), 3),
            "timing_error_observed_minus_forecast_minutes": round(delta, 1),
            "absolute_timing_error_minutes": round(abs_delta, 1),
        })
    return matches

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--observations", required=True)
    p.add_argument("--forecasts", required=True)
    p.add_argument("--pairing", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--max-delta-minutes", type=int, default=120)
    a = p.parse_args()
    if a.max_delta_minutes < 0:
        raise SystemExit("max-delta-minutes must be non-negative.")
    observations = read_csv(a.observations)
    forecasts = read_csv(a.forecasts)
    pairings = read_csv(a.pairing)
    if not observations or not forecasts or not pairings:
        raise SystemExit("Observation, forecast and pairing inputs must all be non-empty.")

    obs_by_station = defaultdict(list)
    forecast_by_location = defaultdict(list)
    for row in observations:
        obs_by_station[row.get("station_id", "")].append(row)
    for row in forecasts:
        forecast_by_location[row.get("location_id", "")].append(row)

    match_rows, station_summaries = [], []
    seen_stations, seen_locations = set(), set()
    for pair in pairings:
        if pair.get("matching_status") != "matched":
            continue
        sid, lid = pair["station_id"], pair["location_id"]
        distance = num(pair.get("distance_m"))
        if not sid or not lid or pair.get("region_id") not in REGIONS or distance is None or distance > 500 or pair.get("comparison_datum") != "TWVD2001":
            raise SystemExit(f"Invalid matched station/location pair: {sid}/{lid}; matched pairs require a valid region, TWVD2001 datum and distance <= 500 m.")
        if sid in seen_stations or lid in seen_locations:
            raise SystemExit(f"Duplicate matched station or forecast location pair: {sid}/{lid}")
        seen_stations.add(sid)
        seen_locations.add(lid)
        obs_rows = obs_by_station.get(sid, [])
        forecast_rows = forecast_by_location.get(lid, [])
        points, extrema, sampling_minutes = find_observed_extrema(obs_rows)
        if not points:
            station_summaries.append({
                "station_id": sid, "location_id": lid, "region_id": pair["region_id"],
                "status": "no_observed_tide_height", "observation_count": 0,
                "forecast_events_in_observation_window": 0, "matched_events": 0,
            })
            continue
        start, end = points[0][0], points[-1][0]
        window_forecasts = [
            f for f in forecast_rows
            if (parse_time(f.get("valid_time")) is not None
                and start <= parse_time(f["valid_time"]) <= end)
        ]
        issue_times = [
            parse_time(f.get("forecast_fetched_at_utc") or f.get("fetched_at_utc") or f.get("collected_at"))
            for f in window_forecasts
        ]
        missing_issue_time_count = sum(issue is None for issue in issue_times)
        issued_after_target_count = sum(
            1 for f, issue in zip(window_forecasts, issue_times)
            if issue is not None and parse_time(f.get("valid_time")) is not None
            and issue >= parse_time(f.get("valid_time"))
        )
        eligible_forecast_count = len(window_forecasts) - missing_issue_time_count - issued_after_target_count
        matches = match_events(window_forecasts, extrema, a.max_delta_minutes)
        for m in matches:
            m.update({
                "station_id": sid, "station_name": pair["station_name"],
                "location_id": lid, "location_name": pair["location_name"],
                "region_id": pair["region_id"], "region_name": REGIONS[pair["region_id"]],
                "pair_distance_m": pair["distance_m"],
                "observation_dataset": "O-B0075-001",
                "forecast_dataset": "F-A0021-001",
                "height_datum": "TWVD2001",
            })
            match_rows.append(m)
        abs_h = [m["absolute_height_error_m"] for m in matches]
        abs_t = [m["absolute_timing_error_minutes"] for m in matches]
        station_summaries.append({
            "station_id": sid, "station_name": pair["station_name"],
            "location_id": lid, "location_name": pair["location_name"],
            "region_id": pair["region_id"], "region_name": REGIONS[pair["region_id"]],
            "pair_distance_m": int(pair["distance_m"]),
            "observation_count": len(points),
            "observation_sampling_interval_median_minutes": sampling_minutes,
            "observed_extrema_count": len(extrema),
            "forecast_events_in_observation_window": len(window_forecasts),
            "forecast_events_missing_issue_time": missing_issue_time_count,
            "forecast_events_issued_at_or_after_target": issued_after_target_count,
            "forecast_events_eligible_for_verification": eligible_forecast_count,
            "matched_events": len(matches),
            "unmatched_eligible_forecast_events": max(0, eligible_forecast_count - len(matches)),
            "mean_absolute_height_error_m": round(mean(abs_h), 3) if abs_h else None,
            "median_absolute_height_error_m": round(median(abs_h), 3) if abs_h else None,
            "mean_absolute_timing_error_minutes": round(mean(abs_t), 1) if abs_t else None,
            "median_absolute_timing_error_minutes": round(median(abs_t), 1) if abs_t else None,
            "status": "matched" if matches else "no_extrema_match_within_tolerance",
        })

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    match_fields = [
        "station_id", "station_name", "location_id", "location_name", "region_id", "region_name",
        "pair_distance_m", "forecast_issue_time_utc", "forecast_time", "lead_time_hours", "observed_extremum_time", "tide_type",
        "forecast_above_twvd_m", "observed_tide_height_m",
        "height_error_observed_minus_forecast_m", "absolute_height_error_m",
        "timing_error_observed_minus_forecast_minutes", "absolute_timing_error_minutes",
        "observation_dataset", "forecast_dataset", "height_datum",
    ]
    with out.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=match_fields)
        w.writeheader()
        w.writerows(match_rows)
    summary = {
        "observation_dataset": "O-B0075-001",
        "forecast_dataset": "F-A0021-001",
        "data_kind": "observed_vs_forecast_diagnostic",
        "height_comparison": "TideHeight metres and AboveTWVD centimetres converted to metres; both relative to TWVD2001 for mainland tide stations",
        "max_event_time_difference_minutes": a.max_delta_minutes,
        "matched_event_count": len(match_rows),
        "stations": station_summaries,
        "limitations": [
            "Only explicit station-to-location pairs are evaluated; no nearest-neighbour pairing is generated automatically.",
            "Observed extrema are detected from the sampled observations, so timing precision is limited by the observation sampling interval.",
            "Only forecast events within the observed time window are evaluated.",
            "Forecasts without a recorded issue/fetch time, or issued at/after the target event, are excluded from verification.",
            "A match within the time tolerance is a diagnostic pairing, not proof of exact forecast verification.",
            "The current rolling observation window is short and selected stations do not represent all six regions.",
            "No regional averaging, interpolation, fish activity score or catch probability is produced.",
        ],
    }
    out.with_name("tide_forecast_observation_comparison_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))

if __name__ == "__main__":
    main()
