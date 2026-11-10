import csv
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).parent/"species"))
from validate_seasonal_activity import validate_seasonal_register

ROOT=Path(__file__).parent
REGISTER=ROOT/"species"/"species_seasonal_activity_register.csv"
CANDIDATES=ROOT.parent/"P1"/"species"/"species_candidate_register.csv"
LITERATURE=ROOT/"species"/"species_response_literature_register.csv"

class SeasonalActivityTests(unittest.TestCase):
    def test_repository_seasonal_records_are_traceable_and_context_only(self):
        errors=validate_seasonal_register(REGISTER,CANDIDATES,LITERATURE)
        self.assertEqual(errors,[])
        with REGISTER.open(encoding="utf-8-sig",newline="") as f:
            rows=list(csv.DictReader(f))
        self.assertEqual(len(rows),12)
        self.assertTrue(all(r["model_use_status"].startswith("context_only_") for r in rows))

    def test_east_taiwan_dolphinfish_commercial_seasonality_remains_context_only(self):
        with REGISTER.open(encoding="utf-8-sig",newline="") as f:
            rows=list(csv.DictReader(f))
        row=next(r for r in rows if r["seasonal_evidence_id"]=="SE005")
        self.assertEqual(row["candidate_id"],"c023")
        self.assertEqual(row["taxon_scientific_name"],"Coryphaena hippurus")
        self.assertIn("4–6月",row["reported_season"])
        self.assertIn("10–12月",row["reported_season"])
        self.assertEqual(row["model_use_status"],"context_only_east_taiwan_commercial_fishery")
        self.assertIn("not shore-angling",row["limitations"].lower())

    def test_east_taiwan_skipjack_spawning_timing_remains_context_only(self):
        with REGISTER.open(encoding="utf-8-sig",newline="") as f:
            rows=list(csv.DictReader(f))
        row=next(r for r in rows if r["seasonal_evidence_id"]=="SE006")
        self.assertEqual(row["candidate_id"],"c039")
        self.assertEqual(row["taxon_scientific_name"],"Katsuwonus pelamis")
        self.assertIn("3–8月",row["reported_season"])
        self.assertIn("4–7月",row["reported_season"])
        self.assertEqual(row["model_use_status"],"context_only_east_taiwan_reproductive_biology")
        self.assertIn("not a fishing-activity",row["limitations"].lower())

    def test_damselfish_nesting_season_remains_northern_taiwan_context_only(self):
        with REGISTER.open(encoding="utf-8-sig",newline="") as f:
            rows=list(csv.DictReader(f))
        row=next(r for r in rows if r["seasonal_evidence_id"]=="SE007")
        self.assertEqual(row["candidate_id"],"c027")
        self.assertIn("5–10月",row["reported_season"])
        self.assertIn("5月與7月",row["reported_season"])
        self.assertEqual(row["model_use_status"],"context_only_northern_taiwan_field_study")
        self.assertIn("北台灣",row["geographic_scope"])
        self.assertIn("不可外推",row["limitations"])


    def test_girella_juvenile_settlement_and_rabbitfish_feeding_season_remain_context_only(self):
        with REGISTER.open(encoding="utf-8-sig",newline="") as f:
            rows=list(csv.DictReader(f))
        girella=next(r for r in rows if r["seasonal_evidence_id"]=="SE008")
        rabbit=next(r for r in rows if r["seasonal_evidence_id"]=="SE009")
        self.assertEqual(girella["candidate_id"],"c001")
        self.assertIn("4–8月",girella["reported_season"])
        self.assertEqual(girella["model_use_status"],"context_only_external_region")
        self.assertIn("幼魚",girella["limitations"])
        self.assertEqual(rabbit["candidate_id"],"c003")
        self.assertIn("9月下旬",rabbit["reported_season"])
        self.assertEqual(rabbit["model_use_status"],"context_only_captive_feeding")
        self.assertIn("不是台灣東部",rabbit["limitations"])


    def test_taiwan_wide_fishery_seasons_are_not_east_taiwan_hourly_scores(self):
        with REGISTER.open(encoding="utf-8-sig",newline="") as f:
            rows=list(csv.DictReader(f))
        drummer=next(r for r in rows if r["seasonal_evidence_id"]=="SE010")
        rabbit=next(r for r in rows if r["seasonal_evidence_id"]=="SE011")
        seabream=next(r for r in rows if r["seasonal_evidence_id"]=="SE012")
        self.assertEqual(drummer["model_use_status"],"context_only_taiwan_fishery_reference")
        self.assertEqual(rabbit["model_use_status"],"context_only_taiwan_fishery_reference")
        self.assertEqual(seabream["model_use_status"],"context_only_taiwan_fishery_reference")
        self.assertIn("冬季盛產",drummer["reported_season"])
        self.assertIn("全年皆產",rabbit["reported_season"])
        self.assertIn("春、冬",seabream["reported_season"])
        self.assertIn("不是東部岸釣",seabream["limitations"])

    def test_seasonal_score_eligibility_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"seasonal.csv"
            with REGISTER.open(encoding="utf-8-sig",newline="") as f:
                rows=list(csv.DictReader(f)); fields=rows[0].keys()
            rows[0]["model_use_status"]="eligible_for_seasonal_scoring"
            with p.open("w",encoding="utf-8",newline="") as f:
                w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
            errors=validate_seasonal_register(p,CANDIDATES,LITERATURE)
            self.assertTrue(any("must remain context_only" in e for e in errors))

    def test_wrong_taxon_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"seasonal.csv"
            with REGISTER.open(encoding="utf-8-sig",newline="") as f:
                rows=list(csv.DictReader(f)); fields=rows[0].keys()
            rows[0]["taxon_scientific_name"]="Kyphosus bigibbus"
            with p.open("w",encoding="utf-8",newline="") as f:
                w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
            errors=validate_seasonal_register(p,CANDIDATES,LITERATURE)
            self.assertTrue(any("does not match candidate register" in e for e in errors))

    def test_white_hair_alias_group_cannot_receive_species_parameter(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"seasonal.csv"
            with REGISTER.open(encoding="utf-8-sig",newline="") as f:
                rows=list(csv.DictReader(f)); fields=rows[0].keys()
            rows[0]["candidate_id"]="c002"
            with p.open("w",encoding="utf-8",newline="") as f:
                w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
            errors=validate_seasonal_register(p,CANDIDATES,LITERATURE)
            self.assertTrue(any("white-hair vernacular group" in e for e in errors))

if __name__=="__main__": unittest.main()
