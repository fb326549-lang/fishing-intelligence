import csv
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
CANDIDATES = ROOT.parent / "P1" / "species" / "species_candidate_register.csv"
OCCURRENCES = ROOT / "species" / "species_regional_occurrence_register.csv"


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
        rows = [row for row in self.occurrences if row["regional_occurrence_id"] not in {"RO006", "RO007"}]
        self.assertTrue(rows)
        for row in rows:
            with self.subTest(occurrence=row["regional_occurrence_id"]):
                if row["site_code"] == "GREEN-ISLAND-FISHERY-2008":
                    self.assertEqual(row["region_id"], "")
                else:
                    self.assertIn(row["region_id"], expected)

    def test_shanyuan_mapping_and_hualien_rows_are_preserved(self):
        self.assertEqual(self.by_occurrence["RO001"]["region_id"], "chenggong_donghe")
        self.assertEqual(self.by_occurrence["RO002"]["region_id"], "chenggong_donghe")
        self.assertEqual(self.by_occurrence["RO004"]["region_id"], "chenggong_donghe")
        self.assertEqual(self.by_occurrence["RO006"]["region_id"], "fengbin_shitiping")
        self.assertEqual(self.by_occurrence["RO007"]["region_id"], "fengbin_shitiping")

    def test_species_level_taxa_are_not_collapsed_into_vernacular_groups(self):
        expected = {
            "RO008": ("c042", "Abudefduf septemfasciatus"),
            "RO016": ("c019", "Trachurus japonicus"),
            "RO018": ("c031", "Scarus rivulatus"),
            "RO019": ("c040", "Lutjanus fulvus"),
            "RO020": ("c041", "Siganus guttatus"),
            "RO021": ("c010", "Terapon jarbua"),
        }
        for occurrence_id, (candidate_id, scientific_name) in expected.items():
            with self.subTest(occurrence=occurrence_id):
                row = self.by_occurrence[occurrence_id]
                self.assertEqual(row["candidate_id"], candidate_id)
                self.assertEqual(row["taxon_scientific_name"], scientific_name)
                expected_region = "chenggong_donghe" if occurrence_id in {"RO008", "RO021"} else "taitung_south"
                self.assertEqual(row["region_id"], expected_region)

    def test_occurrence_ids_are_unique(self):
        ids = [row["regional_occurrence_id"] for row in self.occurrences]
        self.assertEqual(len(ids), len(set(ids)))


if __name__ == "__main__":
    unittest.main()
