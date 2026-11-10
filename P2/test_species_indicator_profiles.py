import csv
import unittest
from pathlib import Path

ROOT=Path(__file__).parent
PROFILE=ROOT/"species"/"species_indicator_model_profiles.csv"

class SpeciesIndicatorProfileTests(unittest.TestCase):
    def test_four_requested_species_have_separate_evidence_gated_profiles(self):
        with PROFILE.open(encoding="utf-8-sig",newline="") as f:
            rows=list(csv.DictReader(f))
        self.assertEqual({r["candidate_id"] for r in rows},{"c001","c003","c004","c036"})
        self.assertEqual(len(rows),4)
        for row in rows:
            self.assertTrue(row["feeding_ecology"])
            self.assertTrue(row["feeding_condition_candidate_inputs"])
            self.assertTrue(row["environment_habitat"])
            self.assertTrue(row["environment_suitability_candidate_inputs"])
            self.assertTrue(row["activity_ecology"])
            self.assertTrue(row["fish_activity_candidate_inputs"])
            self.assertTrue(row["source_record_ids"])
            self.assertTrue(row["model_blockers"])
            self.assertTrue(row["feeding_model_status"].startswith("context_only_"))
            self.assertTrue(row["environment_model_status"].startswith("context_only_"))
            self.assertTrue(row["activity_model_status"].startswith("context_only_"))

    def test_species_specific_taxon_limits_are_preserved(self):
        with PROFILE.open(encoding="utf-8-sig",newline="") as f:
            rows={r["candidate_id"]:r for r in csv.DictReader(f)}
        self.assertIn("K. bigibbus",rows["c036"]["model_blockers"])
        self.assertIn("西部",rows["c004"]["model_blockers"])
        self.assertIn("鑑種",rows["c001"]["model_blockers"])

if __name__=="__main__": unittest.main()
