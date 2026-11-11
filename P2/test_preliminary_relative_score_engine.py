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
from preliminary_relative_score_engine import build_rows, load_profiles
from export_hourly_fish_condition_index_json import export_index

PROFILE = Path(__file__).parent / "species" / "preliminary_relative_score_profiles.csv"
TARGETS = {"c036", "c003", "c004", "c001"}


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
            urls = set(row["source_urls"].split(";"))
            source_ids = set((row["feeding_source_ids"] + ";" + row["activity_source_ids"]).split(";"))
            for source_id in source_ids:
                self.assertIn(source_id, source_by_id)
                self.assertIn(source_by_id[source_id], urls)

    def test_species_with_phase_evidence_receive_traceable_low_confidence_scores(self):
        records, as_of = fixture_records()
        rows = build_rows(records, candidate_rows(), self.profiles, as_of)
        self.assertEqual({r["candidate_id"] for r in rows}, TARGETS)
        self.assertEqual(len(rows), 24 * 4)
        scored = [r for r in rows if r["overall_fish_condition_index"]]
        self.assertEqual({r["candidate_id"] for r in scored}, TARGETS - {"c004"})
        self.assertEqual(len(scored), 24 * 3)
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

    def test_food_and_activity_priors_are_species_specific_but_explicitly_low_confidence(self):
        records, as_of = fixture_records()
        rows = build_rows(records, candidate_rows(), self.profiles, as_of)
        at_noon = {r["candidate_id"]: float(r["feeding_condition_score"]) for r in rows if r["valid_time"].endswith("12:00:00+08:00") and r["feeding_condition_score"]}
        self.assertEqual(len({at_noon[cid] for cid in TARGETS - {"c004"}}), 3)
        self.assertNotIn("c004", at_noon)
        c001 = next(r for r in rows if r["candidate_id"] == "c001")
        self.assertEqual(c001["model_confidence"], "low")
        self.assertIn("confirmed G. punctata", __import__("json").loads(c001["indicator_trace_json"])[0]["limitation"])

    def test_species_without_hourly_east_taiwan_evidence_is_not_given_neutral_scores(self):
        records, as_of = fixture_records()
        rows = [r for r in build_rows(records, candidate_rows(), self.profiles, as_of) if r["candidate_id"] == "c004"]
        self.assertTrue(all(r["feeding_condition_score"] == "" and r["fish_activity_score"] == "" for r in rows))
        self.assertTrue(all(r["overall_fish_condition_index"] == "" for r in rows))
        self.assertTrue(all(r["model_status"] == "insufficient_species_specific_evidence" for r in rows))
        self.assertTrue(all(r["feeding_condition_status"] == "insufficient_species_specific_evidence" for r in rows))

    def test_missing_sea_state_keeps_index_blank_instead_of_filling_zero(self):
        records, as_of = fixture_records(include_sea_state=False)
        rows = build_rows(records, candidate_rows(), self.profiles, as_of)
        self.assertTrue(all(not r["overall_fish_condition_index"] for r in rows))
        self.assertEqual({r["model_status"] for r in rows}, {"preliminary_incomplete_solar_or_environment_input", "insufficient_species_specific_evidence"})

    def test_missing_sunrise_sunset_never_treats_unknown_time_as_night(self):
        records, as_of = fixture_records()
        for record in records:
            record["environment"].pop("sunrise")
            record["environment"].pop("sunset")
        rows = build_rows(records, candidate_rows(), self.profiles, as_of)
        self.assertTrue(all(r["feeding_condition_score"] == "" and r["fish_activity_score"] == "" for r in rows))
        self.assertTrue(all(r["model_status"] == "preliminary_incomplete_solar_or_environment_input" for r in rows))

    def test_best_hours_are_ranked_for_each_requested_horizon(self):
        records, as_of = fixture_records()
        rows = build_rows(records, candidate_rows(), self.profiles, as_of)
        for horizon in (6, 12, 24):
            winners = [r for r in rows if r["candidate_id"] == "c036" and r[f"best_hour_status_{horizon}h"] == "best_hour"]
            self.assertEqual(len(winners), 1)
            self.assertTrue(winners[0][f"best_hour_rank_{horizon}h"])

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
            self.assertEqual(payload["source"], "fishing-intelligence-fci-preliminary-1.1")
            self.assertEqual({row["candidate_id"] for row in payload["rows"]}, TARGETS)
            self.assertEqual(len(payload["rows"]), 24 * 4)
            self.assertTrue(all(row["model_confidence"] == "low" for row in payload["rows"]))
            scored_species = {row["candidate_id"] for row in payload["rows"] if row["overall_fish_condition_index"] is not None}
            self.assertEqual(scored_species, TARGETS - {"c004"})
            black_sea_bream = [row for row in payload["rows"] if row["candidate_id"] == "c004"]
            self.assertTrue(all(row["overall_fish_condition_index"] is None for row in black_sea_bream))
            self.assertTrue(all("catch_probability" not in row for row in payload["rows"]))


if __name__ == "__main__":
    unittest.main()
