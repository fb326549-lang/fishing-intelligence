import sys
import unittest
from datetime import datetime
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent/"species"))
from build_hourly_fish_outlook import build_window_summaries, select_forecast_vintages

AS_OF=datetime.fromisoformat("2026-11-09T10:00:00+08:00")

def forecast(hour,collected="2026-11-09T09:00:00+08:00",data_type="forecast",region="taitung_south"):
    return {"region_id":region,"valid_time":f"2026-11-09T{hour:02d}:00:00+08:00",
        "collected_at":collected,"data_type":data_type,"environment":{}}

def candidate(cid="c003",gate="verified_taxon"):
    return {"candidate_id":cid,"common_name_zh":"臭肚","scientific_name":"Siganus fuscescens","eligibility_gate":gate}

def integrated(hour,score="",activity="context_only_evidence_available",cid="c003"):
    return {"candidate_id":cid,"region_id":"taitung_south",
        "valid_time":f"2026-11-09T{hour:02d}:00:00+08:00",
        "environment_match_score":score,"environment_match_status":"scored" if score!="" else "insufficient_evidence",
        "activity_evidence_status":activity,"activity_evidence_ids":"AE003","seasonal_evidence_ids":"SE003"}

class HourlyFishOutlookTests(unittest.TestCase):
    def test_generates_three_horizons_and_never_best_fishing_window(self):
        env=[forecast(h) for h in range(10,22)]
        joined=[integrated(h,"72") for h in range(10,22)]
        rows=build_window_summaries(env,[candidate()],joined,AS_OF)
        self.assertEqual([r["horizon_hours"] for r in rows],["6","12","24"])
        self.assertEqual([r["forecast_hour_count"] for r in rows],["6","12","12"])
        self.assertTrue(all(r["best_fishing_window_status"]=="not_established" for r in rows))
        self.assertTrue(all(r["activity_score"]=="" and r["catch_probability"]=="" for r in rows))

    def test_latest_forecast_vintage_before_as_of_is_selected(self):
        old=forecast(10,collected="2026-11-09T08:00:00+08:00")
        new=forecast(10,collected="2026-11-09T09:30:00+08:00")
        future_vintage=forecast(10,collected="2026-11-09T10:30:00+08:00")
        chosen=select_forecast_vintages([old,new,future_vintage],AS_OF)
        self.assertEqual(len(chosen),1)
        self.assertEqual(chosen[0]["collected_at"],"2026-11-09T09:30:00+08:00")

    def test_observations_are_not_mixed_into_forecast(self):
        env=[forecast(10),forecast(11,data_type="observation")]
        chosen=select_forecast_vintages(env,AS_OF)
        self.assertEqual(len(chosen),1)
        self.assertEqual(chosen[0]["data_type"],"forecast")

    def test_missing_hours_are_not_filled_and_coverage_is_reduced(self):
        env=[forecast(10),forecast(11),forecast(13)]
        joined=[integrated(h,"70") for h in (10,11,13)]
        row=build_window_summaries(env,[candidate()],joined,AS_OF)[0]
        self.assertEqual(row["forecast_hour_count"],"3")
        self.assertEqual(row["expected_hour_count"],"6")
        self.assertEqual(row["forecast_coverage"],"0.5000")
        self.assertEqual(row["environment_match_status"],"partial_environment_match_coverage")

    def test_no_environment_score_does_not_create_one_from_activity_evidence(self):
        env=[forecast(h) for h in range(10,16)]
        joined=[integrated(h,"",activity="context_only_evidence_available") for h in range(10,16)]
        row=build_window_summaries(env,[candidate()],joined,AS_OF)[0]
        self.assertEqual(row["environment_match_mean"],"")
        self.assertEqual(row["activity_evidence_status"],"context_only_evidence_available")
        self.assertEqual(row["activity_score"],"")

    def test_taxon_gate_is_preserved(self):
        env=[forecast(h) for h in range(10,16)]
        joined=[integrated(h,"",activity="taxon_or_distribution_gate",cid="c002") for h in range(10,16)]
        row=build_window_summaries(env,[candidate("c002","white_hair_is_kyphosus_genus_group_species_identification_required")],joined,AS_OF)[0]
        self.assertEqual(row["activity_evidence_status"],"taxon_or_distribution_gate")

    def test_as_of_must_be_hour_aligned(self):
        with self.assertRaisesRegex(ValueError,"aligned to the start of an hour"):
            build_window_summaries([], [candidate()], [], datetime.fromisoformat("2026-11-09T10:30:00+08:00"))

if __name__=="__main__": unittest.main()
