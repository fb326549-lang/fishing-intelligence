import sys
import csv
import json
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "species"))
sys.path.insert(0, str(Path(__file__).parent / "collector"))
from preliminary_relative_score_engine import build_rows, load_profiles, percentile_scores, rank_best_hours, TAITUNG_ONLY_TARGETS
from export_hourly_fish_condition_index_json import export_index

PROFILE = Path(__file__).parent / "species" / "preliminary_relative_score_profiles.csv"
TARGETS = {"c036", "c003", "c004", "c001", "c010", "c027", "c018", "c023", "c043", "c044", "c045", "c046", "c047", "c048", "c049", "c050", "c051", "c053", "c054", "c055"}
NO_RESPONSE_EVIDENCE = {"c018", "c023", "c043", "c044", "c045", "c046", "c047", "c048", "c049", "c050", "c051", "c053", "c054", "c055"}


def fixture_records(count=24, include_sea_state=True):
    start = datetime.fromisoformat("2026-11-11T00:00:00+08:00")
    rows = []
    for hour in range(count):
        valid = start + timedelta(hours=hour)
        env = {
            "sunrise": "2026-11-11T06:00:00+08:00",
            "sunset": "2026-11-11T17:00:00+08:00",
        }
        if include_sea_state:
            env.update({"wave_height_m": float((hour * 7) % 9) / 2, "wind_speed_10m_ms": float((hour * 5) % 11)})
        rows.append({"region_id": "taitung_south", "valid_time": valid.isoformat(), "collected_at": "2026-11-10T23:00:00+08:00", "data_type": "forecast", "environment": env})
    return rows, start


def candidate_rows():
    return [
        {"candidate_id": cid, "common_name_zh": name, "scientific_name": scientific,
         "eligibility_gate": "black_hair_alias_requires_morphological_species_check" if cid == "c001" else "verified_taxon"}
        for cid, name, scientific in (
            ("c036", "南方舵魚", "Kyphosus bigibbus"),
            ("c003", "臭肚", "Siganus fuscescens"),
            ("c004", "黑鯛", "Acanthopagrus schlegelii"),
            ("c001", "瓜子鱲", "Girella punctata"),
            ("c010", "花身雞魚", "Terapon jarbua"),
            ("c027", "條紋豆娘魚", "Abudefduf vaigiensis"),
            ("c018", "白帶魚", "Trichiurus lepturus"),
            ("c023", "鬼頭刀", "Coryphaena hippurus"),
            ("c043", "長鰭鰤", "Seriola rivoliana"),
            ("c044", "條狀窄顱帶魚", "Evoxymetopon taeniatus"),
            ("c045", "真烏魴", "Eumegistus illustris"),
            ("c046", "紅紫鸚哥魚", "Scarus rubroviolaceus"),
            ("c047", "花腹鯖", "Scomber australasicus"),
            ("c048", "絲鰭姬鯛", "Pristipomoides filamentosus"),
            ("c049", "紅鰓龍占魚", "Lethrinus rubrioperculatus"),
            ("c050", "劍旗魚", "Xiphias gladius"),
            ("c051", "巴布亞鰺", "Caranx papuensis"),
            ("c053", "杜氏刺尾鯛", "Acanthurus dussumieri"),
            ("c054", "黃擬烏尾鮗", "Paracaesio xanthura"),
            ("c055", "黃帶瓜子鱲", "Girella mezina"),
        )
    ]


class PreliminaryRelativeScoreTests(unittest.TestCase):
    def setUp(self):
        self.profiles = load_profiles(PROFILE)

    def test_every_profile_reference_resolves_to_registered_source_url(self):
        species_dir = PROFILE.parent
        source_by_id = {}
        for filename, key in (
            ("species_response_literature_register.csv", "literature_record_id"),
            ("species_activity_evidence_register.csv", "activity_evidence_id"),
            ("species_seasonal_activity_register.csv", "seasonal_evidence_id"),
        ):
            with (species_dir / filename).open(encoding="utf-8-sig", newline="") as handle:
                source_by_id.update({row[key]: row.get("source_url", "") for row in csv.DictReader(handle)})
        with PROFILE.open(encoding="utf-8-sig", newline="") as handle:
            profiles = list(csv.DictReader(handle))
        for row in profiles:
            all_urls = set(row["source_urls"].split(";"))
            for indicator in ("feeding", "activity"):
                source_ids = [x for x in row[f"{indicator}_source_ids"].split(";") if x]
                urls = [x for x in row[f"{indicator}_source_urls"].split(";") if x]
                self.assertEqual(len(source_ids), len(urls))
                for source_id, url in zip(source_ids, urls):
                    self.assertIn(source_id, source_by_id)
                    self.assertEqual(source_by_id[source_id], url)
                    self.assertIn(url, all_urls)
        by_species = {row["candidate_id"]: row for row in profiles}
        self.assertEqual(by_species["c036"]["feeding_source_ids"], "L051;L052;L053")
        self.assertEqual(by_species["c001"]["feeding_source_ids"], "L040")

    def test_each_phase_score_and_missing_value_has_a_qualitative_basis(self):
        with PROFILE.open(encoding="utf-8-sig", newline="") as handle:
            profile_rows = list(csv.DictReader(handle))
        phases = {"dawn", "day", "dusk", "night"}
        for profile in profile_rows:
            for score_key, basis_key in (("feeding_phase_points", "feeding_phase_basis_json"),
                                         ("activity_phase_points", "activity_phase_basis_json")):
                points, basis = json.loads(profile[score_key]), json.loads(profile[basis_key])
                self.assertEqual(set(points), phases)
                self.assertEqual(set(basis), phases)
                self.assertTrue(all(text.strip() for text in basis.values()))
            overrides = json.loads(profile["activity_month_overrides_json"])
            override_basis = json.loads(profile["activity_month_override_basis_json"])
            self.assertEqual(set(overrides), set(override_basis))
            self.assertIn("not quantitatively calibrated", profile["point_method"].lower())

    def test_southern_drummer_feeding_does_not_claim_an_unsupported_diel_gradient(self):
        profile = next(row for row in self.profiles.values() if row["candidate_id"] == "c036")
        points = profile["_feeding_phase_points"]
        self.assertEqual(len(set(points.values())), 1)
        self.assertIn("no significant day-night intake difference", profile["_feeding_phase_basis_json"]["night"])

        records, as_of = fixture_records()
        rows = build_rows(records, candidate_rows(), self.profiles, as_of)
        drummer_scores = [row["feeding_condition_score"] for row in rows if row["candidate_id"] == "c036"]
        self.assertEqual(set(drummer_scores), {"65.00"})

    def test_trace_explains_selected_phase_and_marks_points_uncalibrated(self):
        records, as_of = fixture_records()
        rows = build_rows(records, candidate_rows(), self.profiles, as_of)
        noon = next(row for row in rows if row["candidate_id"] == "c003" and row["valid_time"].endswith("12:00:00+08:00"))
        trace = json.loads(noon["indicator_trace_json"])
        for item in (trace[0], trace[2]):
            self.assertTrue(item["phase_basis"])
            self.assertFalse(item["quantitative_calibration"])
            self.assertIn("not quantitatively calibrated", item["point_method"].lower())
        unavailable = next(row for row in rows if row["candidate_id"] == "c004")
        unavailable_trace = json.loads(unavailable["indicator_trace_json"])
        self.assertIn("intentionally unavailable", unavailable_trace[0]["phase_basis"])

    def test_species_with_phase_evidence_receive_traceable_low_confidence_scores(self):
        records, as_of = fixture_records()
        rows = build_rows(records, candidate_rows(), self.profiles, as_of)
        self.assertEqual({r["candidate_id"] for r in rows}, TARGETS)
        self.assertEqual(len(rows), 24 * len(TARGETS))
        scored = [r for r in rows if r["overall_fish_condition_index"]]
        self.assertEqual({r["candidate_id"] for r in scored}, TARGETS - {"c004", "c001", "c010", "c027"} - NO_RESPONSE_EVIDENCE)
        self.assertEqual(len(scored), 24 * 2)
        for row in scored:
            self.assertEqual(row["model_status"], "preliminary_scored")
            self.assertEqual(row["model_confidence"], "low")
            self.assertAlmostEqual(sum(__import__("json").loads(row["species_weights_json"]).values()), 1.0)
            trace = __import__("json").loads(row["indicator_trace_json"])
            self.assertEqual(len(trace), 4)
            self.assertTrue(any("source_urls" in item for item in trace))
            self.assertEqual(row["interpretation"], "preliminary_species_relative_fish_condition_index_not_catch_probability")

    def test_scores_use_relative_wave_wind_order_and_no_absolute_biological_cutoff(self):
        records, as_of = fixture_records()
        rows = build_rows(records, candidate_rows(), self.profiles, as_of)
        c003 = [r for r in rows if r["candidate_id"] == "c003"]
        env_scores = [float(r["environment_suitability_score"]) for r in c003]
        self.assertGreater(max(env_scores), min(env_scores))
        self.assertTrue(all(0 <= score <= 100 for score in env_scores))
        same_hour = [r for r in rows if r["valid_time"] == c003[0]["valid_time"]]
        self.assertEqual(len({r["environment_suitability_score"] for r in same_hour}), 1)
        env_trace = json.loads(c003[0]["indicator_trace_json"])[1]
        self.assertIn("relative_rank_within_this_region_next_24h", env_trace["score_interpretation"])
        self.assertIn("not_species_ecological_suitability_or_safety_assessment", env_trace["score_interpretation"])

    def test_equal_forecasts_receive_equal_midrank_percentile_scores(self):
        records = [
            {"region_id": "east", "valid_time": f"2026-11-11T{hour:02}:00:00+08:00",
             "environment": {"wind": value}}
            for hour, value in enumerate((1, 1, 3, 3))
        ]
        scores = percentile_scores(records, "wind", lower_is_better=True)
        self.assertEqual(scores[("east", records[0]["valid_time"])], scores[("east", records[1]["valid_time"])])
        self.assertEqual(scores[("east", records[2]["valid_time"])], scores[("east", records[3]["valid_time"])])
        self.assertGreater(scores[("east", records[0]["valid_time"])], scores[("east", records[2]["valid_time"])])

    def test_food_and_activity_priors_are_species_specific_but_explicitly_low_confidence(self):
        records, as_of = fixture_records()
        rows = build_rows(records, candidate_rows(), self.profiles, as_of)
        at_noon = {r["candidate_id"]: float(r["feeding_condition_score"]) for r in rows if r["valid_time"].endswith("12:00:00+08:00") and r["feeding_condition_score"]}
        self.assertEqual(len({at_noon[cid] for cid in TARGETS - {"c004", "c001", "c010", "c027"} - NO_RESPONSE_EVIDENCE}), 2)
        self.assertNotIn("c004", at_noon)
        self.assertNotIn("c001", at_noon)
        c001 = next(r for r in rows if r["candidate_id"] == "c001")
        self.assertEqual(c001["model_confidence"], "low")
        self.assertIn("confirmed G. punctata", __import__("json").loads(c001["indicator_trace_json"])[0]["limitation"])

    def test_port_sample_only_species_are_included_but_never_scored(self):
        records, as_of = fixture_records()
        rows = build_rows(records, candidate_rows(), self.profiles, as_of)
        unsupported_rows = [r for r in rows if r["candidate_id"] in NO_RESPONSE_EVIDENCE]
        self.assertEqual(len(unsupported_rows), 24 * len(NO_RESPONSE_EVIDENCE))
        for row in unsupported_rows:
            with self.subTest(candidate=row["candidate_id"], time=row["valid_time"]):
                self.assertEqual(row["model_status"], "insufficient_species_specific_evidence")
                self.assertEqual(row["feeding_condition_score"], "")
                self.assertEqual(row["fish_activity_score"], "")
                self.assertEqual(row["overall_fish_condition_index"], "")
                self.assertEqual(row["species_weights_json"], "{}")

    def test_new_species_targets_are_scoped_to_taitung_regions(self):
        records, as_of = fixture_records(count=1)
        records += [dict(record, region_id="hualien_north") for record in records]
        rows = build_rows(records, candidate_rows(), self.profiles, as_of)
        taitung_ids = {row["candidate_id"] for row in rows if row["region_id"] == "taitung_south"}
        hualien_ids = {row["candidate_id"] for row in rows if row["region_id"] == "hualien_north"}
        self.assertEqual(taitung_ids, TARGETS)
        self.assertEqual(hualien_ids, TARGETS - TAITUNG_ONLY_TARGETS)

    def test_rabbitfish_month_specific_diel_proxy_follows_registered_captive_observation(self):
        expected = {7: (40.0, 70.0), 8: (70.0, 40.0), 12: (70.0, 40.0)}
        for month, (day_score, night_score) in expected.items():
            records, as_of = fixture_records()
            records = [{**record,
                        "valid_time": datetime.fromisoformat(record["valid_time"]).replace(month=month).isoformat(),
                        "environment": {**record["environment"],
                                        "sunrise": datetime.fromisoformat(record["environment"]["sunrise"]).replace(month=month).isoformat(),
                                        "sunset": datetime.fromisoformat(record["environment"]["sunset"]).replace(month=month).isoformat()}}
                       for record in records]
            as_of = as_of.replace(month=month)
            rows = [row for row in build_rows(records, candidate_rows(), self.profiles, as_of)
                    if row["candidate_id"] == "c003"]
            noon = next(row for row in rows if row["valid_time"].endswith("12:00:00+08:00"))
            night = next(row for row in rows if row["valid_time"].endswith("23:00:00+08:00"))
            self.assertEqual(float(noon["fish_activity_score"]), day_score)
            self.assertEqual(float(night["fish_activity_score"]), night_score)
            trace = json.loads(night["indicator_trace_json"])[2]
            self.assertEqual(trace["seasonal_override_month"], month)
            self.assertIn("L050", trace["evidence_ids"])
            self.assertIn("captive Japan DIDSON", trace["phase_basis"])

    def test_girella_diurnal_activity_summary_does_not_create_feeding_score_or_composite(self):
        records, as_of = fixture_records()
        rows = [r for r in build_rows(records, candidate_rows(), self.profiles, as_of) if r["candidate_id"] == "c001"]
        self.assertTrue(all(r["feeding_condition_score"] == "" for r in rows))
        self.assertTrue(all(r["feeding_condition_status"] == "insufficient_species_specific_evidence" for r in rows))
        self.assertTrue(all(r["fish_activity_score"] != "" for r in rows))
        self.assertTrue(all(r["overall_fish_condition_index"] == "" for r in rows))
        self.assertTrue(all(r["model_status"] == "insufficient_species_specific_evidence" for r in rows))
        self.assertTrue(all(json.loads(r["species_weights_json"]) == {} for r in rows))

    def test_species_without_hourly_east_taiwan_evidence_is_not_given_neutral_scores(self):
        records, as_of = fixture_records()
        rows = [r for r in build_rows(records, candidate_rows(), self.profiles, as_of) if r["candidate_id"] == "c004"]
        self.assertTrue(all(r["feeding_condition_score"] == "" and r["fish_activity_score"] == "" for r in rows))
        self.assertTrue(all(r["overall_fish_condition_index"] == "" for r in rows))
        self.assertTrue(all(r["model_status"] == "insufficient_species_specific_evidence" for r in rows))
        self.assertTrue(all(r["feeding_condition_status"] == "insufficient_species_specific_evidence" for r in rows))
        self.assertTrue(all(json.loads(r["species_weights_json"]) == {} for r in rows))
        self.assertTrue(all(json.loads(r["indicator_trace_json"])[-1]["weight_basis"] == "not_applicable_no_composite_score" for r in rows))

    def test_black_seabream_spawning_activity_proxy_is_seasonal_only_and_never_unlocks_fci(self):
        records, as_of = fixture_records()
        records = [{**record,
                    "valid_time": datetime.fromisoformat(record["valid_time"]).replace(month=6).isoformat(),
                    "environment": {**record["environment"],
                                    "sunrise": datetime.fromisoformat(record["environment"]["sunrise"]).replace(month=6).isoformat(),
                                    "sunset": datetime.fromisoformat(record["environment"]["sunset"]).replace(month=6).isoformat()}}
                   for record in records]
        as_of = as_of.replace(month=6)
        rows = [row for row in build_rows(records, candidate_rows(), self.profiles, as_of)
                if row["candidate_id"] == "c004"]
        dawn = next(row for row in rows if row["valid_time"].endswith("06:00:00+08:00"))
        daytime = next(row for row in rows if row["valid_time"].endswith("12:00:00+08:00"))
        evening = next(row for row in rows if row["valid_time"].endswith("18:00:00+08:00"))
        self.assertEqual(dawn["fish_activity_score"], "")
        self.assertEqual(float(daytime["fish_activity_score"]), 55.0)
        self.assertEqual(float(evening["fish_activity_score"]), 70.0)
        evening_trace = json.loads(evening["indicator_trace_json"])[2]
        self.assertIn("L056", evening_trace["evidence_ids"])
        self.assertIn("spawning-movement proxy", evening_trace["phase_basis"])
        self.assertTrue(all(row["feeding_condition_score"] == "" for row in rows))
        self.assertTrue(all(row["overall_fish_condition_index"] == "" for row in rows))
        self.assertTrue(all(json.loads(row["species_weights_json"]) == {} for row in rows))

    def test_missing_sea_state_keeps_index_blank_instead_of_filling_zero(self):
        records, as_of = fixture_records(include_sea_state=False)
        rows = build_rows(records, candidate_rows(), self.profiles, as_of)
        self.assertTrue(all(not r["overall_fish_condition_index"] for r in rows))
        self.assertEqual({r["model_status"] for r in rows}, {"preliminary_incomplete_environment_input", "insufficient_species_specific_evidence"})

    def test_one_missing_sea_state_proxy_does_not_create_environment_or_composite_score(self):
        records, as_of = fixture_records()
        for record in records:
            record["environment"].pop("wind_speed_10m_ms")
        rows = build_rows(records, candidate_rows(), self.profiles, as_of)
        eligible = [row for row in rows if row["candidate_id"] in {"c036", "c003"}]
        self.assertTrue(all(row["environment_suitability_score"] == "" for row in eligible))
        self.assertTrue(all(row["overall_fish_condition_index"] == "" for row in eligible))
        self.assertTrue(all(row["model_status"] == "preliminary_incomplete_environment_input" for row in eligible))

    def test_missing_sunrise_sunset_never_treats_unknown_time_as_night(self):
        records, as_of = fixture_records()
        for record in records:
            record["environment"].pop("sunrise")
            record["environment"].pop("sunset")
        rows = build_rows(records, candidate_rows(), self.profiles, as_of)
        self.assertTrue(all(r["feeding_condition_score"] == "" and r["fish_activity_score"] == "" for r in rows))
        self.assertTrue(all(r["model_status"] == "preliminary_incomplete_solar_input" for r in rows))

    def test_best_hours_are_ranked_for_each_requested_horizon(self):
        records, as_of = fixture_records()
        rows = build_rows(records, candidate_rows(), self.profiles, as_of)
        for horizon in (6, 12, 24):
            winners = [r for r in rows if r["candidate_id"] == "c036" and r[f"best_hour_status_{horizon}h"] == "best_hour"]
            self.assertTrue(winners)
            self.assertTrue(winners[0][f"best_hour_rank_{horizon}h"])

    def test_composite_ranking_preserves_all_tied_best_hours(self):
        records, as_of = fixture_records()
        rows = build_rows(records, candidate_rows(), self.profiles, as_of)
        c036 = [row for row in rows if row["candidate_id"] == "c036"]
        for row in c036[:6]:
            row["overall_fish_condition_index"] = "42.00"
        rank_best_hours(rows, as_of)
        winners = [row for row in c036[:6] if row["best_hour_status_6h"] == "best_hour"]
        self.assertEqual(len(winners), 6)
        self.assertTrue(all(row["best_hour_rank_6h"] == "1" for row in winners))

    def test_feeding_and_activity_are_ranked_independently_for_all_horizons(self):
        records, as_of = fixture_records()
        rows = build_rows(records, candidate_rows(), self.profiles, as_of)
        for horizon in (6, 12, 24):
            for prefix, score_field in (("best_feeding_hour", "feeding_condition_score"), ("best_activity_hour", "fish_activity_score")):
                winners = [r for r in rows if r["candidate_id"] == "c036" and r[f"{prefix}_status_{horizon}h"] == "best_hour"]
                self.assertTrue(winners)
                in_horizon = [r for r in rows if r["candidate_id"] == "c036" and r[score_field]
                              and as_of <= datetime.fromisoformat(r["valid_time"]) < as_of + timedelta(hours=horizon)]
                maximum = max(float(r[score_field]) for r in in_horizon)
                self.assertTrue(all(float(r[score_field]) == maximum for r in winners))
                self.assertTrue(all(r[f"{prefix}_rank_{horizon}h"] == "1" for r in winners))

    def test_indicator_ranks_preserve_missing_species_evidence(self):
        records, as_of = fixture_records()
        rows = build_rows(records, candidate_rows(), self.profiles, as_of)
        girella = [r for r in rows if r["candidate_id"] == "c001"]
        black_sea_bream = [r for r in rows if r["candidate_id"] == "c004"]
        self.assertTrue(all(r["best_feeding_hour_status_24h"] == "unscored_hour" for r in girella))
        self.assertTrue(any(r["best_activity_hour_status_24h"] == "best_hour" for r in girella))
        self.assertTrue(all(r["best_feeding_hour_status_24h"] == "unscored_hour" for r in black_sea_bream))
        self.assertTrue(all(r["best_activity_hour_status_24h"] == "unscored_hour" for r in black_sea_bream))

    def test_engine_to_mobile_json_integration(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            records, as_of = fixture_records()
            environment_path = root / "environment.jsonl"
            environment_path.write_text("\n".join(json.dumps(row) for row in records) + "\n", encoding="utf-8")
            candidates_path = root / "candidates.csv"
            with candidates_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["candidate_id", "common_name_zh", "scientific_name", "eligibility_gate"])
                writer.writeheader()
                writer.writerows(candidate_rows())
            scored_csv = root / "scored.csv"
            result = subprocess.run([
                sys.executable, str(Path(__file__).parent / "species" / "preliminary_relative_score_engine.py"),
                "--environment-jsonl", str(environment_path), "--candidates-csv", str(candidates_path),
                "--profiles-csv", str(PROFILE), "--as-of", as_of.isoformat(), "--out", str(scored_csv),
            ], check=False, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            mobile_json = root / "latest.json"
            export_index(scored_csv, mobile_json, as_of.isoformat())
            payload = json.loads(mobile_json.read_text(encoding="utf-8"))
            self.assertEqual(payload["source"], "fishing-intelligence-fci-preliminary-1.2")
            app_html = (Path(__file__).parents[1] / "index.html").read_text(encoding="utf-8")
            self.assertIn("'fishing-intelligence-fci-preliminary-1.2'", app_html)
            self.assertIn("海況相對分（風浪）", app_html)
            self.assertIn("不是魚種適合度", app_html)
            self.assertIn("不代表魚種生態適合度或安全判斷", app_html)
            self.assertEqual({row["candidate_id"] for row in payload["rows"]}, TARGETS)
            self.assertEqual(len(payload["rows"]), 24 * len(TARGETS))
            self.assertTrue(all(row["model_confidence"] == "low" for row in payload["rows"]))
            self.assertTrue(all("best_feeding_hour_status_6h" in row and "best_activity_hour_status_24h" in row for row in payload["rows"]))
            scored_species = {row["candidate_id"] for row in payload["rows"] if row["overall_fish_condition_index"] is not None}
            self.assertEqual(scored_species, TARGETS - {"c004", "c001", "c010", "c027"} - NO_RESPONSE_EVIDENCE)
            black_sea_bream = [row for row in payload["rows"] if row["candidate_id"] == "c004"]
            self.assertTrue(all(row["overall_fish_condition_index"] is None for row in black_sea_bream))
            self.assertTrue(all(row["species_weights"] == {} for row in black_sea_bream))
            girella = [row for row in payload["rows"] if row["candidate_id"] == "c001"]
            self.assertTrue(all(row["feeding_condition_score"] is None for row in girella))
            self.assertTrue(all(row["fish_activity_score"] is not None for row in girella))
            self.assertTrue(any(row["best_activity_hour_status_24h"] == "best_hour" for row in girella))
            self.assertTrue(all(row["best_feeding_hour_status_24h"] == "unscored_hour" for row in girella))
            self.assertTrue(all(row["overall_fish_condition_index"] is None and row["species_weights"] == {} for row in girella))
            self.assertTrue(all("catch_probability" not in row for row in payload["rows"]))


if __name__ == "__main__":
    unittest.main()
