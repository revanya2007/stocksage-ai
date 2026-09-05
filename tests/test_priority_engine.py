"""
StockSage AI - Priority Engine Unit Tests (Phase 6B)
"""

import pytest
import math
from src.priority_engine import (
    PRIORITY_CONFIG,
    validate_priority_config,
    get_priority_label,
    score_severity,
    score_business_impact,
    score_urgency,
    score_confidence,
    calculate_priority_score,
    normalize_issue_for_priority,
    score_issue_priority,
    sort_scored_issues
)
from src.risk_engine import classify_stockout_risk, classify_non_moving
from src.impact_engine import estimate_stockout_revenue_at_risk


# TEST 1 — WEIGHTS SUM TO 1
def test_weights_sum_to_one():
    cfg = validate_priority_config()
    weights = cfg["weights"]
    total = sum(weights.values())
    assert math.isclose(total, 1.0, abs_tol=1e-5)
    assert weights["severity"] == 0.35
    assert weights["impact"] == 0.30
    assert weights["urgency"] == 0.25
    assert weights["confidence"] == 0.10


# TEST 2 — INVALID WEIGHTS
def test_invalid_weights():
    # Weights sum to 1.6
    invalid_cfg = {
        "weights": {
            "severity": 0.5,
            "impact": 0.5,
            "urgency": 0.5,
            "confidence": 0.1
        }
    }
    with pytest.raises(ValueError, match="Priority weights must sum to 1.0"):
        validate_priority_config(invalid_cfg)

    # Negative weight
    neg_cfg = {
        "weights": {
            "severity": -0.1,
            "impact": 0.5,
            "urgency": 0.4,
            "confidence": 0.2
        }
    }
    with pytest.raises(ValueError, match="must be between 0.0 and 1.0"):
        validate_priority_config(neg_cfg)


# TEST 3 — PRIORITY COMPONENT RANGE
def test_priority_component_range():
    # Negative component score
    with pytest.raises(ValueError, match="must be between 0 and 100"):
        calculate_priority_score(severity_score=-10, impact_score=50, urgency_score=50, confidence_score=50)

    # Component score > 100
    with pytest.raises(ValueError, match="must be between 0 and 100"):
        calculate_priority_score(severity_score=105, impact_score=50, urgency_score=50, confidence_score=50)


# TEST 4 — FINAL SCORE FORMULA
def test_final_score_formula():
    sev = 100.0
    imp = 60.0
    urg = 80.0
    conf = 90.0

    res = calculate_priority_score(sev, imp, urg, conf)
    # Expected: 100*0.35 + 60*0.30 + 80*0.25 + 90*0.10 = 35 + 18 + 20 + 9 = 82
    assert res["raw_priority_score"] == 82.0
    assert res["priority_score"] == 82
    assert get_priority_label(res["raw_priority_score"]) == "Critical Priority"


# TEST 5 — PRIORITY RANGE
def test_priority_range():
    # Min score
    res_min = calculate_priority_score(0, 0, 0, 0)
    assert res_min["raw_priority_score"] == 0.0
    assert res_min["priority_score"] == 0

    # Max score
    res_max = calculate_priority_score(100, 100, 100, 100)
    assert res_max["raw_priority_score"] == 100.0
    assert res_max["priority_score"] == 100


# TEST 6 — PRIORITY LABEL BOUNDARIES
def test_priority_label_boundaries():
    assert get_priority_label(29.99) == "Monitor"
    assert get_priority_label(30.00) == "Low Priority"

    assert get_priority_label(49.99) == "Low Priority"
    assert get_priority_label(50.00) == "Medium Priority"

    assert get_priority_label(64.99) == "Medium Priority"
    assert get_priority_label(65.00) == "High Priority"

    assert get_priority_label(79.99) == "High Priority"
    assert get_priority_label(80.00) == "Critical Priority"

    assert get_priority_label(100.0) == "Critical Priority"


# TEST 7 — STOCK-OUT SEVERITY
def test_stockout_severity():
    assert score_severity("stockout_risk", severity_level="critical") == 100.0
    assert score_severity("stockout_risk", severity_level="high") == 80.0
    assert score_severity("stockout_risk", severity_level="medium") == 60.0
    assert score_severity("stockout_risk", severity_level="safe") == 0.0
    assert score_severity("stockout_risk", severity_level="none") == 0.0


# TEST 8 — STOCK-OUT URGENCY
def test_stockout_urgency():
    assert score_urgency("stockout_risk", days_remaining=0.0) == 100.0
    assert score_urgency("stockout_risk", days_remaining=1.0) == 100.0
    assert score_urgency("stockout_risk", days_remaining=1.5) == 95.0
    assert score_urgency("stockout_risk", days_remaining=2.99) == 95.0
    assert score_urgency("stockout_risk", days_remaining=3.0) == 80.0
    assert score_urgency("stockout_risk", days_remaining=4.99) == 80.0
    assert score_urgency("stockout_risk", days_remaining=5.0) == 60.0
    assert score_urgency("stockout_risk", days_remaining=6.99) == 60.0
    assert score_urgency("stockout_risk", days_remaining=7.0) == 0.0
    assert score_urgency("stockout_risk", days_remaining=None) == 0.0


# TEST 9 — SPIKE SEVERITY BOUNDARIES
def test_spike_severity_boundaries():
    assert score_severity("sales_spike", percentage_change=49.99) == 0.0
    assert score_severity("sales_spike", percentage_change=50.0) == 55.0
    assert score_severity("sales_spike", percentage_change=74.99) == 55.0
    assert score_severity("sales_spike", percentage_change=75.0) == 70.0
    assert score_severity("sales_spike", percentage_change=99.99) == 70.0
    assert score_severity("sales_spike", percentage_change=100.0) == 85.0


# TEST 10 — DROP SEVERITY BOUNDARIES
def test_drop_severity_boundaries():
    assert score_severity("sales_drop", percentage_change=-29.99) == 0.0
    assert score_severity("sales_drop", percentage_change=-30.0) == 60.0
    assert score_severity("sales_drop", percentage_change=-44.99) == 60.0
    assert score_severity("sales_drop", percentage_change=-45.0) == 75.0
    assert score_severity("sales_drop", percentage_change=-59.99) == 75.0
    assert score_severity("sales_drop", percentage_change=-60.0) == 90.0


# TEST 11 — IMPACT BANDS
def test_impact_bands():
    assert score_business_impact(0) == 0.0
    assert score_business_impact(-500) == 0.0
    assert score_business_impact(500) == 20.0
    assert score_business_impact(999.99) == 20.0
    assert score_business_impact(1000) == 40.0
    assert score_business_impact(2999.99) == 40.0
    assert score_business_impact(3000) == 60.0
    assert score_business_impact(5999.99) == 60.0
    assert score_business_impact(6000) == 75.0
    assert score_business_impact(9999.99) == 75.0
    assert score_business_impact(10000) == 90.0
    assert score_business_impact(19999.99) == 90.0
    assert score_business_impact(20000) == 100.0
    assert score_business_impact(50000) == 100.0


# TEST 12 — MISSING IMPACT
def test_missing_impact():
    issue = {
        "issue_type": "stockout_risk",
        "severity": "critical",
        "days_of_stock_remaining": 1.0
    }
    impact_res = {
        "issue_type": "stockout_risk",
        "impact_label": "Estimated Revenue at Risk",
        "impact_value": None
    }
    scored = score_issue_priority(issue, impact_result=impact_res)
    assert scored["impact_score"] == 0.0
    assert scored["impact_available"] is False
    assert scored["actionable"] is True
    # Priority should still calculate: 100*0.35 + 0*0.30 + 100*0.25 + 95*0.10 = 35 + 0 + 25 + 9.5 = 69.5 -> 70
    assert scored["priority_score"] == 70
    assert scored["priority_label"] == "High Priority"


# TEST 13 — NON-MOVING
def test_non_moving():
    assert score_severity("non_moving") == 85.0
    assert score_urgency("non_moving") == 60.0


# TEST 14 — SLOW-MOVING
def test_slow_moving():
    assert score_severity("slow_moving") == 55.0
    assert score_urgency("slow_moving") == 45.0


# TEST 15 — CONFIDENCE
def test_confidence():
    full_inv = {
        "issue_type": "stockout_risk",
        "data_quality": {"is_sufficient_data": True},
        "historical_days": 30
    }
    assert score_confidence(full_inv) == 95.0

    full_anom = {
        "issue_type": "sales_spike",
        "available_baseline_weeks": 6
    }
    assert score_confidence(full_anom) == 90.0

    low_base = {
        "issue_type": "sales_spike",
        "anomaly_type": "low_baseline"
    }
    assert score_confidence(low_base) == 40.0

    insuff = {
        "issue_type": "sales_spike",
        "anomaly_type": "insufficient_data"
    }
    assert score_confidence(insuff) == 20.0


# TEST 16 — SCORE BREAKDOWN
def test_score_breakdown():
    issue = {
        "issue_type": "stockout_risk",
        "severity": "critical",
        "days_of_stock_remaining": 2.4,
        "impact_value": 4500.0  # Band 3000-5999 -> 60
    }
    scored = score_issue_priority(issue)
    breakdown = scored["score_breakdown"]

    sev_weighted = breakdown["severity"]["weighted_score"]
    imp_weighted = breakdown["impact"]["weighted_score"]
    urg_weighted = breakdown["urgency"]["weighted_score"]
    conf_weighted = breakdown["confidence"]["weighted_score"]

    sum_weighted = round(sev_weighted + imp_weighted + urg_weighted + conf_weighted, 4)
    assert math.isclose(sum_weighted, scored["raw_priority_score"], abs_tol=1e-3)


# TEST 17 — NON-ACTIONABLE NORMAL
def test_non_actionable_normal():
    norm_issue = {
        "issue_type": "normal",
        "percentage_change": 10.0
    }
    scored = score_issue_priority(norm_issue)
    assert scored["actionable"] is False
    assert scored["priority_score"] == 0
    assert scored["raw_priority_score"] == 0.0
    assert scored["priority_label"] == "Monitor"


# TEST 18 — LOW BASELINE
def test_low_baseline():
    low_base_issue = {
        "issue_type": "low_baseline",
        "percentage_change": 200.0
    }
    scored = score_issue_priority(low_base_issue)
    assert scored["actionable"] is False
    assert scored["priority_score"] == 0
    assert scored["priority_label"] == "Monitor"


# TEST 19 — TIE SORTING
def test_tie_sorting():
    issues = [
        {
            "product_id": 2,
            "store_id": 1,
            "raw_priority_score": 75.0,
            "impact_value": 3000.0,
            "urgency_score": 60.0
        },
        {
            "product_id": 1,
            "store_id": 1,
            "raw_priority_score": 75.0,
            "impact_value": 3000.0,
            "urgency_score": 60.0
        },
        {
            "product_id": 3,
            "store_id": 1,
            "raw_priority_score": 85.0,
            "impact_value": 1000.0,
            "urgency_score": 90.0
        },
        {
            "product_id": 4,
            "store_id": 1,
            "raw_priority_score": 75.0,
            "impact_value": 5000.0,
            "urgency_score": 60.0
        }
    ]

    sorted_issues = sort_scored_issues(issues)

    # 1st: highest raw priority (85.0) -> product 3
    assert sorted_issues[0]["product_id"] == 3
    # 2nd: raw 75.0, higher impact (5000) -> product 4
    assert sorted_issues[1]["product_id"] == 4
    # 3rd: raw 75.0, impact 3000, lower product_id -> product 1
    assert sorted_issues[2]["product_id"] == 1
    # 4th: raw 75.0, impact 3000, higher product_id -> product 2
    assert sorted_issues[3]["product_id"] == 2


# TEST 20 — REAL PROJECT CASE
def test_real_project_case():
    # Use real Phase 4 risk function and Phase 6A impact function
    risk_info = classify_stockout_risk(product_id=1, store_id=1)
    impact_info = estimate_stockout_revenue_at_risk(store_id=1, product_id=1)

    scored = score_issue_priority(risk_info, impact_result=impact_info)

    assert 0 <= scored["priority_score"] <= 100
    assert 0.0 <= scored["raw_priority_score"] <= 100.0
    assert "score_breakdown" in scored
    assert "priority_label" in scored
    assert scored["priority_label"] in ["Critical Priority", "High Priority", "Medium Priority", "Low Priority", "Monitor"]
    assert len(scored["priority_factors"]) == 4
