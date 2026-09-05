import unittest
from src.sales_engine import (
    get_dataset_date_range,
    get_units_sold,
    get_sales_revenue,
    get_average_daily_sales,
    get_recent_sales_summary,
    get_weekly_sales_totals,
    get_historical_weekly_baseline,
    get_product_sales_summary
)
from src.data_loader import SCENARIO_PRODUCTS

class TestSalesEngine(unittest.TestCase):
    def test_dataset_date_range(self):
        """Test 1: Verify dataset date range returns start_date, end_date, and total_days."""
        info = get_dataset_date_range()
        self.assertIn("start_date", info)
        self.assertIn("end_date", info)
        self.assertIn("total_days", info)
        self.assertLessEqual(info["start_date"], info["end_date"])
        self.assertEqual(info["total_days"], 120)

    def test_known_product_sales(self):
        """Test 2: Known product sales retrieval for valid product and store."""
        units = get_units_sold(product_id=1, store_id=1)
        revenue = get_sales_revenue(product_id=1, store_id=1)
        self.assertGreaterEqual(units, 0)
        self.assertGreaterEqual(revenue, 0.0)

    def test_average_daily_sales_formula(self):
        """Test 3: Verify 30-day average daily sales formula (units / 30.0)."""
        ads_info = get_average_daily_sales(product_id=1, store_id=1, window_days=30)
        expected_ads = ads_info["units_sold"] / 30.0
        self.assertAlmostEqual(ads_info["average_daily_sales"], expected_ads, places=4)

    def test_zero_sales_product(self):
        """Test 4: Non-moving product in final 30 days must have 0 sales and ADS 0.0."""
        non_moving_id = SCENARIO_PRODUCTS["non_moving"][0]  # ID 34
        ads_info = get_average_daily_sales(product_id=non_moving_id, window_days=30)
        self.assertEqual(ads_info["units_sold"], 0)
        self.assertEqual(ads_info["average_daily_sales"], 0.0)

    def test_store_specific_vs_all_store(self):
        """Test 5: Aggregated all-store units equal sum of store-specific units."""
        all_store_units = get_units_sold(product_id=1, store_id=None)
        store1_units = get_units_sold(product_id=1, store_id=1)
        store2_units = get_units_sold(product_id=1, store_id=2)
        store3_units = get_units_sold(product_id=1, store_id=3)

        self.assertEqual(all_store_units, store1_units + store2_units + store3_units)

    def test_historical_baseline(self):
        """Test 6: Historical baseline returns correct number of weekly windows."""
        baseline = get_historical_weekly_baseline(product_id=1, baseline_weeks=6, exclude_recent_days=7)
        self.assertEqual(len(baseline["weekly_units"]), 6)
        self.assertIn("mean_weekly_units", baseline)
        self.assertIn("median_weekly_units", baseline)

    def test_invalid_product_id(self):
        """Test 7: Invalid product ID raises ValueError."""
        with self.assertRaises(ValueError):
            get_units_sold(product_id=99999)

    def test_invalid_window(self):
        """Test 8: Invalid window_days raises ValueError."""
        with self.assertRaises(ValueError):
            get_average_daily_sales(product_id=1, window_days=0)

if __name__ == "__main__":
    unittest.main()
