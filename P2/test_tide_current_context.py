import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent/"collector"))
from build_tide_current_context import build_context, build_file

def record(env):
    return {"region_id":"taitung_south","valid_time":"2026-11-09T10:00:00+08:00",
            "collected_at":"2026-11-09T09:00:00+08:00","data_type":"forecast",
            "source_records":[{"source_id":"open-meteo","dataset":"marine","url":"https://marine-api.open-meteo.com/"}],
            "environment":env}

class TideCurrentContextTests(unittest.TestCase):
    def test_tide_and_currents_are_kept_as_separate_fields(self):
        row=build_context(record({"tide_height_m":0.8,"tide_phase":"rising",
            "tidal_current_velocity_ms":0.25,"ocean_current_velocity_ms":0.9}))
        self.assertEqual(row["tide_height_m"],0.8)
        self.assertEqual(row["tidal_current_velocity_ms"],0.25)
        self.assertEqual(row["ocean_current_velocity_ms"],0.9)
        self.assertEqual(row["tide_phase"],"rising")

    def test_tide_height_does_not_generate_tide_phase_or_current(self):
        row=build_context(record({"tide_height_m":1.2}))
        self.assertEqual(row["tide_phase"],"unknown")
        self.assertIsNone(row["tidal_current_velocity_ms"])
        self.assertEqual(row["availability"]["tidal_current"],"missing")

    def test_ocean_current_is_not_copied_into_tidal_current(self):
        row=build_context(record({"ocean_current_velocity_ms":0.7,"ocean_current_direction_deg":120}))
        self.assertEqual(row["ocean_current_velocity_ms"],0.7)
        self.assertIsNone(row["tidal_current_velocity_ms"])
        self.assertEqual(row["availability"]["ocean_current"],"available")
        self.assertEqual(row["availability"]["tidal_current"],"missing")

    def test_turning_flag_does_not_create_slack_phase(self):
        row=build_context(record({"tide_turning":True}))
        self.assertIsNone(row["tide_phase"] if row["tide_phase"]=="unknown" else "unexpected")
        self.assertTrue(row["tide_turning"])

    def test_missing_all_fields_is_explicitly_missing(self):
        row=build_context(record({}))
        self.assertEqual(row["availability"],{"tide_height":"missing","tide_phase":"unknown",
            "tidal_current":"missing","ocean_current":"missing"})
        self.assertIn("not_fish_activity",row["interpretation"])

    def test_unknown_phase_is_normalized_to_unknown(self):
        row=build_context(record({"tide_phase":"ebb-ish"}))
        self.assertEqual(row["tide_phase"],"unknown")

    def test_file_conversion_preserves_each_input_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); source=root/"in.jsonl"; target=root/"out.jsonl"
            source.write_text(json.dumps(record({"tide_height_m":0.4}),ensure_ascii=False)+"\n",encoding="utf-8")
            self.assertEqual(build_file(source,target),1)
            output=json.loads(target.read_text(encoding="utf-8").strip())
            self.assertEqual(output["tide_height_m"],0.4)
            self.assertEqual(output["tide_phase"],"unknown")

if __name__=="__main__": unittest.main()
