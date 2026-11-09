import csv
import io
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "collector"))
from fetch_oca_edna_occurrence import (
    build_monthly_summary, collect, load_region_stations, normalize_fields,
    parse_payload, parse_year_month, write_outputs,
)

ROOT = Path(__file__).parent

class OcaEdnaOccurrenceTests(unittest.TestCase):
    def test_csv_field_aliases_and_roc_date_are_normalized(self):
        row = {
            "站點名稱": "成功外海站",
            "緯度(北緯)": "23.10",
            "經度(東經)": "121.40",
            "深度(m)": "15",
            "採樣時間": "112年03月18日",
            "學名(Science Name)": "Abudefduf vaigiensis",
            "中文學名": "條紋豆娘魚",
            "科別(Family)": "Pomacentridae",
            "中文科別": "雀鯛科",
            "所屬計畫類別": "潛水調查",
        }
        normalized = normalize_fields(row)
        self.assertEqual(normalized["scientific_name"], "Abudefduf vaigiensis")
        self.assertEqual(normalized["station_name"], "成功外海站")
        self.assertEqual(parse_year_month(normalized["sampled_at"]), "2023-03")

    def test_parser_supports_csv_json_and_zip_payloads(self):
        csv_bytes = "站點名稱,學名(Science Name),採樣時間\n站點A,Siganus fuscescens,2023-03-18\n".encode()
        self.assertEqual(parse_payload(csv_bytes)[0]["站點名稱"], "站點A")
        json_bytes = json.dumps({"data": [{"station_name": "站點B", "scientific_name": "Abudefduf vaigiensis"}]}).encode()
        self.assertEqual(parse_payload(json_bytes)[0]["station_name"], "站點B")
        zipped = io.BytesIO()
        with zipfile.ZipFile(zipped, "w") as archive:
            archive.writestr("records.csv", csv_bytes)
        self.assertEqual(parse_payload(zipped.getvalue())[0]["學名(Science Name)"], "Siganus fuscescens")

    def test_nearest_region_mapping_is_context_only_and_distance_limited(self):
        mapping = ROOT.parent / "P1" / "stations" / "east_region_station_mapping.csv"
        stations = load_region_stations(mapping)
        source_rows = [("test_dataset", "test", "https://example.org/data", [{
            "站點名稱": "成功外海站", "緯度(北緯)": "23.10", "經度(東經)": "121.40",
            "深度(m)": "15", "採樣時間": "2023-03-18",
            "學名(Science Name)": "Abudefduf vaigiensis", "中文學名": "條紋豆娘魚",
        }, {
            "站點名稱": "遠洋站", "緯度(北緯)": "18.0", "經度(東經)": "130.0",
            "深度(m)": "100", "採樣時間": "2023-03-18",
            "學名(Science Name)": "Abudefduf vaigiensis", "中文學名": "條紋豆娘魚",
        }])]
        detections = collect(source_rows, stations, {"abudefduf vaigiensis": "c027"}, "2026-11-09T00:00:00+00:00")
        self.assertEqual(len(detections), 2)
        near = next(x for x in detections if x["station_name"] == "成功外海站")
        far = next(x for x in detections if x["station_name"] == "遠洋站")
        self.assertEqual(near["candidate_id"], "c027")
        self.assertEqual(near["region_id"], "chenggong_donghe")
        self.assertEqual(near["region_mapping_status"], "nearest_station_context_only")
        self.assertEqual(far["region_id"], "")
        self.assertEqual(far["region_mapping_status"], "outside_six_region_reference_radius")
        self.assertEqual(near["model_use_status"], "context_only_edna_occurrence")
        self.assertNotIn("fish_count", near)
        self.assertNotIn("activity_score", near)
        self.assertNotIn("catch_probability", near)

    def test_monthly_summary_counts_positive_records_not_fish_abundance(self):
        rows = [
            {"candidate_id": "c027", "scientific_name": "Abudefduf vaigiensis", "region_id": "chenggong_donghe", "year_month": "2023-03", "station_name": "A", "depth_m": 10, "dataset_id": "d1"},
            {"candidate_id": "c027", "scientific_name": "Abudefduf vaigiensis", "region_id": "chenggong_donghe", "year_month": "2023-03", "station_name": "B", "depth_m": 20, "dataset_id": "d2"},
        ]
        summary = build_monthly_summary(rows)[0]
        self.assertEqual(summary["positive_detection_record_count"], 2)
        self.assertEqual(summary["distinct_station_count"], 2)
        self.assertEqual(summary["min_sample_depth_m"], 10)
        self.assertEqual(summary["max_sample_depth_m"], 20)
        self.assertEqual(summary["model_use_status"], "context_only_edna_occurrence")
        self.assertNotIn("abundance", summary)
        self.assertNotIn("catch_rate", summary)

    def test_output_manifest_declares_occurrence_only_interpretation(self):
        with tempfile.TemporaryDirectory() as tmp:
            detections = [{
                "record_id": "abc", "dataset_id": "d1", "model_use_status": "context_only_edna_occurrence",
            }]
            with self.assertRaises(KeyError):
                # Monthly aggregation needs full fields; this guards against silently
                # writing a malformed summary as a valid empty result.
                build_monthly_summary(detections)
            detections[0].update({
                "candidate_id": "c027", "scientific_name": "Abudefduf vaigiensis",
                "region_id": "chenggong_donghe", "year_month": "2023-03",
                "station_name": "A", "depth_m": None,
            })
            summary = build_monthly_summary(detections)
            write_outputs(Path(tmp), detections, summary, "2026-11-09T00:00:00+00:00")
            manifest = json.loads((Path(tmp) / "manifest.json").read_text(encoding="utf-8"))
            self.assertIn("do not measure fish abundance", manifest["interpretation"])
            self.assertTrue((Path(tmp) / "edna_occurrence_context.jsonl").exists())
            self.assertTrue((Path(tmp) / "edna_species_monthly_summary.csv").exists())

if __name__ == "__main__":
    unittest.main()
