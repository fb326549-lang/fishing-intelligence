import json
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent / "collector"))
from export_hourly_fish_condition_index_json import export_index

class ExportHourlyFishConditionIndexTests(unittest.TestCase):
    def test_exports_only_forecast_rows_and_preserves_missing_scores_as_null(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            source=root/"index.csv"
            output=root/"latest.json"
            fields=[
                "candidate_id","common_name_zh","scientific_name","region_id","valid_time","data_type",
                "model_status","model_confidence","model_version","feeding_condition_score","feeding_condition_status","feeding_condition_coverage",
                "environment_suitability_score","environment_suitability_status","environment_suitability_coverage",
                "fish_activity_score","fish_activity_status","fish_activity_coverage","overall_fish_condition_index",
                "species_weights_json","best_hour_status_6h","best_hour_rank_6h","best_hour_status_12h",
                "best_hour_rank_12h","best_hour_status_24h","best_hour_rank_24h","indicator_trace_json","interpretation",
            ]
            rows=[
                ["c036","南方舵魚","Kyphosus bigibbus","taitung_south","2026-11-10T10:00:00+08:00","forecast",
                 "preliminary_incomplete_solar_input","low","preliminary-relative-1.2","","insufficient_evidence","0.0000","","insufficient_evidence","0.0000",
                 "","insufficient_evidence","0.0000","","{}","not_established","","not_established","","not_established","","[]",
                 "preliminary_species_relative_fish_condition_index_not_catch_probability"],
                ["c036","南方舵魚","Kyphosus bigibbus","taitung_south","2026-11-10T10:00:00+08:00","observation",
                 "preliminary_incomplete_solar_input","low","preliminary-relative-1.2","","insufficient_evidence","0.0000","","insufficient_evidence","0.0000",
                 "","insufficient_evidence","0.0000","","{}","not_rankable_data_type","","not_rankable_data_type","","not_rankable_data_type","","[]",
                 "preliminary_species_relative_fish_condition_index_not_catch_probability"],
                ["c036","南方舵魚","Kyphosus bigibbus","taitung_south","2026-11-11T12:00:00+08:00","forecast",
                 "preliminary_incomplete_solar_input","low","preliminary-relative-1.2","","insufficient_evidence","0.0000","","insufficient_evidence","0.0000",
                 "","insufficient_evidence","0.0000","","{}","not_established","","not_established","","not_established","","[]",
                 "preliminary_species_relative_fish_condition_index_not_catch_probability"],
            ]
            with source.open("w",encoding="utf-8",newline="") as f:
                import csv
                writer=csv.writer(f)
                writer.writerow(fields)
                writer.writerows(rows)
            export_index(source,output,"2026-11-10T10:00:00+08:00")
            payload=json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema_version"],1)
            self.assertEqual(payload["source"],"fishing-intelligence-fci-preliminary-1.2")
            self.assertIn("low-confidence",payload["model_note"])
            self.assertEqual(len(payload["rows"]),1)
            row=payload["rows"][0]
            self.assertIsNone(row["overall_fish_condition_index"])
            self.assertIsNone(row["feeding_condition_score"])
            self.assertEqual(row["best_hour_status_6h"],"not_established")
            self.assertEqual(row["best_feeding_hour_status_6h"],"not_established")
            self.assertIsNone(row["best_feeding_hour_rank_6h"])
            self.assertEqual(row["best_activity_hour_status_24h"],"not_established")
            self.assertEqual(row["interpretation"],"preliminary_species_relative_fish_condition_index_not_catch_probability")
            self.assertEqual(row["model_confidence"],"low")
            self.assertEqual(row["model_version"],"preliminary-relative-1.2")

if __name__=="__main__": unittest.main()
