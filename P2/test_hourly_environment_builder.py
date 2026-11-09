import csv
import json
import tempfile
import unittest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / 'collector'))

from build_hourly_environment_records import build_forecast_rows, build_cwa_rows, build_tide_phase_index, tide_phase_for_location, regional_tide_phase

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

    def test_cwa_high_low_events_derive_rising_and_falling_phase(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        tz = ZoneInfo("Asia/Taipei")
        events = [
            (datetime.fromisoformat("2026-11-09T00:00:00").replace(tzinfo=tz), "low"),
            (datetime.fromisoformat("2026-11-09T06:00:00").replace(tzinfo=tz), "high"),
            (datetime.fromisoformat("2026-11-09T12:00:00").replace(tzinfo=tz), "low"),
        ]
        self.assertEqual(tide_phase_for_location(events, datetime.fromisoformat("2026-11-09T03:00:00").replace(tzinfo=tz)), "rising")
        self.assertEqual(tide_phase_for_location(events, datetime.fromisoformat("2026-11-09T09:00:00").replace(tzinfo=tz)), "falling")

    def test_cwa_event_near_target_is_slack_and_unbracketed_is_unknown(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        tz = ZoneInfo("Asia/Taipei")
        events = [
            (datetime.fromisoformat("2026-11-09T00:00:00").replace(tzinfo=tz), "low"),
            (datetime.fromisoformat("2026-11-09T06:00:00").replace(tzinfo=tz), "high"),
        ]
        self.assertEqual(tide_phase_for_location(events, datetime.fromisoformat("2026-11-09T05:45:00").replace(tzinfo=tz)), "high_slack")
        self.assertIsNone(tide_phase_for_location(events, datetime.fromisoformat("2026-11-08T20:00:00").replace(tzinfo=tz)))

    def test_regional_tide_phase_requires_all_mapped_locations_to_agree(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        tz = ZoneInfo("Asia/Taipei")
        target = datetime.fromisoformat("2026-11-09T03:00:00").replace(tzinfo=tz)
        low_high = [
            (datetime.fromisoformat("2026-11-09T00:00:00").replace(tzinfo=tz), "low"),
            (datetime.fromisoformat("2026-11-09T06:00:00").replace(tzinfo=tz), "high"),
        ]
        high_low = [
            (datetime.fromisoformat("2026-11-09T00:00:00").replace(tzinfo=tz), "high"),
            (datetime.fromisoformat("2026-11-09T06:00:00").replace(tzinfo=tz), "low"),
        ]
        phase, turning, count = regional_tide_phase({"yilan_suao":{"A":low_high,"B":low_high}}, "yilan_suao", target)
        self.assertEqual((phase, turning, count), ("rising", False, 2))
        phase, turning, count = regional_tide_phase({"yilan_suao":{"A":low_high,"B":high_low}}, "yilan_suao", target)
        self.assertEqual((phase, turning, count), (None, None, 2))

    def test_forecast_builder_adds_cwa_tide_phase_without_fabricating_height_or_current(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw_dir = root / "raw"
            raw_dir.mkdir()
            (raw_dir / "taitung_south_weather_raw.json").write_text(json.dumps({
                "daily": {"time":["2026-11-09"],"sunrise":["2026-11-09T06:02"],"sunset":["2026-11-09T17:12"]}
            }), encoding="utf-8")
            forecast_csv = root / "forecast.csv"
            rows = [{
                "location_id":"taitung_south","valid_time":"2026-11-09T09:00",
                "fetched_at":"2026-11-09T04:00:00+00:00","variable_code":"wave_height",
                "value":"1.1","source":"open-meteo-marine"
            }]
            with forecast_csv.open("w",encoding="utf-8",newline="") as handle:
                writer=csv.DictWriter(handle,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
            tide_csv = root / "tide.csv"
            tide_rows = [
                {"location_id":"10014010","region_id":"taitung_south","valid_time":"2026-11-09T06:00:00","tide":"乾潮","fetched_at_utc":"2026-11-09T04:00:00+00:00"},
                {"location_id":"10014010","region_id":"taitung_south","valid_time":"2026-11-09T12:00:00","tide":"滿潮","fetched_at_utc":"2026-11-09T04:00:00+00:00"},
            ]
            with tide_csv.open("w",encoding="utf-8",newline="") as handle:
                writer=csv.DictWriter(handle,fieldnames=list(tide_rows[0]));writer.writeheader();writer.writerows(tide_rows)
            index=build_tide_phase_index(tide_csv)
            rec=build_forecast_rows(forecast_csv,raw_dir,"Asia/Taipei",index)[0]
            self.assertEqual(rec["environment"]["tide_phase"],"rising")
            self.assertFalse(rec["environment"]["tide_turning"])
            self.assertIsNone(rec["environment"].get("tide_height_m"))
            self.assertIsNone(rec["environment"].get("tidal_current_velocity_ms"))
            cwa_source=next(x for x in rec["source_records"] if x["dataset"]=="F-A0021-001")
            self.assertEqual(cwa_source["retrieved_at"],"2026-11-09T04:00:00+00:00")
            self.assertIn("tide_phase_derived_from_cwa_high_low_forecast_events",rec["quality"]["flags"])

    def test_cwa_aggregate_without_dataset_is_not_mislabelled_as_one_dataset(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "obs.jsonl"
            row = {"region_id":"taitung_south","valid_time":"2026-11-09T12:00:00+08:00","collected_at":"2026-11-09T04:30:00Z","archive_scope":"rolling_48_hour","tide_height_m":"0.2"}
            path.write_text(json.dumps(row) + "\n", encoding="utf-8")
            rec = build_cwa_rows(path)[0]
            self.assertEqual(rec["source_records"][0]["dataset"], "regional-marine-aggregate")
            self.assertEqual(rec["source_records"][0]["url"], "https://opendata.cwa.gov.tw/")
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
            self.assertEqual(rec["source_records"][0]["dataset"], "O-B0075-001")

if __name__ == "__main__":
    unittest.main()
