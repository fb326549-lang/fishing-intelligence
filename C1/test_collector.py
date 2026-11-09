import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent / "collector"))
from fetch_cwa_safety_sources import validate_json_payload,validate_cap_payload
class CollectorValidationTests(unittest.TestCase):
 def test_accepts_cwa_json_records(self):
  self.assertIn("Records",validate_json_payload({"Success":"true","Records":{}}, "W-C0033-001"))
 def test_rejects_failed_application_response(self):
  with self.assertRaises(ValueError): validate_json_payload({"Success":"false","Records":{}}, "W-C0033-001")
 def test_rejects_missing_records(self):
  with self.assertRaises(ValueError): validate_json_payload({"Success":"true","data":[]}, "O-B0069-001")
 def test_accepts_cap_alert_xml(self):
  self.assertEqual(validate_cap_payload(b'<alert xmlns="urn:oasis:names:tc:emergency:cap:1.2"><identifier>x</identifier></alert>').tag.split("}")[-1],"alert")
 def test_rejects_non_cap_xml(self):
  with self.assertRaises(ValueError): validate_cap_payload(b'<html/>')
if __name__=="__main__": unittest.main()
