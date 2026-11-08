#!/usr/bin/env python3
"""Create transparent +6h/+12h/+24h forecast snapshots from Open-Meteo long CSV.

Open-Meteo timestamps are local wall-clock strings when a timezone is requested.
They are interpreted in the configured IANA timezone before comparing with the
UTC fetch timestamp. The first available hourly value at or after each target
is selected; no interpolation or extrapolation is performed.
"""
from __future__ import annotations
import argparse, csv, json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

HORIZONS = (6, 12, 24)
KEYS = ("location_id", "location_name", "source", "data_kind", "variable_code", "unit")

def parse_fetch_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"fetched_at must include timezone: {value}")
    return parsed

def parse_valid_time(value: str, timezone_name: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo(timezone_name))
    return parsed

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--timezone", default="Asia/Taipei")
    a = p.parse_args()
    rows = []
    with open(a.input, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise SystemExit("Forecast CSV is empty; cannot build horizon summaries.")

    fetch_times = [parse_fetch_time(r["fetched_at"]) for r in rows if r.get("fetched_at")]
    if not fetch_times:
        raise SystemExit("Forecast CSV has no valid fetched_at timestamp.")
    fetched_utc = max(fetch_times)
    fetched_local = fetched_utc.astimezone(ZoneInfo(a.timezone))
    groups = {}
    for row in rows:
        if not row.get("valid_time"):
            continue
        key = tuple(row.get(k, "") for k in KEYS)
        groups.setdefault(key, []).append(row)
    for values in groups.values():
        values.sort(key=lambda r: parse_valid_time(r["valid_time"], a.timezone))

    output = []
    for key, values in sorted(groups.items()):
        for hours in HORIZONS:
            target = fetched_local + timedelta(hours=hours)
            selected = next((
                r for r in values
                if parse_valid_time(r["valid_time"], a.timezone) >= target
            ), None)
            record = dict(zip(KEYS, key))
            record.update({
                "horizon_hours": hours,
                "target_time": target.isoformat(),
                "selected_valid_time": selected.get("valid_time") if selected else None,
                "value": selected.get("value") if selected else None,
                "quality_status": (
                    "missing_target" if selected is None else
                    "missing_provider_value" if selected.get("value") in ("", None) else
                    "available"
                ),
                "selection_method": "first_forecast_hour_at_or_after_target",
                "fetched_at": fetched_utc.isoformat(),
            })
            output.append(record)

    if not output:
        raise SystemExit("No valid forecast time series found in input CSV.")
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    fields = list(output[0].keys())
    with out.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(output)
    summary = {
        "generated_at": fetched_utc.isoformat(),
        "timezone": a.timezone,
        "input_rows": len(rows),
        "output_rows": len(output),
        "horizons_hours": list(HORIZONS),
        "available_values": sum(r["quality_status"] == "available" for r in output),
        "missing_values": sum(r["quality_status"] != "available" for r in output),
        "limitations": [
            "Uses the first available hourly model value at or after each target; no interpolation.",
            "Forecast and modelled values are not in-situ observations.",
            "A valid value is not a guarantee of local nearshore accuracy.",
        ],
    }
    out.with_name("forecast_horizon_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Input rows: {len(rows)}; horizon rows: {len(output)}")
    print(f"Available: {summary['available_values']}; missing: {summary['missing_values']}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
