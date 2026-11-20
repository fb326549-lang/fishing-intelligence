import csv
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
CANDIDATES = ROOT.parent / "P1" / "species" / "species_candidate_register.csv"
OCCURRENCES = ROOT / "species" / "species_regional_occurrence_register.csv"
RADAR_PAGE = ROOT.parent / "index.html"


def read_rows(path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


class TaitungRegionalSpeciesDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.candidates = {row["candidate_id"]: row for row in read_rows(CANDIDATES)}
        cls.occurrences = read_rows(OCCURRENCES)
        cls.by_occurrence = {row["regional_occurrence_id"]: row for row in cls.occurrences}

    def test_every_occurrence_has_a_matching_species_candidate(self):
        for row in self.occurrences:
            with self.subTest(occurrence=row["regional_occurrence_id"]):
                candidate = self.candidates[row["candidate_id"]]
                self.assertEqual(row["taxon_scientific_name"], candidate["scientific_name"])
                self.assertTrue(row["source_url"].startswith("https://"))
                self.assertTrue(row["limitations"].strip())
                self.assertTrue(row["model_use_status"].startswith("context_only"))

    def test_taitung_sites_map_to_the_existing_taitung_regions(self):
        expected = {
            "chenggong_donghe",
            "taitung_south",
        }
        rows = self.occurrences
        self.assertTrue(rows)
        for row in rows:
            with self.subTest(occurrence=row["regional_occurrence_id"]):
                if row["site_code"] == "GREEN-ISLAND-FISHERY-2008" or row["candidate_id"] == "c052":
                    self.assertEqual(row["region_id"], "")
                elif row["region_id"] == "taitung":
                    self.assertEqual(row["candidate_id"], "c056")
                else:
                    self.assertIn(row["region_id"], expected)

    def test_shanyuan_mapping_and_non_taitung_rows_are_excluded(self):
        self.assertEqual(self.by_occurrence["RO001"]["region_id"], "chenggong_donghe")
        self.assertEqual(self.by_occurrence["RO002"]["region_id"], "chenggong_donghe")
        self.assertEqual(self.by_occurrence["RO004"]["region_id"], "chenggong_donghe")
        self.assertNotIn("RO006", self.by_occurrence)
        self.assertNotIn("RO007", self.by_occurrence)

    def test_species_level_taxa_are_not_collapsed_into_vernacular_groups(self):
        expected = {
            "RO008": ("c042", "Abudefduf septemfasciatus"),
            "RO016": ("c019", "Trachurus japonicus"),
            "RO018": ("c031", "Scarus rivulatus"),
            "RO019": ("c040", "Lutjanus fulvus"),
            "RO020": ("c041", "Siganus guttatus"),
            "RO021": ("c010", "Terapon jarbua"),
            "RO038": ("c055", "Girella mezina"),
            "RO039": ("c023", "Coryphaena hippurus"),
            "RO040": ("c056", "Istiompax indica"),
        }
        for occurrence_id, (candidate_id, scientific_name) in expected.items():
            with self.subTest(occurrence=occurrence_id):
                row = self.by_occurrence[occurrence_id]
                self.assertEqual(row["candidate_id"], candidate_id)
                self.assertEqual(row["taxon_scientific_name"], scientific_name)
                expected_region = "taitung" if occurrence_id == "RO040" else "chenggong_donghe" if occurrence_id in {"RO008", "RO021", "RO038", "RO039"} else "taitung_south"
                self.assertEqual(row["region_id"], expected_region)

    def test_occurrence_ids_are_unique(self):
        ids = [row["regional_occurrence_id"] for row in self.occurrences]
        self.assertEqual(len(ids), len(set(ids)))

    def test_taitung_radar_uses_local_occurrences_and_excludes_girella(self):
        page = RADAR_PAGE.read_text(encoding="utf-8")
        self.assertIn("{id:'c010',name:'花身雞魚',scientific:'Terapon jarbua'}", page)
        self.assertIn("{id:'c027',name:'條紋豆娘魚',scientific:'Abudefduf vaigiensis'}", page)
        self.assertIn("x.id!=='c001'", page)
        self.assertIn("['present','fishery_record'].includes(r.recorded_presence)", page)
        self.assertIn("r.region_id==='taitung'", page)
        self.assertIn("const available=isTaitungRegion", page)
        self.assertIn("const taitungCandidateIds=getTaitungRadarCandidateIds(region,data)", page)
        self.assertIn("(!taitungCandidateIds||taitungCandidateIds.has(r.candidate_id))", page)
        self.assertIn("本區全部有區域證據魚種", page)
        for cid, region in (("c010", "chenggong_donghe"), ("c027", "taitung_south")):
            self.assertTrue(any(row["candidate_id"] == cid and row["region_id"] == region for row in self.occurrences))
        self.assertIn("{id:'c055',name:'黃帶瓜子鱲',scientific:'Girella mezina'}", page)

    def test_girella_mezina_is_separate_from_punctata_and_naso_is_not_mapped_to_mainland(self):
        girella = self.by_occurrence["RO038"]
        self.assertEqual((girella["candidate_id"], girella["taxon_scientific_name"]), ("c055", "Girella mezina"))
        self.assertIn("定置網而非釣獲", girella["limitations"])
        self.assertFalse(any(row["candidate_id"] == "c001" and row["region_id"] in {"chenggong_donghe", "taitung_south"} for row in self.occurrences))
        island_taxon = self.by_occurrence["RO032"]
        self.assertEqual((island_taxon["candidate_id"], island_taxon["region_id"]), ("c052", ""))
        self.assertIn("東部離島", island_taxon["limitations"])

    def test_port_only_samples_are_not_region_targets_without_independent_catch_evidence(self):
        port_only_candidates = {row["candidate_id"] for row in self.occurrences
                                if row["recorded_presence"] == "port_sample_only" and row["region_id"]}
        target_candidates = {row["candidate_id"] for row in self.occurrences
                             if row["region_id"] in {"chenggong_donghe", "taitung_south", "taitung"}
                             and row["recorded_presence"] in {"present", "fishery_record"}}
        self.assertEqual(port_only_candidates - target_candidates, port_only_candidates - {"c023"})
        self.assertIn("c023", target_candidates)
        self.assertIn("c056", target_candidates)
        self.assertNotIn("c052", target_candidates)
        self.assertNotIn("c001", target_candidates)
        self.assertFalse(any(row["candidate_id"] in {"c003", "c004"} and row["region_id"] == "taitung_south"
                             for row in self.occurrences))
        page = RADAR_PAGE.read_text(encoding="utf-8")
        self.assertIn("id:'c056',name:'立翅旗魚（黑皮旗魚）',scientific:'Istiompax indica'", page)
        self.assertIn("只列本區出現或有台東漁業捕獲依據的魚種", page)

    def test_county_scale_taitung_capture_is_marked_and_not_mapped_to_one_subregion(self):
        row = self.by_occurrence["RO040"]
        self.assertEqual(row["region_id"], "taitung")
        self.assertIn("未細分成功東河／台東南段", row["site_name"])
        self.assertIn("未提供可映射", row["study_scope"])
        self.assertEqual(row["recorded_presence"], "fishery_record")

    def test_success_port_report_sampling_events_match_reported_taxa_and_counts(self):
        sample_rows = [row for row in self.occurrences if row["site_code"] == "TAI-NEWPORT-SAMPLES-2025"]
        expected = {
            "114-1": {"c043": 1, "c044": 1, "c045": 1, "c046": 1, "c047": 4, "c048": 6, "c049": 9, "c018": 10},
            "114-2": {"c050": 1, "c051": 1, "c052": 1, "c023": 1, "c018": 9, "c053": 23, "c054": 7, "c047": 5},
        }
        for event, species_counts in expected.items():
            rows = [row for row in sample_rows if row["visit_number"] == event]
            actual = {row["candidate_id"]: int(row["study_scope"].split("報告總數 ", 1)[1].split(" ", 1)[0]) for row in rows}
            self.assertEqual(actual, species_counts)
            self.assertTrue(all(row["study_year"] == "2025" and row["source_url"].startswith("https://www.namr.gov.tw/") for row in rows))


if __name__ == "__main__":
    unittest.main()
