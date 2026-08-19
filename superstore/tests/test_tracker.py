import unittest
import tracker


class NormalizeTests(unittest.TestCase):
    def test_normalize(self):
        self.assertEqual(tracker.normalize_status("OK"), "OK")
        self.assertEqual(tracker.normalize_status("Low Stock"), "LOW")
        self.assertEqual(tracker.normalize_status("OUT_OF_STOCK"), "OUT")
        self.assertEqual(tracker.normalize_status("OUT"), "OUT")

    def test_qualifying_transitions(self):
        self.assertIn(("OUT", "LOW"), tracker.QUALIFYING)
        self.assertIn(("OUT", "OK"), tracker.QUALIFYING)
        self.assertIn(("LOW", "OK"), tracker.QUALIFYING)
        self.assertNotIn(("OK", "OUT"), tracker.QUALIFYING)
        self.assertNotIn(("OK", "LOW"), tracker.QUALIFYING)

    def test_find_product(self):
        results = [
            {"code": "x", "stockStatus": "OUT"},
            {"articleNumber": "21595715_EA", "stockStatus": "OK"},
        ]
        found = tracker.find_product(results, "21595715_EA")
        self.assertEqual(found["stockStatus"], "OK")


if __name__ == "__main__":
    unittest.main()
