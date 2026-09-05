"""
Unit tests for Phase 8 Query Router & Entity Resolution Layer
"""

import pytest
from src.database import initialize_database
from src.query_router import (
    route_query,
    resolve_product,
    resolve_store,
    extract_limit,
    match_deterministic_intent,
    SUPPORTED_INTENTS
)


@pytest.fixture(scope="module", autouse=True)
def init_db():
    initialize_database()


def test_intent_routing_top_attention():
    """Test 1: Top attention routing."""
    res = route_query("What should I focus on today?")
    assert res["intent"] == "top_attention"


def test_intent_routing_stockout_risks():
    """Test 2: Stockout risk routing."""
    res = route_query("Which products are running out?")
    assert res["intent"] == "stockout_risks"


def test_intent_routing_overstock():
    """Test 3: Overstock routing."""
    res = route_query("Show overstocked products")
    assert res["intent"] == "overstock"


def test_intent_routing_slow_moving():
    """Test 4: Slow moving routing."""
    res = route_query("Which items are slow moving?")
    assert res["intent"] == "slow_moving"


def test_intent_routing_non_moving():
    """Test 5: Non moving routing."""
    res = route_query("What isn't selling?")
    assert res["intent"] == "non_moving"


def test_intent_routing_sales_spikes():
    """Test 6: Sales spikes routing."""
    res = route_query("Which products had a sales spike?")
    assert res["intent"] == "sales_spikes"


def test_intent_routing_sales_drops():
    """Test 7: Sales drops routing."""
    res = route_query("Which products dropped in sales?")
    assert res["intent"] == "sales_drops"


def test_intent_routing_product_status():
    """Test 8: Product status routing & entity resolution."""
    res = route_query("How is Milk 1L doing?")
    assert res["intent"] == "product_status"
    assert res["product_info"]["matched"] is True
    assert res["product_info"]["product_name"] == "Milk 1L"


def test_intent_routing_product_evidence():
    """Test 9: Product evidence routing."""
    res = route_query("Show evidence for Milk 1L")
    assert res["intent"] == "product_evidence"
    assert res["product_info"]["matched"] is True


def test_intent_routing_priority_explanation():
    """Test 10: Priority explanation routing."""
    res = route_query("Why is Milk 1L high priority?")
    assert res["intent"] == "priority_explanation"


def test_limit_extraction():
    """Test 11: Top N limit extraction."""
    res = route_query("Top 3 issues")
    assert res["intent"] == "top_attention"
    assert res["limit"] == 3

    assert extract_limit("Show top 10 products") == 10
    assert extract_limit("Top 100") == 20  # Capped at max 20


def test_unknown_product_fails_closed():
    """Test 12: Unknown product ('iPhone') fails closed and returns matched=False."""
    res = route_query("How is iPhone selling?")
    assert res["product_info"]["matched"] is False
    assert "No matching product found" in res["product_info"]["reason"]


def test_store_resolution():
    """Test 13: Store matching."""
    s_res = resolve_store("Central Market")
    assert s_res["matched"] is True
    assert s_res["store_id"] == 1

    s_res_2 = resolve_store("Branch #108")
    assert s_res_2["matched"] is True
    assert s_res_2["store_id"] == 2


def test_unsupported_profit_question():
    """Test 14: Profit question routes to unsupported_question."""
    res = route_query("What profit did we make?")
    assert res["intent"] == "unsupported_question"


def test_intent_allowlist():
    """Test 15: All routed intents exist in SUPPORTED_INTENTS allowlist."""
    for q in [
        "What should I focus on today?",
        "Which products are running out?",
        "Show overstock",
        "How is Milk 1L performing?",
        "What profit did we make?",
        "Who is our supplier?"
    ]:
        res = route_query(q)
        assert res["intent"] in SUPPORTED_INTENTS
