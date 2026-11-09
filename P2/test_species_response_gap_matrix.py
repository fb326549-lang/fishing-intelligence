import csv
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "species"))
from build_species_response_gap_matrix import build_matrix

class SpeciesGapMatrixTests(unittest.TestCase):
    def test_southern_drummer_literature_is_not_assigned_to_white_alias(self):
        register = Path(__file__).parent / "species" / "species_response_literature_register.csv"
        with register.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        southern_records = [r for r in rows if r["taxon_scientific_name"] == "Kyphosus bigibbus"]
        self.assertTrue(southern_records)
        self.assertTrue(all(r["candidate_id"] == "c036" for r in southern_records))
        self.assertFalse(any(r["candidate_id"] == "c002" for r in southern_records))
        southern_specimen = next(r for r in rows if r["literature_record_id"] == "L020")
        cinerascens_crosswalk = next(r for r in rows if r["literature_record_id"] == "L018")
        self.assertEqual(southern_specimen["model_use_status"], "occurrence_only_no_environment_response")
        self.assertEqual(cinerascens_crosswalk["model_use_status"], "occurrence_record_conflict_requires_reconciliation")
        self.assertIn("成功／三仙台", cinerascens_crosswalk["geographic_scope"])
        self.assertIn("日期、漁法與精確地點", cinerascens_crosswalk["limitations"])
        self.assertIn("台東三仙台", southern_specimen["geographic_scope"])


    def test_matrix_flags_taxonomy_and_distribution_gates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            candidates=root/"candidates.csv"
            ecology=root/"ecology.csv"
            evidence=root/"evidence.csv"
            candidates.write_text(
                "candidate_id,common_name_zh,scientific_name\n"
                "c001,瓜子鱲,Girella punctata\n"
                "c002,白毛,Kyphosus spp.\n"
                "c003,臭肚,Siganus fuscescens\n"
                "c004,黑鯛,Acanthopagrus schlegelii\n"
                "c023,鬼頭刀,Coryphaena hippurus\n"
                "c027,條紋豆娘魚,Abudefduf vaigiensis\n"
                "c028,孟加拉豆娘魚,Abudefduf bengalensis\n"
                "c029,瑪拉巴石斑魚,Epinephelus malabaricus\n"
                "c030,點帶石斑魚,Epinephelus coioides\n"
                "c036,南方舵魚,Kyphosus bigibbus\n"
                "c037,天竺舵魚,Kyphosus cinerascens\n"
                "c039,正鰹,Katsuwonus pelamis\n",encoding="utf-8")
            ecology.write_text("candidate_id,parameter_code,evidence_id\nc001,habitat,E1\n",encoding="utf-8")
            evidence.write_text("candidate_id,evidence_id,source_url\nc001,E1,https://example.org/e1\n",encoding="utf-8")
            literature=root/"literature.csv"
            literature.write_text("literature_record_id,candidate_id,parameter_code,source_url,model_use_status\nL1,c003,temperature_response,https://example.org/l1,context_only_external_region\nL2,c001,activity_period,https://example.org/l2,context_only_northern_taiwan_field_study\nL3,c004,temperature_response,https://example.org/l3,context_only_western_taiwan_fishery_model\nL4,c004,ocean_current_response,https://example.org/l4,context_only_western_taiwan_fishery_model\nL5,c036,temperature_response,https://example.org/l5,context_only_external_region\n",encoding="utf-8")
            rows=build_matrix(candidates,ecology,evidence,literature)
            self.assertEqual(len(rows),84)
            white=next(r for r in rows if r["candidate_id"]=="c002")
            grouper=next(r for r in rows if r["candidate_id"]=="c030")
            black=next(r for r in rows if r["candidate_id"]=="c001")
            skipjack=next(r for r in rows if r["candidate_id"]=="c039" and r["response_domain"]=="temperature_range")
            dolphinfish=next(r for r in rows if r["candidate_id"]=="c023" and r["response_domain"]=="temperature_range")
            self.assertEqual(white["evidence_status"],"species_identification_required")
            self.assertEqual(grouper["evidence_status"],"regional_evidence_gate")
            self.assertEqual(black["evidence_status"],"evidence_gap")
            self.assertEqual(skipjack["eligibility_gate"],"verified_taxon")
            self.assertEqual(skipjack["evidence_status"],"evidence_gap")
            self.assertEqual(dolphinfish["eligibility_gate"],"verified_taxon")
            self.assertEqual(dolphinfish["evidence_status"],"evidence_gap")
            self.assertIn("E001;E002",dolphinfish["evidence_ids"])
            self.assertIn("habitat",black["existing_parameter_codes"])
            rabbit=next(r for r in rows if r["candidate_id"]=="c003" and r["response_domain"]=="temperature_range")
            self.assertEqual(rabbit["evidence_status"],"external_literature_found_context_only")
            self.assertEqual(rabbit["literature_record_ids"],"L1")
            self.assertEqual(white["evidence_status"],"species_identification_required")
            self.assertEqual(black["model_use_policy"],"not_model_eligible_until_direct_response_evidence_reviewed")
            black_activity=next(r for r in rows if r["candidate_id"]=="c001" and r["response_domain"]=="activity_period")
            self.assertEqual(black_activity["evidence_status"],"external_literature_found_context_only")
            black_seabream_temp=next(r for r in rows if r["candidate_id"]=="c004" and r["response_domain"]=="temperature_range")
            self.assertEqual(black_seabream_temp["evidence_status"],"external_literature_found_context_only")
            black_seabream_current=next(r for r in rows if r["candidate_id"]=="c004" and r["response_domain"]=="current_preference")
            self.assertEqual(black_seabream_current["evidence_status"],"external_literature_found_context_only")
            southern = next(r for r in rows if r["candidate_id"]=="c036" and r["response_domain"]=="temperature_range")
            white_alias = next(r for r in rows if r["candidate_id"]=="c002" and r["response_domain"]=="temperature_range")
            self.assertEqual(southern["evidence_status"],"external_literature_found_context_only")
            self.assertEqual(southern["literature_record_ids"],"L5")
            self.assertEqual(white_alias["evidence_status"],"species_identification_required")
            self.assertEqual(white_alias["literature_record_ids"],"")
            self.assertEqual(len([r for r in rows if r["candidate_id"] in {"c036","c037"}]),14)

if __name__ == "__main__":
    unittest.main()
