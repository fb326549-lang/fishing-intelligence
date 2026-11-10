#!/usr/bin/env python3
"""Offline regression tests for evidence-gated 6/12/24-hour fish outlook summaries."""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from build_hourly_fish_outlook import REGIONS, build_window_summaries


class HourlyFishOutlookTests(unittest.TestCase):
    def setUp(self):
        self.as_of = datetime(2026, 11, 10, 8, tzinfo=timezone(timedelta(hours=8)))
        self.candidates = [
            {"candidate_id": "c001", "common_name_zh": "測試魚", "scientific_name": "Testus fishus", "eligibility_gate": "verified_taxon"},
            {"candidate_id": "c002", "common_name_zh": "白毛俗名群", "scientific_name": "Kyphosus spp.", "eligibility_gate": "white_hair_is_kyphosus_genus_group_species_identification_required"},
        ]

    def record(self, region, hour, collected_at=None, data_type="forecast", environment=None):
        valid = self.as_of + timedelta(hours=hour)
        collected = collected_at or (self.as_of - timedelta(hours=1))
        return {
            "region_id": region,
            "valid_time": valid.isoformat(),
            "collected_at": collected.isoformat(),
            "data_type": data_type,
            "environment": environment or {},
        }

    def integrated(self, candidate_id, region, valid_time, score="", status="insufficient_evidence", activity_status="insufficient_east_taiwan_activity_evidence"):
        return {
            "candidate_id": candidate_id,
            "region_id": region,
            "valid_time": valid_time,
            "data_type": "forecast",
            "environment_match_score": score,
            "environment_match_status": status,
            "activity_evidence_status": activity_status,
            "activity_evidence_ids": "",
            "occurrence_evidence_ids": "",
            "seasonal_evidence_ids": "",
            "activity_evidence_context_json": "[]",
            "occurrence_evidence_context_json": "[]",
            "seasonal_evidence_context_json": "[]",
            "rule_evidence_trace_json": "[]",
        }

    def test_outputs_six_regions_three_horizons_without_catch_probability(self):
        records = [self.record(region, hour) for region in REGIONS for hour in range(24)]
        output = build_window_summaries(records, self.candidates, [], self.as_of)
        self.assertEqual(len(output), 6 * 3 * 2)
        self.assertEqual({row["region_id"] for row in output}, set(REGIONS))
        self.assertEqual({row["horizon_hours"] for row in output}, {"6", "12", "24"})
        self.assertTrue(all(row["catch_probability"] == "" for row in output))
        self.assertTrue(all(row["activity_score"] == "" for row in output))
        self.assertTrue(all(row["best_fishing_window_status"] == "not_established" for row in output))

    def test_latest_forecast_vintage_is_selected_and_future_collection_is_excluded(self):
        region = REGIONS[0]
        older = self.record(region, 0, self.as_of - timedelta(hours=2))
        newer = self.record(region, 0, self.as_of - timedelta(minutes=30))
        future = self.record(region, 1, self.as_of + timedelta(minutes=1))
        observation = self.record(region, 2, data_type="observation")
        rows = build_window_summaries([older, newer, future, observation], self.candidates[:1], [], self.as_of)
        six_hour = next(row for row in rows if row["horizon_hours"] == "6")
        self.assertEqual(six_hour["forecast_hour_count"], "1")
        self.assertEqual(six_hour["forecast_coverage"], "0.1667")

    def test_environment_summary_is_partial_and_tide_phase_is_context_only(self):
        region = REGIONS[0]
        records = [
            self.record(region, hour, environment={"tide_phase": "rising" if hour < 3 else "falling", "tide_turning": hour == 3})
            for hour in range(6)
        ]
        integrated = [self.integrated("c001", region, row["valid_time"], "80", "matched") for row in records]
        rows = build_window_summaries(records, self.candidates[:1], integrated, self.as_of)
        six_hour = next(row for row in rows if row["horizon_hours"] == "6")
        self.assertEqual(six_hour["environment_match_status"], "environment_match_summary_available")
        self.assertEqual(six_hour["environment_match_mean"], "80.00")
        self.assertEqual(six_hour["tide_phase_rising_hours"], "3")
        self.assertEqual(six_hour["tide_phase_falling_hours"], "3")
        self.assertEqual(six_hour["tide_turning_hour_count"], "1")
        self.assertEqual(six_hour["activity_score"], "")
        self.assertEqual(six_hour["best_fishing_window_status"], "not_established")

    def test_taxonomic_gate_never_receives_environment_score(self):
        region = REGIONS[0]
        record = self.record(region, 0)
        integrated = [self.integrated("c002", region, record["valid_time"], "99", "matched", "context_only_evidence_available")]
        rows = build_window_summaries([record], self.candidates[1:], integrated, self.as_of)
        six_hour = next(row for row in rows if row["horizon_hours"] == "6")
        self.assertEqual(six_hour["environment_match_status"], "taxon_or_distribution_gate")
        self.assertEqual(six_hour["environment_match_mean"], "")
        self.assertEqual(six_hour["activity_evidence_status"], "taxon_or_distribution_gate")
        self.assertEqual(six_hour["catch_probability"], "")

    def test_missing_hours_are_reported_not_interpolated(self):
        region = REGIONS[0]
        records = [self.record(region, hour) for hour in (0, 2, 4)]
        rows = build_window_summaries(records, self.candidates[:1], [], self.as_of)
        six_hour = next(row for row in rows if row["horizon_hours"] == "6")
        self.assertEqual(six_hour["forecast_hour_count"], "3")
        self.assertEqual(six_hour["expected_hour_count"], "6")
        self.assertEqual(six_hour["forecast_coverage"], "0.5000")
        self.assertEqual(six_hour["tide_phase_missing_forecast_hour_count"], "3")

    def test_as_of_must_be_hour_aligned(self):
        with self.assertRaisesRegex(ValueError, "aligned to the start of an hour"):
            build_window_summaries([], self.candidates, [], self.as_of + timedelta(minutes=1))


if __name__ == "__main__":
    unittest.main(verbosity=2)
