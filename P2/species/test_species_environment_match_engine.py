#!/usr/bin/env python3
"""Offline regression tests for evidence-gated environmental matching."""
import csv
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from environment_match_engine import RULE_FIELDS, evaluate, load_rules


class EnvironmentMatchEngineTests(unittest.TestCase):
    def setUp(self):
        self.environment = [{
            "region_id": "chenggong_donghe",
            "valid_time": "2026-11-10T08:00:00+08:00",
            "data_type": "forecast",
            "environment": {"wave_height_m": 1.2},
        }]
        self.verified = [{"candidate_id": "c-test", "eligibility_gate": "verified_taxon"}]
        self.blocked = [{"candidate_id": "c-test", "eligibility_gate": "white_hair_is_kyphosus_genus_group_species_identification_required"}]

    def rule(self, **overrides):
        row = {field: "" for field in RULE_FIELDS}
        row.update({
            "rule_id": "R001", "candidate_id": "c-test",
            "environment_field": "wave_height_m", "operator": "between",
            "minimum": "0.5", "maximum": "1.5",
            "match_score": "80", "weight": "1",
            "region_scope": "chenggong_donghe", "life_stage": "adult",
            "evidence_id": "E-LOCAL-001", "source_url": "https://example.org/evidence",
            "confidence": "high", "evidence_basis": "east_taiwan_direct_field",
            "model_use_status": "eligible_for_environment_scoring",
            "reviewed_by": "independent_reviewer", "reviewed_at": "2026-11-10",
        })
        row.update(overrides)
        return row

    def write_rules(self, rows):
        tmp = tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="", delete=False, suffix=".csv")
        with tmp:
            writer = csv.DictWriter(tmp, fieldnames=sorted(RULE_FIELDS))
            writer.writeheader()
            writer.writerows(rows)
        self.addCleanup(Path(tmp.name).unlink, missing_ok=True)
        return Path(tmp.name)

    def test_context_only_or_nonlocal_evidence_never_enters_scoring(self):
        path = self.write_rules([
            self.rule(model_use_status="context_only_external_region"),
            self.rule(rule_id="R002", evidence_basis="species_profile_only"),
        ])
        self.assertEqual(load_rules(path), [])

    def test_no_approved_rules_returns_insufficient_evidence_not_zero_score(self):
        result = evaluate(self.environment, self.verified, [])
        self.assertEqual(result[0]["status"], "insufficient_evidence")
        self.assertEqual(result[0]["environment_match_score"], "")
        self.assertEqual(result[0]["interpretation"], "not_fish_activity_or_catch_probability")

    def test_reviewed_east_taiwan_direct_rule_is_traceable(self):
        rules = load_rules(self.write_rules([self.rule()]))
        result = evaluate(self.environment, self.verified, rules)[0]
        self.assertEqual(result["status"], "scored")
        self.assertEqual(result["environment_match_score"], "80.00")
        self.assertEqual(result["rule_coverage"], "1.0000")
        self.assertEqual(result["interpretation"], "environment_match_only_not_fish_activity_or_catch_probability")
        self.assertIn('"evidence_id":"E-LOCAL-001"', result["rule_evidence_trace_json"])

    def test_taxonomic_alias_gate_blocks_even_a_reviewed_rule(self):
        rules = load_rules(self.write_rules([self.rule()]))
        result = evaluate(self.environment, self.blocked, rules)[0]
        self.assertEqual(result["status"], "taxon_or_distribution_gate")
        self.assertEqual(result["environment_match_score"], "")
        self.assertEqual(result["rules_evaluated"], "0")

    def test_approved_rule_requires_reviewer_and_east_taiwan_direct_basis(self):
        with self.assertRaisesRegex(ValueError, "reviewer and review date"):
            load_rules(self.write_rules([self.rule(reviewed_by="", reviewed_at="")]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
