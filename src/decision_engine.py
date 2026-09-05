"""
StockSage AI - Decision Integration Layer (Phase 6C)

Orchestrates Phase 4 (Inventory Risks), Phase 5 (Sales Anomalies),
Phase 6A (Business Impact), and Phase 6B (Priority Scoring) into a single
deterministic, deduplicated, and ranked list of actionable retail issues
for "What Needs Attention Today?".
"""

import copy
import math
import json
from typing import Optional, Dict, Any, List, Set, Tuple
from datetime import datetime, date

from src.database import get_connection
from src.risk_engine import analyze_all_inventory_risks
from src.anomaly_detector import detect_all_sales_anomalies
from src.impact_engine import (
    estimate_stockout_revenue_at_risk,
    estimate_overstock_value,
    estimate_non_moving_value,
    estimate_slow_moving_value,
    estimate_spike_value,
    estimate_drop_value
)
from src.priority_engine import (
    score_issue_priority,
    get_priority_label,
    validate_priority_config,
    sort_scored_issues
)

# Human-Friendly Issue Label Mapping
ISSUE_LABEL_MAP = {
    "stockout_risk": "Stock-out Risk",
    "overstock": "Overstock",
    "non_moving": "Non-Moving",
    "slow_moving": "Slow-Moving",
    "sales_spike": "Sales Spike",
    "sales_drop": "Sales Drop",
    "new_activity": "New Activity"
}

# Issue Precedence Order for Deterministic Tie-Breaking
ISSUE_PRECEDENCE = {
    "stockout_risk": 1,
    "non_moving": 2,
    "overstock": 3,
    "sales_drop": 4,
    "slow_moving": 5,
    "sales_spike": 6,
    "new_activity": 7
}


def _to_json_serializable(obj: Any) -> Any:
    """
    Recursively convert numpy types, timestamps, and sets to standard Python primitives
    for easy JSON serialization.
    """
    if isinstance(obj, dict):
        return {k: _to_json_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple, set)):
        return [_to_json_serializable(item) for item in obj]
    elif hasattr(obj, "item") and callable(getattr(obj, "item")):
        # Handles numpy scalar types like np.int64, np.float64
        return obj.item()
    elif isinstance(obj, (datetime, date)):
        return obj.isoformat()
    elif isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return round(obj, 4)
    return obj


def estimate_issue_impact(
    candidate: Dict[str, Any],
    as_of_date: Optional[str] = None
) -> Dict[str, Any]:
    """
    Reuses Phase 6A financial formulas to compute monetary impact for a candidate issue.
    Reuses candidate evidence metrics when available to eliminate redundant database queries.
    """
    store_id = candidate["store_id"]
    product_id = candidate["product_id"]
    itype = candidate["issue_type"]
    ev = candidate.get("evidence", {})

    from src.impact_engine import (
        _get_product_price,
        estimate_stockout_revenue_at_risk,
        estimate_overstock_value,
        estimate_non_moving_value,
        estimate_slow_moving_value,
        estimate_spike_value,
        estimate_drop_value
    )

    selling_price = _get_product_price(product_id)
    if selling_price is None:
        return {
            "issue_type": itype,
            "impact_label": "Financial Impact",
            "impact_value": None,
            "inputs": {"store_id": store_id, "product_id": product_id},
            "formula": "None",
            "assumptions": ["Selling price is unavailable in database."]
        }

    if itype == "stockout_risk" and "average_daily_sales" in ev and "current_stock" in ev:
        ads = float(ev.get("average_daily_sales") or 0.0)
        stock = float(ev.get("current_stock") or 0.0)
        risk_horizon = 7
        expected_units = ads * float(risk_horizon)
        potential_shortage = max(expected_units - stock, 0.0)
        if ads == 0.0:
            potential_shortage = 0.0
        impact_value = round(potential_shortage * selling_price, 2)
        return {
            "issue_type": "stockout_risk",
            "impact_label": "Estimated Revenue at Risk",
            "impact_value": impact_value,
            "inputs": {
                "store_id": store_id,
                "product_id": product_id,
                "average_daily_sales": round(ads, 4),
                "current_stock": int(stock),
                "selling_price": selling_price,
                "risk_horizon_days": risk_horizon,
                "expected_units": round(expected_units, 2),
                "potential_shortage_units": round(potential_shortage, 2)
            },
            "formula": f"max(({ads:.4f} ADS * {risk_horizon} days) - {int(stock)} stock, 0) * ₹{selling_price:.2f}",
            "assumptions": [
                f"Average daily sales rate ({ads:.2f} units/day) continues over next {risk_horizon} days.",
                "Represents top-line estimated unrealized gross sales revenue at risk, not net profit loss.",
                f"Selling price: ₹{selling_price:.2f}"
            ]
        }

    elif itype == "overstock" and "average_daily_sales" in ev and "current_stock" in ev:
        ads = float(ev.get("average_daily_sales") or 0.0)
        stock = float(ev.get("current_stock") or 0.0)
        target_days = 30.0
        target_stock = ads * target_days
        excess_units = max(stock - target_stock, 0.0)
        impact_value = round(excess_units * selling_price, 2)
        return {
            "issue_type": "overstock",
            "impact_label": "Estimated Retail Value of Excess Stock",
            "impact_value": impact_value,
            "inputs": {
                "store_id": store_id,
                "product_id": product_id,
                "average_daily_sales": round(ads, 4),
                "current_stock": int(stock),
                "selling_price": selling_price,
                "target_coverage_days": target_days,
                "target_stock": round(target_stock, 2),
                "excess_units": round(excess_units, 2)
            },
            "formula": f"max({int(stock)} stock - ({ads:.4f} ADS * {target_days} days), 0) * ₹{selling_price:.2f}",
            "assumptions": [
                f"Target coverage threshold is set to {target_days} calendar days.",
                "Uses selling price because product cost data is unavailable. Do not treat as profit lost.",
                f"Selling price: ₹{selling_price:.2f}"
            ]
        }

    elif itype == "non_moving" and "current_stock" in ev:
        stock = float(ev.get("current_stock") or 0.0)
        impact_value = round(stock * selling_price, 2)
        return {
            "issue_type": "non_moving",
            "impact_label": "Retail Value of Non-Moving Stock",
            "impact_value": impact_value,
            "inputs": {
                "store_id": store_id,
                "product_id": product_id,
                "current_stock": int(stock),
                "selling_price": selling_price
            },
            "formula": f"{int(stock)} stock * ₹{selling_price:.2f}",
            "assumptions": [
                "0 units sold in the last 30 calendar days.",
                "Uses selling price because product cost data is unavailable.",
                f"Selling price: ₹{selling_price:.2f}"
            ]
        }

    elif itype == "slow_moving" and "units_sold_30d" in ev and "current_stock" in ev:
        stock = float(ev.get("current_stock") or 0.0)
        units_30d = float(ev.get("units_sold_30d") or 0.0)
        ads = units_30d / 30.0
        target_days = 30.0
        target_stock = ads * target_days
        excess_units = max(stock - target_stock, 0.0)
        current_retail_val = round(stock * selling_price, 2)
        excess_retail_val = round(excess_units * selling_price, 2)
        impact_value = excess_retail_val if (ads > 0 and excess_units > 0) else current_retail_val
        return {
            "issue_type": "slow_moving",
            "impact_label": "Retail Value of Slow-Moving Stock",
            "impact_value": impact_value,
            "current_inventory_retail_value": current_retail_val,
            "estimated_excess_retail_value": excess_retail_val,
            "inputs": {
                "store_id": store_id,
                "product_id": product_id,
                "average_daily_sales": round(ads, 4),
                "current_stock": int(stock),
                "selling_price": selling_price,
                "target_coverage_days": target_days,
                "excess_units": round(excess_units, 2)
            },
            "formula": f"Total: {int(stock)} stock * ₹{selling_price:.2f} (Excess: max({int(stock)} - ({ads:.4f} * {target_days}), 0) * ₹{selling_price:.2f})",
            "assumptions": [
                "Slow sales rate observed (1-5 units in last 30 days).",
                "Uses selling price because product cost data is unavailable.",
                f"Selling price: ₹{selling_price:.2f}"
            ]
        }

    elif itype == "sales_spike" and "recent_units" in ev and "baseline_weekly_units" in ev:
        rec_units = float(ev.get("recent_units") or 0.0)
        base_units = float(ev.get("baseline_weekly_units") or 0.0)
        incremental_units = max(rec_units - base_units, 0.0)
        impact_value = round(incremental_units * selling_price, 2)
        return {
            "issue_type": "sales_spike",
            "impact_label": "Estimated Incremental Sales Value",
            "impact_value": impact_value,
            "inputs": {
                "store_id": store_id,
                "product_id": product_id,
                "recent_weekly_units": rec_units,
                "baseline_weekly_units": round(base_units, 2),
                "incremental_units": round(incremental_units, 2),
                "selling_price": selling_price
            },
            "formula": f"max({rec_units} recent - {base_units:.2f} baseline, 0) * ₹{selling_price:.2f}",
            "assumptions": [
                "Represents recent sales uplift above the 6-week historical weekly baseline.",
                "Observed sales value indicator, not forward revenue risk.",
                f"Selling price: ₹{selling_price:.2f}"
            ]
        }

    elif itype == "sales_drop" and "recent_units" in ev and "baseline_weekly_units" in ev:
        rec_units = float(ev.get("recent_units") or 0.0)
        base_units = float(ev.get("baseline_weekly_units") or 0.0)
        gap_units = max(base_units - rec_units, 0.0)
        impact_value = round(gap_units * selling_price, 2)
        return {
            "issue_type": "sales_drop",
            "impact_label": "Estimated Sales Value Gap vs Baseline",
            "impact_value": impact_value,
            "inputs": {
                "store_id": store_id,
                "product_id": product_id,
                "recent_weekly_units": rec_units,
                "baseline_weekly_units": round(base_units, 2),
                "gap_units": round(gap_units, 2),
                "selling_price": selling_price
            },
            "formula": f"max({base_units:.2f} baseline - {rec_units} recent, 0) * ₹{selling_price:.2f}",
            "assumptions": [
                "Represents recent sales gap below the 6-week historical weekly baseline.",
                "Observed sales gap indicator, not net profit loss.",
                f"Selling price: ₹{selling_price:.2f}"
            ]
        }

    # Fallback to direct Phase 6A functions
    if itype == "stockout_risk":
        return estimate_stockout_revenue_at_risk(store_id=store_id, product_id=product_id, as_of_date=as_of_date)
    elif itype == "overstock":
        return estimate_overstock_value(store_id=store_id, product_id=product_id, as_of_date=as_of_date)
    elif itype == "non_moving":
        return estimate_non_moving_value(store_id=store_id, product_id=product_id, as_of_date=as_of_date)
    elif itype == "slow_moving":
        return estimate_slow_moving_value(store_id=store_id, product_id=product_id, as_of_date=as_of_date)
    elif itype == "sales_spike":
        return estimate_spike_value(store_id=store_id, product_id=product_id, as_of_date=as_of_date)
    elif itype == "sales_drop":
        return estimate_drop_value(store_id=store_id, product_id=product_id, as_of_date=as_of_date)
    elif itype == "new_activity":
        return {
            "issue_type": "new_activity",
            "impact_label": "Estimated Incremental Sales Value",
            "impact_value": 0.0,
            "inputs": {"store_id": store_id, "product_id": product_id},
            "formula": "None",
            "assumptions": ["New product activity detected with zero baseline."]
        }

    return {
        "issue_type": itype,
        "impact_label": "Financial Impact",
        "impact_value": 0.0,
        "inputs": {"store_id": store_id, "product_id": product_id},
        "formula": "None",
        "assumptions": ["Impact function unavailable for issue type."]
    }


def get_all_issue_candidates(
    store_id: Optional[int] = None,
    as_of_date: Optional[str] = None,
    config: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """
    Collect all actionable inventory risk and sales anomaly candidates across stores and products.
    Enriches every candidate with Phase 6A financial impact and Phase 6B priority scoring.
    """
    if as_of_date is None:
        try:
            from src.sales_engine import get_dataset_date_range
            as_of_date = get_dataset_date_range()["end_date"]
        except Exception:
            pass

    candidates = []

    # 1. Collect Phase 4 Inventory Risks
    inv_risks = analyze_all_inventory_risks(store_id=store_id, as_of_date=as_of_date)
    for item in inv_risks:
        st_id = item["store_id"]
        st_name = item.get("store_name", f"Store {st_id}")
        pr_id = item["product_id"]
        pr_name = item["product_name"]
        cat = item.get("category", "")
        days_rem = item.get("days_of_stock_remaining")

        # Stockout Risk Candidate
        if item.get("stockout_status") == "risk" and item.get("stockout_severity") in ["critical", "high", "medium"]:
            candidates.append({
                "store_id": st_id,
                "store_name": st_name,
                "product_id": pr_id,
                "product_name": pr_name,
                "category": cat,
                "issue_type": "stockout_risk",
                "issue_label": ISSUE_LABEL_MAP["stockout_risk"],
                "source": "inventory",
                "severity": item.get("stockout_severity"),
                "days_of_stock_remaining": days_rem,
                "evidence": {
                    "current_stock": item.get("current_stock"),
                    "reorder_level": item.get("reorder_level"),
                    "reorder_gap": item.get("reorder_gap"),
                    "units_sold_30d": item.get("units_sold_30d"),
                    "average_daily_sales": item.get("average_daily_sales_30d"),
                    "days_of_stock_remaining": days_rem
                }
            })

        # Non-Moving Candidate
        if item.get("is_non_moving"):
            candidates.append({
                "store_id": st_id,
                "store_name": st_name,
                "product_id": pr_id,
                "product_name": pr_name,
                "category": cat,
                "issue_type": "non_moving",
                "issue_label": ISSUE_LABEL_MAP["non_moving"],
                "source": "inventory",
                "severity": "high",
                "evidence": {
                    "current_stock": item.get("current_stock"),
                    "units_sold_30d": item.get("units_sold_30d", 0)
                }
            })

        # Overstock Candidate
        if item.get("is_overstock"):
            candidates.append({
                "store_id": st_id,
                "store_name": st_name,
                "product_id": pr_id,
                "product_name": pr_name,
                "category": cat,
                "issue_type": "overstock",
                "issue_label": ISSUE_LABEL_MAP["overstock"],
                "source": "inventory",
                "severity": "moderate",
                "is_overstock": True,
                "days_of_stock_remaining": days_rem,
                "coverage_days": days_rem,
                "evidence": {
                    "current_stock": item.get("current_stock"),
                    "average_daily_sales": item.get("average_daily_sales_30d"),
                    "days_of_stock_remaining": days_rem
                }
            })

        # Slow-Moving Candidate
        if item.get("is_slow_moving") and not item.get("is_non_moving"):
            candidates.append({
                "store_id": st_id,
                "store_name": st_name,
                "product_id": pr_id,
                "product_name": pr_name,
                "category": cat,
                "issue_type": "slow_moving",
                "issue_label": ISSUE_LABEL_MAP["slow_moving"],
                "source": "inventory",
                "severity": "moderate",
                "evidence": {
                    "current_stock": item.get("current_stock"),
                    "units_sold_30d": item.get("units_sold_30d")
                }
            })

    # 2. Collect Phase 5 Sales Anomalies
    sales_anomalies = detect_all_sales_anomalies(store_id=store_id, as_of_date=as_of_date)
    for anom in sales_anomalies:
        st_id = anom["store_id"]
        pr_id = anom["product_id"]
        pr_name = anom["product_name"]
        cat = anom.get("category", "")
        st_name = anom.get("store_name", f"Store {st_id}")

        cls = anom.get("classification", {})
        anom_type = cls.get("anomaly_type")

        if anom_type in ["spike", "drop", "new_activity"]:
            if anom_type == "spike":
                itype = "sales_spike"
            elif anom_type == "drop":
                itype = "sales_drop"
            else:
                itype = "new_activity"

            chg = anom.get("change", {})
            rec = anom.get("recent_period", {})
            base = anom.get("historical_baseline", {})

            candidates.append({
                "store_id": st_id,
                "store_name": st_name,
                "product_id": pr_id,
                "product_name": pr_name,
                "category": cat,
                "issue_type": itype,
                "issue_label": ISSUE_LABEL_MAP[itype],
                "source": "sales_anomaly",
                "anomaly_type": anom_type,
                "percentage_change": chg.get("percentage_change"),
                "available_baseline_weeks": base.get("baseline_weeks", 6),
                "evidence": {
                    "recent_units": rec.get("units_sold"),
                    "baseline_weekly_units": base.get("mean_weekly_units"),
                    "absolute_units_change": chg.get("absolute_units_change"),
                    "percentage_change": chg.get("percentage_change"),
                    "baseline_weeks": base.get("baseline_weeks")
                }
            })

    # 3. Enrich all candidates with Phase 6A Impact and Phase 6B Priority
    enriched_candidates = []
    for cand in candidates:
        imp_res = estimate_issue_impact(cand, as_of_date=as_of_date)
        pri_res = score_issue_priority(cand, impact_result=imp_res, config=config)

        if not pri_res.get("actionable", True):
            continue

        c_enriched = copy.deepcopy(cand)
        c_enriched["impact"] = {
            "label": imp_res.get("impact_label", "Financial Impact"),
            "value": imp_res.get("impact_value"),
            "formula": imp_res.get("formula", ""),
            "assumptions": imp_res.get("assumptions", [])
        }
        c_enriched["priority"] = {
            "score": pri_res.get("priority_score"),
            "raw_score": pri_res.get("raw_priority_score"),
            "label": pri_res.get("priority_label"),
            "score_breakdown": pri_res.get("score_breakdown"),
            "priority_factors": pri_res.get("priority_factors")
        }
        enriched_candidates.append(c_enriched)

    return enriched_candidates


def select_primary_issue_for_product(
    candidates: List[Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    """
    Given all candidate issues for a single store-product, select 1 primary issue
    and retain remaining actionable candidate issues as secondary_signals.
    """
    if not candidates:
        return None

    def candidate_sort_key(c: Dict[str, Any]):
        pri = c.get("priority", {})
        raw_score = pri.get("raw_score", 0.0)
        imp_val = c.get("impact", {}).get("value")
        if imp_val is None:
            imp_val = 0.0
        urg_score = pri.get("score_breakdown", {}).get("urgency", {}).get("score", 0.0)
        prec = ISSUE_PRECEDENCE.get(c.get("issue_type"), 99)
        return (-raw_score, -imp_val, -urg_score, prec)

    sorted_cands = sorted(candidates, key=candidate_sort_key)
    primary = sorted_cands[0]
    secondaries_raw = sorted_cands[1:]

    secondary_signals = []
    for s in secondaries_raw:
        secondary_signals.append({
            "issue_type": s["issue_type"],
            "issue_label": s.get("issue_label", ISSUE_LABEL_MAP.get(s["issue_type"], s["issue_type"])),
            "priority_score": s["priority"]["score"],
            "priority_label": s["priority"]["label"],
            "impact_label": s["impact"]["label"],
            "impact_value": s["impact"]["value"],
            "evidence": s.get("evidence", {})
        })

    return {
        "store_id": primary["store_id"],
        "store_name": primary["store_name"],
        "product_id": primary["product_id"],
        "product_name": primary["product_name"],
        "category": primary["category"],
        "primary_issue": primary,
        "secondary_signals": secondary_signals
    }


def format_key_evidence(primary_issue: Dict[str, Any]) -> Dict[str, Any]:
    """
    Format concise structured evidence for dashboard and top-attention consumption.
    """
    ev = primary_issue.get("evidence", {})
    itype = primary_issue.get("issue_type")

    if itype == "stockout_risk":
        return {
            "current_stock": ev.get("current_stock"),
            "average_daily_sales": ev.get("average_daily_sales"),
            "days_of_stock_remaining": ev.get("days_of_stock_remaining"),
            "reorder_level": ev.get("reorder_level"),
            "reorder_gap": ev.get("reorder_gap")
        }
    elif itype == "overstock":
        return {
            "current_stock": ev.get("current_stock"),
            "average_daily_sales": ev.get("average_daily_sales"),
            "days_of_stock_remaining": ev.get("days_of_stock_remaining")
        }
    elif itype == "non_moving":
        return {
            "current_stock": ev.get("current_stock"),
            "units_sold_30d": ev.get("units_sold_30d", 0)
        }
    elif itype == "slow_moving":
        return {
            "current_stock": ev.get("current_stock"),
            "units_sold_30d": ev.get("units_sold_30d")
        }
    elif itype in ["sales_spike", "sales_drop"]:
        return {
            "recent_units": ev.get("recent_units"),
            "baseline_weekly_units": ev.get("baseline_weekly_units"),
            "percentage_change": ev.get("percentage_change")
        }

    return ev


def get_ranked_issues(
    store_id: Optional[int] = None,
    as_of_date: Optional[str] = None,
    limit: Optional[int] = None,
    config: Optional[Dict[str, Any]] = None,
    candidates: Optional[List[Dict[str, Any]]] = None
) -> List[Dict[str, Any]]:
    """
    Generate all actionable candidates, deduplicate by store-product into primary and secondary
    issues, and return globally ranked primary issue records.
    """
    if limit is not None and limit <= 0:
        raise ValueError("Limit must be greater than 0.")

    if candidates is None:
        all_candidates = get_all_issue_candidates(store_id=store_id, as_of_date=as_of_date, config=config)
    else:
        if store_id is not None:
            all_candidates = [c for c in candidates if c.get("store_id") == store_id]
        else:
            all_candidates = candidates

    # Group by (store_id, product_id)
    grouped: Dict[Tuple[int, int], List[Dict[str, Any]]] = {}
    for cand in all_candidates:
        key = (cand["store_id"], cand["product_id"])
        grouped.setdefault(key, []).append(cand)

    primary_records = []
    for key, cands in grouped.items():
        record = select_primary_issue_for_product(cands)
        if record:
            primary_records.append(record)

    # Global sort across all primary records
    def global_sort_key(rec: Dict[str, Any]):
        prim = rec["primary_issue"]
        pri = prim.get("priority", {})
        raw_score = pri.get("raw_score", 0.0)
        imp_val = prim.get("impact", {}).get("value")
        if imp_val is None:
            imp_val = 0.0
        urg_score = pri.get("score_breakdown", {}).get("urgency", {}).get("score", 0.0)
        prod_id = rec.get("product_id", 0)
        st_id = rec.get("store_id", 0)
        return (-raw_score, -imp_val, -urg_score, prod_id, st_id)

    sorted_records = sorted(primary_records, key=global_sort_key)

    if limit is not None:
        sorted_records = sorted_records[:limit]

    return _to_json_serializable(sorted_records)


def get_top_attention_items(
    store_id: Optional[int] = None,
    as_of_date: Optional[str] = None,
    limit: int = 5,
    config: Optional[Dict[str, Any]] = None,
    candidates: Optional[List[Dict[str, Any]]] = None
) -> List[Dict[str, Any]]:
    """
    Return top N ranked attention items formatted for backend decision integration
    and frontend dashboard consumption ("What Needs Attention Today?").
    """
    if limit <= 0:
        raise ValueError("Limit must be greater than 0.")

    ranked = get_ranked_issues(store_id=store_id, as_of_date=as_of_date, limit=limit, config=config, candidates=candidates)

    top_items = []
    for idx, rec in enumerate(ranked):
        prim = rec["primary_issue"]
        top_items.append({
            "rank": idx + 1,
            "store_id": rec["store_id"],
            "store_name": rec["store_name"],
            "product_id": rec["product_id"],
            "product_name": rec["product_name"],
            "category": rec["category"],
            "issue_type": prim["issue_type"],
            "issue_label": prim.get("issue_label", ISSUE_LABEL_MAP.get(prim["issue_type"], prim["issue_type"])),
            "priority_score": prim["priority"]["score"],
            "priority_label": prim["priority"]["label"],
            "impact_label": prim["impact"]["label"],
            "impact_value": prim["impact"]["value"],
            "key_evidence": format_key_evidence(prim),
            "secondary_signals": rec.get("secondary_signals", [])
        })

    return _to_json_serializable(top_items)


def get_business_impact_summary(
    store_id: Optional[int] = None,
    as_of_date: Optional[str] = None,
    candidates: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, float]:
    """
    Return separate total financial impact metrics across all actionable candidate issues.
    De-duplicates metrics per (store_id, product_id, metric) to prevent double counting.
    """
    if candidates is None:
        all_cands = get_all_issue_candidates(store_id=store_id, as_of_date=as_of_date)
    else:
        if store_id is not None:
            all_cands = [c for c in candidates if c.get("store_id") == store_id]
        else:
            all_cands = candidates

    totals = {
        "estimated_revenue_at_risk": 0.0,
        "estimated_excess_retail_value": 0.0,
        "non_moving_retail_value": 0.0,
        "slow_moving_retail_value": 0.0,
        "estimated_sales_value_gap": 0.0,
        "estimated_incremental_sales_value": 0.0
    }

    seen_metrics: Set[Tuple[int, int, str]] = set()

    for cand in all_cands:
        st_id = cand["store_id"]
        pr_id = cand["product_id"]
        itype = cand["issue_type"]
        imp_val = cand.get("impact", {}).get("value")

        if imp_val is None or imp_val <= 0:
            continue

        dedup_key = (st_id, pr_id, itype)
        if dedup_key in seen_metrics:
            continue
        seen_metrics.add(dedup_key)

        if itype == "stockout_risk":
            totals["estimated_revenue_at_risk"] += float(imp_val)
        elif itype == "overstock":
            totals["estimated_excess_retail_value"] += float(imp_val)
        elif itype == "non_moving":
            totals["non_moving_retail_value"] += float(imp_val)
        elif itype == "slow_moving":
            totals["slow_moving_retail_value"] += float(imp_val)
        elif itype == "sales_drop":
            totals["estimated_sales_value_gap"] += float(imp_val)
        elif itype == "sales_spike":
            totals["estimated_incremental_sales_value"] += float(imp_val)

    # Round totals
    rounded_totals = {k: round(v, 2) for k, v in totals.items()}
    return _to_json_serializable(rounded_totals)


def get_issue_counts(
    store_id: Optional[int] = None,
    as_of_date: Optional[str] = None,
    candidates: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    Return counts of actionable issues by category across candidate issues and primary issues.
    """
    if candidates is None:
        all_cands = get_all_issue_candidates(store_id=store_id, as_of_date=as_of_date)
    else:
        if store_id is not None:
            all_cands = [c for c in candidates if c.get("store_id") == store_id]
        else:
            all_cands = candidates

    ranked = get_ranked_issues(store_id=store_id, as_of_date=as_of_date, candidates=all_cands)

    candidate_counts = {k: 0 for k in ISSUE_LABEL_MAP.keys()}
    for cand in all_cands:
        itype = cand["issue_type"]
        if itype in candidate_counts:
            candidate_counts[itype] += 1

    primary_counts = {k: 0 for k in ISSUE_LABEL_MAP.keys()}
    for rec in ranked:
        itype = rec["primary_issue"]["issue_type"]
        if itype in primary_counts:
            primary_counts[itype] += 1

    return _to_json_serializable({
        "candidate_issue_counts": candidate_counts,
        "primary_issue_counts": primary_counts,
        "total_actionable_candidates": len(all_cands),
        "total_actionable_products": len(ranked)
    })


def get_decision_summary(
    store_id: Optional[int] = None,
    as_of_date: Optional[str] = None,
    config: Optional[Dict[str, Any]] = None,
    candidates: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    High-level decision summary combining top attention items, priority breakdown,
    issue counts, and separate business impact totals.
    """
    if candidates is None:
        all_cands = get_all_issue_candidates(store_id=store_id, as_of_date=as_of_date, config=config)
    else:
        if store_id is not None:
            all_cands = [c for c in candidates if c.get("store_id") == store_id]
        else:
            all_cands = candidates

    ranked = get_ranked_issues(store_id=store_id, as_of_date=as_of_date, config=config, candidates=all_cands)
    top_5 = get_top_attention_items(store_id=store_id, as_of_date=as_of_date, limit=5, config=config, candidates=all_cands)
    impact_summary = get_business_impact_summary(store_id=store_id, as_of_date=as_of_date, candidates=all_cands)
    counts = get_issue_counts(store_id=store_id, as_of_date=as_of_date, candidates=all_cands)

    priority_distribution = {
        "Critical Priority": 0,
        "High Priority": 0,
        "Medium Priority": 0,
        "Low Priority": 0,
        "Monitor": 0
    }

    for rec in ranked:
        lbl = rec["primary_issue"]["priority"]["label"]
        if lbl in priority_distribution:
            priority_distribution[lbl] += 1

    return _to_json_serializable({
        "total_actionable_products": len(ranked),
        "priority_distribution": priority_distribution,
        "top_attention": top_5,
        "issue_counts": counts,
        "business_impact": impact_summary
    })
