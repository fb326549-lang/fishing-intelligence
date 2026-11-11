import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "collector"))
from export_hourly_fish_outlook_json import build_payload

class ExportHourlyFishOutlookTests(unittest.TestCase):
    def setUp(self):
        self.rows = [
            {"as_of":"2026-11-09T20:00:00+08:00","region_id":"chenggong_donghe","horizon_hours":str(h)}
            for h in (6,12,24)
        ]

    def test_historical_edna_context_is_embedded_but_not_used_as_activity_score(self):
        context = {
            "schema_version":2,
            "source":"OCA Taiwan fish eDNA survey",
            "dataset_page":"https://data.gov.tw/dataset/example",
            "generated_at_utc":"2026-11-09T12:00:00+00:00",
            "interpretation":"Historical positive eDNA occurrence context only.",
            "records":[{
                "candidate_id":"c027","region_id":"chenggong_donghe",
                "exact_positive_detection_record_count":0,
                "ambiguous_positive_detection_record_count":4,
                "exact_sample_month_count":0,
                "exact_distinct_station_count":0,
                "first_sampled_month":"",
                "last_sampled_month":"",
                "min_source_reported_depth_m":None,
                "max_source_reported_depth_m":None,
                "depth_field_semantics":"source_label_unresolved_station_or_sampling_depth",
                "dataset_ids":["oca_example"],
                "ambiguous_taxon_labels":["Siganus canaliculatus/fuscescens"],
                "model_use_status":"context_only_edna_occurrence",
            }],
        }
        payload=build_payload(self.rows,context,"2026-11-09T12:01:00+00:00")
        record=payload["edna_occurrence_context"]["records"][0]
        self.assertEqual(record["candidate_id"],"c027")
        self.assertEqual(record["ambiguous_positive_detection_record_count"],4)
        self.assertIsNone(payload["model_limits"]["activity_score"])
        self.assertIsNone(payload["model_limits"]["catch_probability"])

    def test_missing_edna_context_is_not_presented_as_absence(self):
        payload=build_payload(self.rows)
        self.assertEqual(payload["edna_occurrence_context"]["records"],[])
        self.assertIn("not evidence of absence",payload["edna_occurrence_context"]["interpretation"])

    def test_context_cannot_be_promoted_to_activity_evidence(self):
        context={
            "schema_version":2,
            "source":"OCA Taiwan fish eDNA survey",
            "dataset_page":"https://data.gov.tw/dataset/example",
            "generated_at_utc":"2026-11-09T12:00:00+00:00",
            "interpretation":"Historical positive eDNA occurrence context only.",
            "records":[{
                "candidate_id":"c027","region_id":"chenggong_donghe",
                "exact_positive_detection_record_count":1,
                "ambiguous_positive_detection_record_count":0,
                "exact_sample_month_count":1,
                "exact_distinct_station_count":1,
                "first_sampled_month":"2026-01",
                "last_sampled_month":"2026-01",
                "min_source_reported_depth_m":None,
                "max_source_reported_depth_m":None,
                "depth_field_semantics":"source_label_unresolved_station_or_sampling_depth",
                "dataset_ids":["oca_example"],
                "ambiguous_taxon_labels":[],
                "model_use_status":"eligible_for_activity_scoring",
            }],
        }
        with self.assertRaisesRegex(ValueError,"cannot be promoted"):
            build_payload(self.rows,context)

    def test_rejects_legacy_edna_context_schema(self):
        context={"schema_version":1,"records":[]}
        with self.assertRaisesRegex(ValueError,"schema is invalid"):
            build_payload(self.rows,context)

    def test_species_ecology_context_is_embedded_with_provenance(self):
        context={
            "schema_version":1,
            "record_count":1,
            "interpretation":"Natural-history context only.",
            "records":[{
                "candidate_id":"c027","parameter_code":"habitat",
                "parameter_value":"reef; coastal",
                "source_url":"https://fishdb.sinica.edu.tw/taxon/example",
                "model_use_status":"eligible_as_species_context",
            }],
        }
        payload=build_payload(self.rows,species_context=context)
        record=payload["species_ecology_context"]["records"][0]
        self.assertEqual(record["candidate_id"],"c027")
        self.assertEqual(record["parameter_value"],"reef; coastal")
        self.assertEqual(payload["species_ecology_context"]["interpretation"],"Natural-history context only.")

    def test_species_context_requires_source_provenance(self):
        context={"schema_version":1,"records":[{"candidate_id":"c027","parameter_code":"habitat"}]}
        with self.assertRaisesRegex(ValueError,"missing candidate, parameter or provenance"):
            build_payload(self.rows,species_context=context)

    def test_species_evidence_context_fields_are_preserved_in_published_rows(self):
        row=dict(self.rows[0])
        row.update({
            "activity_evidence_context_json": '[{"id":"AE003","model_use_status":"context_only_captive_feeding"}]',
            "occurrence_evidence_context_json": '[{"id":"AE011","model_use_status":"context_only_east_taiwan_occurrence"}]',
        })
        rows=[row]+[dict(r) for r in self.rows[1:]]
        payload=build_payload(rows)
        published=payload["rows"][0]
        self.assertIn('"AE003"',published["activity_evidence_context_json"])
        self.assertIn('"AE011"',published["occurrence_evidence_context_json"])
        self.assertIsNone(payload["model_limits"]["activity_score"])
        self.assertIsNone(payload["model_limits"]["catch_probability"])

    def test_requires_all_three_horizons(self):
        with self.assertRaisesRegex(ValueError,"6/12/24-hour"):
            build_payload(self.rows[:2])

if __name__=="__main__":
    unittest.main()
