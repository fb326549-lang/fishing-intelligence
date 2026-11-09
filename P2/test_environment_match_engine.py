import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "species"))
from environment_match_engine import evaluate, load_rules

FIELDS = ["rule_id","candidate_id","environment_field","operator","minimum","maximum","match_score","weight","region_scope","life_stage","evidence_id","source_url","confidence","evidence_basis","model_use_status","reviewed_by","reviewed_at"]

def load_fixture_rules(rows):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "rules.csv"
        with path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS)
            w.writeheader()
            w.writerows(rows)
        return load_rules(path)

def rule(**overrides):
    row = {
        "rule_id":"R1","candidate_id":"c003","environment_field":"sea_surface_temperature_c",
        "operator":"between","minimum":"20","maximum":"28","match_score":"85","weight":"1",
        "region_scope":"taitung_south","life_stage":"adult","evidence_id":"E1",
        "source_url":"https://example.org/study","confidence":"high",
        "evidence_basis":"east_taiwan_direct_field",
        "model_use_status":"eligible_for_environment_scoring",
        "reviewed_by":"reviewer","reviewed_at":"2026-11-09"
    }
    row.update(overrides)
    return row

class EnvironmentMatchEngineTests(unittest.TestCase):
    def setUp(self):
        self.candidates = [
            {"candidate_id":"c003","eligibility_gate":"verified_taxon"},
            {"candidate_id":"c002","eligibility_gate":"white_hair_is_kyphosus_genus_group_species_identification_required"},
        ]
        self.environment = [{
            "region_id":"taitung_south","valid_time":"2026-11-09T12:00:00+08:00",
            "environment":{"sea_surface_temperature_c":24}
        }]

    def test_no_approved_rules_returns_insufficient_evidence(self):
        rows = evaluate(self.environment, self.candidates, [])
        rabbit = next(r for r in rows if r["candidate_id"] == "c003")
        self.assertEqual(rabbit["status"], "insufficient_evidence")
        self.assertEqual(rabbit["environment_match_score"], "")

    def test_only_approved_direct_east_taiwan_rule_can_score(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rules.csv"
            with path.open("w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=FIELDS)
                w.writeheader()
                w.writerow(rule())
                w.writerow(rule(rule_id="R2", evidence_basis="external_region", model_use_status="context_only_external_region"))
            approved = load_rules(path)
            rows = evaluate(self.environment, self.candidates, approved)
            rabbit = next(r for r in rows if r["candidate_id"] == "c003")
            self.assertEqual(rabbit["status"], "scored")
            self.assertEqual(rabbit["environment_match_score"], "85.00")
            self.assertEqual(rabbit["rule_coverage"], "1.0000")
            self.assertEqual(rabbit["rules_matched"], "1")
            self.assertEqual(rabbit["rules_evaluated"], "1")
            trace = json.loads(rabbit["rule_evidence_trace_json"])
            self.assertEqual(len(trace), 1)
            self.assertEqual(trace[0]["rule_id"], "R1")
            self.assertEqual(trace[0]["evidence_id"], "E1")
            self.assertEqual(trace[0]["observed_value"], 24)
            self.assertTrue(trace[0]["match"])
            self.assertEqual(rabbit["interpretation"], "environment_match_only_not_fish_activity_or_catch_probability")

    def test_non_matching_environment_value_contributes_zero(self):
        env = [{
            "region_id":"taitung_south","valid_time":"2026-11-09T12:00:00+08:00",
            "environment":{"sea_surface_temperature_c":32}
        }]
        rows = evaluate(env, self.candidates[:1], load_fixture_rules([rule()]))
        self.assertEqual(rows[0]["environment_match_score"], "0.00")
        self.assertEqual(rows[0]["rules_matched"], "0")
        self.assertEqual(rows[0]["rules_evaluated"], "1")

    def test_weighted_score_uses_match_result_for_each_rule(self):
        env = [{
            "region_id":"taitung_south","valid_time":"2026-11-09T12:00:00+08:00",
            "environment":{"sea_surface_temperature_c":24,"wind_speed_10m_ms":3}
        }]
        rules = [
            rule(weight="2"),
            rule(rule_id="R2",environment_field="wind_speed_10m_ms",operator="at_least",
                 minimum="5",maximum="",match_score="70",weight="1")
        ]
        rows = evaluate(env, self.candidates[:1], load_fixture_rules(rules))
        self.assertEqual(rows[0]["environment_match_score"], "56.67")
        self.assertEqual(rows[0]["rules_matched"], "1")
        self.assertEqual(rows[0]["rules_evaluated"], "2")
        self.assertEqual(rows[0]["rule_coverage"], "1.0000")

    def test_taxonomy_gate_prevents_scoring(self):
        rows = evaluate(self.environment, self.candidates, load_fixture_rules([rule()]))
        white = next(r for r in rows if r["candidate_id"] == "c002")
        self.assertEqual(white["status"], "taxon_or_distribution_gate")
        self.assertEqual(white["environment_match_score"], "")

    def test_missing_environment_field_reports_partial_coverage(self):
        env = [{"region_id":"taitung_south","valid_time":"2026-11-09T12:00:00+08:00","environment":{}}]
        rows = evaluate(env, self.candidates[:1], load_fixture_rules([rule()]))
        self.assertEqual(rows[0]["status"], "insufficient_environment_data")
        self.assertEqual(rows[0]["rule_coverage"], "0.0000")
        self.assertEqual(rows[0]["rules_evaluated"], "0")
        self.assertEqual(json.loads(rows[0]["rule_evidence_trace_json"]), [])

    def test_approved_rule_requires_review_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rules.csv"
            bad = rule(reviewed_by="")
            with path.open("w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=FIELDS)
                w.writeheader()
                w.writerow(bad)
            with self.assertRaisesRegex(ValueError, "reviewer and review date"):
                load_rules(path)

if __name__ == "__main__":
    unittest.main()
