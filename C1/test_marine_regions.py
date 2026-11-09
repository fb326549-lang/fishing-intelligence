import csv,json,tempfile,unittest
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).parent/"collector"))
from normalize_cwa_marine_regions import build_snapshot

class MarineRegionTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
  self.mapping=self.root/"stations.csv"
  with self.mapping.open("w",encoding="utf-8",newline="") as f:
   w=csv.DictWriter(f,fieldnames=["station_id","station_name","county","latitude","longitude","region_id","station_status","role"])
   w.writeheader()
   w.writerows([
    {"station_id":"A1","station_name":"花蓮浮標","county":"花蓮縣","latitude":"24.0","longitude":"121.6","region_id":"hualien_north","station_status":"1","role":"marine_buoy"},
    {"station_id":"A2","station_name":"石梯潮位站","county":"花蓮縣","latitude":"23.5","longitude":"121.5","region_id":"fengbin_shitiping","station_status":"1","role":"tide"},
    {"station_id":"A3","station_name":"停送站","county":"宜蘭縣","latitude":"24.5","longitude":"121.8","region_id":"yilan_suao","station_status":"0","role":"marine_buoy"},
   ])
  self.input=self.root/"raw";self.input.mkdir()
  for ds in ("O-B0075-001","O-B0075-002"):
   payload={"Success":"true","Records":{"SeaSurfaceObs":{"Location":[
    {"Station":{"StationID":"A1"},"StationObsTimes":{"StationObsTime":[
     {"DateTime":"2026-11-09T10:00:00+08:00","WeatherElements":{"tideHeight":"1.2","waveHeight":"1.4","windSpeed":"3.2","SeaCurrents":{"Layer":[{"LayerNumber":"1","CurrentSpeed":"0.2"}]}}},
     {"DateTime":"2026-11-09T11:00:00+08:00","WeatherElements":{"tideHeight":"1.3","waveHeight":"1.6","windSpeed":"4.0"}}]}},
    {"Station":{"StationID":"A2"},"StationObsTimes":{"StationObsTime":{"DateTime":"2026-11-09T10:30:00+08:00","WeatherElements":{"tideHeight":"0.9"}}}},
    {"Station":{"StationID":"A3"},"StationObsTimes":{"StationObsTime":{"DateTime":"2026-11-09T11:00:00+08:00","WeatherElements":{"waveHeight":"0.2"}}}},
   ]}}}
   (self.input/f"{ds}.json").write_text(json.dumps(payload,ensure_ascii=False),encoding="utf-8")
 def tearDown(self):self.tmp.cleanup()
 def test_maps_only_explicit_stations_to_regions(self):
  r=build_snapshot(self.input,self.mapping,"2026-11-09T12:00:00+08:00")
  north=r["regions"]["hualien_north"];fengbin=r["regions"]["fengbin_shitiping"]
  self.assertEqual(north["stations_with_recent_observation"],1)
  self.assertEqual(north["stations"][0]["latest_observation"]["weather_elements"]["waveHeight"],"1.6")
  self.assertEqual(fengbin["stations_with_recent_observation"],1)
  self.assertEqual(fengbin["stations"][0]["latest_observation"]["weather_elements"]["tideHeight"],"0.9")
 def test_inactive_station_is_not_included(self):
  r=build_snapshot(self.input,self.mapping,"2026-11-09T12:00:00+08:00")
  ids=[s["station_id"] for s in r["regions"]["yilan_suao"]["stations"]]
  self.assertEqual(ids,[])
 def test_missing_station_observation_is_not_calm_or_safe(self):
  for ds in ("O-B0075-001","O-B0075-002"):
   (self.input/f"{ds}.json").write_text(json.dumps({"Success":"true","Records":{"SeaSurfaceObs":{"Location":[]}}}),encoding="utf-8")
  r=build_snapshot(self.input,self.mapping,"2026-11-09T12:00:00+08:00")
  self.assertEqual(r["regions"]["hualien_north"]["coverage_status"],"no_recent_observation")
  self.assertIn("not interpreted as calm sea",r["interpretation_limits"][3])
 def test_stale_observation_is_not_marked_current(self):\n  r=build_snapshot(self.input,self.mapping,"2026-11-09T15:00:00+08:00")\n  self.assertEqual(r["regions"]["hualien_north"]["coverage_status"],"stale")\n  self.assertEqual(r["regions"]["hualien_north"]["stations"][0]["status"],"stale")\n def test_rejects_failed_provider_payload(self):
  (self.input/"O-B0075-001.json").write_text(json.dumps({"Success":"false","Records":{}}),encoding="utf-8")
  with self.assertRaises(ValueError):build_snapshot(self.input,self.mapping,"2026-11-09T12:00:00+08:00")
 def test_rejects_timezone_naive_as_of(self):
  with self.assertRaises(ValueError):build_snapshot(self.input,self.mapping,"2026-11-09T12:00:00")
if __name__=="__main__":unittest.main()
