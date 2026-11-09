import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "collector"))
from build_hourly_history_catalog import build_catalog

def row(region, kind, valid, collected):
    return {"region_id":region,"data_type":kind,"valid_time":valid,"collected_at":collected}

class HistoryCatalogTests(unittest.TestCase):
    def test_catalog_counts_records_hours_and_vintages_separately(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            folder=root/"hourly_environment/2026/11"
            folder.mkdir(parents=True)
            p=folder/"2026-11-09.jsonl"
            rows=[
                row("taitung_south","forecast","2026-11-09T12:00:00+08:00","2026-11-09T04:00:00+00:00"),
                row("taitung_south","forecast","2026-11-09T12:00:00+08:00","2026-11-09T08:00:00+00:00"),
                row("taitung_south","observation","2026-11-09T12:00:00+08:00","2026-11-09T08:30:00+00:00"),
                row("chenggong_donghe","forecast","2026-11-09T13:00:00+08:00","2026-11-09T04:00:00+00:00"),
            ]
            p.write_text("".join(json.dumps(x)+"\n" for x in rows),encoding="utf-8")
            result=build_catalog(root)
            self.assertEqual(result["partition_count"],1)
            self.assertEqual(result["record_count"],4)
            part=result["partitions"][0]
            self.assertEqual(part["records_by_region_type"]["taitung_south|forecast"],2)
            self.assertEqual(part["unique_valid_hours_by_region_type"]["taitung_south|forecast"],1)
            self.assertEqual(part["collection_vintages_by_region_type"]["taitung_south|forecast"],2)

    def test_duplicate_record_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); folder=root/"hourly_environment/2026/11"; folder.mkdir(parents=True)
            p=folder/"2026-11-09.jsonl"
            x=row("taitung_south","forecast","2026-11-09T12:00:00+08:00","2026-11-09T04:00:00+00:00")
            p.write_text(json.dumps(x)+"\n"+json.dumps(x)+"\n",encoding="utf-8")
            with self.assertRaises(ValueError):
                build_catalog(root)

if __name__ == "__main__":
    unittest.main()
