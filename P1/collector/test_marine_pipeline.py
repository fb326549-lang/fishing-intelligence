#!/usr/bin/env python3
"""Fast offline regression tests for CWA marine parsing and regional math."""
import sys
import unittest
from pathlib import Path

COLLECTOR = Path(__file__).resolve().parents[1] / "collector"
sys.path.insert(0, str(COLLECTOR))

from normalize_cwa_marine import as_layer_list, clean, layer_label  # noqa: E402
from build_east_region_conditions import REGIONS, mean_value, num, parse_status, parse_properties  # noqa: E402


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
