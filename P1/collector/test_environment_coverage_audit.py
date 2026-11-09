import unittest

from audit_environment_coverage import audit_catalog


class EnvironmentCoverageAuditTests(unittest.TestCase):
    def test_reports_missing_region_observations_without_filling_them(self):
        catalog = {
            "partitions": [
                {
                    "records_by_region_type": {
                        "north|forecast": 24,
                        "south|forecast": 24,
                        "north|observation": 8,
                    },
                    "unique_valid_hours_by_region_type": {
                        "north|forecast": 24,
                        "south|forecast": 24,
                        "north|observation": 8,
                    },
                    "collection_vintages_by_region_type": {
                        "north|forecast": 1,
                        "south|forecast": 1,
                        "north|observation": 1,
                    },
                }
            ]
        }
        result = audit_catalog(catalog, ("north", "south"))
        self.assertEqual(result["regions_with_forecast_and_observation"], 1)
        self.assertEqual(result["regions_missing_observations"], ["south"])
        self.assertEqual(result["regions"][1]["observation"]["record_count"], 0)
        self.assertEqual(result["regions"][1]["status"], "forecast_only_observation_missing")

    def test_sums_counts_across_partitions(self):
        partition = {
            "records_by_region_type": {"north|observation": 3},
            "unique_valid_hours_by_region_type": {"north|observation": 2},
            "collection_vintages_by_region_type": {"north|observation": 2},
        }
        result = audit_catalog({"partitions": [partition, partition]}, ("north",))
        self.assertEqual(result["regions"][0]["observation"]["record_count"], 6)
        self.assertEqual(result["regions"][0]["observation"]["unique_valid_hours"], 4)
        self.assertEqual(result["regions"][0]["observation"]["collection_vintages"], 4)

    def test_rejects_negative_or_non_integer_counts(self):
        bad = {
            "partitions": [{
                "records_by_region_type": {"north|forecast": -1},
            }]
        }
        with self.assertRaises(ValueError):
            audit_catalog(bad, ("north",))

    def test_does_not_claim_presence_means_quality_or_sample_sufficiency(self):
        result = audit_catalog({"partitions": []}, ("north",))
        self.assertIn("does not imply sufficient sample size", result["interpretation"])


if __name__ == "__main__":
    unittest.main()
