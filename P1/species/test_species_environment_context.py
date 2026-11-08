#!/usr/bin/env python3
"""Offline tests for evidence-gated species/environment context generation."""
import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("build_species_environment_context.py")

def write_csv(path, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

class SpeciesEnvironmentContextTests(unittest.TestCase):
    def test_generates_context_without_inventing_activity_scores(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            species = root / "species"
            species.mkdir()
            write_csv(species / "species_candidate_register.csv", [{
                "candidate_id": "c001", "common_name_zh": "黑毛",
                "fishery_group": "礁岩磯釣", "scientific_name": "Girella punctata",
                "regional_evidence_status": "regional_distribution_documented",
                "taxonomy_status": "verified_taxon",
            }, {
                "candidate_id": "c002", "common_name_zh": "待確認魚",
                "fishery_group": "未知", "scientific_name": "",
                "regional_evidence_status": "pending", "taxonomy_status": "pending",
            }])
            write_csv(species / "species_evidence_register.csv", [{
                "evidence_id": "E001", "candidate_id": "c001", "confidence": "high",
            }])
            write_csv(species / "species_ecology_parameters.csv", [{
                "ecology_record_id": "EP001", "candidate_id": "c001",
                "parameter_code": "habitat", "parameter_value": "reef;coastal",
                "model_use_status": "eligible_as_species_context", "evidence_id": "E001",
            }])
            forecast = root / "regional.csv"
            write_csv(forecast, [{
                "region_id": "taitung_south", "horizon_hours": "6",
                "target_time": "2026-11-08T22:00:00+08:00",
                "wave_height_m": "1.2", "wave_period_s": "7",
                "sea_surface_temperature_c": "", "sea_level_height_msl_m": "",
                "ocean_current_velocity_ms": "0.3", "wind_speed_10m_ms": "4",
                "wind_direction_10m_deg": "90",
            }])
            output = root / "context.csv"
            subprocess.run([
                sys.executable, str(SCRIPT), "--species-dir", str(species),
                "--regional-forecast", str(forecast), "--out", str(output),
            ], check=True, capture_output=True, text=True)
            with output.open(encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["candidate_id"], "c001")
            self.assertEqual(rows[0]["environment_available_count"], "5")
            self.assertEqual(rows[0]["environment_score"], "")
            self.assertEqual(rows[0]["activity_score"], "")
            self.assertEqual(rows[0]["catch_probability"], "")
            self.assertIn("insufficient_species_specific_response_parameters", rows[0]["model_readiness"])
            summary = json.loads((root / "species_environment_context_summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["activity_scores_generated"], 0)
            self.assertEqual(summary["catch_probabilities_generated"], 0)

if __name__ == "__main__":
    unittest.main()
