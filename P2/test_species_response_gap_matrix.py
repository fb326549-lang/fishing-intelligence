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
                "c010,花身雞魚,Terapon jarbua\n"
                "c012,紅槽,Lutjanus bohar\n"
                "c018,白帶魚,Trichiurus lepturus\n"
                "c019,日本竹筴魚,Trachurus japonicus\n"
                "c023,鬼頭刀,Coryphaena hippurus\n"
                "c024,紅甘,Seriola dumerili\n"
                "c027,條紋豆娘魚,Abudefduf vaigiensis\n"
                "c028,孟加拉豆娘魚,Abudefduf bengalensis\n"
                "c029,瑪拉巴石斑魚,Epinephelus malabaricus\n"
                "c030,點帶石斑魚,Epinephelus coioides\n"
                "c031,雜紋鸚哥魚,Scarus rivulatus\n"
                "c032,史氏鸚哥魚,Scarus schlegeli\n"
                "c033,藍頭綠鸚哥魚,Chlorurus sordidus\n"
                "c034,雙色鯨鸚哥魚,Cetoscarus bicolor\n"
                "c036,南方舵魚,Kyphosus bigibbus\n"
                "c037,天竺舵魚,Kyphosus cinerascens\n"
                "c039,正鰹,Katsuwonus pelamis\n",encoding="utf-8")
            ecology.write_text("candidate_id,parameter_code,evidence_id\nc001,habitat,E1\n",encoding="utf-8")
            evidence.write_text(
                "candidate_id,evidence_id,source_url\n"
                "c001,E1,https://example.org/e1\n"
                "c023,E001,https://fishdb.sinica.edu.tw/taxon/381638-fishdb\n"
                "c023,E002,https://www.tfrin.gov.tw/theme_data.php?id=1382&theme=research\n",encoding="utf-8")
            literature=root/"literature.csv"
            literature.write_text("literature_record_id,candidate_id,parameter_code,source_url,model_use_status\nL1,c003,temperature_response,https://example.org/l1,context_only_external_region\nL2,c001,activity_period,https://example.org/l2,context_only_northern_taiwan_field_study\nL3,c004,temperature_response,https://example.org/l3,context_only_western_taiwan_fishery_model\nL4,c004,ocean_current_response,https://example.org/l4,context_only_western_taiwan_fishery_model\nL5,c036,temperature_response,https://example.org/l5,context_only_external_region\n"
                "L6,c023,seasonal_activity,https://example.org/l6,context_only_east_taiwan_commercial_fishery\n"
                "L034,c036,activity_period,https://doi.org/10.1111/jfb.70024,context_only_external_region\n"
                "L035,c036,activity_period,https://doi.org/10.2331/suisan.23-00035,context_only_external_region\n"
                "L036,c036,activity_period,https://doi.org/10.11233/aquaculturesci.69.135,context_only_captive_feeding\n"
                "L037,c036,temperature_response,https://ypir.lib.yamaguchi-u.ac.jp/fu/335,context_only_captive_feeding\n"
                "L038,c003,feeding_condition,https://doi.org/10.18903/fisheng.43.1_65,context_only_captive_feeding\n"
                "L039,c004,temperature_response,https://doi.org/10.3390/jmse9121442,context_only_western_taiwan_fishery_model\n"
                "L040,c001,feeding_condition,https://zoolstud.sinica.edu.tw/Journals/20.1/17.pdf,context_only_northern_taiwan_field_study\n"
                "L041,c001,seasonal_activity,https://doi.org/10.1007/s12562-018-1206-5,context_only_external_region\n"
                "L042,c001,feeding_condition,https://doi.org/10.1016/j.aqrep.2024.102349,context_only_captive_feeding\n"
                "L043,c036,activity_period,https://kmweb.moa.gov.tw/theme_data.php?id=586&theme=fisheasy,context_only_taiwan_fishery_reference\n"
                "L044,c003,activity_period,https://kmweb.moa.gov.tw/theme_data.php?id=624&theme=fisheasy,context_only_taiwan_fishery_reference\n"
                "L045,c004,activity_period,https://kmweb.moa.gov.tw/theme_data.php?id=536&theme=fisheasy,context_only_taiwan_fishery_reference\n"
                "L046,c003,feeding_condition,https://doi.org/10.18903/fisheng.39.1_5,context_only_external_region\n"
                "L047,c003,feeding_condition,https://doi.org/10.2331/suisan.77.1008,context_only_external_region\n"
                "L048,c003,feeding_condition,https://doi.org/10.11233/aquaculturesci.57.429,context_only_captive_feeding\n"
                "L049,c003,feeding_condition,https://www.fish-u.ac.jp/public/files/68/02_2.pdf,context_only_captive_feeding\n"
                "L050,c003,activity_period,https://doi.org/10.18903/fisheng.47.1_47,context_only_captive_activity\n"
                "L051,c036,feeding_condition,https://doi.org/10.11233/aquaculturesci.64.209,context_only_captive_feeding\n"
                "L052,c036,temperature_response,https://www2.fish-u.ac.jp/kenkyu/sangakukou/kenkyuhoukoku/64/04_1.pdf,context_only_captive_feeding\n"
                "L053,c036,activity_period,https://doi.org/10.11233/aquaculturesci.69.135,context_only_captive_activity\n",encoding="utf-8")
            rows=build_matrix(candidates,ecology,evidence,literature)
            self.assertEqual(len(rows),168)
            white=next(r for r in rows if r["candidate_id"]=="c002")
            grouper=next(r for r in rows if r["candidate_id"]=="c030")
            black=next(r for r in rows if r["candidate_id"]=="c001")
            skipjack=next(r for r in rows if r["candidate_id"]=="c039" and r["response_domain"]=="temperature_range")
            dolphinfish=next(r for r in rows if r["candidate_id"]=="c023" and r["response_domain"]=="temperature_range")
            amberjack=next(r for r in rows if r["candidate_id"]=="c024" and r["response_domain"]=="temperature_range")
            self.assertEqual(white["evidence_status"],"species_identification_required")
            self.assertEqual(grouper["evidence_status"],"regional_evidence_gate")
            self.assertEqual(black["evidence_status"],"evidence_gap")
            self.assertEqual(skipjack["eligibility_gate"],"verified_taxon")
            self.assertEqual(skipjack["evidence_status"],"evidence_gap")
            self.assertEqual(dolphinfish["eligibility_gate"],"verified_taxon")
            self.assertEqual(dolphinfish["evidence_status"],"evidence_gap")
            self.assertIn("E001;E002",dolphinfish["evidence_ids"])
            self.assertEqual(amberjack["eligibility_gate"],"verified_taxon")
            self.assertIn("habitat",black["existing_parameter_codes"])
            rabbit=next(r for r in rows if r["candidate_id"]=="c003" and r["response_domain"]=="temperature_range")
            self.assertEqual(rabbit["evidence_status"],"external_literature_found_context_only")
            self.assertEqual(rabbit["literature_record_ids"],"L1")
            self.assertEqual(white["evidence_status"],"species_identification_required")
            self.assertEqual(black["model_use_policy"],"not_model_eligible_until_direct_response_evidence_reviewed")
            rabbit_feeding=next(r for r in rows if r["candidate_id"]=="c003" and r["response_domain"]=="feeding_conditions")
            self.assertEqual(rabbit_feeding["literature_record_ids"],"L038;L046;L047;L048;L049")
            self.assertEqual(rabbit_feeding["evidence_status"],"external_literature_found_context_only")
            black_feeding=next(r for r in rows if r["candidate_id"]=="c001" and r["response_domain"]=="feeding_conditions")
            self.assertEqual(black_feeding["literature_record_ids"],"L040;L042")
            self.assertEqual(black_feeding["evidence_status"],"external_literature_found_context_only")
            rabbit_activity=next(r for r in rows if r["candidate_id"]=="c003" and r["response_domain"]=="activity_period")
            self.assertEqual(rabbit_activity["literature_record_ids"],"L044;L050")
            black_seabream_activity=next(r for r in rows if r["candidate_id"]=="c004" and r["response_domain"]=="activity_period")
            self.assertEqual(black_seabream_activity["literature_record_ids"],"L045")
            black_activity=next(r for r in rows if r["candidate_id"]=="c001" and r["response_domain"]=="activity_period")
            self.assertEqual(black_activity["evidence_status"],"external_literature_found_context_only")
            black_seabream_temp=next(r for r in rows if r["candidate_id"]=="c004" and r["response_domain"]=="temperature_range")
            self.assertEqual(black_seabream_temp["evidence_status"],"external_literature_found_context_only")
            black_seabream_current=next(r for r in rows if r["candidate_id"]=="c004" and r["response_domain"]=="current_preference")
            self.assertEqual(black_seabream_current["evidence_status"],"external_literature_found_context_only")
            southern = next(r for r in rows if r["candidate_id"]=="c036" and r["response_domain"]=="temperature_range")
            white_alias = next(r for r in rows if r["candidate_id"]=="c002" and r["response_domain"]=="temperature_range")
            self.assertEqual(southern["evidence_status"],"external_literature_found_context_only")
            self.assertEqual(southern["literature_record_ids"],"L037;L052;L5")
            self.assertEqual(southern["literature_use_status"],"context_only_captive_feeding;context_only_external_region")
            self.assertEqual(white_alias["evidence_status"],"species_identification_required")
            self.assertEqual(white_alias["literature_record_ids"],"")
            self.assertEqual(len([r for r in rows if r["candidate_id"] in {"c036","c037"}]),16)
            seasonal_fishery=next(r for r in rows if r["candidate_id"]=="c023" and r["response_domain"]=="activity_period")
            self.assertEqual(seasonal_fishery["evidence_status"],"external_literature_found_context_only")
            self.assertEqual(seasonal_fishery["literature_record_ids"],"L6")
            self.assertEqual(seasonal_fishery["literature_use_status"],"context_only_east_taiwan_commercial_fishery")
            context=__import__("json").loads(seasonal_fishery["literature_context_json"])
            self.assertEqual(context[0]["model_use_status"],"context_only_east_taiwan_commercial_fishery")
            self.assertEqual(seasonal_fishery["model_use_policy"],"not_model_eligible_until_direct_response_evidence_reviewed")
            southern_feeding=next(r for r in rows if r["candidate_id"]=="c036" and r["response_domain"]=="feeding_conditions")
            self.assertEqual(southern_feeding["literature_record_ids"],"L051")
            self.assertEqual(southern_feeding["literature_use_status"],"context_only_captive_feeding")
            southern_activity=next(r for r in rows if r["candidate_id"]=="c036" and r["response_domain"]=="activity_period")
            self.assertEqual(southern_activity["literature_record_ids"],"L034;L035;L036;L043;L053")
            self.assertEqual(southern_activity["literature_use_status"],"context_only_captive_activity;context_only_captive_feeding;context_only_external_region;context_only_taiwan_fishery_reference")
            southern_context=__import__("json").loads(southern_activity["literature_context_json"])
            self.assertEqual([x["literature_record_id"] for x in southern_context],["L034","L035","L036","L043","L053"])
            self.assertTrue(all(x["model_use_status"] != "eligible_for_activity_scoring" for x in southern_context))

if __name__ == "__main__":
    unittest.main()
