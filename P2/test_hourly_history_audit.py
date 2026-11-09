import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "collector"))
from build_hourly_history_catalog import build_catalog
from validate_hourly_history import audit_history

def make_record(valid="2026-11-09T12:00:00+08:00", collected="2026-11-09T04:00:00+00:00", kind="forecast", region="taitung_south"):
    return {
        "schema_version": "1.0.0",
        "region_id": region,
        "valid_time": valid,
        "collected_at": collected,
        "data_type": kind,
        "source_records": [{"source_id": "test", "dataset": "fixture"}],
        "environment": {"wave_height_m": 1.2},
        "completeness": {"available_fields": 1, "expected_fields": 1, "ratio": 1.0},
        "quality": {"status": "good", "confidence": "unknown", "flags": []},
    }

class HourlyHistoryAuditTests(unittest.TestCase):
    def prepare(self, root, rows):
        folder = root / "hourly_environment" / "2026" / "11"
        folder.mkdir(parents=True)
        partition = folder / "2026-11-09.jsonl"
        partition.write_text("".join(json.dumps(x, ensure_ascii=False, sort_keys=True) + "\n" for x in rows), encoding="utf-8")
        catalog = build_catalog(root)
        (root / "hourly_environment" / "catalog.json").write_text(json.dumps(catalog, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        return partition

    def test_valid_catalog_and_partitions_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.prepare(root, [make_record(), make_record(kind="observation", collected="2026-11-09T04:30:00+00:00")])
            result = audit_history(root)
            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["record_count"], 2)
            self.assertEqual(result["regions"], ["taitung_south"])

    def test_partition_hash_mismatch_is_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            partition = self.prepare(root, [make_record()])
            partition.write_text(partition.read_text(encoding="utf-8") + partition.read_text(encoding="utf-8"), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                audit_history(root)

    def test_valid_time_date_must_match_partition(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.prepare(root, [make_record(valid="2026-11-10T00:00:00+08:00")])
            with self.assertRaisesRegex(ValueError, "date does not match partition"):
                audit_history(root)

    def test_catalog_builder_rejects_duplicate_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "hourly_environment" / "2026" / "11"
            folder.mkdir(parents=True)
            partition = folder / "2026-11-09.jsonl"
            row = make_record()
            partition.write_text(json.dumps(row) + "\n" + json.dumps(row) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "exact duplicate"):
                build_catalog(root)

if __name__ == "__main__":
    unittest.main()
