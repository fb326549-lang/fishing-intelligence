import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent/"species"))
from integrate_environment_and_activity import build_integrated_rows

class IntegratedActivityTests(unittest.TestCase):
    def setUp(self):
        self.env=[{"region_id":"taitung_south","valid_time":"2026-11-09T12:00:00+08:00","data_type":"forecast","environment":{}}]
        self.candidates=[
            {"candidate_id":"c003","common_name_zh":"臭肚","scientific_name":"Siganus fuscescens","eligibility_gate":"verified_taxon"},
            {"candidate_id":"c002","common_name_zh":"白毛","scientific_name":"Kyphosus spp.","eligibility_gate":"white_hair_is_kyphosus_genus_group_species_identification_required"},
        ]
        self.matches=[
            {"candidate_id":"c003","region_id":"taitung_south","valid_time":"2026-11-09T12:00:00+08:00","data_type":"forecast","status":"insufficient_evidence","environment_match_score":"","rule_coverage":"0"},
            {"candidate_id":"c002","region_id":"taitung_south","valid_time":"2026-11-09T12:00:00+08:00","status":"taxon_or_distribution_gate","environment_match_score":"","rule_coverage":"0"},
        ]
        self.activity=[{"candidate_id":"c003","activity_evidence_id":"AE003","model_use_status":"context_only_captive_feeding","transferability":"low_for_wild_east_taiwan_angler_prediction"}]
        self.seasonal=[{"candidate_id":"c003","seasonal_evidence_id":"SE003","model_use_status":"context_only_northern_taiwan_field_study","transferability":"low_for_east_taiwan"}]

    def test_context_only_evidence_does_not_create_activity_score(self):
        rows=build_integrated_rows(self.env,self.candidates,self.matches,self.activity,self.seasonal)
        fish=next(r for r in rows if r["candidate_id"]=="c003")
        self.assertEqual(fish["activity_evidence_status"],"context_only_evidence_available")
        self.assertEqual(fish["activity_evidence_count"],"1")
        self.assertEqual(fish["seasonal_evidence_count"],"1")
        self.assertEqual(fish["activity_score"],"")
        self.assertEqual(fish["catch_probability"],"")
        self.assertEqual(fish["best_fishing_window_status"],"not_established")

    def test_taxonomy_gate_remains_blocked_even_with_no_match_score(self):
        rows=build_integrated_rows(self.env,self.candidates,self.matches,self.activity,self.seasonal)
        fish=next(r for r in rows if r["candidate_id"]=="c002")
        self.assertEqual(fish["activity_evidence_status"],"taxon_or_distribution_gate")
        self.assertEqual(fish["activity_score"],"")

    def test_environment_match_score_is_separate_from_activity_status(self):
        rows=build_integrated_rows(self.env,self.candidates,self.matches,self.activity,self.seasonal)
        fish=next(r for r in rows if r["candidate_id"]=="c003")
        self.assertEqual(fish["environment_match_status"],"insufficient_evidence")
        self.assertEqual(fish["environment_match_score"],"")
        self.assertEqual(fish["interpretation"],"environment_match_is_not_fish_activity_or_catch_probability")

    def test_missing_match_row_is_explicit(self):
        rows=build_integrated_rows(self.env,self.candidates,[],self.activity,self.seasonal)
        fish=next(r for r in rows if r["candidate_id"]=="c003")
        self.assertEqual(fish["environment_match_status"],"missing_environment_match_result")

    def test_duplicate_match_keys_are_rejected(self):
        with self.assertRaisesRegex(ValueError,"duplicate environment match"):
            build_integrated_rows(self.env,self.candidates,self.matches+self.matches[:1],self.activity,self.seasonal)

    def test_conflicting_candidate_gates_are_rejected(self):
        bad=self.candidates+[dict(self.candidates[0],eligibility_gate="regional_occurrence_conflict_requires_review")]
        with self.assertRaisesRegex(ValueError,"conflicting eligibility_gate"):
            build_integrated_rows(self.env,bad,self.matches,self.activity,self.seasonal)

if __name__=="__main__": unittest.main()
