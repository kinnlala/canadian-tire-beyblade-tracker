import unittest
import tracker


class ExtractQuantityTests(unittest.TestCase):
    def test_store_id_as_key(self):
        payload = {
            "0187": {"Quantity": 4, "Price": 17.99},
            "0460": {"Quantity": 1},
        }
        self.assertEqual(
            tracker.extract_quantities(payload, {"0187", "0460"}),
            {"0187": 4, "0460": 1},
        )

    def test_store_fields_in_list(self):
        payload = {
            "stores": [
                {"storeNumber": "0187", "Quantity": "7"},
                {"storeId": 460, "quantity": 2},
            ]
        }
        self.assertEqual(
            tracker.extract_quantities(payload, {"0187", "0460"}),
            {"0187": 7, "0460": 2},
        )

    def test_missing_store_is_not_zero(self):
        payload = [{"storeNumber": "0187", "Quantity": 0}]
        result = tracker.extract_quantities(payload, {"0187", "0460"})
        self.assertEqual(result, {"0187": 0})
        self.assertNotIn("0460", result)


if __name__ == "__main__":
    unittest.main()
