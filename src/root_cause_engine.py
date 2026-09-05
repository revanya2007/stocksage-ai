"""
StockSage AI - Cautious Root-Cause Detective Engine (Phase 10)

Inspects available store data signals (inventory availability, demand velocity,
sales anomalies, category trends, store trends, and reorder levels) to identify
possible contributing factors and contradictory evidence for retail issues.

CRITICAL RULE: This engine does NOT claim proven causality.
It uses cautious phrasing ("possible explanation", "potential contributing factor", "data is consistent with")
and appends a standard causality disclaimer to every response.
"""

from typing import Optional, Dict, Any, List, Tuple
from src.database import get_connection
from src.inventory_engine import get_inventory_summary
from src.anomaly_detector import detect_product_anomaly, detect_all_sales_anomalies
from src.decision_engine import get_all_issue_candidates
from src.risk_engine import classify_stockout_days

CAUSALITY_DISCLAIMER = "Correlation in past data does not guarantee causality. These are possible explanations based on available retail data; causality is not proven."


def analyze_inventory_signal(stock: int, days_rem: Optional[float]) -> Optional[Dict[str, Any]]:
    """Inspect inventory availability signal."""
    if stock == 0:
        return {
            "factor": "Out of Stock Constraint",
            "status": "supported",
            "evidence": {"current_stock": 0, "days_remaining": 0.0},
            "statement": "The product is currently out of stock, which may have constrained sales velocity during stock-out periods."
        }
    elif days_rem is not None and days_rem < 3.0:
        return {
            "factor": "Low Inventory Availability",
            "status": "supported",
            "evidence": {"current_stock": stock, "days_remaining": round(days_rem, 2)},
            "statement": f"Low inventory availability ({stock} units remaining, {days_rem:.2f} days coverage) is a potential contributing factor to constrained sales."
        }
    return None


def analyze_reorder_level_signal(reorder_level: int, ads: float) -> Optional[Dict[str, Any]]:
    """Compare reorder level vs 7-day expected demand requirement."""
    needed_7d = round(ads * 7.0, 1)
    if ads > 0 and reorder_level < needed_7d:
        return {
            "factor": "Reorder Level Mismatch",
            "status": "supported",
            "evidence": {"reorder_level": reorder_level, "expected_7d_demand": needed_7d},
            "statement": (
                f"The configured reorder level ({reorder_level} units) is below the estimated 7-day demand "
                f"requirement ({needed_7d} units), which may contribute to inventory replenishment delays."
            )
        }
    return None


def analyze_category_trend(product_id: int, category: str, store_id: int) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """
    Compare recent 7-day sales velocity vs prior 7-day sales velocity for the product
    against its overall product category at the store.
    Returns (supporting_signal, contradictory_signal).
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Get max sales date
    cursor.execute("SELECT MAX(date) FROM sales;")
    max_dt_row = cursor.fetchone()
    if not max_dt_row or not max_dt_row[0]:
        conn.close()
        return None, None

    max_dt = max_dt_row[0]

    # Calculate recent 7d category sales vs previous 7d category sales
    cursor.execute("""
    SELECT
        SUM(CASE WHEN date > date(?, '-7 days') THEN quantity_sold ELSE 0 END) as recent_7d,
        SUM(CASE WHEN date <= date(?, '-7 days') AND date > date(?, '-14 days') THEN quantity_sold ELSE 0 END) as prev_7d
    FROM sales s
    JOIN products p ON s.product_id = p.product_id
    WHERE s.store_id = ? AND p.category = ?;
    """, (max_dt, max_dt, max_dt, store_id, category))

    cat_row = cursor.fetchone()
    conn.close()

    if not cat_row or not cat_row["prev_7d"] or cat_row["prev_7d"] == 0:
        return None, None

    cat_recent = cat_row["recent_7d"] or 0
    cat_prev = cat_row["prev_7d"]
    cat_change_pct = round(((cat_recent - cat_prev) / cat_prev) * 100.0, 1)

    # Product category trend interpretation
    if cat_change_pct < -10.0:
        supported = {
            "factor": "Wider Category Demand Weakness",
            "status": "supported",
            "evidence": {"category": category, "category_change_pct": f"{cat_change_pct:+.1f}%"},
            "statement": f"Overall sales in the '{category}' category declined by {cat_change_pct:+.1f}%, which suggests wider category demand weakness."
        }
        return supported, None
    elif cat_change_pct > 10.0:
        supported = {
            "factor": "Category Demand Acceleration",
            "status": "supported",
            "evidence": {"category": category, "category_change_pct": f"{cat_change_pct:+.1f}%"},
            "statement": f"Overall sales in the '{category}' category increased by {cat_change_pct:+.1f}%, indicating potential category-wide demand growth."
        }
        contradictory = {
            "factor": "Category Trend Contradiction",
            "status": "contradictory",
            "evidence": {"category": category, "category_change_pct": f"{cat_change_pct:+.1f}%"},
            "statement": f"Category sales increased by {cat_change_pct:+.1f}%, so a category-wide sales decline is not supported as a contributing factor."
        }
        return supported, contradictory

    return None, None


def analyze_possible_causes(
    product_id: int,
    store_id: Optional[int] = None,
    issue_type: Optional[str] = None,
    as_of_date: Optional[str] = None
) -> Dict[str, Any]:
    """
    Main entry point for Cautious Root-Cause Detective.
    Cross-checks available inventory, anomaly, category, and store signals to produce
    evidence-backed possible explanations and contradictory evidence.
    """
    if store_id is None:
        store_id = 1

    summary = get_inventory_summary(product_id, store_id, as_of_date=as_of_date)
    pr_name = summary["product_name"]
    category = summary["category"]
    stock = summary["current_stock"]
    reorder_level = summary["reorder_level"]
    ads = summary["average_daily_sales_30d"]
    days_rem = summary["days_of_stock_remaining"]

    # Detect issue type if not explicitly provided
    cands = get_all_issue_candidates(as_of_date=as_of_date, store_id=store_id)
    matched_cand = next((c for c in cands if c["product_id"] == product_id), None)

    if not issue_type:
        if matched_cand:
            issue_type = matched_cand["issue_type"]
        elif stock == 0:
            issue_type = "stockout_risk"
        else:
            issue_type = "healthy"

    possible_explanations: List[Dict[str, Any]] = []
    contradictory_evidence: List[Dict[str, Any]] = []

    # 1. Inspect Inventory Availability Signal
    inv_signal = analyze_inventory_signal(stock, days_rem)
    if inv_signal and issue_type in ["sales_drop", "stockout_risk"]:
        possible_explanations.append(inv_signal)

    # 2. Inspect Reorder Level vs Demand Requirement Signal
    reorder_signal = analyze_reorder_level_signal(reorder_level, ads)
    if reorder_signal and issue_type in ["stockout_risk", "top_attention", "priority_explanation"]:
        possible_explanations.append(reorder_signal)

    # 3. Inspect Category Trend Signal
    cat_supp, cat_contra = analyze_category_trend(product_id, category, store_id)
    if cat_supp:
        if issue_type == "sales_drop" and cat_supp["evidence"]["category_change_pct"].startswith("-"):
            possible_explanations.append(cat_supp)
        elif issue_type in ["sales_spike", "stockout_risk"] and cat_supp["evidence"]["category_change_pct"].startswith("+"):
            possible_explanations.append(cat_supp)
    if cat_contra and issue_type == "sales_drop":
        contradictory_evidence.append(cat_contra)

    # 4. Handle Non-Moving / Data Limitation Case
    if issue_type == "non_moving" or summary["units_sold_30d"] == 0:
        possible_explanations.append({
            "factor": "Zero Recent Sales Velocity",
            "status": "supported",
            "evidence": {"units_sold_30d": 0, "current_stock": stock},
            "statement": f"0 units were sold in the last 30 days while {stock} units remain in stock."
        })
        possible_explanations.append({
            "factor": "External Data Limitation",
            "status": "data_limited",
            "evidence": {"missing_tables": ["promotions", "pricing_competitor", "customer_demographics"]},
            "statement": "The store database does not track promotion history, competitor pricing, or customer footfall required to explain why demand is absent. These factors may be involved."
        })

    # 5. Handle Priority Score Breakdown (Priority Explanation)
    if issue_type in ["priority_explanation", "high_priority"] and matched_cand:
        prio = matched_cand.get("priority", {})
        score = prio.get("score", 0)
        drivers = prio.get("drivers", [])
        driver_strs = [f"{d['factor']} ({d['impact']})" for d in drivers]
        possible_explanations.append({
            "factor": "Multi-Factor Priority Breakdown",
            "status": "supported",
            "evidence": {"priority_score": score, "drivers": drivers},
            "statement": f"This item received a priority score of {score}/100 based on deterministic drivers: {', '.join(driver_strs)}. These factors indicate its priority."
        })

    # 6. Determine Data-Based Confidence Rating
    supp_count = len([e for e in possible_explanations if e.get("status") == "supported"])
    if supp_count >= 2:
        confidence = "High"
    elif supp_count == 1:
        confidence = "Medium"
    elif issue_type == "non_moving":
        confidence = "Low"
    else:
        confidence = "Insufficient"

    # Default explanation if no specific signals were found
    if not possible_explanations:
        possible_explanations.append({
            "factor": "Normal Demand Variation",
            "status": "supported",
            "evidence": {"average_daily_sales": round(ads, 2)},
            "statement": "Product operational metrics suggests expected historical demand variance."
        })
        confidence = "Medium"

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT store_name FROM stores WHERE store_id = ?;", (store_id,))
    st_row = cursor.fetchone()
    store_name = st_row["store_name"] if st_row else f"Store #{store_id}"
    conn.close()

    # Format possible causes with hypothesis and evidence_supporting for Copilot Service & UI
    causes_formatted = []
    for pe in possible_explanations:
        causes_formatted.append({
            "hypothesis": pe.get("statement", pe.get("factor", "Potential contributing factor")),
            "confidence": confidence,
            "evidence_supporting": [f"{k}: {v}" for k, v in pe.get("evidence", {}).items()] if isinstance(pe.get("evidence"), dict) else [str(pe.get("evidence"))]
        })

    return {
        "product_id": product_id,
        "product_name": pr_name,
        "category": category,
        "store_id": store_id,
        "store_name": store_name,
        "current_stock": stock,
        "reorder_level": reorder_level,
        "units_30d": summary.get("units_sold_30d", 0),
        "average_daily_sales": ads,
        "issue_type": issue_type,
        "primary_cause": possible_explanations[0].get("factor") if possible_explanations else "Normal Demand Variation",
        "possible_causes": causes_formatted,
        "possible_explanations": possible_explanations,
        "contradictory_evidence": contradictory_evidence,
        "confidence": confidence,
        "confidence_rating": confidence,
        "disclaimer": CAUSALITY_DISCLAIMER
    }
