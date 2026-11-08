#!/usr/bin/env python3
"""Fast offline regression tests for CWA marine parsing and regional math."""
import sys
import unittest
import csv
import json
import subprocess
import tempfile
from pathlib import Path

COLLECTOR = Path(__file__).resolve().parents[1] / "collector"
sys.path.insert(0, str(COLLECTOR))

from normalize_cwa_marine import as_layer_list, clean, layer_label  # noqa: E402
from fetch_cwa_tide_forecast import normalize as normalize_tides  # noqa: E402
from build_east_region_conditions import REGIONS, mean_value, num, parse_status, parse_properties  # noqa: E402


class CwaTideForecastTests(unittest.TestCase):
    def test_documented_tide_forecast_shape_and_height_datums(self):
        event_low = {
            "DateTime": "2026-11-16T04:06:00+08:00",
            "Tide": "乾潮",
            "TideHeights": {"AboveTWVD": "-33", "AboveLocalMSL": "-22", "AboveChartDatum": "90"},
        }
        event_high = {
            "DateTime": "2026-11-16T11:23:00+08:00",
            "Tide": "滿潮",
            "TideHeights": {"AboveTWVD": "31", "AboveLocalMSL": "41", "AboveChartDatum": "153"},
        }
        daily = {
            "Date": "2026-11-16",
            "LunarDate": "2026-10-08",
            "TideRange": "小",
            "Time": [event_low, event_high],
        }
        location = {
            "LocationId": "10015050",
            "LocationName": "花蓮縣吉安鄉",
            "Latitude": "23.94240",
            "Longitude": "121.61250",
            "TimePeriods": {"Daily": [daily]},
        }
        payload = {"cwaopendata": {"Resources": {"Resource": {
            "Data": {"TideForecasts": {"Location": [location]}}
        }}}}
        rows = normalize_tides(payload, "2026-11-08T00:00:00+00:00")
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["location_id"], "10015050")
        self.assertEqual(rows[0]["height_above_local_msl_cm"], -22.0)
        self.assertEqual(rows[1]["tide"], "滿潮")
        self.assertEqual(rows[1]["region_id"], "")

    def test_tide_missing_height_stays_null_not_zero(self):
        payload = {"Data": {"TideForecasts": {"Location": [{
            "LocationId": "X1", "LocationName": "測試",
            "TimePeriods": {"Daily": [{"Date": "2026-11-08", "Time": [{
                "DateTime": "2026-11-08T10:00:00+08:00", "Tide": "滿潮",
                "TideHeights": {"AboveTWVD": "None"}
            }]}]}
        }]}}}
        row = normalize_tides(payload, "test")[0]
        self.assertIsNone(row["height_above_twvd_cm"])
        self.assertIsNone(row["height_above_local_msl_cm"])

    def test_tide_failure_or_unrecognized_schema_is_rejected(self):
        with self.assertRaises(ValueError):
            normalize_tides({"success": "false"}, "test")
        with self.assertRaises(ValueError):
            normalize_tides({"Records": {}}, "test")



class CwaRegionalTideBuilderTests(unittest.TestCase):
    def run_builder(self, tide_rows, mapping_rows):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tide_path, map_path, out_path = root / "tides.csv", root / "mapping.csv", root / "regional.csv"
            with tide_path.open("w", encoding="utf-8-sig", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(tide_rows[0]))
                w.writeheader()
                w.writerows(tide_rows)
            with map_path.open("w", encoding="utf-8-sig", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(mapping_rows[0]))
                w.writeheader()
                w.writerows(mapping_rows)
            result = subprocess.run([
                sys.executable, str(COLLECTOR / "build_cwa_regional_tide_forecast.py"),
                "--input", str(tide_path), "--mapping", str(map_path), "--out", str(out_path)
            ], capture_output=True, text=True)
            return result, out_path

    def test_six_region_mapping_keeps_site_events_separate_and_excludes_islands(self):
        tide_rows = [
            {"location_id": "10002030", "location_name": "宜蘭縣蘇澳鎮", "valid_time": "2026-11-09T06:00:00+08:00", "tide": "滿潮", "height_above_twvd_cm": "40"},
            {"location_id": "10002030", "location_name": "宜蘭縣蘇澳鎮", "valid_time": "2026-11-09T12:00:00+08:00", "tide": "乾潮", "height_above_twvd_cm": "-20"},
            {"location_id": "10014110", "location_name": "臺東縣綠島鄉", "valid_time": "2026-11-09T08:00:00+08:00", "tide": "滿潮", "height_above_twvd_cm": "50"},
            {"location_id": "999999", "location_name": "未對照地點", "valid_time": "2026-11-09T09:00:00+08:00", "tide": "滿潮", "height_above_twvd_cm": "10"},
        ]
        base = {"latitude": "24.5925", "longitude": "121.8669", "mapping_basis": "official_CWA_location_id_and_coordinate", "notes": "test"}
        mapping_rows = [
            dict(base, location_id="10002030", location_name="宜蘭縣蘇澳鎮", region_id="yilan_suao", mapping_status="mapped"),
            dict(base, location_id="10014110", location_name="臺東縣綠島鄉", region_id="", mapping_status="excluded_offshore_context"),
        ]
        result, out_path = self.run_builder(tide_rows, mapping_rows)
        self.assertEqual(result.returncode, 0, result.stderr)
        with out_path.open(encoding="utf-8-sig", newline="") as f:
            output = list(csv.DictReader(f))
        self.assertEqual(len(output), 2)
        self.assertEqual({r["region_id"] for r in output}, {"yilan_suao"})
        self.assertEqual({r["height_above_twvd_cm"] for r in output}, {"40", "-20"})
        summary = json.loads(out_path.with_name("regional_tide_summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["mapped_event_rows"], 2)
        self.assertEqual(summary["mapped_unique_locations"], 1)
        self.assertEqual(summary["unmapped_or_excluded_location_count"], 2)

    def test_duplicate_mapping_id_is_rejected(self):
        tide_rows = [{"location_id": "X", "location_name": "測試", "valid_time": "t"}]
        base = {"latitude": "1", "longitude": "2", "mapping_basis": "test", "notes": "test"}
        mapping_rows = [
            dict(base, location_id="X", location_name="測試", region_id="yilan_suao", mapping_status="mapped"),
            dict(base, location_id="X", location_name="測試", region_id="yilan_suao", mapping_status="mapped"),
        ]
        result, _ = self.run_builder(tide_rows, mapping_rows)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Duplicate location_id", result.stderr)

    def test_feed_location_name_mismatch_is_rejected(self):
        tide_rows = [{"location_id": "X", "location_name": "不同名稱", "valid_time": "t"}]
        base = {"latitude": "1", "longitude": "2", "mapping_basis": "test", "notes": "test"}
        mapping_rows = [dict(base, location_id="X", location_name="原始名稱", region_id="yilan_suao", mapping_status="mapped")]
        result, _ = self.run_builder(tide_rows, mapping_rows)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Location name mismatch", result.stderr)


class MarineNormalizationTests(unittest.TestCase):
    def test_missing_sentinels_are_not_zero(self):
        for value in (None, "", "None", "null", "NaN", "N/A"):
            self.assertIsNone(clean(value))
        self.assertEqual(num("0"), 0.0)
        self.assertIsNone(num("None"))

    def test_current_layer_object_and_list_shapes(self):
        layer = {"LayerNumber": "1", "CurrentDirection": "270", "CurrentSpeed": "0.5"}
        self.assertEqual(as_layer_list({"Layer": layer}), [layer])
        self.assertEqual(as_layer_list({"Layer": [layer]}), [layer])
        self.assertEqual(as_layer_list([{"Layer": layer}, {"Layer": [layer]}]), [layer, layer])
        self.assertEqual(layer_label(layer, 1), "1")

    def test_empty_or_unexpected_current_shape_is_safe(self):
        self.assertEqual(as_layer_list(None), [])
        self.assertEqual(as_layer_list({"Layer": None}), [])
        self.assertEqual(as_layer_list("unexpected"), [])

    def test_direction_uses_circular_mean(self):
        # 359° and 1° should average to north, not 180°.
        result = mean_value("wave_direction_deg", [359.0, 1.0])
        self.assertTrue(result < 0.01 or result > 359.99)

    def test_live_station_status_and_element_metadata_parsing(self):
        self.assertEqual(parse_status("1"), 1)
        self.assertEqual(parse_status("0"), 0)
        self.assertIsNone(parse_status("unknown"))
        props = parse_properties('{"WaveHeight":"1","SeaTemperature":"0"}')
        self.assertEqual(parse_status(props.get("WaveHeight")), 1)
        self.assertEqual(parse_status(props.get("SeaTemperature")), 0)
        self.assertEqual(parse_properties("invalid-json"), {})

    def test_all_six_planning_regions_are_declared(self):
        self.assertEqual(len(REGIONS), 6)
        self.assertIn("hualien_south", REGIONS)
        self.assertIn("taitung_south", REGIONS)


if __name__ == "__main__":
    unittest.main(verbosity=2)
