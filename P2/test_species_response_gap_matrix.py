import csv
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "species"))
from build_species_response_gap_matrix import build_matrix

class SpeciesGapMatrixTests(unittest.TestCase):
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
                "c027,條紋豆娘魚,Abudefduf vaigiensis\n"
                "c028,孟加拉豆娘魚,Abudefduf bengalensis\n"
                "c029,瑪拉巴石斑魚,Epinephelus malabaricus\n"
                "c030,點帶石斑魚,Epinephelus coioides\n",encoding="utf-8")
            ecology.write_text("candidate_id,parameter_code,evidence_id\nc001,habitat,E1\n",encoding="utf-8")
            evidence.write_text("candidate_id,evidence_id,source_url\nc001,E1,https://example.org/e1\n",encoding="utf-8")
            rows=build_matrix(candidates,ecology,evidence)
            self.assertEqual(len(rows),56)
            white=next(r for r in rows if r["candidate_id"]=="c002")
            grouper=next(r for r in rows if r["candidate_id"]=="c030")
            black=next(r for r in rows if r["candidate_id"]=="c001")
            self.assertEqual(white["evidence_status"],"species_identification_required")
            self.assertEqual(grouper["evidence_status"],"regional_evidence_gate")
            self.assertEqual(black["evidence_status"],"evidence_gap")
            self.assertIn("habitat",black["existing_parameter_codes"])
            self.assertEqual(black["model_use_policy"],"not_model_eligible_until_direct_response_evidence_reviewed")

if __name__ == "__main__":
    unittest.main()
