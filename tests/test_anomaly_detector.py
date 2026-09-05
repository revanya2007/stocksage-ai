import unittest
from src.anomaly_detector import (
    classify_percentage_change,
    validate_anomaly_thresholds,
    detect_product_anomaly,
    detect_all_sales_anomalies,
    get_sales_spikes,
    get_sales_drops,
    get_normal_sales_products
)
from src.sales_engine import get_recent_sales_summary
from src.data_loader import SCENARIO_PRODUCTS

class TestAnomalyDetector(unittest.TestCase):
    def test_known_spike_product(self):
        """Test 1: Known injected spike product (Mango Juice 1L ID 15)."""
        spike_id = SCENARIO_PRODUCTS["sales_spike"][0]  # ID 15
        res = detect_product_anomaly(spike_id, store_id=1)
        self.assertEqual(res["classification"]["anomaly_type"], "spike")
        self.assertGreaterEqual(res["change"]["percentage_change"], 50.0)

    def test_known_drop_product(self):
        """Test 2: Known injected drop product (Orange Juice 1L ID 16)."""
        drop_id = SCENARIO_PRODUCTS["sales_drop"][0]  # ID 16
        res = detect_product_anomaly(drop_id, store_id=1)
        self.assertEqual(res["classification"]["anomaly_type"], "drop")
        self.assertLessEqual(res["change"]["percentage_change"], -30.0)

    def test_spike_boundary_pure(self):
        """Test 3: Spike boundary pure logic test (+49.99% -> normal, +50.00% -> spike)."""
        # baseline = 100
        res_normal = classify_percentage_change(149, 100.0)
        self.assertEqual(res_normal["anomaly_type"], "normal")

        res_spike = classify_percentage_change(150, 100.0)
        self.assertEqual(res_spike["anomaly_type"], "spike")
        self.assertEqual(res_spike["percentage_change"], 50.0)

    def test_drop_boundary_pure(self):
        """Test 4: Drop boundary pure logic test (-29.99% -> normal, -30.00% -> drop)."""
        # baseline = 100
        res_normal = classify_percentage_change(71, 100.0)
        self.assertEqual(res_normal["anomaly_type"], "normal")

        res_drop = classify_percentage_change(70, 100.0)
        self.assertEqual(res_drop["anomaly_type"], "drop")
        self.assertEqual(res_drop["percentage_change"], -30.0)

    def test_zero_baseline_zero_recent(self):
        """Test 5: baseline=0, recent=0 yields no_activity."""
        res = classify_percentage_change(0, 0.0)
        self.assertEqual(res["anomaly_type"], "no_activity")
        self.assertIsNone(res["percentage_change"])

    def test_zero_baseline_positive_recent(self):
        """Test 6: baseline=0, recent>0 yields new_activity without division by zero."""
        res = classify_percentage_change(10, 0.0)
        self.assertEqual(res["anomaly_type"], "new_activity")
        self.assertIsNone(res["percentage_change"])
        self.assertEqual(res["absolute_units_change"], 10.0)

    def test_low_baseline_protection(self):
        """Test 7: baseline < min_baseline_units yields low_baseline."""
        res = classify_percentage_change(5, 2.0, thresholds={"min_baseline_units": 5.0})
        self.assertEqual(res["anomaly_type"], "low_baseline")
        self.assertEqual(res["percentage_change"], 150.0)

    def test_normal_product(self):
        """Test 8: Normal non-injected product returns normal classification."""
        # Product 42 (Rice 5kg) at store 1
        res = detect_product_anomaly(42, store_id=1)
        self.assertIn(res["classification"]["anomaly_type"], ["normal", "spike", "drop"])

    def test_historical_windows(self):
        """Test 9: Historical baseline weeks=6 returns 6 weekly baseline values."""
        res = detect_product_anomaly(1, store_id=1, baseline_weeks=6)
        self.assertEqual(len(res["historical_baseline"]["weekly_units"]), 6)

    def test_recent_window_span(self):
        """Test 10: Recent window spans 7 calendar days."""
        res = detect_product_anomaly(1, store_id=1, recent_window_days=7)
        self.assertEqual(res["recent_period"]["units_sold"], get_recent_sales_summary(1, store_id=1, days=7)["units_sold"])

    def test_store_filtering(self):
        """Test 11: Store filtering restricts results correctly."""
        results = detect_all_sales_anomalies(store_id=1)
        self.assertEqual(len(results), 60)
        self.assertTrue(all(x["store_id"] == 1 for x in results))

    def test_invalid_product_id(self):
        """Test 12: Invalid product ID raises ValueError."""
        with self.assertRaises(ValueError):
            detect_product_anomaly(99999, store_id=1)

    def test_invalid_store_id(self):
        """Test 13: Invalid store ID raises ValueError."""
        with self.assertRaises(ValueError):
            detect_product_anomaly(1, store_id=99999)

    def test_invalid_thresholds(self):
        """Test 14: Invalid thresholds raise ValueError."""
        with self.assertRaises(ValueError):
            validate_anomaly_thresholds({"spike_percent": -10.0})
        with self.assertRaises(ValueError):
            validate_anomaly_thresholds({"drop_percent": 10.0})

    def test_batch_row_count(self):
        """Test 15: detect_all_sales_anomalies() returns 180 records matching DB inventory count."""
        results = detect_all_sales_anomalies()
        self.assertEqual(len(results), 180)

    def test_sorting(self):
        """Test 16: Sorting validation for get_sales_spikes and get_sales_drops."""
        spikes = get_sales_spikes()
        if len(spikes) > 1:
            pcts = [x["change"]["percentage_change"] for x in spikes]
            self.assertEqual(pcts, sorted(pcts, reverse=True))

        drops = get_sales_drops()
        if len(drops) > 1:
            pcts = [x["change"]["percentage_change"] for x in drops]
            self.assertEqual(pcts, sorted(pcts))

if __name__ == "__main__":
    unittest.main()
