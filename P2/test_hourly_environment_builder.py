import csv
import json
import tempfile
import unittest
from pathlib import Path

from build_hourly_environment_records import build_forecast_rows, build_cwa_rows

class HourlyBuilderTests(unittest.TestCase):
    def test_forecast_rows_join_marine_weather_and_daily_sun(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw_dir = root / "raw"
            raw_dir.mkdir()
            (raw_dir / "taitung_south_weather_raw.json").write_text(json.dumps({
                "daily": {
                    "time": ["2026-11-09"],
                    "sunrise": ["2026-11-09T06:02"],
                    "sunset": ["2026-11-09T17:12"]
                }
            }), encoding="utf-8")
            csv_path = root / "forecast.csv"
            rows = []
            for variable, value, source in [
                ("wave_height", "1.1", "open-meteo-marine"),
                ("wave_period", "7.2", "open-meteo-marine"),
                ("wave_direction", "80", "open-meteo-marine"),
                ("sea_surface_temperature", "26.5", "open-meteo-marine"),
                ("sea_level_height_msl", "0.1", "open-meteo-marine"),
                ("ocean_current_velocity", "0.2", "open-meteo-marine"),
                ("ocean_current_direction", "170", "open-meteo-marine"),
                ("wind_speed_10m", "3.0", "open-meteo-forecast"),
                ("wind_direction_10m", "90", "open-meteo-forecast"),
                ("precipitation", "1.4", "open-meteo-forecast"),
                ("showers", "0.2", "open-meteo-forecast"),
                ("precipitation_probability", "40", "open-meteo-forecast"),
                ("weather_code", "95", "open-meteo-forecast"),
            ]:
                rows.append({
                    "location_id": "taitung_south",
                    "valid_time": "2026-11-09T12:00",
                    "fetched_at": "2026-11-09T04:00:00+00:00",
                    "variable_code": variable, "value": value, "source": source,
                })
            with csv_path.open("w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0]))
                w.writeheader()
                w.writerows(rows)
            result = build_forecast_rows(csv_path, raw_dir, "Asia/Taipei")
            self.assertEqual(len(result), 1)
            rec = result[0]
            self.assertEqual(rec["data_type"], "forecast")
            self.assertEqual(rec["region_id"], "taitung_south")
            self.assertEqual(rec["environment"]["thunderstorm_risk"], "high")
            self.assertEqual(rec["environment"]["precipitation_probability_pct"], 40)
            self.assertEqual(rec["environment"]["sunrise"], "2026-11-09T06:02:00+08:00")
            self.assertEqual(len(rec["source_records"]), 2)
            self.assertEqual(rec["completeness"]["ratio"], 1.0)

    def test_missing_forecast_values_stay_null(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "raw"
            raw.mkdir()
            csv_path = root / "f.csv"
            rows = [{
                "location_id": "hualien_south",
                "valid_time": "2026-11-09T12:00",
                "fetched_at": "2026-11-09T04:00:00+00:00",
                "variable_code": "wave_height", "value": "", "source": "open-meteo-marine",
            }]
            with csv_path.open("w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0]))
                w.writeheader()
                w.writerows(rows)
            rec = build_forecast_rows(csv_path, raw, "Asia/Taipei")[0]
            self.assertIsNone(rec["environment"]["wave_height_m"])
            self.assertIn("missing_wave_height_m", rec["quality"]["flags"])

    def test_cwa_observation_keeps_tide_height_separate_from_current(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "obs.jsonl"
            row = {
                "region_id": "chenggong_donghe",
                "valid_time": "2026-11-09T12:00:00+08:00",
                "collected_at": "2026-11-09T04:30:00Z",
                "source_dataset": "O-B0075-001",
                "revision_key": "rev-1",
                "tide_height_m": "0.45",
                "current_speed_ms": "0.31",
                "current_direction_deg": "120",
                "wave_height_m": "1.2",
            }
            path.write_text(json.dumps(row) + "\n", encoding="utf-8")
            rec = build_cwa_rows(path)[0]
            env = rec["environment"]
            self.assertEqual(env["tide_height_m"], 0.45)
            self.assertEqual(env["ocean_current_velocity_ms"], 0.31)
            self.assertNotIn("tidal_current_velocity_ms", env)
            self.assertEqual(rec["data_type"], "observation")

if __name__ == "__main__":
    unittest.main()
