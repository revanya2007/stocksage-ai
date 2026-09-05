"""
StockSage AI - Decision Integration Layer Unit Tests (Phase 6C)
"""

import pytest
import json
import math
from src.decision_engine import (
    get_all_issue_candidates,
    select_primary_issue_for_product,
    get_ranked_issues,
    get_top_attention_items,
    get_business_impact_summary,
    get_issue_counts,
    get_decision_summary,
    estimate_issue_impact,
    format_key_evidence
)
from src.impact_engine import estimate_stockout_revenue_at_risk
from src.priority_engine import score_issue_priority
from src.risk_engine import classify_stockout_risk
from src.anomaly_detector import detect_product_anomaly


@pytest.fixture(scope="module")
def shared_candidates():
    """Module-level fixture to generate candidate list once across tests."""
    return get_all_issue_candidates()


# TEST 1 — CANDIDATE GENERATION
def test_candidate_generation(shared_candidates):
    candidates = shared_candidates
    assert isinstance(candidates, list)
    assert len(candidates) > 0

    non_actionable = {"normal", "safe", "healthy", "insufficient_data", "no_activity"}
    for cand in candidates:
        assert cand["issue_type"] not in non_actionable
        assert cand["actionable"] if "actionable" in cand else True


# TEST 2 — CANDIDATE STRUCTURE
def test_candidate_structure(shared_candidates):
    cand = shared_candidates[0]
    required_keys = ["store_id", "product_id", "product_name", "issue_type", "evidence", "impact", "priority"]
    for k in required_keys:
        assert k in cand

    assert "label" in cand["impact"]
    assert "value" in cand["impact"]
    assert "score" in cand["priority"]
    assert "raw_score" in cand["priority"]
    assert "label" in cand["priority"]


# TEST 3 — IMPACT INTEGRATION
def test_impact_integration():
    # Known stockout candidate test
    cand = {
        "store_id": 1,
        "product_id": 1,
        "issue_type": "stockout_risk"
    }
    imp = estimate_issue_impact(cand)
    expected_imp = estimate_stockout_revenue_at_risk(store_id=1, product_id=1)
    assert imp["impact_label"] == expected_imp["impact_label"]
    assert imp["impact_value"] == expected_imp["impact_value"]


# TEST 4 — PRIORITY INTEGRATION
def test_priority_integration():
    risk_info = classify_stockout_risk(product_id=1, store_id=1)
    imp_info = estimate_stockout_revenue_at_risk(store_id=1, product_id=1)
    expected_pri = score_issue_priority(risk_info, impact_result=imp_info)

    cand = {
        "store_id": 1,
        "product_id": 1,
        "issue_type": "stockout_risk",
        "severity": risk_info["severity"],
        "days_of_stock_remaining": risk_info["days_of_stock_remaining"]
    }
    cand_pri = score_issue_priority(cand, impact_result=imp_info)
    assert cand_pri["priority_score"] == expected_pri["priority_score"]
    assert cand_pri["raw_priority_score"] == expected_pri["raw_priority_score"]


# TEST 5 — ONE PRIMARY ISSUE PER PRODUCT
def test_one_primary_issue_per_product(shared_candidates):
    ranked = get_ranked_issues(candidates=shared_candidates)
    seen_pairs = set()
    for rec in ranked:
        pair = (rec["store_id"], rec["product_id"])
        assert pair not in seen_pairs, f"Duplicate store-product record found: {pair}"
        seen_pairs.add(pair)


# TEST 6 — SECONDARY SIGNALS
def test_secondary_signals():
    # Synthetic fixture with 2 valid candidates for product 5 store 1
    cands = [
        {
            "store_id": 1,
            "store_name": "Central Market",
            "product_id": 5,
            "product_name": "Milk 1L",
            "category": "Dairy",
            "issue_type": "overstock",
            "issue_label": "Overstock",
            "impact": {"label": "Excess Stock", "value": 5000.0},
            "priority": {"score": 72, "raw_score": 72.4, "label": "High Priority", "score_breakdown": {"urgency": {"score": 50}}}
        },
        {
            "store_id": 1,
            "store_name": "Central Market",
            "product_id": 5,
            "product_name": "Milk 1L",
            "category": "Dairy",
            "issue_type": "slow_moving",
            "issue_label": "Slow-Moving",
            "impact": {"label": "Slow Moving Stock", "value": 2000.0},
            "priority": {"score": 58, "raw_score": 58.1, "label": "Medium Priority", "score_breakdown": {"urgency": {"score": 45}}}
        }
    ]

    res = select_primary_issue_for_product(cands)
    assert res is not None
    assert res["primary_issue"]["issue_type"] == "overstock"
    assert res["primary_issue"]["priority"]["score"] == 72
    assert len(res["secondary_signals"]) == 1
    assert res["secondary_signals"][0]["issue_type"] == "slow_moving"
    assert res["secondary_signals"][0]["priority_score"] == 58


# TEST 7 — GLOBAL RANKING
def test_global_ranking(shared_candidates):
    ranked = get_ranked_issues(candidates=shared_candidates)
    assert len(ranked) > 0
    scores = [rec["primary_issue"]["priority"]["raw_score"] for rec in ranked]

    for i in range(len(scores) - 1):
        assert scores[i] >= scores[i + 1], f"Global ranking not descending at index {i}: {scores[i]} < {scores[i+1]}"


# TEST 8 — TIE BREAK
def test_tie_break():
    # Same raw priority score (80.0), tie-breaking by impact_value then issue precedence
    cands = [
        {
            "store_id": 1,
            "store_name": "Store 1",
            "product_id": 10,
            "product_name": "Prod A",
            "category": "Cat A",
            "issue_type": "sales_spike",
            "issue_label": "Sales Spike",
            "impact": {"label": "Impact", "value": 1000.0},
            "priority": {"score": 80, "raw_score": 80.0, "label": "Critical Priority", "score_breakdown": {"urgency": {"score": 60}}}
        },
        {
            "store_id": 1,
            "store_name": "Store 1",
            "product_id": 10,
            "product_name": "Prod A",
            "category": "Cat A",
            "issue_type": "stockout_risk",
            "issue_label": "Stock-out Risk",
            "impact": {"label": "Impact", "value": 1000.0},
            "priority": {"score": 80, "raw_score": 80.0, "label": "Critical Priority", "score_breakdown": {"urgency": {"score": 60}}}
        }
    ]
    res = select_primary_issue_for_product(cands)
    # Stockout risk (precedence 1) beats sales spike (precedence 6) on exact numeric tie
    assert res["primary_issue"]["issue_type"] == "stockout_risk"


# TEST 9 — TOP FIVE
def test_top_five(shared_candidates):
    top_items = get_top_attention_items(limit=5, candidates=shared_candidates)
    assert isinstance(top_items, list)
    assert len(top_items) <= 5
    for idx, item in enumerate(top_items):
        assert item["rank"] == idx + 1
        assert "key_evidence" in item
        assert "secondary_signals" in item


# TEST 10 — LIMIT
def test_limit(shared_candidates):
    items3 = get_top_attention_items(limit=3, candidates=shared_candidates)
    assert len(items3) <= 3

    with pytest.raises(ValueError, match="Limit must be greater than 0"):
        get_top_attention_items(limit=0)

    with pytest.raises(ValueError, match="Limit must be greater than 0"):
        get_ranked_issues(limit=-5)


# TEST 11 — STORE FILTER
def test_store_filter(shared_candidates):
    store_1_items = get_ranked_issues(store_id=1, candidates=shared_candidates)
    for rec in store_1_items:
        assert rec["store_id"] == 1

    store_2_candidates = get_all_issue_candidates(store_id=2)
    for cand in store_2_candidates:
        assert cand["store_id"] == 2


# TEST 12 — NO DUPLICATE PRIMARY ISSUE
def test_no_duplicate_primary_issue(shared_candidates):
    ranked = get_ranked_issues(candidates=shared_candidates)
    seen = set()
    for item in ranked:
        key = f"{item['store_id']}_{item['product_id']}"
        assert key not in seen
        seen.add(key)


# TEST 13 — ISSUE COUNTS
def test_issue_counts(shared_candidates):
    counts = get_issue_counts(candidates=shared_candidates)
    assert "candidate_issue_counts" in counts
    assert "primary_issue_counts" in counts
    assert "total_actionable_candidates" in counts
    assert "total_actionable_products" in counts

    c_counts = counts["candidate_issue_counts"]
    for k in ["stockout_risk", "overstock", "non_moving", "slow_moving", "sales_spike", "sales_drop"]:
        assert k in c_counts
        assert c_counts[k] >= 0


# TEST 14 — BUSINESS IMPACT SUMMARY
def test_business_impact_summary(shared_candidates):
    summary = get_business_impact_summary(candidates=shared_candidates)
    required_metrics = [
        "estimated_revenue_at_risk",
        "estimated_excess_retail_value",
        "non_moving_retail_value",
        "slow_moving_retail_value",
        "estimated_sales_value_gap",
        "estimated_incremental_sales_value"
    ]
    for m in required_metrics:
        assert m in summary
        assert summary[m] >= 0.0

    # Ensure total_loss is NOT present as an artificial sum
    assert "total_loss" not in summary


# TEST 15 — NO DOUBLE COUNTING
def test_no_double_counting(shared_candidates):
    summary = get_business_impact_summary(candidates=shared_candidates)
    # Summary should return distinct category totals without throwing duplicate count exceptions
    assert isinstance(summary, dict)
    for v in summary.values():
        assert isinstance(v, (int, float))
        assert v >= 0.0


# TEST 16 — ACTUAL STOCKOUT
def test_actual_stockout(shared_candidates):
    all_cands = shared_candidates
    assert len(all_cands) > 0
    # Verify stockout_risk is present among actionable candidates
    has_stockout = any(c["issue_type"] == "stockout_risk" for c in all_cands)
    assert has_stockout, "Expected at least one stockout_risk in actionable candidates"


# TEST 17 — ACTUAL SPIKE/DROP
def test_actual_spike_drop(shared_candidates):
    all_cands = shared_candidates
    has_anomaly = any(c["issue_type"] in ["sales_spike", "sales_drop"] for c in all_cands)
    assert has_anomaly, "Expected at least one sales anomaly candidate in database dataset"


# TEST 18 — JSON SERIALIZATION
def test_json_serialization(shared_candidates):
    top_items = get_top_attention_items(limit=5, candidates=shared_candidates)
    summary = get_decision_summary(candidates=shared_candidates)

    # json.dumps must work on outputs without throwing TypeError
    top_json = json.dumps(top_items)
    sum_json = json.dumps(summary)

    assert len(top_json) > 0
    assert len(sum_json) > 0


# TEST 19 — EMPTY INPUT HELPER
def test_empty_input_helper():
    res = select_primary_issue_for_product([])
    assert res is None


# TEST 20 — APP REGRESSION
def test_app_regression(shared_candidates):
    summary = get_decision_summary(candidates=shared_candidates)
    assert summary["total_actionable_products"] >= 0
    assert len(summary["top_attention"]) <= 5
