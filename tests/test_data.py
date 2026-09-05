import unittest
import sqlite3
import csv
from pathlib import Path
from datetime import datetime, timedelta
from src.database import get_db_path, get_connection, table_exists, get_table_counts
from src.data_loader import SCENARIO_PRODUCTS, DATA_DIR

class TestPhase2DataLayer(unittest.TestCase):
    def setUp(self):
        self.db_path = get_db_path()
        self.assertTrue(self.db_path.exists(), "Database file data/stocksage.db does not exist.")
        self.conn = get_connection()
        self.conn.execute("DELETE FROM recommendations;")
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def test_database_tables_exist(self):
        """Test that all required tables exist in SQLite database."""
        required_tables = ["stores", "products", "sales", "inventory", "recommendations"]
        for table in required_tables:
            self.assertTrue(table_exists(table), f"Table {table} does not exist.")

    def test_table_row_counts(self):
        """Test exact store, product, inventory, and recommendations table counts."""
        counts = get_table_counts()
        self.assertEqual(counts["stores"], 3, "Stores count must be exactly 3.")
        self.assertEqual(counts["products"], 60, "Products count must be exactly 60.")
        self.assertEqual(counts["inventory"], 180, "Inventory count must be exactly 180 (3 stores x 60 products).")
        self.assertEqual(counts["recommendations"], 0, "Recommendations table must be empty in Phase 2.")
        self.assertGreater(counts["sales"], 5000, "Sales table should contain realistic thousands of rows.")

    def test_sqlite_foreign_keys(self):
        """Test that SQLite foreign key integrity check returns zero violations."""
        cursor = self.conn.cursor()
        cursor.execute("PRAGMA foreign_key_check;")
        violations = cursor.fetchall()
        self.assertEqual(len(violations), 0, f"Foreign key check failed with violations: {violations}")

    def test_non_negative_values(self):
        """Test that prices, quantities, amounts, stock levels, and reorder levels are non-negative."""
        cursor = self.conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM products WHERE selling_price <= 0;")
        self.assertEqual(cursor.fetchone()[0], 0, "Selling prices must be strictly positive.")

        cursor.execute("SELECT COUNT(*) FROM sales WHERE quantity_sold < 0 OR sales_amount < 0;")
        self.assertEqual(cursor.fetchone()[0], 0, "Sales quantities and amounts must be non-negative.")

        cursor.execute("SELECT COUNT(*) FROM inventory WHERE current_stock < 0 OR reorder_level < 0;")
        self.assertEqual(cursor.fetchone()[0], 0, "Current stock and reorder level must be non-negative.")

    def test_sales_amount_math_consistency(self):
        """Test that sales_amount = quantity_sold * selling_price for all sales lines."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT s.sales_amount, s.quantity_sold, p.selling_price
            FROM sales s
            JOIN products p ON s.product_id = p.product_id;
        """)
        rows = cursor.fetchall()
        for row in rows:
            expected = round(row["quantity_sold"] * row["selling_price"], 2)
            self.assertAlmostEqual(row["sales_amount"], expected, delta=0.01,
                                   msg=f"Sales amount mismatch: {row['sales_amount']} vs {expected}")

    def test_non_moving_scenario(self):
        """Test that non-moving products have zero sales in the final 30 calendar days."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT MAX(date) FROM sales;")
        max_date_str = cursor.fetchone()[0]
        max_date = datetime.strptime(max_date_str, "%Y-%m-%d")
        cutoff_30d = (max_date - timedelta(days=30)).strftime("%Y-%m-%d")

        for p_id in SCENARIO_PRODUCTS["non_moving"]:
            cursor.execute("""
                SELECT COALESCE(SUM(quantity_sold), 0)
                FROM sales
                WHERE product_id = ? AND date > ?;
            """, (p_id, cutoff_30d))
            sales_sum = cursor.fetchone()[0]
            self.assertEqual(sales_sum, 0, f"Non-moving product ID {p_id} has {sales_sum} sales in final 30 days.")

    def test_sales_spike_scenario_sanity(self):
        """Sanity check that sales spike products have higher recent 7-day sales than baseline."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT MAX(date) FROM sales;")
        max_date_str = cursor.fetchone()[0]
        max_date = datetime.strptime(max_date_str, "%Y-%m-%d")
        cutoff_7d = (max_date - timedelta(days=7)).strftime("%Y-%m-%d")

        for p_id in SCENARIO_PRODUCTS["sales_spike"]:
            cursor.execute("SELECT COALESCE(SUM(quantity_sold), 0) FROM sales WHERE product_id = ? AND date <= ?;", (p_id, cutoff_7d))
            hist_sales = cursor.fetchone()[0]
            hist_7d_avg = (hist_sales / 113.0) * 7.0

            cursor.execute("SELECT COALESCE(SUM(quantity_sold), 0) FROM sales WHERE product_id = ? AND date > ?;", (p_id, cutoff_7d))
            rec_7d_sales = cursor.fetchone()[0]

            self.assertGreater(rec_7d_sales, hist_7d_avg,
                               f"Spike product ID {p_id} recent 7d sales ({rec_7d_sales}) <= baseline ({hist_7d_avg}).")

    def test_sales_drop_scenario_sanity(self):
        """Sanity check that sales drop products have lower recent 7-day sales than baseline."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT MAX(date) FROM sales;")
        max_date_str = cursor.fetchone()[0]
        max_date = datetime.strptime(max_date_str, "%Y-%m-%d")
        cutoff_7d = (max_date - timedelta(days=7)).strftime("%Y-%m-%d")

        for p_id in SCENARIO_PRODUCTS["sales_drop"]:
            cursor.execute("SELECT COALESCE(SUM(quantity_sold), 0) FROM sales WHERE product_id = ? AND date <= ?;", (p_id, cutoff_7d))
            hist_sales = cursor.fetchone()[0]
            hist_7d_avg = (hist_sales / 113.0) * 7.0

            cursor.execute("SELECT COALESCE(SUM(quantity_sold), 0) FROM sales WHERE product_id = ? AND date > ?;", (p_id, cutoff_7d))
            rec_7d_sales = cursor.fetchone()[0]

            self.assertLess(rec_7d_sales, hist_7d_avg,
                            f"Drop product ID {p_id} recent 7d sales ({rec_7d_sales}) >= baseline ({hist_7d_avg}).")

    def test_csv_files_exist_and_match(self):
        """Test that CSV files exist in data/ directory and line counts match SQLite tables."""
        for filename in ["stores.csv", "products.csv", "inventory.csv"]:
            csv_path = DATA_DIR / filename
            self.assertTrue(csv_path.exists(), f"CSV file {filename} does not exist.")
            with open(csv_path, "r", encoding="utf-8") as f:
                reader = csv.reader(f)
                header = next(reader)
                rows = list(reader)

            table_name = filename.replace(".csv", "")
            counts = get_table_counts()
            self.assertEqual(len(rows), counts[table_name],
                             f"CSV row count for {filename} ({len(rows)}) does not match DB table count ({counts[table_name]}).")

if __name__ == "__main__":
    unittest.main()
