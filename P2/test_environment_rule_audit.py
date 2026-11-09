import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "species"))
from audit_environment_response_rules import audit_rules

def candidate(gate="verified_taxon"):
    return {"candidate_id":"c003","eligibility_gate":gate}

def rule(**changes):
    row = {
        "rule_id":"R1","candidate_id":"c003","environment_field":"sea_surface_temperature_c",
        "operator":"between","minimum":"20","maximum":"28","match_score":"85","weight":"1",
        "region_scope":"taitung_south","life_stage":"adult","evidence_id":"E1",
        "source_url":"https://example.org/study","confidence":"high",
        "evidence_basis":"east_taiwan_direct_field",
        "model_use_status":"eligible_for_environment_scoring",
        "reviewed_by":"reviewer","reviewed_at":"2026-11-09"
    }
    row.update(changes)
    return row

class EnvironmentRuleAuditTests(unittest.TestCase):
    def test_fully_reviewed_direct_rule_is_approved(self):
        result = audit_rules([rule()], [candidate()])[0]
        self.assertEqual(result["audit_status"], "approved_for_scoring")
        self.assertEqual(result["rejection_reasons"], "")

    def test_external_or_context_only_rule_is_excluded_with_reasons(self):
        result = audit_rules([rule(evidence_basis="external_region",
            model_use_status="context_only_external_region")], [candidate()])[0]
        self.assertEqual(result["audit_status"], "excluded")
        self.assertIn("evidence_not_direct_east_taiwan_field", result["rejection_reasons"])
        self.assertIn("model_use_status_not_approved", result["rejection_reasons"])

    def test_taxonomy_gate_blocks_rule_even_when_other_fields_are_valid(self):
        result = audit_rules([rule()], [candidate("white_hair_is_kyphosus_genus_group_species_identification_required")])[0]
        self.assertEqual(result["audit_status"], "excluded")
        self.assertIn("candidate_taxonomy_or_distribution_gate", result["rejection_reasons"])

    def test_missing_reviewer_and_evidence_are_reported(self):
        result = audit_rules([rule(evidence_id="", reviewed_by="", reviewed_at="", source_url="")], [candidate()])[0]
        self.assertIn("missing_evidence_id", result["rejection_reasons"])
        self.assertIn("missing_reviewer", result["rejection_reasons"])
        self.assertIn("missing_review_date", result["rejection_reasons"])
        self.assertIn("invalid_source_url", result["rejection_reasons"])

    def test_invalid_range_and_weight_are_reported(self):
        result = audit_rules([rule(minimum="30", maximum="20", weight="0")], [candidate()])[0]
        self.assertIn("invalid_between_range", result["rejection_reasons"])
        self.assertIn("weight_must_be_positive", result["rejection_reasons"])

    def test_duplicate_rule_ids_are_reported(self):
        rows = audit_rules([rule(), rule(candidate_id="c003")], [candidate()])
        self.assertIn("duplicate_rule_id", rows[1]["rejection_reasons"])

    def test_conflicting_candidate_gates_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "conflicting eligibility_gate"):
            audit_rules([rule()], [candidate(), candidate("regional_occurrence_conflict_requires_review")])

if __name__ == "__main__":
    unittest.main()
