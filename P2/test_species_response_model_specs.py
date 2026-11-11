import csv
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SPECIES_DIR = ROOT / "species"


class SpeciesResponseModelSpecTests(unittest.TestCase):
    def test_each_target_species_has_three_indicator_spec_and_registered_sources(self):
        with (SPECIES_DIR / "species_response_literature_register.csv").open(
            encoding="utf-8-sig", newline=""
        ) as source_file:
            registered_ids = {
                row["literature_record_id"]
                for row in csv.DictReader(source_file)
            }

        specs = {
            "southern_drummer_response_model_spec.md": {"L051", "L052", "L053"},
            "rabbitfish_response_model_spec.md": {"L002", "L004", "L005", "L046", "L047", "L048", "L049", "L050"},
            "black_seabream_response_model_spec.md": {"L012", "L013", "L014", "L023", "L054"},
            "girella_punctata_response_model_spec.md": {"L006", "L007", "L008", "L009", "L010", "L011", "L015", "L019"},
        }
        required_sections = (
            "覓食條件",
            "環境適合度",
            "魚類活動力",
            "缺值",
            "中魚",
        )

        for filename, expected_ids in specs.items():
            with self.subTest(spec=filename):
                content = (SPECIES_DIR / filename).read_text(encoding="utf-8")
                for section in required_sections:
                    self.assertIn(section, content)
                cited_ids = set(re.findall(r"\bL\d{3}\b", content))
                self.assertTrue(expected_ids.issubset(cited_ids))
                self.assertTrue(cited_ids.issubset(registered_ids))


if __name__ == "__main__":
    unittest.main()
