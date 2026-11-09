import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "collector"))
from collect_open_meteo import resolve_source_location


class OpenMeteoSourceLocationTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
