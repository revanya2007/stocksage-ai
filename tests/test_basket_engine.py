"""
Unit tests for Phase 11 Basket Intelligence Engine.
"""
import pytest
from src.basket_engine import (
    get_transaction_baskets,
    calculate_product_pairs,
    get_top_product_pairs,
    get_related_products,
    BASKET_CONFIG
)

def test_transaction_grouping():
    """Test that transactions are grouped correctly."""
    baskets = get_transaction_baskets(store_id=1)
    assert isinstance(baskets, list)
    assert len(baskets) > 0
    assert isinstance(baskets[0], list)

def test_calculate_product_pairs():
    """Test product pair metric calculation."""
    # Temporarily lower thresholds for testing
    old_min = BASKET_CONFIG["min_pair_transactions"]
    old_sup = BASKET_CONFIG["min_support"]
    BASKET_CONFIG["min_pair_transactions"] = 1
    BASKET_CONFIG["min_support"] = 0.0001
    
    pairs = calculate_product_pairs(store_id=1)
    assert isinstance(pairs, list)
    if pairs:
        pair = pairs[0]
        assert "product_a_id" in pair
        assert "product_b_id" in pair
        assert "support" in pair
        assert "confidence_a_to_b" in pair
        assert "confidence_b_to_a" in pair
        assert "lift" in pair
        assert pair["support"] > 0
        assert pair["confidence_a_to_b"] > 0
        assert pair["confidence_b_to_a"] > 0
        assert pair["lift"] > 0
        
    BASKET_CONFIG["min_pair_transactions"] = old_min
    BASKET_CONFIG["min_support"] = old_sup

def test_get_top_product_pairs():
    pairs = get_top_product_pairs(store_id=1, limit=5)
    assert len(pairs) <= 5

def test_get_related_products():
    """Test getting related products for a specific product."""
    old_min = BASKET_CONFIG["min_pair_transactions"]
    BASKET_CONFIG["min_pair_transactions"] = 1
    BASKET_CONFIG["min_support"] = 0.0001
    
    # Try finding related products for product 1
    related = get_related_products(product_id=1, store_id=1)
    assert isinstance(related, list)
    for r in related:
        assert "related_product_id" in r
        assert "confidence" in r
        assert "lift" in r
        
    BASKET_CONFIG["min_pair_transactions"] = old_min
    BASKET_CONFIG["min_support"] = 0.005

def test_unknown_store():
    pairs = calculate_product_pairs(store_id=999)
    assert len(pairs) == 0

def test_unknown_product():
    related = get_related_products(product_id=999)
    assert len(related) == 0
