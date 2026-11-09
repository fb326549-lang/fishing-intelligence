#!/usr/bin/env python3
"""Fast offline regression tests for CWA marine parsing and regional math."""
import sys
import unittest
import csv
import json
import subprocess
import tempfile
from pathlib import Path

COLLECTOR = Path(__file__).resolve().parents[1] / "collector"
sys.path.insert(0, str(COLLECTOR))

from normalize_cwa_marine import as_layer_list, clean, layer_label  # noqa: E402
from fetch_cwa_tide_forecast import normalize as normalize_tides  # noqa: E402
from build_east_region_conditions import REGIONS, mean_value, num, parse_status, parse_properties  # noqa: E402


class CwaTideForecastTests(unittest.TestCase):
    def test_documented_tide_forecast_shape_and_height_datums(self):
        event_low = {
            "DateTime": "2026-11-16T04:06:00+08:00",
            "Tide": "乾潮",
            "TideHeights": {"AboveTWVD": "-33", "AboveLocalMSL": "-22", "AboveChartDatum": "90"},
        }
        event_high = {
            "DateTime": "2026-11-16T11:23:00+08:00",
            "Tide": "滿潮",
            "TideHeights": {"AboveTWVD": "31", "AboveLocalMSL": "41", "AboveChartDatum": "153"},
        }
        daily = {
            "Date": "2026-11-16",
            "LunarDate": "2026-10-08",
            "TideRange": "小",
            "Time": [event_low, event_high],
        }
        location = {
            "LocationId": "10015050",
            "LocationName": "花蓮縣吉安鄉",
            "Latitude": "23.94240",
            "Longitude": "121.61250",
            "TimePeriods": {"Daily": [daily]},
        }
        payload = {"cwaopendata": {"Resources": {"Resource": {
            "Data": {"TideForecasts": {"Location": [location]}}
        }}}}
        rows = normalize_tides(payload, "2026-11-08T00:00:00+00:00")
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["location_id"], "10015050")
        self.assertEqual(rows[0]["height_above_local_msl_cm"], -22.0)
        self.assertEqual(rows[1]["tide"], "滿潮")
        self.assertEqual(rows[1]["region_id"], "")

    def test_tide_missing_height_stays_null_not_zero(self):
        payload = {"Data": {"TideForecasts": {"Location": [{
            "LocationId": "X1", "LocationName": "測試",
            "TimePeriods": {"Daily": [{"Date": "2026-11-08", "Time": [{
                "DateTime": "2026-11-08T10:00:00+08:00", "Tide": "滿潮",
                "TideHeights": {"AboveTWVD": "None"}
            }]}]}
        }]}}}
        row = normalize_tides(payload, "test")[0]
        self.assertIsNone(row["height_above_twvd_cm"])
        self.assertIsNone(row["height_above_local_msl_cm"])

    def test_tide_failure_or_unrecognized_schema_is_rejected(self):
        with self.assertRaises(ValueError):
            normalize_tides({"success": "false"}, "test")
        with self.assertRaises(ValueError):
            normalize_tides({"Records": {}}, "test")



class CwaRegionalTideBuilderTests(unittest.TestCase):
    def run_builder(self, tide_rows, mapping_rows):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tide_path, map_path, out_path = root / "tides.csv", root / "mapping.csv", root / "regional.csv"
            with tide_path.open("w", encoding="utf-8-sig", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(tide_rows[0]))
                w.writeheader()
                w.writerows(tide_rows)
            with map_path.open("w", encoding="utf-8-sig", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(mapping_rows[0]))
                w.writeheader()
                w.writerows(mapping_rows)
            result = subprocess.run([
                sys.executable, str(COLLECTOR / "build_cwa_regional_tide_forecast.py"),
                "--input", str(tide_path), "--mapping", str(map_path), "--out", str(out_path)
            ], capture_output=True, text=True)
            output_text = out_path.read_text(encoding="utf-8-sig") if out_path.exists() else None
            summary_path = out_path.with_name("regional_tide_summary.json")
            summary_text = summary_path.read_text(encoding="utf-8") if summary_path.exists() else None
            return result, output_text, summary_text

    def test_six_region_mapping_keeps_site_events_separate_and_excludes_islands(self):
        tide_rows = [
            {"location_id": "10002030", "location_name": "宜蘭縣蘇澳鎮", "valid_time": "2026-11-09T06:00:00+08:00", "tide": "滿潮", "height_above_twvd_cm": "40"},
            {"location_id": "10002030", "location_name": "宜蘭縣蘇澳鎮", "valid_time": "2026-11-09T12:00:00+08:00", "tide": "乾潮", "height_above_twvd_cm": "-20"},
            {"location_id": "10014110", "location_name": "臺東縣綠島鄉", "valid_time": "2026-11-09T08:00:00+08:00", "tide": "滿潮", "height_above_twvd_cm": "50"},
            {"location_id": "999999", "location_name": "未對照地點", "valid_time": "2026-11-09T09:00:00+08:00", "tide": "滿潮", "height_above_twvd_cm": "10"},
        ]
        base = {"latitude": "24.5925", "longitude": "121.8669", "mapping_basis": "official_CWA_location_id_and_coordinate", "notes": "test"}
        mapping_rows = [
            dict(base, location_id="10002030", location_name="宜蘭縣蘇澳鎮", region_id="yilan_suao", mapping_status="mapped"),
            dict(base, location_id="10014110", location_name="臺東縣綠島鄉", region_id="", mapping_status="excluded_offshore_context"),
        ]
        result, output_text, summary_text = self.run_builder(tide_rows, mapping_rows)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIsNotNone(output_text)
        output = list(csv.DictReader(output_text.splitlines()))
        self.assertEqual(len(output), 2)
        self.assertEqual({r["region_id"] for r in output}, {"yilan_suao"})
        self.assertEqual({r["height_above_twvd_cm"] for r in output}, {"40", "-20"})
        summary = json.loads(summary_text)
        self.assertEqual(summary["mapped_event_rows"], 2)
        self.assertEqual(summary["mapped_unique_locations"], 1)
        self.assertEqual(summary["unmapped_or_excluded_location_count"], 2)

    def test_duplicate_mapping_id_is_rejected(self):
        tide_rows = [{"location_id": "X", "location_name": "測試", "valid_time": "t"}]
        base = {"latitude": "1", "longitude": "2", "mapping_basis": "test", "notes": "test"}
        mapping_rows = [
            dict(base, location_id="X", location_name="測試", region_id="yilan_suao", mapping_status="mapped"),
            dict(base, location_id="X", location_name="測試", region_id="yilan_suao", mapping_status="mapped"),
        ]
        result, _, _ = self.run_builder(tide_rows, mapping_rows)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Duplicate location_id", result.stderr)

    def test_feed_location_name_mismatch_is_rejected(self):
        tide_rows = [{"location_id": "X", "location_name": "不同名稱", "valid_time": "t"}]
        base = {"latitude": "1", "longitude": "2", "mapping_basis": "test", "notes": "test"}
        mapping_rows = [dict(base, location_id="X", location_name="原始名稱", region_id="yilan_suao", mapping_status="mapped")]
        result, _, _ = self.run_builder(tide_rows, mapping_rows)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Location name mismatch", result.stderr)



class CwaTideObservationForecastComparisonTests(unittest.TestCase):
    def test_observed_extrema_match_forecast_events_after_datum_unit_conversion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            obs_path, forecast_path, pair_path, out_path = [root / n for n in (
                "observations.csv", "forecasts.csv", "pairing.csv", "comparison.csv"
            )]
            observations = [
                {"station_id": "S1", "valid_time": f"2026-11-09T{hour:02d}:00:00+08:00", "TideHeight": str(height)}
                for hour, height in [(0, 0.2), (1, 0.5), (2, 0.3), (3, -0.2), (4, -0.5), (5, -0.1)]
            ]
            forecasts = [
                {"location_id": "L1", "valid_time": "2026-11-09T01:30:00+08:00", "tide": "滿潮", "height_above_twvd_cm": "45", "fetched_at_utc": "2026-11-08T00:00:00+00:00"},
                {"location_id": "L1", "valid_time": "2026-11-09T03:30:00+08:00", "tide": "乾潮", "height_above_twvd_cm": "-45", "fetched_at_utc": "2026-11-08T00:00:00+00:00"},
                {"location_id": "L1", "valid_time": "2026-11-09T01:30:00+08:00", "tide": "滿潮", "height_above_twvd_cm": "45", "fetched_at_utc": "2026-11-09T02:00:00+00:00"},
                {"location_id": "L1", "valid_time": "2026-11-09T01:30:00+08:00", "tide": "滿潮", "height_above_twvd_cm": "45"},
            ]
            pairings = [{
                "station_id": "S1", "station_name": "測試潮位站",
                "location_id": "L1", "location_name": "測試預報地點",
                "region_id": "yilan_suao", "distance_m": "100", "matching_status": "matched", "comparison_datum": "TWVD2001"
            }]
            for path, rows in [(obs_path, observations), (forecast_path, forecasts), (pair_path, pairings)]:
                with path.open("w", encoding="utf-8-sig", newline="") as f:
                    w = csv.DictWriter(f, fieldnames=list(rows[0]))
                    w.writeheader()
                    w.writerows(rows)
            result = subprocess.run([
                sys.executable, str(COLLECTOR / "compare_cwa_tide_observed_forecast.py"),
                "--observations", str(obs_path), "--forecasts", str(forecast_path),
                "--pairing", str(pair_path), "--out", str(out_path),
                "--max-delta-minutes", "120"
            ], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            with out_path.open(encoding="utf-8-sig", newline="") as f:
                matches = list(csv.DictReader(f))
            self.assertEqual(len(matches), 2)
            self.assertTrue(all(row["forecast_issue_time_utc"] for row in matches))
            self.assertTrue(all(float(row["lead_time_hours"]) > 0 for row in matches))
            self.assertEqual(matches[0]["forecast_above_twvd_m"], "0.45")
            summary = json.loads(out_path.with_name("tide_forecast_observation_comparison_summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["stations"][0]["forecast_events_missing_issue_time"], 1)
            self.assertEqual(summary["stations"][0]["forecast_events_issued_at_or_after_target"], 1)
            self.assertEqual(summary["stations"][0]["forecast_events_eligible_for_verification"], 2)
            self.assertAlmostEqual(float(matches[0]["height_error_observed_minus_forecast_m"]), 0.05, places=3)
            summary = json.loads(out_path.with_name("tide_forecast_observation_comparison_summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["matched_event_count"], 2)
            self.assertEqual(summary["stations"][0]["observation_sampling_interval_median_minutes"], 60.0)

    def test_pairing_over_500m_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            obs, fc, pair, out = [root / n for n in ("o.csv", "f.csv", "p.csv", "out.csv")]
            for path, row in [
                (obs, {"station_id": "S1", "valid_time": "2026-11-09T00:00:00+08:00", "TideHeight": "0"}),
                (fc, {"location_id": "L1", "valid_time": "2026-11-09T00:00:00+08:00", "tide": "滿潮", "height_above_twvd_cm": "0"}),
                (pair, {"station_id": "S1", "station_name": "S", "location_id": "L1", "location_name": "L", "region_id": "yilan_suao", "distance_m": "501", "matching_status": "matched", "comparison_datum": "TWVD2001"}),
            ]:
                with path.open("w", encoding="utf-8-sig", newline="") as f:
                    w = csv.DictWriter(f, fieldnames=list(row))
                    w.writeheader()
                    w.writerow(row)
            result = subprocess.run([
                sys.executable, str(COLLECTOR / "compare_cwa_tide_observed_forecast.py"),
                "--observations", str(obs), "--forecasts", str(fc),
                "--pairing", str(pair), "--out", str(out)
            ], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("distance <= 500 m", result.stderr)




class CwaTideHistoryAnalysisTests(unittest.TestCase):
    def test_scores_forecast_vintage_by_positive_lead_time_and_twvd_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            history, out = root / "history", root / "analysis"
            history.mkdir()
            observations = [
                {"station_id": "C4U02", "valid_time": "2026-11-09T00:00:00+08:00", "TideHeight": "0.50", "collected_at": "2026-11-09T03:00:00+00:00"},
                {"station_id": "C4U02", "valid_time": "2026-11-09T01:00:00+08:00", "TideHeight": "1.00", "collected_at": "2026-11-09T03:00:00+00:00"},
                {"station_id": "C4U02", "valid_time": "2026-11-09T02:00:00+08:00", "TideHeight": "0.40", "collected_at": "2026-11-09T03:00:00+00:00"},
            ]
            forecasts = [
                {"snapshot_id": "early", "location_id": "10002040", "valid_time": "2026-11-09T01:00:00+08:00", "tide": "滿潮", "height_above_twvd_cm": "80", "forecast_fetched_at_utc": "2026-11-08T00:00:00+00:00"},
                {"snapshot_id": "late", "location_id": "10002040", "valid_time": "2026-11-09T01:00:00+08:00", "tide": "滿潮", "height_above_twvd_cm": "80", "forecast_fetched_at_utc": "2026-11-09T02:00:00+00:00"},
            ]
            (history / "observed_tides.jsonl").write_text(
                "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in observations), encoding="utf-8")
            (history / "forecast_vintages.jsonl").write_text(
                "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in forecasts), encoding="utf-8")
            result = subprocess.run([
                sys.executable, str(COLLECTOR / "analyze_cwa_tide_forecast_history.py"),
                "--history-dir", str(history), "--out-dir", str(out)
            ], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            matches = list(csv.DictReader((out / "event_matches.csv").open(encoding="utf-8-sig", newline="")))
            self.assertEqual(len(matches), 1)
            self.assertEqual(matches[0]["snapshot_id"], "early")
            self.assertEqual(matches[0]["lead_time_bucket"], "12-24h")
            self.assertEqual(matches[0]["absolute_height_error_m"], "0.2")
            summary = json.loads((out / "analysis_summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["matched_event_count"], 1)
            self.assertEqual(summary["interpretation"], "Insufficient evidence")

    def test_analysis_rejects_empty_history_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            history, out = root / "history", root / "analysis"
            history.mkdir()
            (history / "observed_tides.jsonl").write_text("", encoding="utf-8")
            (history / "forecast_vintages.jsonl").write_text("", encoding="utf-8")
            result = subprocess.run([
                sys.executable, str(COLLECTOR / "analyze_cwa_tide_forecast_history.py"),
                "--history-dir", str(history), "--out-dir", str(out)
            ], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("must both be non-empty", result.stderr)


class CwaTideHistoryArchiveTests(unittest.TestCase):
    def test_archive_is_idempotent_for_observations_and_keeps_forecast_vintages(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            obs, fc, pair, history = [root / n for n in ("obs.csv", "fc.csv", "pair.csv", "history")]
            observations = [{
                "station_id": "S1", "station_name": "測站", "latitude": "23.0",
                "longitude": "121.0", "valid_time": "2026-11-09T01:00:00+08:00",
                "TideHeight": "0.71"
            }]
            forecasts = [{
                "location_id": "L1", "location_name": "預報地點", "region_id": "taitung_south",
                "valid_time": "2026-11-09T01:00:00+08:00", "tide": "滿潮",
                "height_above_twvd_cm": "70", "height_above_local_msl_cm": "80",
                "height_above_chart_datum_cm": "150", "fetched_at_utc": "2026-11-08T00:00:00+00:00"
            }]
            pairing = [{
                "station_id": "S1", "location_id": "L1", "matching_status": "matched"
            }]
            for path, rows in [(obs, observations), (fc, forecasts), (pair, pairing)]:
                with path.open("w", encoding="utf-8-sig", newline="") as f:
                    w = csv.DictWriter(f, fieldnames=list(rows[0]))
                    w.writeheader()
                    w.writerows(rows)

            def run(snapshot):
                return subprocess.run([
                    sys.executable, str(COLLECTOR / "archive_cwa_tide_history.py"),
                    "--observations", str(obs), "--forecasts", str(fc),
                    "--pairing", str(pair), "--history-dir", str(history),
                    "--snapshot-id", snapshot, "--collected-at", "2026-11-09T02:00:00+00:00"
                ], capture_output=True, text=True)

            first = run("run-1")
            self.assertEqual(first.returncode, 0, first.stderr)
            second = run("run-1")
            self.assertEqual(second.returncode, 0, second.stderr)
            third = run("run-2")
            self.assertEqual(third.returncode, 0, third.stderr)

            obs_lines = (history / "observed_tides.jsonl").read_text(encoding="utf-8").splitlines()
            forecast_lines = (history / "forecast_vintages.jsonl").read_text(encoding="utf-8").splitlines()
            run_lines = (history / "collection_runs.jsonl").read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(obs_lines), 1)
            self.assertEqual(len(forecast_lines), 2)
            self.assertEqual(len(run_lines), 3)
            archived = [json.loads(line) for line in forecast_lines]
            self.assertEqual({row["snapshot_id"] for row in archived}, {"run-1", "run-2"})
            self.assertEqual({row["height_above_twvd_cm"] for row in archived}, {"70"})


    def test_archive_regional_series_deduplicates_identical_rows_and_keeps_revisions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            obs, fc, pair, regional48, regional30, history = [
                root / n for n in ("obs.csv", "fc.csv", "pair.csv", "r48.csv", "r30.csv", "history")
            ]
            observations = [{
                "station_id": "S1", "station_name": "測站", "latitude": "23.0",
                "longitude": "121.0", "valid_time": "2026-11-09T01:00:00+08:00",
                "TideHeight": "0.71"
            }]
            forecasts = [{
                "location_id": "L1", "location_name": "預報地點", "region_id": "taitung_south",
                "valid_time": "2026-11-09T01:00:00+08:00", "tide": "滿潮",
                "height_above_twvd_cm": "70", "height_above_local_msl_cm": "80",
                "height_above_chart_datum_cm": "150", "fetched_at_utc": "2026-11-08T00:00:00+00:00"
            }]
            pairing = [{"station_id": "S1", "location_id": "L1", "matching_status": "matched"}]
            regional = [{
                "dataset_id": "O-B0075-002", "region_id": "taitung_south",
                "region_name": "台東南段", "valid_time": "2026-11-09T01:00:00+08:00",
                "wave_height_m": "1.2", "wave_height_m_sample_count": "2",
                "data_kind": "observed_historical_window"
            }]
            for path, rows in [
                (obs, observations), (fc, forecasts), (pair, pairing),
                (regional48, regional), (regional30, regional)
            ]:
                with path.open("w", encoding="utf-8-sig", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=list(rows[0]))
                    writer.writeheader()
                    writer.writerows(rows)

            def run(snapshot):
                return subprocess.run([
                    sys.executable, str(COLLECTOR / "archive_cwa_tide_history.py"),
                    "--observations", str(obs), "--forecasts", str(fc),
                    "--pairing", str(pair), "--regional-48h", str(regional48),
                    "--regional-30d", str(regional30), "--history-dir", str(history),
                    "--snapshot-id", snapshot, "--collected-at", "2026-11-09T02:00:00+00:00"
                ], capture_output=True, text=True)

            first = run("run-1")
            self.assertEqual(first.returncode, 0, first.stderr)
            second = run("run-2")
            self.assertEqual(second.returncode, 0, second.stderr)
            regional[0]["wave_height_m"] = "1.3"
            for path in (regional48, regional30):
                with path.open("w", encoding="utf-8-sig", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=list(regional[0]))
                    writer.writeheader()
                    writer.writerows(regional)
            third = run("run-3")
            self.assertEqual(third.returncode, 0, third.stderr)

            for filename in ("regional_marine_observations_48h.jsonl", "regional_marine_observations_30d.jsonl"):
                records = [json.loads(line) for line in (history / filename).read_text(encoding="utf-8").splitlines()]
                self.assertEqual(len(records), 2)
                self.assertEqual({row["wave_height_m"] for row in records}, {"1.2", "1.3"})
            summary = json.loads((history / "history_summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["regional_48h_history_records"], 2)
            self.assertEqual(summary["regional_30d_history_records"], 2)

    def test_archive_rejects_invalid_history_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            obs, fc, pair, history = [root / n for n in ("obs.csv", "fc.csv", "pair.csv", "history")]
            history.mkdir()
            (history / "observed_tides.jsonl").write_text("{bad json\n", encoding="utf-8")
            for path, row in [
                (obs, {"station_id": "S1", "valid_time": "t", "TideHeight": "1"}),
                (fc, {"location_id": "L1", "region_id": "taitung_south", "valid_time": "t", "tide": "滿潮"}),
                (pair, {"station_id": "S1", "location_id": "L1", "matching_status": "matched"}),
            ]:
                with path.open("w", encoding="utf-8-sig", newline="") as f:
                    w = csv.DictWriter(f, fieldnames=list(row))
                    w.writeheader()
                    w.writerow(row)
            result = subprocess.run([
                sys.executable, str(COLLECTOR / "archive_cwa_tide_history.py"),
                "--observations", str(obs), "--forecasts", str(fc),
                "--pairing", str(pair), "--history-dir", str(history),
                "--snapshot-id", "run-1"
            ], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("invalid JSON", result.stderr)


class MarineNormalizationTests(unittest.TestCase):
    def test_missing_sentinels_are_not_zero(self):
        for value in (None, "", "None", "null", "NaN", "N/A"):
            self.assertIsNone(clean(value))
        self.assertEqual(num("0"), 0.0)
        self.assertIsNone(num("None"))

    def test_current_layer_object_and_list_shapes(self):
        layer = {"LayerNumber": "1", "CurrentDirection": "270", "CurrentSpeed": "0.5"}
        self.assertEqual(as_layer_list({"Layer": layer}), [layer])
        self.assertEqual(as_layer_list({"Layer": [layer]}), [layer])
        self.assertEqual(as_layer_list([{"Layer": layer}, {"Layer": [layer]}]), [layer, layer])
        self.assertEqual(layer_label(layer, 1), "1")

    def test_empty_or_unexpected_current_shape_is_safe(self):
        self.assertEqual(as_layer_list(None), [])
        self.assertEqual(as_layer_list({"Layer": None}), [])
        self.assertEqual(as_layer_list("unexpected"), [])

    def test_direction_uses_circular_mean(self):
        # 359° and 1° should average to north, not 180°.
        result = mean_value("wave_direction_deg", [359.0, 1.0])
        self.assertTrue(result < 0.01 or result > 359.99)

    def test_live_station_status_and_element_metadata_parsing(self):
        self.assertEqual(parse_status("1"), 1)
        self.assertEqual(parse_status("0"), 0)
        self.assertIsNone(parse_status("unknown"))
        props = parse_properties('{"WaveHeight":"1","SeaTemperature":"0"}')
        self.assertEqual(parse_status(props.get("WaveHeight")), 1)
        self.assertEqual(parse_status(props.get("SeaTemperature")), 0)
        self.assertEqual(parse_properties("invalid-json"), {})

    def test_all_six_planning_regions_are_declared(self):
        self.assertEqual(len(REGIONS), 6)
        self.assertIn("hualien_south", REGIONS)
        self.assertIn("taitung_south", REGIONS)




class CwaRegionalMarineObservationTests(unittest.TestCase):
    def test_historical_mode_keeps_records_from_stations_now_inactive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            observations_path = root / "observations.csv"
            mapping_path = root / "mapping.csv"
            stations_path = root / "stations.csv"
            out_dir = root / "regional_30d"

            with observations_path.open("w", encoding="utf-8-sig", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=[
                    "dataset_id", "station_id", "valid_time", "WaveHeight",
                    "WavePeriod", "WaveDirection", "SeaTemperature"
                ])
                writer.writeheader()
                writer.writerow({
                    "dataset_id": "O-B0075-002", "station_id": "S1",
                    "valid_time": "2026-11-01T10:00:00+08:00",
                    "WaveHeight": "1.2", "WavePeriod": "8",
                    "WaveDirection": "359", "SeaTemperature": "25"
                })

            with mapping_path.open("w", encoding="utf-8-sig", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=["station_id", "region_id"])
                writer.writeheader()
                writer.writerow({"station_id": "S1", "region_id": "yilan_suao"})

            with stations_path.open("w", encoding="utf-8-sig", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=["station_id", "station_status", "observed_properties"])
                writer.writeheader()
                writer.writerow({
                    "station_id": "S1", "station_status": "0",
                    "observed_properties": json.dumps({"WaveHeight": 0, "WavePeriod": 0})
                })

            result = subprocess.run([
                sys.executable, str(COLLECTOR / "build_east_region_conditions.py"),
                "--input", str(observations_path), "--mapping", str(mapping_path),
                "--stations", str(stations_path), "--out", str(out_dir), "--historical"
            ], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

            output_path = out_dir / "east_region_conditions.csv"
            with output_path.open(encoding="utf-8-sig", newline="") as f:
                rows = list(csv.DictReader(f))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["data_kind"], "observed_historical_window")
            self.assertEqual(rows[0]["wave_height_m"], "1.2")
            self.assertEqual(rows[0]["wave_period_s"], "8.0")

            summary = json.loads((out_dir / "east_region_summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["source_datasets"], ["O-B0075-002"])
            self.assertEqual(summary["temporal_scope"], "rolling_30_day")
            self.assertEqual(summary["regions"][0]["stations_with_observations"], 1)

if __name__ == "__main__":
    unittest.main(verbosity=2)
