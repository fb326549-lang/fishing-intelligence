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
        self.assertEqual(len(rows),4)
        self.assertTrue(all(r["model_use_status"].startswith("context_only_") for r in rows))

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
