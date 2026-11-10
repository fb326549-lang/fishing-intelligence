import csv
import unittest
from pathlib import Path

REGISTER=Path(__file__).parent/"species"/"fishery_effort_study_register.csv"

class FisheryEffortStudyRegisterTests(unittest.TestCase):
    def test_effort_methods_are_traceable_and_nonlocal_studies_are_not_east_taiwan_weights(self):
        with REGISTER.open(encoding="utf-8-sig",newline="") as f:
            rows=list(csv.DictReader(f))
        self.assertEqual(len(rows),4)
        by_id={r["effort_source_id"]:r for r in rows}
        self.assertEqual(set(by_id),{"EV001","EV002","EV003","EV004"})
        self.assertIn("非必填",by_id["EV001"]["effort_measure"])
        self.assertIn("3–4小時",by_id["EV002"]["sampling_design"])
        self.assertIn("Kyphosus spp.",by_id["EV002"]["target_taxon_scope"])
        self.assertIn("1.37±2.99",by_id["EV003"]["reported_result"])
        self.assertIn("65%",by_id["EV003"]["reported_result"])
        self.assertEqual(by_id["EV004"]["model_use_status"],"awaiting_full_report_review")
        self.assertTrue(all(r["source_url"].startswith("https://") for r in rows))
        self.assertFalse(any(r["model_use_status"]=="east_taiwan_effort_validated_catch" for r in rows))

if __name__=="__main__": unittest.main()
