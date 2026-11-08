#!/usr/bin/env python3
"""Fast offline regression tests for CWA marine parsing and regional math."""
import sys
import unittest
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
