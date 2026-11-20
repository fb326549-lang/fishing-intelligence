import csv
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).parent
REGISTER=ROOT/"species"/"southern_drummer_response_curve_observations.csv"
sys.path.insert(0, str(ROOT/"species"))
from southern_drummer_context_response_engine import (  # noqa: E402
    compare_observed_points,
    load_temperature_observations,
)

class SouthernDrummerResponseCurveTests(unittest.TestCase):
    def test_observed_curve_points_are_traceable_and_not_scoring_rules(self):
        with REGISTER.open(encoding="utf-8-sig",newline="") as f:
            rows=list(csv.DictReader(f))
        self.assertEqual(len(rows),10)
        self.assertTrue(all(r["candidate_id"]=="c036" for r in rows))
        self.assertTrue(all(r["model_use_status"].startswith("context_only_") for r in rows))
        self.assertTrue(all(r["source_literature_id"] in {"L051","L052","L053"} for r in rows))
        self.assertTrue(all(r["source_url"].startswith("https://") for r in rows))
        self.assertFalse(any(r["model_use_status"]=="eligible_for_indicator_scoring" for r in rows))
        sargassum=[r for r in rows if r["response_group"]=="macroalgae_sst_sargassum"]
        self.assertEqual({r["condition_value"] for r in sargassum},{"30","16","14","12"})
        self.assertEqual({r["observed_response"] for r in sargassum},{"4.5","2.4","0.3","0.1"})
        diel=next(r for r in rows if r["response_curve_id"]=="RC03611")
        self.assertEqual(diel["observed_response"],"45.6")
        self.assertIn("P=0.12",diel["limitations"])
        pooled=next(r for r in rows if r["response_curve_id"]=="RC03607")
        self.assertIn("four tested 3-hour windows",pooled["temporal_window"])
        self.assertIn("does not provide separate values",pooled["limitations"])

    def test_same_alga_observed_temperature_points_are_compared_without_becoming_score(self):
        observations=load_temperature_observations(REGISTER)
        result=compare_observed_points(observations,"macroalgae_sst_sargassum",30,16)
        self.assertEqual(result["status"],"observed_point_comparison")
        self.assertEqual(result["reference_rate"],4.5)
        self.assertEqual(result["comparison_rate"],2.4)
        self.assertEqual(result["rate_ratio_reference_over_comparison"],1.875)
        self.assertFalse(result["is_fci_score"])
        self.assertFalse(result["is_fishing_probability"])
        self.assertFalse(result["interpolation_performed"])
        self.assertEqual(result["evidence_ids"],["L052"])

    def test_unobserved_temperature_returns_missing_instead_of_interpolating(self):
        observations=load_temperature_observations(REGISTER)
        result=compare_observed_points(observations,"macroalgae_sst_sargassum",15,16)
        self.assertEqual(result["status"],"no_exact_observed_point")
        self.assertIsNone(result["reference_rate"])
        self.assertIsNone(result["rate_ratio_reference_over_comparison"])
        self.assertFalse(result["interpolation_performed"])

    def test_temperature_comparison_never_combines_different_algae(self):
        observations=load_temperature_observations(REGISTER)
        result=compare_observed_points(observations,"macroalgae_sst_eisenia",30,16)
        self.assertEqual(result["status"],"no_exact_observed_point")
        self.assertIsNone(result["comparison_rate"])

if __name__=="__main__":
    unittest.main()
