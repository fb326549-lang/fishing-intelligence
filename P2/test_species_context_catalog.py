import csv
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "species"))
from build_species_context_catalog import build_catalog

class SpeciesContextCatalogTests(unittest.TestCase):
    def test_catalog_preserves_species_context_provenance_and_limits(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            candidates=root/"candidates.csv"
            ecology=root/"ecology.csv"
            evidence=root/"evidence.csv"
            candidates.write_text(
                "candidate_id,common_name_zh,scientific_name,taxonomy_status\n"
                "c027,條紋豆娘魚,Abudefduf vaigiensis,verified_taxon\n",encoding="utf-8")
            ecology.write_text(
                "ecology_record_id,candidate_id,scientific_name,parameter_code,parameter_value,unit_or_format,geographic_scope,evidence_id,confidence,model_use_status,limitations\n"
                "EP001,c027,Abudefduf vaigiensis,habitat,reef; coastal,controlled_vocabulary,Taiwan including East Taiwan,E021,high,eligible_as_species_context,Not proof of presence at every fishing spot\n"
                "EP002,c027,Abudefduf vaigiensis,reported_depth_max,15,m,Species description,E021,high,context_only,Not a recommended fishing depth\n",encoding="utf-8")
            evidence.write_text(
                "evidence_id,source_name,source_url\n"
                "E021,Taiwan Fish Database,https://fishdb.sinica.edu.tw/taxon/example\n",encoding="utf-8")
            catalog=build_catalog(candidates,ecology,evidence)
            self.assertEqual(catalog["record_count"],2)
            habitat=next(r for r in catalog["records"] if r["category"]=="habitat")
            depth=next(r for r in catalog["records"] if r["category"]=="depth")
            self.assertEqual(habitat["parameter_value"],"reef; coastal")
            self.assertEqual(habitat["source_url"],"https://fishdb.sinica.edu.tw/taxon/example")
            self.assertEqual(depth["unit_or_format"],"m")
            self.assertIn("not a recommended fishing depth",depth["limitations"].lower())
            self.assertIn("not current presence",catalog["interpretation"].lower())

    def test_catalog_includes_scoped_east_coast_occurrence_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            candidates=root/"candidates.csv"
            ecology=root/"ecology.csv"
            evidence=root/"evidence.csv"
            occurrence=root/"occurrence.csv"
            candidates.write_text(
                "candidate_id,common_name_zh,scientific_name,taxonomy_status\n"
                "c036,南方舵魚,Kyphosus bigibbus,verified_taxon\n"
                "c026,豆娘魚,,not_single_species\n",encoding="utf-8")
            ecology.write_text(
                "ecology_record_id,candidate_id,scientific_name,parameter_code,parameter_value,unit_or_format,geographic_scope,evidence_id,confidence,model_use_status,limitations\n",
                encoding="utf-8")
            evidence.write_text("evidence_id,source_name,source_url\n",encoding="utf-8")
            occurrence.write_text(
                "regional_occurrence_id,candidate_id,taxon_scientific_name,common_name_zh,site_code,site_name,region_id,visit_number,recorded_presence,study_year,study_scope,method,source_name,source_url,confidence,model_use_status,limitations\n"
                "RO001,c036,Kyphosus bigibbus,南方舵魚,A1,杉原北側,chenggong_donghe,2,present,2016,東部海岸淺海,水下調查,官方報告,https://example.org/report,medium,context_only_east_coast_biodiversity_survey,not a fishing catch record\n"
                "RO008,c026,Abudefduf septemfasciatus,七帶豆娘魚,A1,杉原北側,chenggong_donghe,2,present,2016,東部海岸淺海,水下調查,官方報告,https://example.org/report,medium,context_only_east_coast_biodiversity_survey,one member species only\n",
                encoding="utf-8")
            catalog=build_catalog(candidates,ecology,evidence,occurrence)
            self.assertEqual(catalog["record_count"],0)
            self.assertEqual(catalog["regional_occurrence_record_count"],2)
            row=next(x for x in catalog["regional_occurrence_records"] if x["candidate_id"]=="c036")
            self.assertEqual(row["candidate_id"],"c036")
            self.assertEqual(row["region_id"],"chenggong_donghe")
            self.assertEqual(row["recorded_presence"],"present")
            self.assertEqual(row["model_use_status"],"context_only_east_coast_biodiversity_survey")
            damselfish=next(x for x in catalog["regional_occurrence_records"] if x["candidate_id"]=="c026")
            self.assertEqual(damselfish["common_name_zh"],"七帶豆娘魚")
            self.assertEqual(damselfish["scientific_name"],"Abudefduf septemfasciatus")

    def test_unknown_candidate_and_missing_source_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            candidates=root/"candidates.csv"
            ecology=root/"ecology.csv"
            evidence=root/"evidence.csv"
            candidates.write_text("candidate_id,common_name_zh,scientific_name,taxonomy_status\n",encoding="utf-8")
            ecology.write_text(
                "ecology_record_id,candidate_id,scientific_name,parameter_code,parameter_value,unit_or_format,geographic_scope,evidence_id,confidence,model_use_status,limitations\n"
                "EP001,c999,Unknown,habitat,reef,controlled_vocabulary,Taiwan,E999,low,context_only,Unknown\n",encoding="utf-8")
            evidence.write_text("evidence_id,source_name,source_url\n",encoding="utf-8")
            with self.assertRaisesRegex(ValueError,"unknown candidate_id"):
                build_catalog(candidates,ecology,evidence)

if __name__=="__main__":
    unittest.main()
