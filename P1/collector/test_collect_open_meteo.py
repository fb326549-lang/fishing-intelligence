import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "collector"))
from collect_open_meteo import normalize_hourly, resolve_source_location


class OpenMeteoSourceLocationTests(unittest.TestCase):
    def test_config_fetches_three_days_to_cover_24h_horizon_after_hour_boundary(self):
        config_path = Path(__file__).parent / "config.example.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        self.assertGreaterEqual(config["forecast_days"], 3)

    def test_marine_can_use_offshore_coordinates_without_moving_weather_point(self):
        location = {
            "id": "hualien_south",
            "name": "花蓮南段",
            "latitude": 23.72,
            "longitude": 121.48,
            "marine_latitude": 23.72,
            "marine_longitude": 121.62,
        }
        marine = resolve_source_location(location, "marine")
        weather = resolve_source_location(location, "weather")
        self.assertEqual((marine["latitude"], marine["longitude"]), (23.72, 121.62))
        self.assertEqual((weather["latitude"], weather["longitude"]), (23.72, 121.48))

    def test_marine_falls_back_to_existing_coordinates_when_not_overridden(self):
        location = {"id": "chenggong_donghe", "name": "成功、東河", "latitude": 23.10, "longitude": 121.38}
        marine = resolve_source_location(location, "marine")
        self.assertEqual((marine["latitude"], marine["longitude"]), (23.10, 121.38))

    def test_marine_rows_keep_region_request_and_actual_grid_coordinates_separate(self):
        location = {
            "id": "hualien_south", "name": "花蓮南段",
            "latitude": 23.72, "longitude": 121.48,
            "marine_latitude": 23.72, "marine_longitude": 121.62,
        }
        marine = resolve_source_location(location, "marine")
        payload = {
            "latitude": 23.7, "longitude": 121.6,
            "hourly": {"time": ["2026-11-09T12:00"], "wave_height": [1.2]},
            "hourly_units": {"wave_height": "m"},
        }
        row = normalize_hourly(marine, payload, "test", "open-meteo-marine", "modelled")[0]
        self.assertEqual((row["requested_latitude"], row["requested_longitude"]), (23.72, 121.48))
        self.assertEqual((row["grid_latitude"], row["grid_longitude"]), (23.7, 121.6))


if __name__ == "__main__":
    unittest.main()
