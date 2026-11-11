import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "species"))
from audit_iocean_effort_data import audit_rows


FIELDS = [
    "ID", "Type_Name", "Fishing_Time", "People_Count", "WGS84X", "WGS84Y",
    "Species_Name", "Name_Code", "Fishing_Count", "Fishing_Length",
]


class IOceanEffortAuditTests(unittest.TestCase):
    def test_ignores_translated_label_row_and_does_not_infer_zero_catch(self):
        metadata = {
            "ID": "垂釣類型", "Type_Name": "垂釣類型", "Fishing_Time": "垂釣時間",
            "People_Count": "同行人數", "WGS84X": "經度", "WGS84Y": "緯度",
            "Species_Name": "垂釣魚種", "Name_Code": "物種學名代碼",
            "Fishing_Count": "尾數", "Fishing_Length": "體長(cm)",
        }
        report = dict(metadata, ID="report-1", Type_Name="岸釣", Fishing_Time="2026-06-01",
                      People_Count="2", WGS84X="121.5", WGS84Y="23.5",
                      Species_Name="臭肚", Name_Code="123", Fishing_Count="", Fishing_Length="")
        result = audit_rows(FIELDS, [metadata, report])
        self.assertEqual(result["record_rows"], 1)
        self.assertEqual(result["fishing_time_value_kinds"], {"date_only": 1})
        self.assertEqual(result["fishing_count_value_kinds"], {"missing": 1})
        self.assertFalse(result["has_explicit_zero_catch_rows"])
        self.assertFalse(result["has_fields_for_person_hour_cpue_screen"])
        self.assertEqual(result["unique_report_ids"], 1)

    def test_clock_time_duration_and_explicit_zero_are_reported_separately(self):
        fields = FIELDS + ["Fishing_Duration_Hours"]
        rows = [
            dict.fromkeys(fields, ""),
            dict.fromkeys(fields, ""),
        ]
        rows[0].update(ID="r1", Fishing_Time="2026-06-01T05:00:00+08:00", People_Count="2",
                       Fishing_Count="0", Fishing_Duration_Hours="3")
        rows[1].update(ID="r2", Fishing_Time="2026-06-01T06:00:00+08:00", People_Count="1",
                       Fishing_Count="1", Fishing_Duration_Hours="2")
        result = audit_rows(fields, rows)
        self.assertEqual(result["fishing_time_value_kinds"]["datetime_with_clock"], 2)
        self.assertEqual(result["fishing_count_value_kinds"]["zero"], 1)
        self.assertEqual(result["candidate_effort_duration_fields"], ["Fishing_Duration_Hours"])
        self.assertTrue(result["has_datetime_with_clock"])
        self.assertTrue(result["has_fields_for_hourly_effort_screen"])
        self.assertTrue(result["has_fields_for_person_hour_cpue_screen"])

    def test_partial_duration_data_does_not_qualify_for_effort_validation(self):
        fields = FIELDS + ["Fishing_Duration_Hours"]
        row = {field: "" for field in fields}
        row.update(ID="r1", Fishing_Time="2026-06-01T05:00:00+08:00", People_Count="2",
                   Fishing_Count="0", Fishing_Duration_Hours="")
        result = audit_rows(fields, [row])
        self.assertTrue(result["has_explicit_zero_catch_rows"])
        self.assertFalse(result["has_reported_zero_catch_with_complete_effort"])
        self.assertFalse(result["has_fields_for_person_hour_cpue_screen"])
        self.assertFalse(result["has_fields_for_hourly_effort_screen"])

    def test_repeat_report_ids_are_reported_not_discarded(self):
        fields = FIELDS
        row = {field: "" for field in fields}
        row.update(ID="same-trip", Fishing_Time="2026-06-01", People_Count="1", Fishing_Count="1")
        other_species_row = dict(row, Species_Name="other")
        result = audit_rows(fields, [row, other_species_row])
        self.assertEqual(result["record_rows"], 2)
        self.assertEqual(result["unique_report_ids"], 1)
        self.assertEqual(result["report_ids_repeated_across_species_rows"], 1)


if __name__ == "__main__":
    unittest.main()
