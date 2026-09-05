"""
StockSage AI - Business Impact Engine (Phase 6A)

Provides truthful financial impact estimates for retail inventory and sales issues.
Uses actual selling price from SQLite database.
Does NOT assume product cost, profit margin, or holding cost as cost data is unavailable.
"""

import math
from typing import Optional, Dict, Any, List
from src.database import get_connection
from src.sales_engine import get_average_daily_sales
from src.anomaly_detector import detect_product_anomaly


def _normalize_store_product(arg1: int, arg2: int, db_path: Optional[str] = None):
    """
    Helper to accept (store_id, product_id) or (product_id, store_id) flexibly.
    Returns (store_id, product_id).
    """
    try:
        conn = get_connection(db_path)
        cursor = conn.cursor()
        
        # Check if arg1 is store_id and arg2 is product_id
        cursor.execute("SELECT 1 FROM stores WHERE store_id = ?;", (arg1,))
        is_arg1_store = cursor.fetchone() is not None
        
        cursor.execute("SELECT 1 FROM products WHERE product_id = ?;", (arg2,))
        is_arg2_product = cursor.fetchone() is not None
        
        if is_arg1_store and is_arg2_product:
            conn.close()
            return arg1, arg2
            
        # Check if arg1 is product_id and arg2 is store_id
        cursor.execute("SELECT 1 FROM products WHERE product_id = ?;", (arg1,))
        is_arg1_product = cursor.fetchone() is not None
        
        cursor.execute("SELECT 1 FROM stores WHERE store_id = ?;", (arg2,))
        is_arg2_store = cursor.fetchone() is not None
        
        conn.close()
        if is_arg1_product and is_arg2_store:
            return arg2, arg1
    except Exception:
        pass
        
    return arg1, arg2


def _get_product_price(product_id: int, db_path: Optional[str] = None) -> Optional[float]:
    """
    Fetch product selling price from SQLite database.
    Returns None if product missing or price is null/invalid.
    """
    try:
        conn = get_connection(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT selling_price FROM products WHERE product_id = ?;", (product_id,))
        row = cursor.fetchone()
        conn.close()
        if not row or row["selling_price"] is None:
            return None
        price = float(row["selling_price"])
        if price <= 0:
            return None
        return price
    except Exception:
        return None


def _get_current_stock(store_id: int, product_id: int, db_path: Optional[str] = None) -> int:
    """Fetch current stock from inventory table."""
    try:
        conn = get_connection(db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT current_stock FROM inventory WHERE store_id = ? AND product_id = ?;",
            (store_id, product_id)
        )
        row = cursor.fetchone()
        conn.close()
        if not row:
            return 0
        return int(row["current_stock"])
    except Exception:
        return 0


def estimate_stockout_revenue_at_risk(
    store_id: int,
    product_id: int,
    db_path: Optional[str] = None,
    risk_horizon_days: int = 7,
    as_of_date: Optional[str] = None
) -> Dict[str, Any]:
    """
    Estimate revenue at risk for potential stockouts over a forward risk horizon.
    Formula:
      expected_units = ADS * risk_horizon_days
      potential_shortage_units = max(expected_units - current_stock, 0)
      estimated_revenue_at_risk = potential_shortage_units * selling_price
    """
    store_id, product_id = _normalize_store_product(store_id, product_id, db_path)
    selling_price = _get_product_price(product_id, db_path)
    current_stock = _get_current_stock(store_id, product_id, db_path)

    if selling_price is None:
        return {
            "issue_type": "stockout_risk",
            "impact_label": "Estimated Revenue at Risk",
            "impact_value": None,
            "inputs": {
                "store_id": store_id,
                "product_id": product_id,
                "average_daily_sales": 0.0,
                "current_stock": current_stock,
                "selling_price": None,
                "risk_horizon_days": risk_horizon_days,
                "expected_units": 0.0,
                "potential_shortage_units": 0.0
            },
            "formula": "None",
            "assumptions": [
                "Selling price is unavailable or invalid in database; impact value cannot be computed."
            ]
        }

    try:
        ads_info = get_average_daily_sales(product_id, store_id=store_id, window_days=30, as_of_date=as_of_date, db_path=db_path)
        ads = float(ads_info["average_daily_sales"])
    except Exception:
        ads = 0.0

    expected_units = ads * float(risk_horizon_days)
    potential_shortage_units = max(expected_units - float(current_stock), 0.0)
    impact_value = round(potential_shortage_units * selling_price, 2)

    if ads == 0.0:
        potential_shortage_units = 0.0
        impact_value = 0.0

    formula_str = (
        f"max(({ads:.4f} ADS * {risk_horizon_days} days) - {current_stock} stock, 0) * ₹{selling_price:.2f}"
    )

    return {
        "issue_type": "stockout_risk",
        "impact_label": "Estimated Revenue at Risk",
        "impact_value": impact_value,
        "inputs": {
            "store_id": store_id,
            "product_id": product_id,
            "average_daily_sales": round(ads, 4),
            "current_stock": current_stock,
            "selling_price": selling_price,
            "risk_horizon_days": risk_horizon_days,
            "expected_units": round(expected_units, 2),
            "potential_shortage_units": round(potential_shortage_units, 2)
        },
        "formula": formula_str,
        "assumptions": [
            f"Average daily sales rate ({ads:.2f} units/day) continues over next {risk_horizon_days} days.",
            "Represents top-line estimated unrealized gross sales revenue at risk, not net profit loss.",
            f"Selling price: ₹{selling_price:.2f}"
        ]
    }


def estimate_overstock_value(
    store_id: int,
    product_id: int,
    db_path: Optional[str] = None,
    target_coverage_days: float = 30.0,
    as_of_date: Optional[str] = None
) -> Dict[str, Any]:
    """
    Estimate retail value of excess inventory above target coverage days.
    Formula:
      target_stock = ADS * target_coverage_days
      excess_units = max(current_stock - target_stock, 0)
      estimated_excess_retail_value = excess_units * selling_price
    """
    store_id, product_id = _normalize_store_product(store_id, product_id, db_path)
    selling_price = _get_product_price(product_id, db_path)
    current_stock = _get_current_stock(store_id, product_id, db_path)

    if selling_price is None:
        return {
            "issue_type": "overstock",
            "impact_label": "Estimated Retail Value of Excess Stock",
            "impact_value": None,
            "inputs": {
                "store_id": store_id,
                "product_id": product_id,
                "average_daily_sales": 0.0,
                "current_stock": current_stock,
                "selling_price": None,
                "target_coverage_days": target_coverage_days,
                "target_stock": 0.0,
                "excess_units": 0.0
            },
            "formula": "None",
            "assumptions": [
                "Selling price is unavailable or invalid in database; impact value cannot be computed."
            ]
        }

    try:
        ads_info = get_average_daily_sales(product_id, store_id=store_id, window_days=30, as_of_date=as_of_date, db_path=db_path)
        ads = float(ads_info["average_daily_sales"])
    except Exception:
        ads = 0.0

    target_stock = ads * float(target_coverage_days)
    excess_units = max(float(current_stock) - target_stock, 0.0)
    impact_value = round(excess_units * selling_price, 2)

    formula_str = (
        f"max({current_stock} stock - ({ads:.4f} ADS * {target_coverage_days} days), 0) * ₹{selling_price:.2f}"
    )

    return {
        "issue_type": "overstock",
        "impact_label": "Estimated Retail Value of Excess Stock",
        "impact_value": impact_value,
        "inputs": {
            "store_id": store_id,
            "product_id": product_id,
            "average_daily_sales": round(ads, 4),
            "current_stock": current_stock,
            "selling_price": selling_price,
            "target_coverage_days": target_coverage_days,
            "target_stock": round(target_stock, 2),
            "excess_units": round(excess_units, 2)
        },
        "formula": formula_str,
        "assumptions": [
            f"Target coverage threshold is set to {target_coverage_days} calendar days.",
            "Uses selling price because product cost data is unavailable. Do not treat as profit lost.",
            f"Selling price: ₹{selling_price:.2f}"
        ]
    }


def estimate_non_moving_value(
    store_id: int,
    product_id: int,
    db_path: Optional[str] = None,
    as_of_date: Optional[str] = None
) -> Dict[str, Any]:
    """
    Estimate total retail value of non-moving inventory (0 sales in 30 days).
    Formula: current_stock * selling_price
    """
    store_id, product_id = _normalize_store_product(store_id, product_id, db_path)
    selling_price = _get_product_price(product_id, db_path)
    current_stock = _get_current_stock(store_id, product_id, db_path)

    if selling_price is None:
        return {
            "issue_type": "non_moving",
            "impact_label": "Retail Value of Non-Moving Stock",
            "impact_value": None,
            "inputs": {
                "store_id": store_id,
                "product_id": product_id,
                "current_stock": current_stock,
                "selling_price": None
            },
            "formula": "None",
            "assumptions": [
                "Selling price is unavailable or invalid in database; impact value cannot be computed."
            ]
        }

    impact_value = round(float(current_stock) * selling_price, 2)

    return {
        "issue_type": "non_moving",
        "impact_label": "Retail Value of Non-Moving Stock",
        "impact_value": impact_value,
        "inputs": {
            "store_id": store_id,
            "product_id": product_id,
            "current_stock": current_stock,
            "selling_price": selling_price
        },
        "formula": f"{current_stock} stock * ₹{selling_price:.2f}",
        "assumptions": [
            "0 units sold in the last 30 calendar days.",
            "Uses selling price because product cost data is unavailable.",
            f"Selling price: ₹{selling_price:.2f}"
        ]
    }


def estimate_slow_moving_value(
    store_id: int,
    product_id: int,
    db_path: Optional[str] = None,
    target_coverage_days: float = 30.0,
    as_of_date: Optional[str] = None
) -> Dict[str, Any]:
    """
    Estimate retail value of slow-moving stock (1-5 units sold in 30 days).
    Returns total current inventory retail value and excess retail value above target.
    """
    store_id, product_id = _normalize_store_product(store_id, product_id, db_path)
    selling_price = _get_product_price(product_id, db_path)
    current_stock = _get_current_stock(store_id, product_id, db_path)

    if selling_price is None:
        return {
            "issue_type": "slow_moving",
            "impact_label": "Retail Value of Slow-Moving Stock",
            "impact_value": None,
            "current_inventory_retail_value": None,
            "estimated_excess_retail_value": None,
            "inputs": {
                "store_id": store_id,
                "product_id": product_id,
                "average_daily_sales": 0.0,
                "current_stock": current_stock,
                "selling_price": None,
                "target_coverage_days": target_coverage_days,
                "excess_units": 0.0
            },
            "formula": "None",
            "assumptions": [
                "Selling price is unavailable or invalid in database; impact value cannot be computed."
            ]
        }

    try:
        ads_info = get_average_daily_sales(product_id, store_id=store_id, window_days=30, as_of_date=as_of_date, db_path=db_path)
        ads = float(ads_info["average_daily_sales"])
    except Exception:
        ads = 0.0

    target_stock = ads * float(target_coverage_days)
    excess_units = max(float(current_stock) - target_stock, 0.0)

    current_inventory_retail_value = round(float(current_stock) * selling_price, 2)
    estimated_excess_retail_value = round(excess_units * selling_price, 2)
    impact_value = estimated_excess_retail_value if (ads > 0 and excess_units > 0) else current_inventory_retail_value

    formula_str = (
        f"Total: {current_stock} stock * ₹{selling_price:.2f} "
        f"(Excess: max({current_stock} - ({ads:.4f} * {target_coverage_days}), 0) * ₹{selling_price:.2f})"
    )

    return {
        "issue_type": "slow_moving",
        "impact_label": "Retail Value of Slow-Moving Stock",
        "impact_value": impact_value,
        "current_inventory_retail_value": current_inventory_retail_value,
        "estimated_excess_retail_value": estimated_excess_retail_value,
        "inputs": {
            "store_id": store_id,
            "product_id": product_id,
            "average_daily_sales": round(ads, 4),
            "current_stock": current_stock,
            "selling_price": selling_price,
            "target_coverage_days": target_coverage_days,
            "excess_units": round(excess_units, 2)
        },
        "formula": formula_str,
        "assumptions": [
            "Slow sales rate observed (1-5 units in last 30 days).",
            "Uses selling price because product cost data is unavailable.",
            f"Selling price: ₹{selling_price:.2f}"
        ]
    }


def estimate_spike_value(
    store_id: int,
    product_id: int,
    db_path: Optional[str] = None,
    as_of_date: Optional[str] = None
) -> Dict[str, Any]:
    """
    Estimate incremental sales value for a sales spike.
    Formula:
      incremental_units = max(recent_weekly_units - baseline_weekly_units, 0)
      estimated_incremental_sales_value = incremental_units * selling_price
    """
    store_id, product_id = _normalize_store_product(store_id, product_id, db_path)
    selling_price = _get_product_price(product_id, db_path)

    if selling_price is None:
        return {
            "issue_type": "sales_spike",
            "impact_label": "Estimated Incremental Sales Value",
            "impact_value": None,
            "inputs": {
                "store_id": store_id,
                "product_id": product_id,
                "recent_weekly_units": 0.0,
                "baseline_weekly_units": 0.0,
                "incremental_units": 0.0,
                "selling_price": None
            },
            "formula": "None",
            "assumptions": [
                "Selling price is unavailable or invalid in database; impact value cannot be computed."
            ]
        }

    try:
        anomaly = detect_product_anomaly(product_id, store_id=store_id, as_of_date=as_of_date)
        recent_units = float(anomaly["recent_period"]["units_sold"])
        baseline_units = float(anomaly["historical_baseline"]["mean_weekly_units"])
    except Exception:
        recent_units = 0.0
        baseline_units = 0.0

    incremental_units = max(recent_units - baseline_units, 0.0)
    impact_value = round(incremental_units * selling_price, 2)

    formula_str = (
        f"max({recent_units} recent - {baseline_units:.2f} baseline, 0) * ₹{selling_price:.2f}"
    )

    return {
        "issue_type": "sales_spike",
        "impact_label": "Estimated Incremental Sales Value",
        "impact_value": impact_value,
        "inputs": {
            "store_id": store_id,
            "product_id": product_id,
            "recent_weekly_units": recent_units,
            "baseline_weekly_units": round(baseline_units, 2),
            "incremental_units": round(incremental_units, 2),
            "selling_price": selling_price
        },
        "formula": formula_str,
        "assumptions": [
            "Represents recent sales uplift above the 6-week historical weekly baseline.",
            "Observed sales value indicator, not forward revenue risk.",
            f"Selling price: ₹{selling_price:.2f}"
        ]
    }


def estimate_drop_value(
    store_id: int,
    product_id: int,
    db_path: Optional[str] = None,
    as_of_date: Optional[str] = None
) -> Dict[str, Any]:
    """
    Estimate sales value gap for a sales drop.
    Formula:
      gap_units = max(baseline_weekly_units - recent_weekly_units, 0)
      estimated_sales_value_gap = gap_units * selling_price
    """
    store_id, product_id = _normalize_store_product(store_id, product_id, db_path)
    selling_price = _get_product_price(product_id, db_path)

    if selling_price is None:
        return {
            "issue_type": "sales_drop",
            "impact_label": "Estimated Sales Value Gap vs Baseline",
            "impact_value": None,
            "inputs": {
                "store_id": store_id,
                "product_id": product_id,
                "recent_weekly_units": 0.0,
                "baseline_weekly_units": 0.0,
                "gap_units": 0.0,
                "selling_price": None
            },
            "formula": "None",
            "assumptions": [
                "Selling price is unavailable or invalid in database; impact value cannot be computed."
            ]
        }

    try:
        anomaly = detect_product_anomaly(product_id, store_id=store_id, as_of_date=as_of_date)
        recent_units = float(anomaly["recent_period"]["units_sold"])
        baseline_units = float(anomaly["historical_baseline"]["mean_weekly_units"])
    except Exception:
        recent_units = 0.0
        baseline_units = 0.0

    gap_units = max(baseline_units - recent_units, 0.0)
    impact_value = round(gap_units * selling_price, 2)

    formula_str = (
        f"max({baseline_units:.2f} baseline - {recent_units} recent, 0) * ₹{selling_price:.2f}"
    )

    return {
        "issue_type": "sales_drop",
        "impact_label": "Estimated Sales Value Gap vs Baseline",
        "impact_value": impact_value,
        "inputs": {
            "store_id": store_id,
            "product_id": product_id,
            "recent_weekly_units": recent_units,
            "baseline_weekly_units": round(baseline_units, 2),
            "gap_units": round(gap_units, 2),
            "selling_price": selling_price
        },
        "formula": formula_str,
        "assumptions": [
            "Represents sales value shortfall compared with historical 6-week baseline.",
            "Estimated sales value gap vs baseline, not confirmed permanent revenue loss.",
            f"Selling price: ₹{selling_price:.2f}"
        ]
    }


def estimate_issue_impact(
    store_id: Optional[int] = None,
    product_id: Optional[int] = None,
    issue_type: Optional[str] = None,
    db_path: Optional[str] = None,
    **kwargs
) -> Dict[str, Any]:
    """
    Unified dispatcher to estimate financial impact for any issue.
    Supports either explicit parameters or issue_dict passing.
    """
    issue_dict = kwargs.get("issue_dict") or kwargs.get("issue")
    if isinstance(store_id, dict):
        issue_dict = store_id
        store_id = None

    if issue_dict and isinstance(issue_dict, dict):
        if not issue_type:
            issue_type = issue_dict.get("issue_type") or issue_dict.get("primary_issue")
        if not product_id:
            product_id = issue_dict.get("product_id") or issue_dict.get("product", {}).get("product_id")
        if not store_id:
            store_id = issue_dict.get("store_id") or issue_dict.get("store", {}).get("store_id")

    if not product_id or not store_id:
        raise ValueError("Both store_id and product_id are required for impact estimation.")

    if issue_type in ("stockout_risk", "stockout", "out_of_stock"):
        return estimate_stockout_revenue_at_risk(store_id, product_id, db_path=db_path)
    elif issue_type in ("overstock", "overstocked"):
        return estimate_overstock_value(store_id, product_id, db_path=db_path)
    elif issue_type in ("non_moving", "nonmoving", "dead_stock"):
        return estimate_non_moving_value(store_id, product_id, db_path=db_path)
    elif issue_type in ("slow_moving", "slowmoving"):
        return estimate_slow_moving_value(store_id, product_id, db_path=db_path)
    elif issue_type in ("sales_spike", "spike"):
        return estimate_spike_value(store_id, product_id, db_path=db_path)
    elif issue_type in ("sales_drop", "drop"):
        return estimate_drop_value(store_id, product_id, db_path=db_path)
    else:
        selling_price = _get_product_price(product_id, db_path)
        return {
            "issue_type": str(issue_type or "healthy"),
            "impact_label": "No Financial Impact",
            "impact_value": 0.0 if selling_price is not None else None,
            "inputs": {
                "store_id": store_id,
                "product_id": product_id,
                "selling_price": selling_price
            },
            "formula": "0.0",
            "assumptions": ["Normal operating status; no issue detected."]
        }
