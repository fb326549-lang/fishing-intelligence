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
        self.assertEqual(len(rows),15)
        self.assertTrue(all(r["model_use_status"].startswith("context_only_") for r in rows))

    def test_east_taiwan_museum_occurrence_records_remain_context_only(self):
        with REGISTER.open(encoding="utf-8-sig",newline="") as f:
            rows=list(csv.DictReader(f))
        occurrence=[r for r in rows if r["activity_dimension"]=="occurrence_record"]
        self.assertEqual({r["activity_evidence_id"] for r in occurrence},{"AE010","AE011","AE012"})
        self.assertTrue(all(r["evidence_kind"]=="verified_museum_specimen" for r in occurrence))
        self.assertTrue(all(r["model_use_status"]=="context_only_east_taiwan_occurrence" for r in occurrence))
        self.assertTrue(all("不得作為活動分數" in r["limitations"] for r in occurrence))

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
