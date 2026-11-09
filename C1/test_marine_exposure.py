import sys, unittest
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "collector"))
from analyze_marine_exposure import build_assessment, assess_region, REGIONS

NOW=datetime.fromisoformat("2026-11-09T12:00:00+08:00")

def region(wave=1.2,wind=4.0,at="2026-11-09T11:00:00+08:00",coverage="observations_available"):
 return {"region_name":"測試區","observed_48h":{
  "latest_observation_time":at,"coverage_status":coverage,
  "mapped_station_count":2,"stations_with_observations":2,
  "latest_values":{"wave_height_m":wave,"wind_speed_ms":wind,"wave_period_s":6.0,"tide_height_m":0.3,"current_speed_ms":0.2,"wave_direction_deg":45,"wind_direction_deg":90},
  "variable_coverage":{"wave_height_m":{"coverage_ratio":1.0},"wind_speed_ms":{"coverage_ratio":0.5}}
 },"observed_30d":{"latest_observation_time":"2026-11-08T23:00:00+08:00","data_kind":"observed","latest_values":{"wave_height_m":1.0}}}

def snapshot(overrides=None):
 rows={r:region() for r in REGIONS}
 if overrides: rows.update(overrides)
 return {"schema_version":1,"source":"CWA","generated_at":"2026-11-09T11:30:00+08:00","regions":rows}

class MarineExposureTests(unittest.TestCase):
 def test_six_regions_and_normal_assessment(self):
  result=build_assessment(snapshot(),NOW)
  self.assertEqual(len(result["regions"]),6)
  self.assertEqual(result["regions"]["yilan_suao"]["state"],"assessed")
  self.assertEqual(result["regions"]["yilan_suao"]["exposure_level"],"moderate")
  self.assertFalse(result["regions"]["yilan_suao"]["safety_clearance"])
 def test_highest_of_wave_and_wind_is_reported(self):
  r=build_assessment(snapshot({"yilan_suao":region(2.8,3.0)}),NOW)["regions"]["yilan_suao"]
  self.assertEqual(r["exposure_level"],"very_high")
  self.assertEqual({x["factor"] for x in r["factors"]},{"wave_height_m","wind_speed_ms"})
 def test_stale_observation_is_insufficient_not_calm(self):
  r=build_assessment(snapshot({"yilan_suao":region(0.2,1.0,"2026-11-09T07:00:00+08:00")}),NOW)["regions"]["yilan_suao"]
  self.assertEqual(r["state"],"insufficient_data")
  self.assertEqual(r["exposure_level"],"unknown")
 def test_missing_wave_and_wind_is_insufficient(self):
  r=build_assessment(snapshot({"yilan_suao":region(None,None)}),NOW)["regions"]["yilan_suao"]
  self.assertEqual(r["state"],"insufficient_data")
 def test_uncovered_region_is_never_filled_from_neighbor(self):
  r=build_assessment(snapshot({"hualien_south":region(0.1,1.0,coverage="no_cwa_station_coverage")}),NOW)["regions"]["hualien_south"]
  self.assertEqual(r["state"],"insufficient_data")
  self.assertEqual(r["exposure_level"],"unknown")
 def test_negative_and_non_numeric_values_are_not_classified(self):
  r=build_assessment(snapshot({"yilan_suao":region(-1,"bad")}),NOW)["regions"]["yilan_suao"]
  self.assertEqual(r["state"],"insufficient_data")
 def test_direction_is_preserved_but_not_interpreted_against_shoreline(self):
  r=build_assessment(snapshot(),NOW)["regions"]["yilan_suao"]
  self.assertEqual(r["other_observations"]["wave_direction_deg"],45)
  self.assertTrue(any("岸線方位" in x for x in r["limitations"]))
 def test_30day_window_is_not_misrepresented_as_climatology(self):
  r=build_assessment(snapshot(),NOW)["regions"]["yilan_suao"]
  self.assertIn("不是30天平均",r["historical_window"]["use_limit"])
 def test_rejects_missing_region(self):
  s=snapshot();s["regions"].pop("hualien_south")
  with self.assertRaises(ValueError):build_assessment(s,NOW)
 def test_rejects_bad_schema_and_naive_time(self):
  s=snapshot();s["schema_version"]=2
  with self.assertRaises(ValueError):build_assessment(s,NOW)
  with self.assertRaises(SystemExit):
   parse=__import__("analyze_marine_exposure").parse_time
   if parse("2026-11-09T12:00:00") is None: raise SystemExit("naive time rejected")

if __name__=="__main__":unittest.main(verbosity=2)
