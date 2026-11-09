import csv,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent/"field_data"))
from validate_fishing_logs import validate

SESSION_HEADER="session_id,started_at_local,ended_at_local,region_id,location_label,habitat,method,effort_minutes,catch_count,angler_ref,weather_notes,sea_state_notes,photo_reference,notes\n"
CATCH_HEADER="catch_id,session_id,caught_at_local,candidate_id,common_name_reported,scientific_name_confirmed,species_identification_confidence,count,length_cm,weight_g,released,bait_or_lure,photo_reference,notes\n"
SESSION="S1,2026-11-08T16:30:00+08:00,2026-11-08T19:00:00+08:00,taitung_south,台東南段,礁岩,磯釣,120,0,,,,,\n"

class FishingLogTests(unittest.TestCase):
    def run_files(self,session_rows=SESSION,catch_rows=""):
        with tempfile.TemporaryDirectory() as d:
            s=Path(d)/"sessions.csv";c=Path(d)/"catches.csv"
            s.write_text(SESSION_HEADER+session_rows,encoding="utf-8")
            c.write_text(CATCH_HEADER+catch_rows,encoding="utf-8")
            return validate(s,c)
    def test_zero_catch_session_is_valid_and_preserved(self):
        self.assertEqual(self.run_files(),[])
    def test_catch_events_must_reconcile_to_session_total(self):
        session=SESSION.replace(",120,0,",",120,2,")
        catch="C1,S1,2026-11-08T17:00:00+08:00,c003,臭肚,,medium,1,,,,,\n"
        self.assertTrue(any("catch_count=2" in e for e in self.run_files(session,catch)))
    def test_valid_catch_events_reconcile(self):
        session=SESSION.replace(",120,0,",",120,2,")
        catch="C1,S1,2026-11-08T17:00:00+08:00,c003,臭肚,,medium,2,,,,,\n"
        self.assertEqual(self.run_files(session,catch),[])
    def test_catch_outside_session_rejected(self):
        catch="C1,S1,2026-11-08T20:00:00+08:00,c003,臭肚,,medium,1,,,,,\n"
        self.assertTrue(any("outside session interval" in e for e in self.run_files(SESSION.replace(",120,0,",",120,1,"),catch)))
    def test_timezone_required(self):
        row=SESSION.replace("2026-11-08T16:30:00+08:00","2026-11-08T16:30:00")
        self.assertTrue(any("must include timezone" in e for e in self.run_files(row)))
    def test_unknown_region_rejected(self):
        self.assertTrue(any("unknown region_id" in e for e in self.run_files(SESSION.replace("taitung_south","unknown"))))
    def test_duplicate_session_id_rejected(self):
        self.assertTrue(any("duplicate session_id" in e for e in self.run_files(SESSION+SESSION)))
if __name__=="__main__":unittest.main()
