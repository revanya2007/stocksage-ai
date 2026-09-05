"""
Tests for StockSage AI Business Impact Engine (Phase 6A)
"""

import pytest
import sqlite3
from src.impact_engine import (
    estimate_stockout_revenue_at_risk,
    estimate_overstock_value,
    estimate_non_moving_value,
    estimate_slow_moving_value,
    estimate_spike_value,
    estimate_drop_value,
    estimate_issue_impact,
    _get_product_price
)

# Use real dataset for Integration tests
DB_PATH = "data/stocksage.db"

def test_stockout_revenue_at_risk_formula():
    """1. Test stock-out revenue at risk formula on a known stockout product."""
    # Store 1, Product 1 (known stockout risk in database)
    res = estimate_stockout_revenue_at_risk(store_id=1, product_id=1, db_path=DB_PATH)
    
    assert res["issue_type"] == "stockout_risk"
    assert res["impact_label"] == "Estimated Revenue at Risk"
    assert res["impact_value"] is not None
    assert res["impact_value"] >= 0.0
    
    # Verify mathematical formula manually
    ads = res["inputs"]["average_daily_sales"]
    stock = res["inputs"]["current_stock"]
    price = res["inputs"]["selling_price"]
    horizon = res["inputs"]["risk_horizon_days"]
    expected_shortage = max((ads * horizon) - stock, 0.0)
    expected_val = round(expected_shortage * price, 2)
    
    assert res["impact_value"] == pytest.approx(expected_val, abs=0.01)

def test_stock_covers_horizon_zero_risk():
    """2. Test stock covers horizon -> risk = 0."""
    # Product with high stock (e.g. overstocked product 3 at Store 1)
    res = estimate_stockout_revenue_at_risk(store_id=1, product_id=3, db_path=DB_PATH)
    assert res["inputs"]["potential_shortage_units"] == 0.0
    assert res["impact_value"] == 0.0

def test_ads_zero_zero_risk(tmp_path):
    """3. Test ADS = 0 -> risk = 0."""
    db_file = tmp_path / "temp_zero_ads.db"
    conn = sqlite3.connect(db_file)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE stores (store_id INTEGER PRIMARY KEY);")
    cursor.execute("CREATE TABLE products (product_id INTEGER PRIMARY KEY, selling_price REAL);")
    cursor.execute("CREATE TABLE sales (sale_line_id INTEGER PRIMARY KEY, date TEXT, store_id INTEGER, product_id INTEGER, quantity_sold INTEGER, sales_amount REAL);")
    cursor.execute("CREATE TABLE inventory (store_id INTEGER, product_id INTEGER, current_stock INTEGER, reorder_level INTEGER, last_updated TEXT);")
    
    cursor.execute("INSERT INTO stores VALUES (1);")
    cursor.execute("INSERT INTO products VALUES (10, 100.0);")
    cursor.execute("INSERT INTO inventory VALUES (1, 10, 0, 5, '2026-03-31');")
    cursor.execute("INSERT INTO sales VALUES (1, '2026-01-01', 1, 10, 0, 0.0);")
    conn.commit()
    conn.close()

    res = estimate_stockout_revenue_at_risk(store_id=1, product_id=10, db_path=str(db_file), as_of_date="2026-03-31")
    assert res["inputs"]["average_daily_sales"] == 0.0
    assert res["inputs"]["potential_shortage_units"] == 0.0
    assert res["impact_value"] == 0.0

def test_overstock_excess_value_formula():
    """4. Test overstock excess value formula."""
    # Store 1, Product 3 (known overstock)
    res = estimate_overstock_value(store_id=1, product_id=3, db_path=DB_PATH)
    
    assert res["issue_type"] == "overstock"
    assert res["impact_label"] == "Estimated Retail Value of Excess Stock"
    assert res["impact_value"] > 0.0
    
    ads = res["inputs"]["average_daily_sales"]
    stock = res["inputs"]["current_stock"]
    price = res["inputs"]["selling_price"]
    target_days = res["inputs"]["target_coverage_days"]
    
    expected_excess = max(stock - (ads * target_days), 0.0)
    expected_val = round(expected_excess * price, 2)
    
    assert res["impact_value"] == pytest.approx(expected_val, abs=0.01)

def test_non_moving_retail_value():
    """5. Test non-moving retail value."""
    # Store 1, Product 4 (known non-moving product)
    res = estimate_non_moving_value(store_id=1, product_id=4, db_path=DB_PATH)
    
    assert res["issue_type"] == "non_moving"
    assert res["impact_label"] == "Retail Value of Non-Moving Stock"
    
    stock = res["inputs"]["current_stock"]
    price = res["inputs"]["selling_price"]
    expected_val = round(stock * price, 2)
    
    assert res["impact_value"] == pytest.approx(expected_val, abs=0.01)

def test_slow_moving_value():
    """6. Test slow-moving value."""
    # Store 1, Product 5 (known slow-moving product)
    res = estimate_slow_moving_value(store_id=1, product_id=5, db_path=DB_PATH)
    
    assert res["issue_type"] == "slow_moving"
    assert res["impact_label"] == "Retail Value of Slow-Moving Stock"
    assert res["current_inventory_retail_value"] is not None
    assert res["impact_value"] >= 0.0

def test_spike_incremental_value():
    """7. Test spike incremental sales value."""
    # Store 1, Product 6 (known sales spike)
    res = estimate_spike_value(store_id=1, product_id=6, db_path=DB_PATH)
    
    assert res["issue_type"] == "sales_spike"
    assert res["impact_label"] == "Estimated Incremental Sales Value"
    assert res["impact_value"] is not None
    assert res["impact_value"] >= 0.0
    
    recent = res["inputs"]["recent_weekly_units"]
    baseline = res["inputs"]["baseline_weekly_units"]
    price = res["inputs"]["selling_price"]
    
    expected_inc = max(recent - baseline, 0.0)
    expected_val = round(expected_inc * price, 2)
    assert res["impact_value"] == pytest.approx(expected_val, abs=0.01)

def test_drop_baseline_gap_value():
    """8. Test drop baseline gap value."""
    # Store 1, Product 7 (known sales drop)
    res = estimate_drop_value(store_id=1, product_id=7, db_path=DB_PATH)
    
    assert res["issue_type"] == "sales_drop"
    assert res["impact_label"] == "Estimated Sales Value Gap vs Baseline"
    assert res["impact_value"] is not None
    assert res["impact_value"] >= 0.0
    
    recent = res["inputs"]["recent_weekly_units"]
    baseline = res["inputs"]["baseline_weekly_units"]
    price = res["inputs"]["selling_price"]
    
    expected_gap = max(baseline - recent, 0.0)
    expected_val = round(expected_gap * price, 2)
    assert res["impact_value"] == pytest.approx(expected_val, abs=0.01)

def test_monetary_values_never_negative():
    """9. Test monetary values are never negative across all issue types."""
    for p_id in range(1, 10):
        stockout = estimate_stockout_revenue_at_risk(store_id=1, product_id=p_id, db_path=DB_PATH)
        overstock = estimate_overstock_value(store_id=1, product_id=p_id, db_path=DB_PATH)
        non_moving = estimate_non_moving_value(store_id=1, product_id=p_id, db_path=DB_PATH)
        
        if stockout["impact_value"] is not None:
            assert stockout["impact_value"] >= 0.0
        if overstock["impact_value"] is not None:
            assert overstock["impact_value"] >= 0.0
        if non_moving["impact_value"] is not None:
            assert non_moving["impact_value"] >= 0.0

def test_missing_price_handled_truthfully(tmp_path):
    """10. Test missing price handled truthfully (impact_value = None)."""
    db_file = tmp_path / "temp_stocksage.db"
    conn = sqlite3.connect(db_file)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE stores (store_id INTEGER PRIMARY KEY);")
    cursor.execute("CREATE TABLE products (product_id INTEGER PRIMARY KEY, selling_price REAL);")
    cursor.execute("CREATE TABLE sales (sale_line_id INTEGER PRIMARY KEY, date TEXT, store_id INTEGER, product_id INTEGER, quantity_sold INTEGER, sales_amount REAL);")
    cursor.execute("CREATE TABLE inventory (store_id INTEGER, product_id INTEGER, current_stock INTEGER, reorder_level INTEGER, last_updated TEXT);")
    
    cursor.execute("INSERT INTO stores VALUES (1);")
    cursor.execute("INSERT INTO products VALUES (999, NULL);")
    cursor.execute("INSERT INTO inventory VALUES (1, 999, 50, 10, '2026-03-31');")
    cursor.execute("INSERT INTO sales VALUES (1, '2026-03-30', 1, 999, 2, 0.0);")
    conn.commit()
    conn.close()
    
    assert _get_product_price(999, db_path=str(db_file)) is None
    
    res = estimate_stockout_revenue_at_risk(store_id=1, product_id=999, db_path=str(db_file))
    assert res["impact_value"] is None
    assert "unavailable" in res["assumptions"][-1].lower()
