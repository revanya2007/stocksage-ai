"""
Unit tests for Phase 11 Opportunity Detector Engine.
"""
import pytest
from src.opportunity_engine import (
    get_all_opportunities,
    get_top_opportunities,
    OPPORTUNITY_CONFIG
)

def test_get_top_opportunities():
    opps = get_top_opportunities(store_id=1, limit=5)
    assert isinstance(opps, list)
    assert len(opps) <= 5

def test_opportunity_structure():
    opps = get_top_opportunities(store_id=1)
    if opps:
        o = opps[0]
        assert "opportunity_type" in o
        assert "score" in o
        assert "evidence" in o
        assert "opportunity_label" in o
        assert "suggested_action" in o
        assert 0 <= o["score"] <= 100
        
def test_no_profit_predictions():
    opps = get_top_opportunities(store_id=1)
    for o in opps:
        assert "profit" not in o.get("suggested_action", "").lower()
        assert "future revenue" not in o.get("suggested_action", "").lower()

def test_deterministic_sorting():
    opps1 = get_top_opportunities(store_id=1)
    opps2 = get_top_opportunities(store_id=1)
    assert len(opps1) == len(opps2)
    if opps1:
        assert opps1[0]["product_id"] == opps2[0]["product_id"]
        assert opps1[0]["opportunity_type"] == opps2[0]["opportunity_type"]
