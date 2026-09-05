"""
StockSage AI - Evidence-Backed Recommendation Engine (Phase 7)

Generates deterministic, evidence-backed advisory recommendations from Phase 6C
decision records. Implements evidence inspection payloads, confidence scoring,
inherits calculation assumptions, and handles SQLite persistence with deduplication.
"""

import json
import math
from datetime import datetime
from typing import Optional, Dict, Any, List

from src.database import get_connection
from src.decision_engine import (
    get_ranked_issues,
    get_top_attention_items,
    ISSUE_LABEL_MAP
)

ALLOWED_MANAGER_ACTIONS = {"Review", "Accept", "Dismiss"}

def get_confidence_label(score: float) -> str:
    """
    Map priority or data quality confidence score to human-readable confidence level.
    """
    if score is None:
        return "Insufficient"
    try:
        val = float(score)
    except (ValueError, TypeError):
        return "Insufficient"

    if val >= 85.0:
        return "High"
    elif val >= 60.0:
        return "Medium"
    elif val >= 30.0:
        return "Low"
    else:
        return "Insufficient"


def build_recommendation_evidence(decision_record: Dict[str, Any]) -> Dict[str, Any]:
    """
    Construct frontend-friendly structured evidence from a Phase 6C decision record.
    Returns machine-readable metrics list, formula, impact summary, assumptions, and confidence.
    """
    prim = decision_record.get("primary_issue", decision_record)
    ev = prim.get("evidence", {})
    itype = prim.get("issue_type")
    impact_info = prim.get("impact", {})
    priority_info = prim.get("priority", {})

    metrics = []
    calc = {"label": "Formula", "formula": "None"}

    if itype == "stockout_risk":
        stock = ev.get("current_stock")
        ads = ev.get("average_daily_sales")
        days = ev.get("days_of_stock_remaining")

        metrics.append({"label": "Current Stock", "value": stock, "unit": "units"})
        metrics.append({"label": "30-Day Units Sold", "value": ev.get("units_sold_30d"), "unit": "units"})
        metrics.append({"label": "Average Daily Sales", "value": round(ads, 2) if ads is not None else 0.0, "unit": "units/day"})

        if stock == 0:
            metrics.append({"label": "Days Remaining", "value": 0.0, "unit": "days"})
            calc = {
                "label": "Stock Coverage",
                "formula": "0 stock units available (Out of Stock)"
            }
        elif ads is not None and ads > 0:
            metrics.append({"label": "Days Remaining", "value": round(days, 2) if days is not None else None, "unit": "days"})
            calc = {
                "label": "Stock Coverage",
                "formula": f"{stock} ÷ {round(ads, 2)} = {round(days, 2) if days is not None else 'N/A'} days"
            }
        else:
            metrics.append({"label": "Days Remaining", "value": None, "unit": "Not calculable — no recent sales"})
            calc = {
                "label": "Stock Coverage",
                "formula": "Not calculable — 0 average daily sales"
            }

    elif itype == "overstock":
        stock = ev.get("current_stock")
        ads = ev.get("average_daily_sales")
        days = ev.get("days_of_stock_remaining")

        metrics.append({"label": "Current Stock", "value": stock, "unit": "units"})
        metrics.append({"label": "Average Daily Sales", "value": round(ads, 2) if ads is not None else 0.0, "unit": "units/day"})
        metrics.append({"label": "Days Coverage", "value": round(days, 1) if days is not None else None, "unit": "days"})
        calc = {
            "label": "Excess Coverage Calculation",
            "formula": f"max({stock} stock - ({round(ads, 2) if ads else 0} ADS * 30 target days), 0)"
        }

    elif itype == "non_moving":
        stock = ev.get("current_stock")
        units_30d = ev.get("units_sold_30d", 0)

        metrics.append({"label": "Current Stock", "value": stock, "unit": "units"})
        metrics.append({"label": "30-Day Units Sold", "value": units_30d, "unit": "units"})
        calc = {
            "label": "Non-Moving Inventory Value",
            "formula": f"{stock} stock * selling price (0 units sold in 30 days)"
        }

    elif itype == "slow_moving":
        stock = ev.get("current_stock")
        units_30d = ev.get("units_sold_30d", 0)

        metrics.append({"label": "Current Stock", "value": stock, "unit": "units"})
        metrics.append({"label": "30-Day Units Sold", "value": units_30d, "unit": "units"})
        calc = {
            "label": "Slow-Moving Retail Value",
            "formula": f"{stock} stock * selling price (1-5 units sold in 30 days)"
        }

    elif itype in ["sales_spike", "sales_drop"]:
        rec_units = ev.get("recent_units")
        base_units = ev.get("baseline_weekly_units")
        pct_chg = ev.get("percentage_change")

        metrics.append({"label": "Recent 7-Day Units", "value": rec_units, "unit": "units"})
        metrics.append({"label": "Baseline Weekly Units", "value": round(base_units, 2) if base_units is not None else 0.0, "unit": "units/week"})
        metrics.append({"label": "Percentage Change", "value": f"{pct_chg:+.1f}%" if pct_chg is not None else "N/A", "unit": ""})
        calc = {
            "label": "Sales Anomaly Gap",
            "formula": f"Recent ({rec_units}) vs Baseline ({round(base_units, 2) if base_units else 0})"
        }

    elif itype == "new_activity":
        rec_units = ev.get("recent_units")
        metrics.append({"label": "Recent 7-Day Units", "value": rec_units, "unit": "units"})
        metrics.append({"label": "Baseline Weekly Units", "value": 0, "unit": "units/week"})
        calc = {
            "label": "New Activity Indicator",
            "formula": "First-time sales observed after 0 historical baseline"
        }

    # Extract assumptions
    assumptions = impact_info.get("assumptions", [])
    if not assumptions:
        if itype == "stockout_risk":
            assumptions = [
                "Recent 30-day average daily sales velocity is assumed to continue.",
                "Estimated Revenue at Risk horizon is set to 7 calendar days.",
                "Selling price is assumed unchanged over the forecast horizon."
            ]
        elif itype == "overstock":
            assumptions = [
                "Target inventory coverage threshold is set to 30 calendar days.",
                "Excess inventory value uses selling price because product cost is unavailable."
            ]
        elif itype in ["sales_spike", "sales_drop"]:
            assumptions = [
                "Latest 7-day sales are compared against the 6-week historical weekly baseline.",
                "Historical sales patterns do not guarantee future customer demand."
            ]

    # Calculate confidence label
    conf_score = priority_info.get("score")
    conf_label = get_confidence_label(conf_score)
    if itype == "new_activity":
        conf_label = "Low"  # New activity has inherent lower baseline confidence

    return {
        "metrics": metrics,
        "calculation": calc,
        "impact": {
            "label": impact_info.get("label", "Financial Impact"),
            "value": impact_info.get("value")
        },
        "priority_breakdown": priority_info.get("score_breakdown", {}),
        "assumptions": assumptions,
        "confidence": conf_label,
        "secondary_signals": decision_record.get("secondary_signals", [])
    }


def generate_recommendation(decision_record: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate a structured, evidence-backed advisory recommendation from a Phase 6C primary decision record.
    Uses strictly deterministic rules and advisory phrasing.
    """
    # Normalize record if wrapped in primary_issue
    if "primary_issue" in decision_record:
        prim = decision_record["primary_issue"]
        store_id = decision_record["store_id"]
        store_name = decision_record["store_name"]
        product_id = decision_record["product_id"]
        product_name = decision_record["product_name"]
        category = decision_record["category"]
        secondary_signals = decision_record.get("secondary_signals", [])
    else:
        prim = decision_record
        store_id = prim.get("store_id")
        store_name = prim.get("store_name", f"Store {store_id}")
        product_id = prim.get("product_id")
        product_name = prim.get("product_name", f"Product {product_id}")
        category = prim.get("category", "")
        secondary_signals = prim.get("secondary_signals", [])

    itype = prim.get("issue_type")
    ev = prim.get("evidence", {})
    impact_info = prim.get("impact", {})
    priority_info = prim.get("priority", {})

    priority_score = priority_info.get("score", 0)
    priority_label = priority_info.get("label", "Monitor")

    recommendation_title = f"Review {product_name} ({ISSUE_LABEL_MAP.get(itype, itype)})"
    rec_text = ""

    # Rule-based Advisory Recommendation Wording Generation
    if itype == "stockout_risk":
        stock = ev.get("current_stock")
        ads = ev.get("average_daily_sales")
        days = ev.get("days_of_stock_remaining")
        severity = prim.get("severity")

        if stock == 0:
            rec_text = (
                f"{product_name} is currently out of stock. "
                "Consider replenishment and review whether the reorder level is adequate for recent demand."
            )
        elif ads is None or ads == 0:
            rec_text = (
                f"{product_name} has stock available but no recent sales recorded. "
                "Consider checking product placement and demand before adjusting stock levels."
            )
        elif days is not None and days < 3.0 or severity == "critical":
            rec_text = (
                f"Stock coverage is below 3 days at the recent sales rate. "
                f"Consider replenishing {product_name} urgently and review the reorder level."
            )
        elif days is not None and days < 5.0 or severity == "high":
            rec_text = (
                f"Stock coverage is below 5 days at the recent sales rate. "
                f"Consider replenishing {product_name} soon and review upcoming demand."
            )
        else:
            rec_text = (
                f"Stock coverage is below 7 days. "
                f"Monitor {product_name} closely and consider replenishment before stock becomes constrained."
            )

    elif itype == "overstock":
        rec_text = (
            f"{product_name} has inventory coverage above the configured target. "
            "Consider reducing upcoming replenishment and reviewing options such as promotion, bundling, or stock transfer."
        )

    elif itype == "non_moving":
        rec_text = (
            f"No units of {product_name} were sold during the last 30 days while inventory remains. "
            "Consider reviewing demand, pausing additional replenishment, and evaluating promotion, bundling, or transfer options."
        )

    elif itype == "slow_moving":
        rec_text = (
            f"Recent sales of {product_name} are very low relative to available inventory. "
            "Consider reviewing future replenishment and evaluating promotion, bundling, or stock transfer options."
        )

    elif itype == "sales_spike":
        rec_text = (
            f"Recent weekly sales of {product_name} are significantly above the historical baseline. "
            "Monitor inventory availability and review whether replenishment should be adjusted if the higher demand continues."
        )

    elif itype == "sales_drop":
        rec_text = (
            f"Recent weekly sales of {product_name} are significantly below the historical baseline. "
            "Investigate demand changes and review inventory conditions before changing replenishment."
        )

    elif itype == "new_activity":
        rec_text = (
            f"Recent sales activity for {product_name} appeared after a zero historical baseline. "
            "Monitor the product over the next period before making a major inventory change."
        )

    else:
        rec_text = f"Review operational conditions and inventory levels for {product_name}."

    # Build Evidence payload
    structured_evidence = build_recommendation_evidence({
        "primary_issue": prim,
        "secondary_signals": secondary_signals
    })

    return {
        "store_id": store_id,
        "store_name": store_name,
        "product_id": product_id,
        "product_name": product_name,
        "category": category,
        "issue_type": itype,
        "issue_label": ISSUE_LABEL_MAP.get(itype, itype),
        "priority_score": priority_score,
        "priority_label": priority_label,
        "recommendation_title": recommendation_title,
        "recommendation": rec_text,
        "evidence": structured_evidence,
        "impact": {
            "label": impact_info.get("label", "Financial Impact"),
            "value": impact_info.get("value")
        },
        "assumptions": structured_evidence.get("assumptions", []),
        "confidence": structured_evidence.get("confidence", "Medium"),
        "secondary_signals": secondary_signals
    }


def generate_recommendations_for_ranked_issues(
    ranked_issues: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Convert a list of Phase 6C ranked primary issue records into structured recommendation objects.
    """
    recommendations = []
    for issue in ranked_issues:
        rec = generate_recommendation(issue)
        recommendations.append(rec)
    return recommendations


def generate_top_recommendations(
    store_id: Optional[int] = None,
    as_of_date: Optional[str] = None,
    limit: int = 5,
    config: Optional[Dict[str, Any]] = None,
    candidates: Optional[List[Dict[str, Any]]] = None
) -> List[Dict[str, Any]]:
    """
    Fetch top Phase 6C ranked issues and convert them to top N structured recommendation objects.
    """
    ranked = get_ranked_issues(
        store_id=store_id,
        as_of_date=as_of_date,
        limit=limit,
        config=config,
        candidates=candidates
    )
    return generate_recommendations_for_ranked_issues(ranked)


def save_recommendation(rec_data: Dict[str, Any], conn=None) -> int:
    """
    Persist a single recommendation object to the SQLite `recommendations` table.
    Serializes evidence into JSON string using json.dumps(). Defaults manager_action to 'Review'.
    """
    should_close = False
    if conn is None:
        conn = get_connection()
        should_close = True

    timestamp = datetime.now().isoformat()
    store_id = rec_data.get("store_id")
    product_id = rec_data.get("product_id")
    issue_type = rec_data.get("issue_type")
    priority_score = rec_data.get("priority_score")
    recommendation_text = rec_data.get("recommendation")
    confidence = rec_data.get("confidence", "Medium")
    manager_action = rec_data.get("manager_action", "Review")

    # Serialize evidence dict cleanly
    evidence_json = json.dumps(rec_data.get("evidence", {}))

    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO recommendations (
        timestamp, store_id, product_id, issue_type, priority_score,
        evidence, recommendation, confidence, manager_action
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
    """, (
        timestamp, store_id, product_id, issue_type, priority_score,
        evidence_json, recommendation_text, confidence, manager_action
    ))

    rec_id = cursor.lastrowid
    if should_close:
        conn.commit()
        conn.close()

    return rec_id


def save_recommendations(rec_list: List[Dict[str, Any]]) -> List[int]:
    """
    Bulk save a list of recommendation objects to SQLite database.
    """
    conn = get_connection()
    rec_ids = []
    try:
        for rec in rec_list:
            rid = save_recommendation(rec, conn=conn)
            rec_ids.append(rid)
        conn.commit()
    finally:
        conn.close()
    return rec_ids


def get_saved_recommendations(
    store_id: Optional[int] = None,
    limit: Optional[int] = None
) -> List[Dict[str, Any]]:
    """
    Retrieve stored recommendation records from SQLite, ordered by timestamp DESC.
    Safely parses JSON evidence strings back into Python dictionaries.
    """
    conn = get_connection()
    cursor = conn.cursor()

    query = "SELECT recommendation_id, timestamp, store_id, product_id, issue_type, priority_score, evidence, recommendation, confidence, manager_action, action_timestamp, action_note FROM recommendations"
    params = []

    if store_id is not None:
        query += " WHERE store_id = ?"
        params.append(store_id)

    query += " ORDER BY recommendation_id DESC"

    if limit is not None and limit > 0:
        query += " LIMIT ?"
        params.append(limit)

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    saved = []
    for row in rows:
        r_dict = dict(row)
        # Parse JSON evidence string safely
        if r_dict.get("evidence"):
            try:
                r_dict["evidence"] = json.loads(r_dict["evidence"])
            except Exception:
                pass
        saved.append(r_dict)

    return saved


def update_manager_action(recommendation_id: int, action: str, note: Optional[str] = None) -> bool:
    if action not in ALLOWED_MANAGER_ACTIONS:
        raise ValueError(f"Invalid action: {action}. Must be one of {ALLOWED_MANAGER_ACTIONS}")
        
    conn = get_connection()
    cursor = conn.cursor()
    
    # Check if recommendation exists
    res = cursor.execute("SELECT recommendation_id FROM recommendations WHERE recommendation_id = ?", (recommendation_id,)).fetchone()
    if not res:
        conn.close()
        raise ValueError("Unknown recommendation_id")
        
    ts = datetime.now().isoformat()
    cursor.execute("""
        UPDATE recommendations 
        SET manager_action = ?, action_timestamp = ?, action_note = ? 
        WHERE recommendation_id = ?
    """, (action, ts, note, recommendation_id))
    
    conn.commit()
    conn.close()
    return True


def sync_current_recommendations(
    store_id: Optional[int] = None,
    as_of_date: Optional[str] = None,
    limit: int = 10,
    candidates: Optional[List[Dict[str, Any]]] = None
) -> List[int]:
    """
    Synchronize current top actionable recommendations into SQLite.
    Checks existing latest recommendations to prevent duplicate inserts for unchanged state.
    """
    current_recs = generate_top_recommendations(
        store_id=store_id,
        as_of_date=as_of_date,
        limit=limit,
        candidates=candidates
    )
    existing_recs = get_saved_recommendations(store_id=store_id, limit=50)

    # Build set of (store_id, product_id, issue_type, priority_score) for recent entries
    existing_set = set()
    for ex in existing_recs:
        existing_set.add((ex.get("store_id"), ex.get("product_id"), ex.get("issue_type"), ex.get("priority_score")))

    new_to_save = []
    for rec in current_recs:
        key = (rec.get("store_id"), rec.get("product_id"), rec.get("issue_type"), rec.get("priority_score"))
        if key not in existing_set:
            new_to_save.append(rec)

    if new_to_save:
        return save_recommendations(new_to_save)
    return []
