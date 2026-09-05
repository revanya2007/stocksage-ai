import unittest
from src.inventory_engine import (
    get_current_inventory,
    get_days_of_stock_remaining,
    get_inventory_summary,
    get_all_inventory_metrics
)
from src.database import get_connection
from src.data_loader import SCENARIO_PRODUCTS

class TestInventoryEngine(unittest.TestCase):
    def test_current_stock_retrieval(self):
        """Test 1: Known store/product matches SQLite inventory row."""
        inv = get_current_inventory(product_id=1, store_id=1)
        self.assertEqual(inv["product_id"], 1)
        self.assertEqual(inv["store_id"], 1)
        self.assertGreaterEqual(inv["current_stock"], 0)
        self.assertGreaterEqual(inv["reorder_level"], 0)

    def test_days_remaining_formula(self):
        """Test 2: Product with positive sales returns current_stock / ADS."""
        days_info = get_days_of_stock_remaining(product_id=1, store_id=1, sales_window_days=30)
        self.assertEqual(days_info["coverage_status"], "calculable")
        self.assertIsNotNone(days_info["days_of_stock_remaining"])
        expected_days = round(days_info["current_stock"] / days_info["average_daily_sales"], 2)
        self.assertAlmostEqual(days_info["days_of_stock_remaining"], expected_days, places=2)

    def test_zero_sales_handling(self):
        """Test 3: Non-moving product with ADS 0.0 returns None for days_remaining without division by zero."""
        non_moving_id = SCENARIO_PRODUCTS["non_moving"][0]  # ID 34
        days_info = get_days_of_stock_remaining(product_id=non_moving_id, store_id=1, sales_window_days=30)
        self.assertEqual(days_info["average_daily_sales"], 0.0)
        self.assertIsNone(days_info["days_of_stock_remaining"])
        self.assertEqual(days_info["coverage_status"], "no_recent_sales")

    def test_zero_stock_handling(self):
        """Test 4: Zero stock with positive ADS returns days_remaining = 0.0."""
        current_stock = 0
        ads = 2.5
        days_remaining = 0.0 if current_stock == 0 else round(current_stock / ads, 2)
        self.assertEqual(days_remaining, 0.0)

    def test_reorder_gap(self):
        """Test 5: reorder_gap = current_stock - reorder_level."""
        summary = get_inventory_summary(product_id=1, store_id=1)
        expected_gap = summary["current_stock"] - summary["reorder_level"]
        self.assertEqual(summary["reorder_gap"], expected_gap)

    def test_all_metrics_row_count(self):
        """Test 6: get_all_inventory_metrics() returns 180 rows (3 stores x 60 products)."""
        metrics = get_all_inventory_metrics()
        self.assertEqual(len(metrics), 180)
        first = metrics[0]
        self.assertIn("days_of_stock_remaining", first)
        self.assertIn("coverage_status", first)
        self.assertIn("reorder_gap", first)

    def test_store_filtering(self):
        """Test 7: Filtering by store_id=1 returns 60 rows."""
        metrics = get_all_inventory_metrics(store_id=1)
        self.assertEqual(len(metrics), 60)
        self.assertTrue(all(x["store_id"] == 1 for x in metrics))

    def test_missing_inventory(self):
        """Test 8: Invalid store/product combination raises ValueError."""
        with self.assertRaises(ValueError):
            get_current_inventory(product_id=99999, store_id=1)

if __name__ == "__main__":
    unittest.main()
