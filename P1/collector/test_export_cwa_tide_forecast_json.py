import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from export_cwa_tide_forecast_json import build_payload


class CwaTideForecastExportTests(unittest.TestCase):
    def test_builds_nearest_location_feed_and_keeps_height_datums_separate(self):
        rows = [
            {"location_id":"B00400","location_name":"海釣芭崎牛寮坑","latitude":"23.729","longitude":"121.559","region_id":"hualien_south","valid_time":"2026-11-10T06:58:00+08:00","tide":"滿潮","height_above_local_msl_cm":"70","height_above_chart_datum_cm":"182","height_above_twvd_cm":"60","tide_range":"大"},
            {"location_id":"B00400","location_name":"海釣芭崎牛寮坑","latitude":"23.729","longitude":"121.559","region_id":"hualien_south","valid_time":"2026-11-10T12:12:00+08:00","tide":"乾潮","height_above_local_msl_cm":"-9","height_above_chart_datum_cm":"103","height_above_twvd_cm":"-20","tide_range":"大"},
        ]
        payload = build_payload(rows, "2026-11-09T14:00:00+00:00")
        self.assertEqual(payload["location_count"], 1)
        self.assertEqual(payload["event_count"], 2)
        location = payload["locations"][0]
        self.assertEqual(location["region_id"], "hualien_south")
        self.assertEqual(location["events"][0]["height_above_local_msl_cm"], 70)
        self.assertEqual(location["events"][0]["height_above_chart_datum_cm"], 182)
        self.assertEqual(location["events"][0]["height_above_twvd_cm"], 60)
        self.assertIn("not continuous tide observation", payload["interpretation"])

    def test_excludes_unmapped_locations_and_deduplicates_events(self):
        row = {"location_id":"10014020","location_name":"成功","latitude":"23.0972","longitude":"121.38","region_id":"chenggong_donghe","valid_time":"2026-11-10T06:00:00+08:00","tide":"高潮","height_above_local_msl_cm":"55"}
        payload = build_payload([row, row, {**row, "region_id":"", "location_id":"UNMAPPED"}])
        self.assertEqual(payload["event_count"], 1)
        self.assertEqual(payload["excluded_event_row_count"], 1)
        self.assertEqual(payload["locations"][0]["events"][0]["tide"], "滿潮")

    def test_rejects_empty_mapped_feed(self):
        with self.assertRaisesRegex(ValueError, "No mapped CWA tide forecast locations"):
            build_payload([{ "region_id":"", "location_id":"X" }])


if __name__ == "__main__":
    unittest.main()
