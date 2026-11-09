import tempfile, unittest
from pathlib import Path
from validate_p2_data import validate_environment, validate_species_csv

def sample():
    return {"schema_version":"1.0.0","region_id":"taitung_south","valid_time":"2026-11-09T12:00:00+08:00","collected_at":"2026-11-09T11:05:00+08:00","data_type":"forecast","source_records":[{"source_id":"open-meteo","dataset":"marine-api","url":"https://open-meteo.com/"}],"environment":{"wave_height_m":1.2,"wave_period_s":7.0,"wave_direction_deg":90,"sea_surface_temperature_c":None,"sea_level_height_msl_m":0.2,"ocean_current_velocity_ms":0.3,"ocean_current_direction_deg":180,"wind_speed_10m_ms":4,"wind_direction_10m_deg":90,"tide_height_m":0.4,"tide_phase":"rising","tide_turning":False,"tidal_current_velocity_ms":None,"tidal_current_direction_deg":None,"precipitation_mm_h":0,"thunderstorm_risk":"unknown","sunrise":None,"sunset":None},"completeness":{"available_fields":9,"expected_fields":18,"ratio":0.5},"quality":{"status":"partial","confidence":"medium","flags":["sst_missing"]}}

class P2ValidationTests(unittest.TestCase):
    def test_valid_environment_record(self): self.assertEqual(validate_environment(sample()),[])
    def test_missing_provenance_rejected(self):
        x=sample(); x["source_records"]=[]
        self.assertTrue(any("source_records" in e for e in validate_environment(x)))
    def test_tide_height_not_current_speed(self):
        x=sample(); x["environment"]["tidal_current_velocity_ms"]=x["environment"]["tide_height_m"]
        self.assertEqual(validate_environment(x),[])
    def test_invalid_direction_rejected(self):
        x=sample(); x["environment"]["wave_direction_deg"]=360
        self.assertTrue(any("wave_direction_deg" in e for e in validate_environment(x)))
    def test_inconsistent_completeness_rejected(self):
        x=sample(); x["completeness"]["ratio"]=0.9
        self.assertTrue(any("completeness" in e for e in validate_environment(x)))
    def test_species_template_header(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"p.csv"; p.write_text("response_record_id,candidate_id,parameter_code,parameter_value,unit,life_stage,geographic_scope,habitat_scope,evidence_id,source_url,confidence,model_use_status,notes\n",encoding="utf-8")
            self.assertEqual(validate_species_csv(p),[])
if __name__=="__main__": unittest.main()
