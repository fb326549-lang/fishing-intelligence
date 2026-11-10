import csv
import json
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
            {"candidate_id":"c027","common_name_zh":"條紋豆娘魚","scientific_name":"Abudefduf vaigiensis","eligibility_gate":"verified_taxon"},
            {"candidate_id":"c036","common_name_zh":"南方舵魚","scientific_name":"Kyphosus bigibbus","eligibility_gate":"verified_taxon"},
            {"candidate_id":"c037","common_name_zh":"天竺舵魚","scientific_name":"Kyphosus cinerascens","eligibility_gate":"verified_taxon"},
            {"candidate_id":"c001","common_name_zh":"瓜子鱲","scientific_name":"Girella punctata","eligibility_gate":"verified_taxon"},
        ]
        self.matches=[
            {"candidate_id":"c003","region_id":"taitung_south","valid_time":"2026-11-09T12:00:00+08:00","data_type":"forecast","status":"insufficient_evidence","environment_match_score":"","rule_coverage":"0"},
            {"candidate_id":"c002","region_id":"taitung_south","valid_time":"2026-11-09T12:00:00+08:00","status":"taxon_or_distribution_gate","environment_match_score":"","rule_coverage":"0"},
            {"candidate_id":"c036","region_id":"taitung_south","valid_time":"2026-11-09T12:00:00+08:00","data_type":"forecast","status":"insufficient_evidence","environment_match_score":"","rule_coverage":"0"},
            {"candidate_id":"c037","region_id":"taitung_south","valid_time":"2026-11-09T12:00:00+08:00","data_type":"forecast","status":"insufficient_evidence","environment_match_score":"","rule_coverage":"0"},
            {"candidate_id":"c001","region_id":"taitung_south","valid_time":"2026-11-09T12:00:00+08:00","data_type":"forecast","status":"insufficient_evidence","environment_match_score":"","rule_coverage":"0"},
        ]
        self.activity=[
            {"candidate_id":"c003","activity_evidence_id":"AE003","activity_dimension":"diel_feeding","evidence_kind":"captive_feeding_trial","geographic_scope":"Japan, southern Kii Peninsula","study_period":"2006 publication","life_stage":"not_separately_specified","method":"controlled algae-feeding study","source_literature_id":"L005","source_url":"https://www.jstage.jst.go.jp/article/fisheng/43/1/43_KJ00004558953/_article/-char/en","confidence":"medium","model_use_status":"context_only_captive_feeding","transferability":"low_for_wild_east_taiwan_angler_prediction","limitations":"Captive feeding is not wild bite activity."},
            {"candidate_id":"c027","activity_evidence_id":"AE011","activity_dimension":"occurrence_record","evidence_kind":"verified_museum_specimen","geographic_scope":"Taitung, Taiwan","study_period":"2005-10-06","source_literature_id":"L025","source_url":"https://fishdb.sinica.edu.tw/muse/digi_object/0370d946f2c769aac414b179f3786f0b","confidence":"high","model_use_status":"context_only_east_taiwan_occurrence","transferability":"high_for_occurrence_only_no_activity_transfer","limitations":"Occurrence only."},
            {"candidate_id":"c036","activity_evidence_id":"AE014","activity_dimension":"occurrence_record","model_use_status":"context_only_east_taiwan_occurrence","transferability":"high_for_occurrence_only_no_activity_transfer"},
            {"candidate_id":"c037","activity_evidence_id":"AE015","activity_dimension":"occurrence_record","model_use_status":"context_only_east_taiwan_occurrence","transferability":"high_for_occurrence_only_no_activity_transfer"},
            {"candidate_id":"c001","activity_evidence_id":"AE013","activity_dimension":"occurrence_record","model_use_status":"context_only_east_taiwan_occurrence","transferability":"high_for_occurrence_only_no_activity_transfer"},
        ]
        self.seasonal=[{"candidate_id":"c003","seasonal_evidence_id":"SE003","reported_season":"春季至6月上旬","geographic_scope":"Shimen coast, northern Taiwan","model_use_status":"context_only_northern_taiwan_field_study","transferability":"low_for_east_taiwan","limitations":"Secondary northern Taiwan context only."}]

    def test_context_only_evidence_does_not_create_activity_score(self):
        rows=build_integrated_rows(self.env,self.candidates,self.matches,self.activity,self.seasonal)
        fish=next(r for r in rows if r["candidate_id"]=="c003")
        self.assertEqual(fish["activity_evidence_status"],"context_only_evidence_available")
        self.assertEqual(fish["activity_evidence_count"],"1")
        self.assertEqual(fish["seasonal_evidence_count"],"1")
        seasonal_context=json.loads(fish["seasonal_evidence_context_json"])
        self.assertEqual(seasonal_context[0]["id"],"SE003")
        self.assertIn("Shimen coast",seasonal_context[0]["geographic_scope"])
        self.assertTrue(seasonal_context[0]["limitations"])
        self.assertEqual(fish["activity_score"],"")
        self.assertEqual(fish["catch_probability"],"")
        self.assertEqual(fish["best_fishing_window_status"],"not_established")

    def test_east_taiwan_occurrence_does_not_become_activity_evidence(self):
        rows=build_integrated_rows(self.env,self.candidates,self.matches,self.activity,self.seasonal)
        fish=next(r for r in rows if r["candidate_id"]=="c027")
        self.assertEqual(fish["activity_evidence_status"],"context_only_evidence_available")
        self.assertEqual(fish["activity_evidence_count"],"0")
        self.assertEqual(fish["occurrence_evidence_count"],"1")
        self.assertEqual(fish["occurrence_evidence_ids"],"AE011")
        self.assertEqual(fish["activity_score"],"")
        self.assertEqual(fish["catch_probability"],"")
        self.assertEqual(fish["best_fishing_window_status"],"not_established")

    def test_east_taiwan_occurrence_context_is_added_to_verified_kyphosus_species(self):
        rows=build_integrated_rows(self.env,self.candidates,self.matches,self.activity,self.seasonal)
        for cid in ("c036","c037"):
            fish=next(r for r in rows if r["candidate_id"]==cid)
            self.assertEqual(fish["activity_evidence_status"],"context_only_evidence_available")
            self.assertEqual(fish["activity_evidence_count"],"0")
            self.assertEqual(fish["occurrence_evidence_count"],"1")
            self.assertEqual(fish["activity_score"],"")
            self.assertEqual(fish["catch_probability"],"")
            self.assertEqual(fish["best_fishing_window_status"],"not_established")

    def test_black_hair_candidate_catch_record_does_not_create_activity_score(self):
        rows=build_integrated_rows(self.env,self.candidates,self.matches,self.activity,self.seasonal)
        fish=next(r for r in rows if r["candidate_id"]=="c001")
        self.assertEqual(fish["activity_evidence_status"],"context_only_evidence_available")
        self.assertEqual(fish["activity_evidence_count"],"0")
        self.assertEqual(fish["occurrence_evidence_count"],"1")
        self.assertEqual(fish["activity_score"],"")
        self.assertEqual(fish["catch_probability"],"")
        self.assertEqual(fish["best_fishing_window_status"],"not_established")

    def test_taxonomy_gate_remains_blocked_even_with_no_match_score(self):
        rows=build_integrated_rows(self.env,self.candidates,self.matches,self.activity,self.seasonal)
        fish=next(r for r in rows if r["candidate_id"]=="c002")
        self.assertEqual(fish["activity_evidence_status"],"taxon_or_distribution_gate")
        self.assertEqual(fish["activity_score"],"")


    def test_southern_drummer_context_studies_do_not_create_activity_score(self):
        register=Path(__file__).parent/"species"/"species_activity_evidence_register.csv"
        with register.open(encoding="utf-8-sig",newline="") as f:
            evidence=list(csv.DictReader(f))
        southern=[r for r in evidence if r["candidate_id"]=="c036" and r["activity_evidence_id"] in {"AE017","AE018","AE019","AE020"}]
        self.assertEqual(len(southern),4)
        rows=build_integrated_rows(self.env,self.candidates,self.matches,self.activity+southern,self.seasonal)
        fish=next(r for r in rows if r["candidate_id"]=="c036")
        self.assertEqual(fish["activity_evidence_status"],"context_only_evidence_available")
        self.assertEqual(fish["activity_evidence_count"],"4")
        self.assertEqual(fish["activity_score"],"")
        self.assertEqual(fish["catch_probability"],"")
        self.assertEqual(fish["best_fishing_window_status"],"not_established")
        context=json.loads(fish["activity_evidence_context_json"])
        self.assertEqual({x["id"] for x in context},{"AE017","AE018","AE019","AE020"})
        self.assertTrue(all(x["model_use_status"].startswith("context_only_") for x in context))

    def test_environment_match_score_is_separate_from_activity_status(self):
        rows=build_integrated_rows(self.env,self.candidates,self.matches,self.activity,self.seasonal)
        fish=next(r for r in rows if r["candidate_id"]=="c003")
        self.assertEqual(fish["environment_match_status"],"insufficient_evidence")
        self.assertEqual(fish["environment_match_score"],"")
        self.assertEqual(fish["interpretation"],"environment_match_is_not_fish_activity_or_catch_probability")


    def test_approved_environment_rule_provenance_is_carried_forward(self):
        matches=[dict(self.matches[0],status="scored",environment_match_score="85.00",
            rule_coverage="1.0000",
            rule_evidence_trace_json='[{"rule_id":"R1","evidence_id":"E1","source_url":"https://example.org/rule","valid_time":"2026-11-09T12:00:00+08:00","match":true}]')]
        rows=build_integrated_rows(self.env,self.candidates,matches,self.activity,self.seasonal)
        fish=next(r for r in rows if r["candidate_id"]=="c003")
        self.assertIn('"rule_id":"R1"',fish["rule_evidence_trace_json"])
        self.assertIn('"evidence_id":"E1"',fish["rule_evidence_trace_json"])

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
