import json
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
    return {"candidate_id":cid,"region_id":"taitung_south","data_type":"forecast",
        "valid_time":f"2026-11-09T{hour:02d}:00:00+08:00",
        "environment_match_score":score,"environment_match_status":"scored" if score!="" else "insufficient_evidence",
        "activity_evidence_status":activity,"activity_evidence_ids":"AE003","seasonal_evidence_ids":"SE003",
        "activity_evidence_context_json":"[]","occurrence_evidence_context_json":"[]","rule_evidence_trace_json":"[]"}

class HourlyFishOutlookTests(unittest.TestCase):
    def test_generates_three_horizons_and_never_best_fishing_window(self):
        env=[forecast(h) for h in range(10,22)]
        joined=[integrated(h,"72") for h in range(10,22)]
        rows=[r for r in build_window_summaries(env,[candidate()],joined,AS_OF) if r["region_id"]=="taitung_south"]
        self.assertEqual([r["horizon_hours"] for r in rows],["6","12","24"])
        self.assertEqual([r["forecast_hour_count"] for r in rows],["6","12","12"])
        self.assertTrue(all(r["best_fishing_window_status"]=="not_established" for r in rows))
        self.assertTrue(all(r["activity_score"]=="" and r["catch_probability"]=="" for r in rows))

    def test_tide_phase_counts_are_context_only_and_missing_hours_stay_visible(self):
        env=[forecast(h) for h in range(10,16)]
        phases=["rising","rising","falling","high_slack","low_slack",None]
        for row,phase in zip(env,phases):
            row["environment"]={"tide_phase":phase,"tide_turning":phase in {"high_slack","low_slack"}}
        joined=[integrated(h,"") for h in range(10,16)]
        row=next(r for r in build_window_summaries(env,[candidate()],joined,AS_OF) if r["region_id"]=="taitung_south" and r["horizon_hours"]=="6")
        self.assertEqual(row["tide_phase_rising_hours"],"2")
        self.assertEqual(row["tide_phase_falling_hours"],"1")
        self.assertEqual(row["tide_phase_high_slack_hours"],"1")
        self.assertEqual(row["tide_phase_low_slack_hours"],"1")
        self.assertEqual(row["tide_phase_known_hour_count"],"5")
        self.assertEqual(row["tide_phase_missing_hour_count"],"1")
        self.assertEqual(row["tide_phase_missing_forecast_hour_count"],"0")
        self.assertEqual(row["tide_phase_coverage"],"0.8333")
        self.assertEqual(row["tide_turning_hour_count"],"2")
        self.assertEqual(row["activity_score"],"")
        self.assertEqual(row["catch_probability"],"")

    def test_occurrence_records_are_aggregated_separately_from_activity_evidence(self):
        env=[forecast(h) for h in range(10,16)]
        joined=[integrated(h,"") for h in range(10,16)]
        for row in joined:
            row["activity_evidence_ids"]=""
            row["occurrence_evidence_ids"]="AE011;AE012"
        result=next(r for r in build_window_summaries(env,[candidate()],joined,AS_OF)
                    if r["region_id"]=="taitung_south" and r["horizon_hours"]=="6")
        self.assertEqual(result["occurrence_evidence_count"],"2")
        self.assertEqual(result["occurrence_evidence_ids"],"AE011;AE012")
        self.assertEqual(result["activity_evidence_ids"],"")
        self.assertEqual(result["activity_score"],"")
        self.assertEqual(result["catch_probability"],"")

    def test_seasonal_context_is_deduplicated_and_preserved_in_outlook(self):
        env=[forecast(h) for h in range(10,16)]
        joined=[integrated(h,"") for h in range(10,16)]
        context=[
            {"id":"SE005","reported_season":"April–June and October–December","geographic_scope":"Eastern Taiwan offshore commercial longline grounds","model_use_status":"context_only_east_taiwan_commercial_fishery","limitations":"Not shore-angling catch data."},
            {"id":"SE006","reported_season":"March–August spawning stage; peak April–July","geographic_scope":"Eastern Taiwan; Taitung XinGang fish market","model_use_status":"context_only_east_taiwan_reproductive_biology","limitations":"Not nearshore availability or catch probability."}
        ]
        for row in joined:
            row["seasonal_evidence_ids"]="SE005;SE006"
            row["seasonal_evidence_context_json"]=json.dumps(context,ensure_ascii=False)
        result=next(r for r in build_window_summaries(env,[candidate()],joined,AS_OF)
                    if r["region_id"]=="taitung_south" and r["horizon_hours"]=="6")
        saved=json.loads(result["seasonal_evidence_context_json"])
        self.assertEqual([x["id"] for x in saved],["SE005","SE006"])
        self.assertEqual(result["seasonal_evidence_ids"],"SE005;SE006")
        self.assertEqual(result["activity_score"],"")
        self.assertEqual(result["catch_probability"],"")

    def test_activity_and_occurrence_source_contexts_are_deduplicated_and_preserved(self):
        env=[forecast(h) for h in range(10,16)]
        activity_context=[{
            "id":"AE003","dimension":"diel_feeding","geographic_scope":"Japan",
            "source_url":"https://example.org/study","model_use_status":"context_only_captive_feeding",
            "limitations":"Captive study, not wild bite activity."
        }]
        occurrence_context=[{
            "id":"AE011","geographic_scope":"Taitung, Taiwan","source_url":"https://example.org/specimen",
            "model_use_status":"context_only_east_taiwan_occurrence","limitations":"One specimen only."
        }]
        joined=[integrated(h,"") for h in range(10,16)]
        for row in joined:
            row["activity_evidence_context_json"]=json.dumps(activity_context)
            row["occurrence_evidence_context_json"]=json.dumps(occurrence_context)
        result=next(r for r in build_window_summaries(env,[candidate()],joined,AS_OF)
                    if r["region_id"]=="taitung_south" and r["horizon_hours"]=="6")
        self.assertEqual(json.loads(result["activity_evidence_context_json"]),activity_context)
        self.assertEqual(json.loads(result["occurrence_evidence_context_json"]),occurrence_context)
        self.assertEqual(result["activity_score"],"")
        self.assertEqual(result["catch_probability"],"")

    def test_conflicting_evidence_metadata_is_rejected(self):
        env=[forecast(h) for h in range(10,16)]
        joined=[integrated(h,"") for h in range(10,16)]
        for row in joined:
            row["activity_evidence_context_json"]=json.dumps([{
                "id":"AE003","model_use_status":"context_only_captive_feeding",
                "source_url":"https://example.org/study"
            }])
        joined[-1]["activity_evidence_context_json"]=json.dumps([{
            "id":"AE003","model_use_status":"eligible_for_activity_scoring",
            "source_url":"https://example.org/study"
        }])
        with self.assertRaisesRegex(ValueError,"conflicting activity_evidence_context_json"):
            build_window_summaries(env,[candidate()],joined,AS_OF)


    def test_rule_provenance_is_aggregated_per_forecast_hour(self):
        env=[forecast(h) for h in range(10,16)]
        joined=[integrated(h,"85") for h in range(10,16)]
        for row in joined:
            row["rule_evidence_trace_json"]=json.dumps([{
                "rule_id":"R1","evidence_id":"E1","source_url":"https://example.org/rule",
                "valid_time":row["valid_time"],"observed_value":24,"match":True,
                "evaluation_status":"evaluated"
            }])
        result=next(r for r in build_window_summaries(env,[candidate()],joined,AS_OF)
                    if r["region_id"]=="taitung_south" and r["horizon_hours"]=="6")
        trace=json.loads(result["rule_evidence_trace_json"])
        self.assertEqual(len(trace),6)
        self.assertEqual({x["rule_id"] for x in trace},{"R1"})
        self.assertEqual({x["evidence_id"] for x in trace},{"E1"})
        self.assertEqual(len({x["valid_time"] for x in trace}),6)

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
        row=next(r for r in build_window_summaries(env,[candidate()],joined,AS_OF) if r["region_id"]=="taitung_south" and r["horizon_hours"]=="6")
        self.assertEqual(row["forecast_hour_count"],"3")
        self.assertEqual(row["expected_hour_count"],"6")
        self.assertEqual(row["forecast_coverage"],"0.5000")
        self.assertEqual(row["environment_match_status"],"partial_environment_match_coverage")

    def test_no_environment_score_does_not_create_one_from_activity_evidence(self):
        env=[forecast(h) for h in range(10,16)]
        joined=[integrated(h,"",activity="context_only_evidence_available") for h in range(10,16)]
        row=next(r for r in build_window_summaries(env,[candidate()],joined,AS_OF) if r["region_id"]=="taitung_south" and r["horizon_hours"]=="6")
        self.assertEqual(row["environment_match_mean"],"")
        self.assertEqual(row["activity_evidence_status"],"context_only_evidence_available")
        self.assertEqual(row["activity_score"],"")

    def test_taxon_gate_is_preserved(self):
        env=[forecast(h) for h in range(10,16)]
        joined=[integrated(h,"",activity="taxon_or_distribution_gate",cid="c002") for h in range(10,16)]
        row=next(r for r in build_window_summaries(env,[candidate("c002","white_hair_is_kyphosus_genus_group_species_identification_required")],joined,AS_OF) if r["region_id"]=="taitung_south" and r["horizon_hours"]=="6")
        self.assertEqual(row["activity_evidence_status"],"taxon_or_distribution_gate")

    def test_as_of_must_be_hour_aligned(self):
        with self.assertRaisesRegex(ValueError,"aligned to the start of an hour"):
            build_window_summaries([], [candidate()], [], datetime.fromisoformat("2026-11-09T10:30:00+08:00"))

    def test_all_six_regions_are_reported_even_without_forecast_records(self):
        rows=build_window_summaries([], [candidate()], [], AS_OF)
        self.assertEqual(len(rows),18)
        self.assertEqual({r["region_id"] for r in rows},{
            "yilan_suao","hualien_north","hualien_south",
            "fengbin_shitiping","chenggong_donghe","taitung_south"})
        self.assertTrue(all(r["environment_match_status"]=="no_forecast_records" for r in rows))
        self.assertTrue(all(r["forecast_coverage"]=="0.0000" for r in rows))

if __name__=="__main__": unittest.main()
