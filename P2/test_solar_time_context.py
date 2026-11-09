import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent/"collector"))
from build_solar_time_context import build_context, build_file

def record(valid_time, sunrise="2026-11-09T06:00:00+08:00", sunset="2026-11-09T17:00:00+08:00"):
    return {"region_id":"taitung_south","valid_time":valid_time,"data_type":"forecast",
            "source_records":[{"source_id":"open-meteo","dataset":"forecast","url":"https://open-meteo.com/"}],
            "environment":{"sunrise":sunrise,"sunset":sunset}}

class SolarTimeContextTests(unittest.TestCase):
    def test_dawn_window_is_neutral_time_context(self):
        row=build_context(record("2026-11-09T05:30:00+08:00"))
        self.assertEqual(row["solar_phase"],"dawn")
        self.assertEqual(row["minutes_from_sunrise"],-30.0)
        self.assertIn("not_fish_activity",row["interpretation"])

    def test_daylight_between_twilight_windows(self):
        row=build_context(record("2026-11-09T10:00:00+08:00"))
        self.assertEqual(row["solar_phase"],"daylight")

    def test_dusk_window(self):
        row=build_context(record("2026-11-09T17:30:00+08:00"))
        self.assertEqual(row["solar_phase"],"dusk")
        self.assertEqual(row["minutes_to_sunset"],-30.0)

    def test_night_outside_twilight_windows(self):
        row=build_context(record("2026-11-09T22:00:00+08:00"))
        self.assertEqual(row["solar_phase"],"night")

    def test_missing_sunrise_or_sunset_stays_unknown(self):
        row=build_context(record("2026-11-09T10:00:00+08:00",sunrise=None))
        self.assertEqual(row["solar_phase"],"unknown")
        self.assertEqual(row["status"],"insufficient_solar_time_data")

    def test_file_conversion_preserves_one_output_per_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); inp=root/"in.jsonl"; out=root/"out.jsonl"
            inp.write_text(__import__("json").dumps(record("2026-11-09T10:00:00+08:00"))+"\n",encoding="utf-8")
            self.assertEqual(build_file(inp,out),1)
            self.assertEqual(len(out.read_text(encoding="utf-8").splitlines()),1)

if __name__=="__main__": unittest.main()
