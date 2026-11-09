import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent/"collector"))
from normalize_cwa_safety_sources import regions_for_area,marine_alerts,source_coverage

def payload(station,warning,field,value):
    elements={"WarningStatus":warning,field:value}
    station_time={"StartTime":"2026-11-09T11:00:00+08:00","EndTime":"2026-11-09T19:00:00+08:00","WeatherElements":elements}
    location={"StationName":station,"StationObsTimes":{"StationObsTime":station_time}}
    return {"cwaopendata":{"Resources":{"Resource":{"Data":{"SeaSurfaceObs":[{"Location":location}]}}}}}

class RegionMappingTests(unittest.TestCase):
 def test_hualien_county_warning_expands_conservatively(self):
  self.assertEqual(set(regions_for_area("花蓮縣")),{"hualien_north","hualien_south","fengbin_shitiping"})
 def test_fengbin_township_maps_only_to_fengbin(self):
  self.assertEqual(regions_for_area("花蓮縣豐濱鄉"),["fengbin_shitiping"])
 def test_taitung_county_maps_two_mainland_regions(self):
  self.assertEqual(set(regions_for_area("臺東縣")),{"chenggong_donghe","taitung_south"})
 def test_unmapped_area_is_not_guessed(self):
  self.assertEqual(regions_for_area("臺東縣綠島鄉"),[])
 def test_long_wave_station_does_not_cover_other_subregions(self):
  p=payload("花蓮浮標","超過長浪警戒","MaximumWaveHeight","2.0")
  alerts,covered=marine_alerts("O-B0070-001",p,"2026-11-09T19:20:00+08:00")
  self.assertEqual(covered,["chenggong_donghe","hualien_north","taitung_south","yilan_suao"])
  self.assertEqual(alerts[0]["region_ids"],["hualien_north"])
  self.assertEqual(alerts[0]["alert_type"],"long_wave")
 def test_east_monitor_coverage_does_not_invent_hualien_south_or_fengbin(self):\n  coverage=source_coverage("O-B0070-001")\n  self.assertFalse(coverage["hualien_south"]);self.assertFalse(coverage["fengbin_shitiping"])\n  self.assertTrue(coverage["hualien_north"])\n def test_large_tide_monitor_uses_o_b0069(self):
  p=payload("成功","超過大潮注意值","MaximumTideHeight","1.4")
  alerts,covered=marine_alerts("O-B0069-001",p,"2026-11-09T19:20:00+08:00")
  self.assertEqual(alerts[0]["alert_type"],"large_tide")
  self.assertEqual(alerts[0]["severity"],"moderate")
if __name__=="__main__":unittest.main()
