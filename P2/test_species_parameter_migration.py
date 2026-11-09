import csv
import tempfile
import unittest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "species"))
from migrate_p1_ecology_parameters import migrate

class SpeciesParameterMigrationTests(unittest.TestCase):
    def test_preserves_values_and_links_evidence_url(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            ecology=root/"ecology.csv"
            evidence=root/"evidence.csv"
            ecology.write_text(
                "ecology_record_id,candidate_id,scientific_name,parameter_code,parameter_value,unit_or_format,geographic_scope,evidence_id,source_type,confidence,model_use_status,limitations\n"
                'EP1,c001,Girella punctata,habitat,"reef; coastal",controlled_vocabulary,Taiwan East,E1,taxonomic_database,high,eligible_as_species_context,"Not every spot"\n',
                encoding="utf-8"
            )
            evidence.write_text(
                "evidence_id,candidate_id,source_url\nE1,c001,https://example.org/species\n",
                encoding="utf-8"
            )
            rows=migrate(ecology,evidence)
            self.assertEqual(len(rows),1)
            self.assertEqual(rows[0]["parameter_value"],"reef; coastal")
            self.assertEqual(rows[0]["source_url"],"https://example.org/species")
            self.assertEqual(rows[0]["model_use_status"],"eligible_as_species_context")
            self.assertEqual(rows[0]["life_stage"],"not_specified")

    def test_rejects_missing_evidence_link(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            ecology=root/"ecology.csv"; evidence=root/"evidence.csv"
            ecology.write_text("ecology_record_id,candidate_id,scientific_name,parameter_code,parameter_value,unit_or_format,geographic_scope,evidence_id,source_type,confidence,model_use_status,limitations\nEP1,c001,Girella punctata,habitat,reef,controlled_vocabulary,Taiwan East,E404,taxonomic_database,high,context_only,\n",encoding="utf-8")
            evidence.write_text("evidence_id,candidate_id,source_url\n",encoding="utf-8")
            with self.assertRaises(ValueError):
                migrate(ecology,evidence)

if __name__ == "__main__":
    unittest.main()
