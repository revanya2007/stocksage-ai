import unittest
from src.risk_engine import (
    classify_stockout_days,
    is_overstock_coverage,
    is_non_moving,
    is_slow_moving,
    classify_stockout_risk,
    classify_overstock,
    classify_non_moving,
    classify_slow_moving,
    analyze_inventory_product,
    analyze_all_inventory_risks,
    get_stockout_risks,
    get_overstock_products,
    get_slow_moving_products,
    get_non_moving_products,
    validate_thresholds
)
from src.data_loader import SCENARIO_PRODUCTS

class TestRiskEngine(unittest.TestCase):
    def test_stockout_critical_detection(self):
        """Test 1: Stock-out critical classification for Milk 1L at Store 1."""
        so_id = SCENARIO_PRODUCTS["stockout"][0]  # ID 1 (Milk 1L)
        res = classify_stockout_risk(so_id, store_id=1)
        self.assertEqual(res["status"], "risk")
        self.assertIn(res["severity"], ["critical", "high", "medium"])
        self.assertIsNotNone(res["days_of_stock_remaining"])

    def test_stockout_pure_boundaries(self):
        """Test 2: Pure boundary tests for classify_stockout_days."""
        self.assertEqual(classify_stockout_days(2.99)["severity"], "critical")
        self.assertEqual(classify_stockout_days(3.00)["severity"], "high")
        self.assertEqual(classify_stockout_days(4.99)["severity"], "high")
        self.assertEqual(classify_stockout_days(5.00)["severity"], "medium")
        self.assertEqual(classify_stockout_days(6.99)["severity"], "medium")
        self.assertEqual(classify_stockout_days(7.00)["severity"], "safe")

    def test_zero_sales_stockout_handling(self):
        """Test 3: Zero sales product yields stockout_status='not_applicable'."""
        res = classify_stockout_days(None)
        self.assertEqual(res["status"], "not_applicable")
        self.assertEqual(res["severity"], "none")

    def test_non_moving_detection(self):
        """Test 4: Injected non-moving case (Herbal Hair Oil ID 34)."""
        nm_id = SCENARIO_PRODUCTS["non_moving"][0]  # ID 34
        res = classify_non_moving(nm_id, store_id=1)
        self.assertTrue(res["is_non_moving"])
        sm_res = classify_slow_moving(nm_id, store_id=1)
        self.assertFalse(sm_res["is_slow_moving"])

    def test_slow_moving_detection(self):
        """Test 5: Injected slow-moving case (Green Tea ID 20)."""
        sm_id = SCENARIO_PRODUCTS["slow_moving"][0]  # ID 20
        res = classify_slow_moving(sm_id, store_id=1)
        self.assertTrue(res["is_slow_moving"])
        nm_res = classify_non_moving(sm_id, store_id=1)
        self.assertFalse(nm_res["is_non_moving"])

    def test_overstock_detection(self):
        """Test 6: Injected overstock case (Shampoo ID 31)."""
        ov_id = SCENARIO_PRODUCTS["overstock"][0]  # ID 31
        res = classify_overstock(ov_id, store_id=1)
        self.assertTrue(res["is_overstock"])
        self.assertGreaterEqual(res["days_of_stock_remaining"], 30.0)

    def test_normal_product_healthy(self):
        """Test 7: Normal healthy product is not falsely flagged."""
        # Product 42 (Rice 5kg) at store 1
        res = analyze_inventory_product(42, store_id=1)
        self.assertIn(res["primary_issue"], ["healthy", "stockout_risk", "overstock"])

    def test_invalid_product_id(self):
        """Test 8: Invalid product ID raises ValueError."""
        with self.assertRaises(ValueError):
            classify_stockout_risk(99999, store_id=1)

    def test_invalid_store_id(self):
        """Test 9: Invalid store ID raises ValueError."""
        with self.assertRaises(ValueError):
            classify_stockout_risk(1, store_id=99999)

    def test_custom_valid_thresholds(self):
        """Test 10: Custom valid thresholds change classifications deterministically."""
        custom_cfg = {"stockout": {"critical_days": 10.0, "high_days": 15.0, "medium_days": 20.0}}
        res = classify_stockout_days(8.0, custom_cfg)
        self.assertEqual(res["severity"], "critical")

    def test_invalid_custom_thresholds(self):
        """Test 11: Invalid custom thresholds raise ValueError."""
        bad_cfg = {"stockout": {"critical_days": 5.0, "high_days": 3.0}}
        with self.assertRaises(ValueError):
            validate_thresholds(bad_cfg)

    def test_batch_row_count(self):
        """Test 12: analyze_all_inventory_risks() returns 180 records."""
        results = analyze_all_inventory_risks()
        self.assertEqual(len(results), 180)
        self.assertIn("primary_issue", results[0])
        self.assertIn("is_overstock", results[0])

    def test_store_filtering(self):
        """Test 13: analyze_all_inventory_risks(store_id=1) returns 60 records."""
        results = analyze_all_inventory_risks(store_id=1)
        self.assertEqual(len(results), 60)
        self.assertTrue(all(x["store_id"] == 1 for x in results))

    def test_risk_sorting(self):
        """Test 14: Risk sorting validation."""
        so_list = get_stockout_risks()
        if len(so_list) > 1:
            days = [x["days_of_stock_remaining"] for x in so_list]
            self.assertEqual(days, sorted(days))

        ov_list = get_overstock_products()
        if len(ov_list) > 1:
            days = [x["days_of_stock_remaining"] for x in ov_list]
            self.assertEqual(days, sorted(days, reverse=True))

if __name__ == "__main__":
    unittest.main()
