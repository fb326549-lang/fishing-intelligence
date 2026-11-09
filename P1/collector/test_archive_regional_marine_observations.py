#!/usr/bin/env python3
"""Offline tests for append-only regional CWA observation history."""
import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from archive_regional_marine_observations import archive


class RegionalObservationArchiveTests(unittest.TestCase):
    def write_csv(self, path, wave_height):
        fields = ["region_id", "region_name", "valid_time", "source", "data_kind", "wave_height_m"]
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerow({
                "region_id": "chenggong_donghe",
                "region_name": "成功、東河",
                "valid_time": "2026-11-10T08:00:00+08:00",
                "source": "CWA",
                "data_kind": "observed",
                "wave_height_m": wave_height,
            })

    def read_rows(self, path):
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def test_first_snapshot_appends_traceable_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "observations.csv"
            history = Path(tmp) / "history"
            self.write_csv(csv_path, "1.2")
            result = archive(str(csv_path), str(history), "run-1", "2026-11-10T00:00:00Z")
            target = history / "regional_marine_observations_48h.jsonl"
            rows = self.read_rows(target)
            self.assertEqual(result["new_revisions"], 1)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["source_dataset"], "O-B0075-001")
            self.assertEqual(rows[0]["archive_scope"], "rolling_48_hour")
            self.assertEqual(rows[0]["snapshot_id"], "run-1")
            self.assertEqual(rows[0]["wave_height_m"], "1.2")

    def test_identical_repeated_snapshot_is_deduplicated(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "observations.csv"
            history = Path(tmp) / "history"
            self.write_csv(csv_path, "1.2")
            first = archive(str(csv_path), str(history), "run-1", "2026-11-10T00:00:00Z")
            second = archive(str(csv_path), str(history), "run-2", "2026-11-10T04:00:00Z")
            self.assertEqual(first["new_revisions"], 1)
            self.assertEqual(second["new_revisions"], 0)
            self.assertEqual(len(self.read_rows(history / "regional_marine_observations_48h.jsonl")), 1)

    def test_changed_measurement_is_appended_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "observations.csv"
            history = Path(tmp) / "history"
            target = history / "regional_marine_observations_48h.jsonl"
            self.write_csv(csv_path, "1.2")
            archive(str(csv_path), str(history), "run-1", "2026-11-10T00:00:00Z")
            self.write_csv(csv_path, "1.4")
            result = archive(str(csv_path), str(history), "run-2", "2026-11-10T04:00:00Z")
            rows = self.read_rows(target)
            self.assertEqual(result["new_revisions"], 1)
            self.assertEqual(len(rows), 2)
            self.assertEqual({row["wave_height_m"] for row in rows}, {"1.2", "1.4"})
            self.assertEqual(len({row["revision_key"] for row in rows}), 2)

    def test_missing_region_or_valid_time_is_not_archived(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "observations.csv"
            history = Path(tmp) / "history"
            fields = ["region_id", "region_name", "valid_time", "wave_height_m"]
            with csv_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                writer.writerow({"region_id": "", "valid_time": "2026-11-10T08:00:00+08:00", "wave_height_m": "1.2"})
                writer.writerow({"region_id": "chenggong_donghe", "valid_time": "", "wave_height_m": "1.2"})
            result = archive(str(csv_path), str(history), "run-1", "2026-11-10T00:00:00Z")
            self.assertEqual(result["new_revisions"], 0)
            self.assertFalse((history / "regional_marine_observations_48h.jsonl").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
