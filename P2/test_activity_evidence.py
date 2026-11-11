import csv
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "species"))
from validate_activity_evidence import validate_activity_register

ROOT=Path(__file__).parent
REGISTER=ROOT/"species"/"species_activity_evidence_register.csv"
CANDIDATES=ROOT.parent/"P1"/"species"/"species_candidate_register.csv"
LITERATURE=ROOT/"species"/"species_response_literature_register.csv"

class ActivityEvidenceTests(unittest.TestCase):
    def test_repository_activity_evidence_is_traceable_and_context_only(self):
        errors=validate_activity_register(REGISTER,CANDIDATES,LITERATURE)
        self.assertEqual(errors,[])
        with REGISTER.open(encoding="utf-8-sig",newline="") as f:
            rows=list(csv.DictReader(f))
        self.assertEqual(len(rows),38)
        self.assertTrue(all(r["model_use_status"].startswith("context_only_") for r in rows))

    def test_east_taiwan_museum_occurrence_records_remain_context_only(self):
        with REGISTER.open(encoding="utf-8-sig",newline="") as f:
            rows=list(csv.DictReader(f))
        occurrence=[r for r in rows if r["activity_dimension"]=="occurrence_record"]
        self.assertEqual({r["activity_evidence_id"] for r in occurrence},{"AE010","AE011","AE012","AE013","AE014","AE015"})
        self.assertTrue(all(r["evidence_kind"]=="verified_museum_specimen" for r in occurrence))
        self.assertTrue(all(r["model_use_status"]=="context_only_east_taiwan_occurrence" for r in occurrence))
        self.assertTrue(all("不得作為活動分數" in r["limitations"] for r in occurrence))

    def test_damselfish_feeding_observation_is_context_only(self):
        with REGISTER.open(encoding="utf-8-sig",newline="") as f:
            rows=list(csv.DictReader(f))
        row=next(r for r in rows if r["activity_evidence_id"]=="AE016")
        self.assertEqual(row["candidate_id"],"c027")
        self.assertEqual(row["activity_dimension"],"feeding_activity")
        self.assertEqual(row["model_use_status"],"context_only_northern_taiwan_field_study")
        self.assertIn("護卵雄魚",row["limitations"])
        self.assertIn("沒有測量",row["limitations"])


    def test_southern_drummer_new_feeding_and_movement_studies_remain_context_only(self):
        with REGISTER.open(encoding="utf-8-sig",newline="") as f:
            rows=list(csv.DictReader(f))
        feeding=next(r for r in rows if r["activity_evidence_id"]=="AE017")
        movement=next(r for r in rows if r["activity_evidence_id"]=="AE018")
        self.assertEqual(feeding["candidate_id"],"c036")
        self.assertEqual(feeding["source_literature_id"],"L034")
        self.assertEqual(feeding["activity_dimension"],"feeding_activity")
        self.assertEqual(feeding["model_use_status"],"context_only_external_region")
        self.assertIn("日落至日出",feeding["reported_pattern"])
        self.assertIn("不可直接作為東部夜釣",feeding["limitations"])
        self.assertEqual(movement["candidate_id"],"c036")
        self.assertEqual(movement["source_literature_id"],"L035")
        self.assertEqual(movement["activity_dimension"],"movement_activity")
        self.assertEqual(movement["model_use_status"],"context_only_external_region")
        self.assertIn("1至5月",movement["reported_pattern"])
        self.assertIn("不是魚群豐度",movement["limitations"])


    def test_southern_drummer_captive_feeding_trials_remain_context_only(self):
        with REGISTER.open(encoding="utf-8-sig",newline="") as f:
            rows=list(csv.DictReader(f))
        diel=next(r for r in rows if r["activity_evidence_id"]=="AE019")
        temp=next(r for r in rows if r["activity_evidence_id"]=="AE020")
        self.assertEqual(diel["candidate_id"],"c036")
        self.assertEqual(diel["source_literature_id"],"L036")
        self.assertEqual(diel["evidence_kind"],"captive_feeding_trial")
        self.assertEqual(diel["model_use_status"],"context_only_captive_feeding")
        self.assertIn("45.6%",diel["reported_pattern"])
        self.assertIn("不是野外魚群活動",diel["limitations"])
        self.assertEqual(temp["candidate_id"],"c036")
        self.assertEqual(temp["source_literature_id"],"L037")
        self.assertEqual(temp["evidence_kind"],"captive_feeding_trial")
        self.assertEqual(temp["model_use_status"],"context_only_captive_feeding")
        self.assertIn("12°C",temp["reported_pattern"])
        self.assertIn("不得直接套用台灣東部",temp["limitations"])


    def test_taiwan_wide_fishery_guides_remain_context_only(self):
        with REGISTER.open(encoding="utf-8-sig",newline="") as f:
            rows=list(csv.DictReader(f))
        selected={r["activity_evidence_id"]:r for r in rows if r["activity_evidence_id"] in {"AE028","AE029","AE030"}}
        self.assertEqual(set(selected),{"AE028","AE029","AE030"})
        self.assertEqual(selected["AE028"]["source_literature_id"],"L043")
        self.assertIn("冬季盛產",selected["AE028"]["reported_pattern"])
        self.assertEqual(selected["AE029"]["source_literature_id"],"L044")
        self.assertIn("冬季味美",selected["AE029"]["reported_pattern"])
        self.assertEqual(selected["AE030"]["source_literature_id"],"L045")
        self.assertIn("春冬",selected["AE030"]["reported_pattern"])
        self.assertTrue(all(r["model_use_status"]=="context_only_taiwan_fishery_reference" for r in selected.values()))


    def test_rabbitfish_field_diet_and_captive_activity_sources_remain_context_only(self):
        with REGISTER.open(encoding="utf-8-sig",newline="") as f:
            rows=list(csv.DictReader(f))
        selected={r["activity_evidence_id"]:r for r in rows if r["activity_evidence_id"] in {"AE031","AE032","AE033","AE034","AE035"}}
        self.assertEqual(set(selected),{"AE031","AE032","AE033","AE034","AE035"})
        self.assertEqual(selected["AE031"]["source_literature_id"],"L046")
        self.assertIn("低於濕重2%",selected["AE031"]["reported_pattern"])
        self.assertEqual(selected["AE032"]["source_literature_id"],"L047")
        self.assertIn("夏季45%",selected["AE032"]["reported_pattern"])
        self.assertEqual(selected["AE033"]["source_literature_id"],"L048")
        self.assertIn("15及30株",selected["AE033"]["reported_pattern"])
        self.assertEqual(selected["AE034"]["source_literature_id"],"L049")
        self.assertEqual(selected["AE035"]["source_literature_id"],"L050")
        self.assertEqual(selected["AE035"]["evidence_kind"],"captive_activity_observation")
        self.assertTrue(all(r["model_use_status"].startswith("context_only_") for r in selected.values()))


    def test_southern_drummer_2016_and_2021_diel_trials_remain_captive_context_only(self):
        with REGISTER.open(encoding="utf-8-sig",newline="") as f:
            rows=list(csv.DictReader(f))
        early=next(r for r in rows if r["activity_evidence_id"]=="AE036")
        later=next(r for r in rows if r["activity_evidence_id"]=="AE037")
        self.assertEqual(early["source_literature_id"],"L051")
        self.assertEqual(early["evidence_kind"],"captive_feeding_trial")
        self.assertIn("21:00–24:00",early["reported_pattern"])
        self.assertEqual(early["model_use_status"],"context_only_captive_feeding")
        self.assertEqual(later["source_literature_id"],"L053")
        self.assertEqual(later["evidence_kind"],"captive_activity_observation")
        self.assertIn("45.6%",later["reported_pattern"])
        self.assertEqual(later["model_use_status"],"context_only_captive_activity")
        self.assertTrue(all("台灣東部" in r["limitations"] for r in (early,later)))

    def test_black_seabream_telemetry_is_external_spawning_activity_context_only(self):
        with REGISTER.open(encoding="utf-8-sig",newline="") as f:
            rows=list(csv.DictReader(f))
        evidence=next(r for r in rows if r["activity_evidence_id"]=="AE038")
        self.assertEqual(evidence["candidate_id"],"c004")
        self.assertEqual(evidence["source_literature_id"],"L056")
        self.assertEqual(evidence["activity_dimension"],"movement_activity")
        self.assertEqual(evidence["evidence_kind"],"telemetry_proxy")
        self.assertEqual(evidence["model_use_status"],"context_only_external_region")
        self.assertIn("雄魚",evidence["reported_pattern"])
        self.assertIn("台灣東部",evidence["limitations"])
        self.assertIn("不能代表索餌或咬餌",evidence["limitations"])

    def test_scoring_eligibility_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"activity.csv"
            with REGISTER.open(encoding="utf-8-sig",newline="") as f:
                rows=list(csv.DictReader(f)); fields=rows[0].keys()
            rows[0]["model_use_status"]="eligible_for_activity_scoring"
            with p.open("w",encoding="utf-8",newline="") as f:
                w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
            errors=validate_activity_register(p,CANDIDATES,LITERATURE)
            self.assertTrue(any("must remain context-only" in e for e in errors))

    def test_source_url_must_match_literature_register(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"activity.csv"
            with REGISTER.open(encoding="utf-8-sig",newline="") as f:
                rows=list(csv.DictReader(f)); fields=rows[0].keys()
            rows[0]["source_url"]="https://example.org/wrong"
            with p.open("w",encoding="utf-8",newline="") as f:
                w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
            errors=validate_activity_register(p,CANDIDATES,LITERATURE)
            self.assertTrue(any("source_url does not match literature register" in e for e in errors))

    def test_taxon_must_match_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"activity.csv"
            with REGISTER.open(encoding="utf-8-sig",newline="") as f:
                rows=list(csv.DictReader(f)); fields=rows[0].keys()
            rows[0]["taxon_scientific_name"]="Kyphosus bigibbus"
            with p.open("w",encoding="utf-8",newline="") as f:
                w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
            errors=validate_activity_register(p,CANDIDATES,LITERATURE)
            self.assertTrue(any("does not match candidate register" in e for e in errors))

if __name__=="__main__": unittest.main()
