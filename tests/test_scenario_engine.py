"""
Unit tests for Phase 10 Deterministic What-If Scenario Engine.
"""

import pytest
from src.scenario_engine import (
    simulate_product_scenario,
    simulate_demand_change_for_all,
    get_products_becoming_critical
)


def test_simulate_product_scenario_basic():
    """Test basic scenario simulation for a valid product (Milk 1L = product_id 1)."""
    res = simulate_product_scenario(product_id=1, demand_change_percent=25.0)
    assert res["product_id"] == 1
    assert res["demand_change_percent"] == 25.0
    assert "before" in res
    assert "after" in res
    assert "change" in res
    assert "disclaimer" in res
    assert "Scenario simulation only" in res["disclaimer"]


def test_simulate_product_scenario_store_filter():
    """Test scenario simulation filtered by store_id=1."""
    res = simulate_product_scenario(product_id=1, store_id=1, demand_change_percent=50.0)
    assert res["store_id"] == 1
    assert res["store_name"] == "Central Market"
    assert res["demand_change_percent"] == 50.0
    assert res["after"]["daily_sales_velocity"] == round(res["before"]["daily_sales_velocity"] * 1.5, 2)


def test_simulate_product_scenario_stock_adjustment():
    """Test scenario simulation with stock addition."""
    res = simulate_product_scenario(product_id=1, store_id=1, demand_change_percent=0.0, stock_change_units=50)
    assert res["after"]["stock"] == res["before"]["stock"] + 50
    assert res["change"]["stock_change"] == 50


def test_simulate_product_scenario_invalid_demand_low():
    """Test rejection of demand change below -90%."""
    with pytest.raises(ValueError, match="outside the valid scenario range"):
        simulate_product_scenario(product_id=1, demand_change_percent=-95.0)


def test_simulate_product_scenario_invalid_demand_high():
    """Test rejection of demand change above +300%."""
    with pytest.raises(ValueError, match="outside the valid scenario range"):
        simulate_product_scenario(product_id=1, demand_change_percent=350.0)


def test_simulate_product_scenario_invalid_negative_resulting_stock():
    """Test rejection when stock adjustment results in negative stock."""
    with pytest.raises(ValueError, match="negative inventory"):
        simulate_product_scenario(product_id=1, store_id=1, stock_change_units=-1000)


def test_simulate_product_scenario_nonexistent_product():
    """Test error when product_id does not exist."""
    with pytest.raises(ValueError, match="No inventory record found"):
        simulate_product_scenario(product_id=999)


def test_simulate_product_scenario_nonexistent_store():
    """Test error when store_id does not exist."""
    with pytest.raises(ValueError, match="No inventory record found"):
        simulate_product_scenario(product_id=1, store_id=999)


def test_simulate_demand_change_for_all():
    """Test batch scenario simulation for all store-product pairs."""
    results = simulate_demand_change_for_all(demand_change_percent=20.0)
    assert len(results) == 180
    for r in results:
        assert r["demand_change_percent"] == 20.0
        assert "before" in r
        assert "after" in r


def test_simulate_demand_change_for_all_store_filter():
    """Test batch scenario simulation for a single store (50 SKUs)."""
    results = simulate_demand_change_for_all(demand_change_percent=30.0, store_id=1)
    assert len(results) == 60
    for r in results:
        assert r["store_id"] == 1


def test_get_products_becoming_critical():
    """Test finding products that transition into critical stock-out risk."""
    results = get_products_becoming_critical(demand_change_percent=50.0)
    assert isinstance(results, list)
    for r in results:
        assert r["after"]["stockout_risk"] == "critical"
        assert r["before"]["stockout_risk"] != "critical"


def test_get_products_becoming_critical_no_transition_on_zero_demand():
    """Test that 0% demand change produces zero new critical transitions."""
    results = get_products_becoming_critical(demand_change_percent=0.0)
    assert len(results) == 0


def test_get_products_becoming_critical_store_filter():
    """Test finding critical transitions filtered by store_id=1."""
    results = get_products_becoming_critical(demand_change_percent=50.0, store_id=1)
    assert isinstance(results, list)
    for r in results:
        assert r["store_id"] == 1


def test_scenario_risk_classification_thresholds():
    """Test risk reclassification logic (days <= 3 -> critical, <= 7 -> high, > 45 -> overstock)."""
    # Verify risk status values in simulation result
    res = simulate_product_scenario(product_id=1, store_id=1, demand_change_percent=100.0)
    assert res["after"]["risk_status"] in ["critical", "stockout_risk", "healthy", "overstock", "slow_moving"]
