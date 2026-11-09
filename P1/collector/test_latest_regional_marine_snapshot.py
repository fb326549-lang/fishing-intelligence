#!/usr/bin/env python3
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

COLLECTOR = Path(__file__).resolve().parent
SCRIPT = COLLECTOR / "build_latest_regional_marine_snapshot.py"
REGIONS = [
    "yilan_suao", "hualien_north", "hualien_south",
    "fengbin_shitiping", "chenggong_donghe", "taitung_south",
]


def make_summary(scope):
    rows = []
    for region_id in REGIONS:
        missing = region_id == "hualien_south"
        rows.append({
            "region_id": region_id,
            "region_name": region_id,
            "mapped_station_count": 0 if missing else 2,
            "stations_with_observations": 0 if missing else 1,
            "latest_observation_time": None if missing else "2026-11-09T04:00:00+08:00",
            "latest_values": {"wave_height_m": None if missing else 1.2},
            "variable_coverage": {},
            "status": "no_mapped_station_observations" if missing else "observed",
        })
    return {"source_dataset": scope, "regions": rows}


class LatestRegionalMarineSnapshotTests(unittest.TestCase):
    def test_builds_six_region_snapshot_and_marks_uncovered_hualien_south(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            short, long, output = root / "48h.json", root / "30d.json", root / "latest.json"
            short.write_text(json.dumps(make_summary("O-B0075-001")), encoding="utf-8")
            long.write_text(json.dumps(make_summary("O-B0075-002")), encoding="utf-8")
            result = subprocess.run([
                sys.executable, str(SCRIPT),
                "--observed-48h", str(short), "--observed-30d", str(long),
                "--out", str(output), "--generated-at", "2026-11-09T04:00:00Z"
            ], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(data["source"], "CWA")
            self.assertEqual(len(data["regions"]), 6)
            self.assertEqual(data["regions"]["yilan_suao"]["observed_48h"]["latest_values"]["wave_height_m"], 1.2)
            self.assertEqual(data["regions"]["hualien_south"]["observed_48h"]["coverage_status"], "no_cwa_station_coverage")
            self.assertEqual(data["regions"]["hualien_south"]["observed_30d"]["coverage_status"], "no_cwa_station_coverage")

    def test_rejects_missing_region(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            short, long, output = root / "48h.json", root / "30d.json", root / "latest.json"
            rows = make_summary("O-B0075-001")
            rows["regions"] = rows["regions"][:-1]
            short.write_text(json.dumps(rows), encoding="utf-8")
            long.write_text(json.dumps(make_summary("O-B0075-002")), encoding="utf-8")
            result = subprocess.run([
                sys.executable, str(SCRIPT),
                "--observed-48h", str(short), "--observed-30d", str(long),
                "--out", str(output)
            ], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Region set mismatch", result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
