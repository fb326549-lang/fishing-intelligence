import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "species"))
from indicator_score_engine import assess_hour, load_rules, load_weights, rank_best_hours

CANDIDATES = [{
    "candidate_id": "c036",
    "common_name_zh": "南方舵魚",
    "scientific_name": "Kyphosus bigibbus",
    "eligibility_gate": "verified_taxon",
}]

def rule(rid, indicator, field, minimum, maximum, score):
    return {
        "rule_id": rid, "candidate_id": "c036", "indicator_code": indicator,
        "response_group": rid, "environment_field": field, "operator": "between",
        "minimum": str(minimum), "maximum": str(maximum),
        "match_score": str(score), "weight": "1",
        "region_scope": "all_east_taiwan", "life_stage": "adult",
        "evidence_id": "EAST-FIELD-001", "source_url": "https://example.org/east-field",
        "confidence": "high", "evidence_basis": "east_taiwan_direct_field",
        "model_use_status": "eligible_for_indicator_scoring",
        "reviewed_by": "test-reviewer", "reviewed_at": "2026-11-10",
        "limitations": "Synthetic test fixture only",
    }

class IndicatorScoreEngineTests(unittest.TestCase):
    def setUp(self):
        self.record = {
            "region_id": "taitung_south",
            "valid_time": "2026-11-10T12:00:00+08:00",
            "data_type": "forecast",
            "environment": {
                "sea_surface_temperature_c": 25,
                "wave_height_m": 0.8,
                "sunrise": "2026-11-10T05:55:00+08:00",
                "sunset": "2026-11-10T17:05:00+08:00",
            },
        }
        self.rule_rows = [
            rule("F1", "feeding_condition", "sea_surface_temperature_c", 20, 30, 80),
            rule("E1", "environment_suitability", "wave_height_m", 0, 1.2, 70),
            rule("A1", "fish_activity", "daylight", 1, 1, 90),
        ]
        self.weight_rows = [{
            "candidate_id": "c036", "feeding_weight": "0.40",
            "environment_weight": "0.35", "activity_weight": "0.25",
            "evidence_basis": "east_taiwan_catch_validation",
            "model_use_status": "eligible_for_composite_scoring",
            "source_ids": "LOCAL-CATCH-001", "reviewed_by": "test-reviewer",
            "reviewed_at": "2026-11-10", "notes": "Synthetic test fixture only",
        }]

    def test_three_indicator_scores_and_species_weighted_composite(self):
        rules = load_rules(self.rule_rows, CANDIDATES)
        weights = load_weights(self.weight_rows, CANDIDATES)
        rows = assess_hour(self.record, CANDIDATES, rules, weights)
        fish = rows[0]
        self.assertEqual(fish["feeding_condition_score"], "80.00")
        self.assertEqual(fish["environment_suitability_score"], "70.00")
        self.assertEqual(fish["fish_activity_score"], "90.00")
        self.assertEqual(fish["overall_fish_condition_index"], "80.00")
        self.assertEqual(fish["model_status"], "scored")
        self.assertEqual(fish["best_hour_status"], "rankable")

    def test_missing_indicator_prevents_composite_score(self):
        rules = load_rules(self.rule_rows[:2], CANDIDATES)
        weights = load_weights(self.weight_rows, CANDIDATES)
        fish = assess_hour(self.record, CANDIDATES, rules, weights)[0]
        self.assertEqual(fish["feeding_condition_score"], "80.00")
        self.assertEqual(fish["environment_suitability_score"], "70.00")
        self.assertEqual(fish["fish_activity_score"], "")
        self.assertEqual(fish["overall_fish_condition_index"], "")
        self.assertEqual(fish["model_status"], "one_or_more_indicators_unavailable")

    def test_unvalidated_species_weights_prevent_composite_score(self):
        rules = load_rules(self.rule_rows, CANDIDATES)
        weights = load_weights([], CANDIDATES)
        fish = assess_hour(self.record, CANDIDATES, rules, weights)[0]
        self.assertEqual(fish["feeding_condition_score"], "80.00")
        self.assertEqual(fish["environment_suitability_score"], "70.00")
        self.assertEqual(fish["fish_activity_score"], "90.00")
        self.assertEqual(fish["overall_fish_condition_index"], "")
        self.assertEqual(fish["model_status"], "species_weights_not_validated")

    def test_context_only_or_non_east_taiwan_rule_never_scores(self):
        context = dict(self.rule_rows[0], model_use_status="context_only_external_region",
                       evidence_basis="external_region")
        rules = load_rules([context], CANDIDATES)
        self.assertEqual(rules, [])
        fish = assess_hour(self.record, CANDIDATES, rules, {})[0]
        self.assertEqual(fish["feeding_condition_score"], "")
        self.assertEqual(fish["overall_fish_condition_index"], "")

    def test_taxonomy_gate_prevents_all_indicator_scores(self):
        gated = [dict(CANDIDATES[0], eligibility_gate="white_hair_is_kyphosus_genus_group_species_identification_required")]
        rules = load_rules(self.rule_rows, CANDIDATES)
        weights = load_weights(self.weight_rows, CANDIDATES)
        fish = assess_hour(self.record, gated, rules, weights)[0]
        self.assertEqual(fish["model_status"], "taxon_or_distribution_gate")
        self.assertEqual(fish["overall_fish_condition_index"], "")

    def test_best_hour_ranking_only_uses_fully_scored_hours(self):
        base = {
            "candidate_id": "c036", "region_id": "taitung_south", "data_type": "forecast",
            "overall_fish_condition_index": "75.00", "valid_time": "2026-11-10T10:00:00+08:00",
        }
        other = dict(base, overall_fish_condition_index="88.00", valid_time="2026-11-10T11:00:00+08:00")
        missing = dict(base, overall_fish_condition_index="", valid_time="2026-11-10T12:00:00+08:00")
        ranked = rank_best_hours([base, other, missing])
        self.assertEqual(next(r for r in ranked if r["valid_time"] == other["valid_time"])["best_hour_status"], "best_hour")
        self.assertEqual(next(r for r in ranked if r["valid_time"] == missing["valid_time"])["best_hour_status"], "unscored_hour")

    def test_rule_cannot_score_without_direct_east_taiwan_basis(self):
        bad = dict(self.rule_rows[0], evidence_basis="western_taiwan_fishery")
        with self.assertRaisesRegex(ValueError, "East Taiwan direct field"):
            load_rules([bad], CANDIDATES)

    def test_species_weights_must_sum_to_one(self):
        bad = dict(self.weight_rows[0], activity_weight="0.30")
        with self.assertRaisesRegex(ValueError, "sum to 1"):
            load_weights([bad], CANDIDATES)

if __name__ == "__main__":
    unittest.main()
