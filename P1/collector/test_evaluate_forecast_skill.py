import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "collector"))
from evaluate_forecast_skill import build_verification

class ForecastSkillTests(unittest.TestCase):
    def write_rows(self, root, rows):
        folder=root/"hourly_environment/2026/11"
        folder.mkdir(parents=True,exist_ok=True)
        path=folder/"2026-11-09.jsonl"
        path.write_text("".join(json.dumps(x)+"\n" for x in rows),encoding="utf-8")

    def row(self, kind, valid, collected, region="taitung_south", env=None):
        return {
            "region_id":region,"valid_time":valid,"collected_at":collected,
            "data_type":kind,"environment":env or {},
        }

    def test_exact_hour_pairs_all_forecast_vintages_and_circular_direction(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            valid="2026-11-09T12:00:00+08:00"
            observed={
                "wave_height_m":2.0,
                "wind_direction_10m_deg":2.0,
            }
            rows=[self.row("observation",valid,"2026-11-09T13:10:00+08:00",env=observed)]
            rows.append(self.row("forecast",valid,"2026-11-09T06:00:00+08:00",env={
                "wave_height_m":3.0,"wind_direction_10m_deg":358.0,
            }))
            rows.append(self.row("forecast",valid,"2026-11-09T10:00:00+08:00",env={
                "wave_height_m":2.5,"wind_direction_10m_deg":4.0,
            }))
            # No exact valid-hour observation: must not be nearest-time matched.
            rows.append(self.row("forecast","2026-11-09T13:00:00+08:00","2026-11-09T10:00:00+08:00",env={"wave_height_m":9.0}))
            # A forecast collected after its valid time must be excluded.
            rows.append(self.row("forecast",valid,"2026-11-09T13:30:00+08:00",env={"wave_height_m":99.0}))
            self.write_rows(root,rows)
            result=build_verification(root,minimum_pairs=2)
            self.assertEqual(result["forecast_observation_hour_pairs"],1)
            self.assertEqual(result["forecast_vintages_with_any_comparable_variable"],2)
            wave=result["variables"]["wave_height_m"]
            self.assertEqual(wave["sample_count"],2)
            self.assertEqual(wave["status"],"exploratory_metrics")
            self.assertAlmostEqual(wave["mae"],0.75)
            direction=result["variables"]["wind_direction_deg"]
            self.assertAlmostEqual(direction["mae"],3.0)

    def test_no_time_aligned_observations_is_reported_as_waiting_not_zero_skill(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            rows=[
                self.row("observation","2026-11-09T11:00:00+08:00","2026-11-09T12:00:00+08:00",env={"wave_height_m":1.0}),
                self.row("forecast","2026-11-09T13:00:00+08:00","2026-11-09T12:30:00+08:00",env={"wave_height_m":2.0}),
            ]
            self.write_rows(root,rows)
            result=build_verification(root)
            self.assertEqual(result["status"],"awaiting_time_aligned_observations")
            self.assertEqual(result["forecast_observation_hour_pairs"],0)
            self.assertEqual(result["variables"],{})

    def test_latest_observation_revision_is_used_and_small_samples_are_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            valid="2026-11-09T12:00:00+08:00"
            rows=[
                self.row("observation",valid,"2026-11-09T12:30:00+08:00",env={"wave_height_m":1.0}),
                self.row("observation",valid,"2026-11-09T13:30:00+08:00",env={"wave_height_m":2.0}),
                self.row("forecast",valid,"2026-11-09T08:00:00+08:00",env={"wave_height_m":2.5}),
            ]
            self.write_rows(root,rows)
            result=build_verification(root,minimum_pairs=5)
            wave=result["variables"]["wave_height_m"]
            self.assertEqual(wave["sample_count"],1)
            self.assertEqual(wave["status"],"insufficient_sample")
            self.assertAlmostEqual(wave["mae"],0.5)

if __name__ == "__main__":
    unittest.main()
