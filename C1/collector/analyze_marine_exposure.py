#!/usr/bin/env python3
"""Evidence-gated CWA marine exposure assessment for six East Taiwan planning regions.

This is an internal screening aid, not an official marine warning, forecast,
shoreline-specific assessment, or permission to fish. It deliberately avoids
inferring tide direction, wave run-up, or fish activity from point observations.
"""
from __future__ import annotations
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

REGIONS = (
    "yilan_suao", "hualien_north", "hualien_south",
    "fengbin_shitiping", "chenggong_donghe", "taitung_south",
)
# Internal screening bands only. They are not official CWA warning thresholds.
BANDS = {
    "wave_height_m": [
        (1.0, "low", "低"), (1.5, "moderate", "中"), (2.5, "high", "高"),
        (float("inf"), "very_high", "極高"),
    ],
    "wind_speed_ms": [
        (5.0, "low", "低"), (8.0, "moderate", "中"), (11.0, "high", "高"),
        (float("inf"), "very_high", "極高"),
    ],
}
LEVEL_RANK = {"low": 0, "moderate": 1, "high": 2, "very_high": 3}


def parse_time(value):
    if not isinstance(value, str):
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return result if result.tzinfo else None
    except ValueError:
        return None


def finite_number(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and abs(number) != float("inf") else None


def classify(value, bands):
    if value is None:
        return None
    for upper, code, label in bands:
        if value < upper:
            return {"level": code, "label": label}
    return None


def assess_region(region_id, region, generated_at, now, stale_after_minutes=180):
    observed = region.get("observed_48h") or {}
    history = region.get("observed_30d") or {}
    latest_at = parse_time(observed.get("latest_observation_time"))
    age_minutes = None if latest_at is None else round((now - latest_at).total_seconds() / 60, 1)
    freshness = "missing_time"
    if age_minutes is not None:
        if age_minutes < -15:
            freshness = "future_timestamp"
        elif age_minutes <= stale_after_minutes:
            freshness = "fresh"
        else:
            freshness = "stale"

    values = observed.get("latest_values") or {}
    wave = finite_number(values.get("wave_height_m"))
    wind = finite_number(values.get("wind_speed_ms"))
    period = finite_number(values.get("wave_period_s"))
    tide = finite_number(values.get("tide_height_m"))
    current = finite_number(values.get("current_speed_ms"))
    factors = []
    for key, value, unit in (
        ("wave_height_m", wave, "m"),
        ("wind_speed_ms", wind, "m/s"),
    ):
        band = classify(value, BANDS[key])
        if band:
            factors.append({
                "factor": key, "value": value, "unit": unit,
                "level": band["level"], "label": band["label"],
                "basis": "internal_screening_band_not_official_warning",
            })

    coverage = observed.get("variable_coverage") or {}
    coverage_ratios = []
    for key in ("wave_height_m", "wind_speed_ms"):
        item = coverage.get(key) or {}
        ratio = finite_number(item.get("coverage_ratio"))
        if ratio is not None:
            coverage_ratios.append(ratio)
    coverage_ratio = round(sum(coverage_ratios) / len(coverage_ratios), 3) if coverage_ratios else None

    if freshness != "fresh":
        state = "insufficient_data"
        level = "unknown"
        reason = "最新觀測時間缺失、超前或已逾時，不能當作目前海況。"
    elif not factors:
        state = "insufficient_data"
        level = "unknown"
        reason = "目前沒有可用的浪高或風速觀測，不能推定海況平穩。"
    else:
        level = max((item["level"] for item in factors), key=lambda x: LEVEL_RANK[x])
        state = "assessed"
        reason = "依目前可用的浪高與風速觀測，提供環境暴露篩檢；不是安全判定。"

    if observed.get("coverage_status") == "no_cwa_station_coverage":
        state, level = "insufficient_data", "unknown"
        reason = "此區沒有映射的中央氣象署測站，不以鄰區資料代替。"

    return {
        "region_id": region_id,
        "region_name": region.get("region_name", region_id),
        "state": state,
        "exposure_level": level,
        "exposure_label": {"low": "低", "moderate": "中", "high": "高", "very_high": "極高", "unknown": "無法判定"}[level],
        "freshness": freshness,
        "latest_observation_time": observed.get("latest_observation_time"),
        "observation_age_minutes": age_minutes,
        "stale_after_minutes": stale_after_minutes,
        "station_count": observed.get("stations_with_observations", 0),
        "mapped_station_count": observed.get("mapped_station_count", 0),
        "exposure_variable_coverage_ratio": coverage_ratio,
        "factors": factors,
        "other_observations": {
            "wave_period_s": period,
            "tide_height_m": tide,
            "current_speed_ms": current,
            "wave_direction_deg": finite_number(values.get("wave_direction_deg")),
            "wind_direction_deg": finite_number(values.get("wind_direction_deg")),
        },
        "historical_window": {
            "latest_observation_time": history.get("latest_observation_time"),
            "data_kind": history.get("data_kind", "observed"),
            "latest_values": history.get("latest_values") or {},
            "use_limit": "30天資料中的最新觀測快照，不是30天平均、分布或氣候常態；不計算異常值或趨勢。",
        },
        "reason": reason,
        "limitations": [
            "浪高與風速級別是本專案內部環境暴露篩檢門檻，不是中央氣象署警戒標準。",
            "測站區域平均不代表個別岸際釣點；地形、湧浪、離岸流及浪襲仍須現場判斷。",
            "浪向與風向僅呈現原始方向角；未建立各釣點岸線方位前，不推斷迎岸或背風。",
            "單一潮位高度不能判定漲潮或退潮；需要連續同站時間序列及基準一致性。",
            "本分析不推論魚種活性、中魚率，也不提供安全許可。",
        ],
        "safety_clearance": False,
    }


def build_assessment(snapshot, now, stale_after_minutes=180):
    if snapshot.get("schema_version") != 1 or snapshot.get("source") != "CWA":
        raise ValueError("Unsupported regional marine snapshot schema/source")
    regions = snapshot.get("regions")
    if not isinstance(regions, dict):
        raise ValueError("Snapshot regions must be an object")
    missing = sorted(set(REGIONS) - set(regions))
    if missing:
        raise ValueError("Missing regions: " + ", ".join(missing))
    generated = parse_time(snapshot.get("generated_at"))
    if generated is None:
        raise ValueError("Snapshot generated_at must be timezone-aware ISO-8601")
    return {
        "schema_version": "1.0.0",
        "source": "CWA",
        "analysis_kind": "observed_marine_exposure_screening",
        "generated_at": now.isoformat(),
        "source_snapshot_generated_at": snapshot["generated_at"],
        "stale_after_minutes": stale_after_minutes,
        "threshold_policy": {
            "type": "internal_screening_only",
            "wave_height_m": [{"below_m": x, "level": y} for x, y, _ in BANDS["wave_height_m"]],
            "wind_speed_ms": [{"below_ms": x, "level": y} for x, y, _ in BANDS["wind_speed_ms"]],
            "notice": "These bands are not official CWA warning thresholds, local shoreline safety limits, or fishing-success thresholds.",
        },
        "regions": {
            region_id: assess_region(region_id, regions[region_id], generated, now, stale_after_minutes)
            for region_id in REGIONS
        },
        "global_limitations": [
            "This is a screening aid, not an official warning, forecast, safety clearance, or recommendation to enter the water.",
            "No station data is spatially extrapolated to an uncovered region.",
            "No tide phase, shoreline exposure, rip-current risk, or fish activity is inferred.",
        ],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--as-of", help="Timezone-aware ISO-8601; defaults to current UTC time.")
    parser.add_argument("--stale-after-minutes", type=int, default=180)
    args = parser.parse_args()
    now = parse_time(args.as_of) if args.as_of else datetime.now(timezone.utc)
    if now is None:
        raise SystemExit("--as-of must be timezone-aware ISO-8601")
    if args.stale_after_minutes < 1:
        raise SystemExit("--stale-after-minutes must be positive")
    snapshot = json.loads(args.input.read_text(encoding="utf-8"))
    result = build_assessment(snapshot, now, args.stale_after_minutes)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "regions": len(result["regions"]),
        "states": {key: value["state"] for key, value in result["regions"].items()},
        "levels": {key: value["exposure_level"] for key, value in result["regions"].items()},
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
