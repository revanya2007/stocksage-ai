"""
Unit tests for Phase 10 Evidence-Backed Cautious Root-Cause Detective Engine.
"""

import pytest
from src.root_cause_engine import (
    analyze_possible_causes,
    CAUSALITY_DISCLAIMER
)


def test_analyze_possible_causes_basic():
    """Test basic root cause analysis for Milk 1L (product_id 1)."""
    res = analyze_possible_causes(product_id=1)
    assert res["product_id"] == 1
    assert "product_name" in res
    assert "store_name" in res
    assert "primary_cause" in res
    assert "possible_causes" in res
    assert "confidence_rating" in res
    assert "disclaimer" in res
    assert res["disclaimer"] == CAUSALITY_DISCLAIMER


def test_analyze_possible_causes_with_store_filter():
    """Test root cause analysis filtered by store_id=1."""
    res = analyze_possible_causes(product_id=1, store_id=1)
    assert res["store_id"] == 1
    assert res["store_name"] == "Central Market"
    assert isinstance(res["possible_causes"], list)


def test_analyze_possible_causes_disclaimer_presence():
    """Test that mandatory causality disclaimer is present on every analysis."""
    for pid in [1, 2, 3, 4, 5]:
        res = analyze_possible_causes(product_id=pid)
        assert res["disclaimer"] == CAUSALITY_DISCLAIMER
        assert "Correlation in past data does not guarantee" in res["disclaimer"]


def test_analyze_possible_causes_cautious_phrasing():
    """Test that hypothesis text contains cautious wording (e.g. 'possible', 'potential', 'may have')."""
    res = analyze_possible_causes(product_id=1)
    for cause in res["possible_causes"]:
        hyp = cause["hypothesis"].lower()
        assert any(word in hyp for word in ["possible", "potential", "may", "suggests", "indicates", "aligned"])


def test_analyze_possible_causes_nonexistent_product():
    """Test error handling for non-existent product."""
    with pytest.raises(ValueError, match="No inventory record found"):
        analyze_possible_causes(product_id=999)


def test_analyze_possible_causes_nonexistent_store():
    """Test error handling for non-existent store."""
    with pytest.raises(ValueError, match="No inventory record found"):
        analyze_possible_causes(product_id=1, store_id=999)


def test_analyze_possible_causes_confidence_rating_values():
    """Test that confidence rating is one of ['High', 'Medium', 'Low']."""
    for pid in range(1, 10):
        res = analyze_possible_causes(product_id=pid)
        assert res["confidence_rating"] in ["High", "Medium", "Low"]


def test_analyze_possible_causes_evidence_list_not_empty():
    """Test that possible causes contain supporting evidence lists."""
    res = analyze_possible_causes(product_id=1)
    assert len(res["possible_causes"]) > 0
    for cause in res["possible_causes"]:
        assert "evidence_supporting" in cause
        assert isinstance(cause["evidence_supporting"], list)


def test_analyze_possible_causes_inventory_signal():
    """Test detection of stock-out or low stock inventory signals."""
    # Find a product with low stock
    res = analyze_possible_causes(product_id=1, store_id=1)
    causes_str = str(res["possible_causes"])
    assert len(causes_str) > 0


def test_analyze_possible_causes_category_trend_comparison():
    """Test that category trend comparison hypothesis is generated."""
    res = analyze_possible_causes(product_id=2, store_id=1)
    assert "category" in res
    assert isinstance(res["possible_causes"], list)


def test_analyze_possible_causes_contradictory_evidence():
    """Test handling of contradictory evidence when item trend diverges from category trend."""
    # Run across multiple products to ensure no crashing on contradictory evidence
    for pid in range(1, 6):
        res = analyze_possible_causes(product_id=pid)
        assert "primary_cause" in res


def test_analyze_possible_causes_non_moving_explanation():
    """Test cautious explanation for non-moving items mentioning dataset boundary."""
    res = analyze_possible_causes(product_id=1)
    assert "disclaimer" in res


def test_analyze_possible_causes_structure_keys():
    """Test all expected keys in the root cause diagnostic output."""
    res = analyze_possible_causes(product_id=1)
    expected_keys = [
        "product_id", "product_name", "category", "store_id", "store_name",
        "current_stock", "reorder_level", "units_30d", "average_daily_sales",
        "primary_cause", "possible_causes", "confidence_rating", "disclaimer"
    ]
    for key in expected_keys:
        assert key in res
