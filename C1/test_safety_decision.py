import sys,unittest
from datetime import datetime,timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from safety_decision import decide_region,validate_alert
NOW=datetime(2026,11,9,12,0,tzinfo=timezone.utc)
IDS=("W-C0033-001","W-C0033-002","W-C0033-003","W-C0033-006","W-C0034-001")
def statuses(state="ok",at="2026-11-09T11:30:00+00:00"): return {x:{"status":state,"collected_at":at} for x in IDS}
def alert(kind="heavy_rain",region=("taitung_south",),end="2026-11-09T13:00:00+00:00"):
 return {"schema_version":"1.0.0","alert_id":"A1","source_id":"CWA_OPENDATA","dataset_id":"W-C0033-001","source_url":"https://opendata.cwa.gov.tw/example","region_ids":list(region),"alert_type":kind,"severity":"moderate","status":"active","issued_at":"2026-11-09T10:00:00+00:00","effective_start":"2026-11-09T11:00:00+00:00","effective_end":end,"collected_at":"2026-11-09T11:30:00+00:00","message":"official alert"}
class SafetyTests(unittest.TestCase):
 def test_no_alert_not_clearance(self):
  r=decide_region("taitung_south",[],statuses(),NOW);self.assertEqual(r["state"],"no_active_alerts_reported");self.assertFalse(r["safety_clearance"])
 def test_missing_source_is_unknown(self): self.assertEqual(decide_region("taitung_south",[],statuses("failed"),NOW)["state"],"insufficient_data")
 def test_stale_source_is_unknown(self): self.assertEqual(decide_region("taitung_south",[],statuses(at="2026-11-09T09:00:00+00:00"),NOW)["state"],"insufficient_data")
 def test_typhoon_high_risk(self): self.assertEqual(decide_region("taitung_south",[alert("typhoon")],statuses(),NOW)["state"],"high_risk")
 def test_other_alert_warning(self): self.assertEqual(decide_region("taitung_south",[alert()],statuses(),NOW)["state"],"warning")
 def test_expired_alert_not_active(self): self.assertEqual(decide_region("taitung_south",[alert(end="2026-11-09T11:59:00+00:00")],statuses(),NOW)["state"],"no_active_alerts_reported")
 def test_other_region_not_affected(self): self.assertEqual(decide_region("taitung_south",[alert(region=("yilan_suao",))],statuses(),NOW)["active_alert_count"],0)
 def test_unmapped_area_means_unknown(self):
  a=alert();a["region_ids"]=[];a["unmapped_area"]="unmapped";self.assertEqual(decide_region("taitung_south",[a],statuses(),NOW)["state"],"insufficient_data")
 def test_timezone_required(self):
  a=alert();a["issued_at"]="2026-11-09T10:00:00";self.assertTrue(validate_alert(a))
 def test_never_returns_clearance(self):
  for alerts in ([],[alert()],[alert("typhoon")]): self.assertFalse(decide_region("taitung_south",alerts,statuses(),NOW)["safety_clearance"])
if __name__=="__main__": unittest.main()
