import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "collector"))
from archive_hourly_environment import archive

def record(valid="2026-11-09T12:00:00+08:00", collected="2026-11-09T04:00:00+00:00", height=1.2, kind="forecast"):
    return {
        "schema_version":"1.0.0","region_id":"taitung_south","valid_time":valid,
        "collected_at":collected,"data_type":kind,"source_records":[{"source_id":"test"}],
        "environment":{"wave_height_m":height},
        "completeness":{"available_fields":1,"expected_fields":1,"ratio":1.0},
        "quality":{"status":"good","confidence":"unknown","flags":[]}
    }

class HourlyArchiveTests(unittest.TestCase):
    def test_exact_duplicate_is_skipped_and_new_vintage_is_kept(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); source=root/"input.jsonl"
            source.write_text(json.dumps(record())+"\n"+json.dumps(record())+"\n"+json.dumps(record(collected="2026-11-09T08:00:00+00:00",height=1.5))+"\n",encoding="utf-8")
            result=archive(source,root/"archive")
            self.assertEqual(result["input_records"],3)
            self.assertEqual(result["records_added"],2)
            self.assertEqual(result["exact_duplicates_skipped"],1)
            target=root/"archive/hourly_environment/2026/11/2026-11-09.jsonl"
            self.assertEqual(len(target.read_text(encoding="utf-8").splitlines()),2)

    def test_second_run_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); source=root/"input.jsonl"
            source.write_text(json.dumps(record())+"\n",encoding="utf-8")
            archive(source,root/"archive")
            result=archive(source,root/"archive")
            self.assertEqual(result["records_added"],0)
            self.assertEqual(result["exact_duplicates_skipped"],1)

    def test_observation_and_forecast_are_not_collapsed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); source=root/"input.jsonl"
            source.write_text(json.dumps(record(kind="forecast"))+"\n"+json.dumps(record(kind="observation"))+"\n",encoding="utf-8")
            result=archive(source,root/"archive")
            self.assertEqual(result["records_added"],2)

if __name__ == "__main__":
    unittest.main()
