import copy
from typing import Optional, Dict, Any, List
from src.database import get_connection
from src.sales_engine import (
    get_dataset_date_range,
    get_recent_sales_summary,
    get_historical_weekly_baseline
)

# Centralized Default Anomaly Thresholds
DEFAULT_ANOMALY_THRESHOLDS = {
    "spike_percent": 50.0,
    "drop_percent": -30.0,
    "recent_window_days": 7,
    "baseline_weeks": 6,
    "min_baseline_units": 5.0
}

def validate_anomaly_thresholds(thresholds: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Validate and merge user thresholds with default anomaly thresholds.
    Raises ValueError if thresholds violate logical constraints.
    """
    merged = copy.deepcopy(DEFAULT_ANOMALY_THRESHOLDS)
    if thresholds:
        merged.update(thresholds)

    spike_p = float(merged["spike_percent"])
    drop_p = float(merged["drop_percent"])
    recent_d = int(merged["recent_window_days"])
    base_w = int(merged["baseline_weeks"])
    min_base = float(merged["min_baseline_units"])

    if spike_p <= 0:
        raise ValueError(f"Invalid spike_percent: {spike_p}. Must be strictly positive (> 0).")
    if drop_p >= 0:
        raise ValueError(f"Invalid drop_percent: {drop_p}. Must be strictly negative (< 0).")
    if recent_d <= 0:
        raise ValueError(f"Invalid recent_window_days: {recent_d}. Must be greater than 0.")
    if base_w <= 0:
        raise ValueError(f"Invalid baseline_weeks: {base_w}. Must be greater than 0.")
    if min_base < 0:
        raise ValueError(f"Invalid min_baseline_units: {min_base}. Must be non-negative (>= 0).")

    return merged

def classify_percentage_change(
    recent_units: int,
    baseline_mean_units: float,
    available_baseline_weeks: int = 6,
    thresholds: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Pure helper function to evaluate anomaly type and percentage change.
    Contains NO database calls.
    Returns:
      {
        "anomaly_type": str,  # spike, drop, normal, new_activity, no_activity, low_baseline, insufficient_data
        "absolute_units_change": float,
        "percentage_change": Optional[float]
      }
    """
    cfg = validate_anomaly_thresholds(thresholds)
    req_weeks = cfg["baseline_weeks"]
    min_base = cfg["min_baseline_units"]
    spike_p = cfg["spike_percent"]
    drop_p = cfg["drop_percent"]

    if available_baseline_weeks < req_weeks:
        return {
            "anomaly_type": "insufficient_data",
            "absolute_units_change": round(recent_units - baseline_mean_units, 2),
            "percentage_change": None
        }

    if baseline_mean_units == 0 and recent_units == 0:
        return {
            "anomaly_type": "no_activity",
            "absolute_units_change": 0.0,
            "percentage_change": None
        }

    if baseline_mean_units == 0 and recent_units > 0:
        return {
            "anomaly_type": "new_activity",
            "absolute_units_change": float(recent_units),
            "percentage_change": None
        }

    abs_change = round(recent_units - baseline_mean_units, 2)
    pct_change = round(((recent_units - baseline_mean_units) / baseline_mean_units) * 100.0, 2)

    if 0 < baseline_mean_units < min_base:
        return {
            "anomaly_type": "low_baseline",
            "absolute_units_change": abs_change,
            "percentage_change": pct_change
        }

    if pct_change >= spike_p:
        return {
            "anomaly_type": "spike",
            "absolute_units_change": abs_change,
            "percentage_change": pct_change
        }

    if pct_change <= drop_p:
        return {
            "anomaly_type": "drop",
            "absolute_units_change": abs_change,
            "percentage_change": pct_change
        }

    return {
        "anomaly_type": "normal",
        "absolute_units_change": abs_change,
        "percentage_change": pct_change
    }

def detect_product_anomaly(
    product_id: int,
    store_id: Optional[int] = None,
    as_of_date: Optional[str] = None,
    recent_window_days: int = 7,
    baseline_weeks: int = 6,
    thresholds: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Detect sales anomaly (spike, drop, normal, etc.) for a specific product and optional store.
    Returns structured evidence and non-causal explanation reason.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT product_name, category FROM products WHERE product_id = ?;", (product_id,))
    p_row = cursor.fetchone()
    if not p_row:
        conn.close()
        raise ValueError(f"Invalid product_id: {product_id}. Product does not exist.")

    store_name = None
    if store_id is not None:
        cursor.execute("SELECT store_name FROM stores WHERE store_id = ?;", (store_id,))
        s_row = cursor.fetchone()
        if not s_row:
            conn.close()
            raise ValueError(f"Invalid store_id: {store_id}. Store does not exist.")
        store_name = s_row["store_name"]

    conn.close()

    if as_of_date is None:
        as_of_date = get_dataset_date_range()["end_date"]

    custom_cfg = copy.deepcopy(thresholds) if thresholds else {}
    custom_cfg["recent_window_days"] = recent_window_days
    custom_cfg["baseline_weeks"] = baseline_weeks
    cfg = validate_anomaly_thresholds(custom_cfg)

    recent_summary = get_recent_sales_summary(
        product_id=product_id,
        store_id=store_id,
        days=cfg["recent_window_days"],
        as_of_date=as_of_date
    )

    baseline_summary = get_historical_weekly_baseline(
        product_id=product_id,
        store_id=store_id,
        baseline_weeks=cfg["baseline_weeks"],
        exclude_recent_days=cfg["recent_window_days"],
        as_of_date=as_of_date
    )

    recent_units = recent_summary["units_sold"]
    baseline_mean = baseline_summary["mean_weekly_units"]
    avail_weeks = len(baseline_summary["weekly_units"])

    classification = classify_percentage_change(
        recent_units=recent_units,
        baseline_mean_units=baseline_mean,
        available_baseline_weeks=avail_weeks,
        thresholds=cfg
    )

    anom_type = classification["anomaly_type"]
    pct_change = classification["percentage_change"]
    abs_change = classification["absolute_units_change"]

    # Construct deterministic non-causal explanation text
    if anom_type == "spike":
        reason = f"Recent {recent_window_days}-day sales were {recent_units} units versus a {baseline_weeks}-week average of {baseline_mean:.1f} units, an increase of {pct_change:+.2f}%."
    elif anom_type == "drop":
        reason = f"Recent {recent_window_days}-day sales were {recent_units} units versus a {baseline_weeks}-week average of {baseline_mean:.1f} units, a decrease of {abs(pct_change):.2f}%."
    elif anom_type == "normal":
        reason = f"Recent {recent_window_days}-day sales ({recent_units} units) are within normal baseline range ({baseline_mean:.1f} units/week)."
    elif anom_type == "no_activity":
        reason = f"No sales recorded in both recent {recent_window_days}-day period and historical baseline."
    elif anom_type == "new_activity":
        reason = f"Recent sales of {recent_units} units detected, but historical weekly baseline is zero."
    elif anom_type == "low_baseline":
        reason = f"Historical weekly baseline ({baseline_mean:.1f} units) is too small (< {cfg['min_baseline_units']} units) for reliable relative-change anomaly classification."
    else:
        reason = "Insufficient historical baseline weeks available for anomaly detection."

    return {
        "product_id": product_id,
        "product_name": p_row["product_name"],
        "category": p_row["category"],
        "store_id": store_id,
        "store_name": store_name,
        "as_of_date": as_of_date,
        "recent_period": {
            "start_date": recent_summary["start_date"],
            "end_date": recent_summary["end_date"],
            "units_sold": recent_units,
            "revenue": recent_summary["revenue"]
        },
        "historical_baseline": {
            "baseline_weeks": cfg["baseline_weeks"],
            "weekly_units": baseline_summary["weekly_units"],
            "mean_weekly_units": baseline_mean,
            "median_weekly_units": baseline_summary["median_weekly_units"]
        },
        "change": {
            "absolute_units_change": abs_change,
            "percentage_change": pct_change
        },
        "classification": {
            "anomaly_type": anom_type,
            "spike_threshold_used": cfg["spike_percent"],
            "drop_threshold_used": cfg["drop_percent"]
        },
        "reason": reason
    }

def detect_all_sales_anomalies(
    store_id: Optional[int] = None,
    as_of_date: Optional[str] = None,
    recent_window_days: int = 7,
    baseline_weeks: int = 6,
    thresholds: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """
    Bulk calculation returning anomaly results for all store/product combinations.
    Base population is derived from inventory to ensure zero-sales items remain present.
    """
    conn = get_connection()
    cursor = conn.cursor()

    query = "SELECT store_id, product_id FROM inventory"
    params = []
    if store_id is not None:
        query += " WHERE store_id = ?"
        params.append(store_id)

    query += " ORDER BY store_id, product_id;"
    cursor.execute(query, params)
    inv_pairs = cursor.fetchall()
    conn.close()

    results = []
    for pair in inv_pairs:
        s_id = pair["store_id"]
        p_id = pair["product_id"]
        anom = detect_product_anomaly(
            product_id=p_id,
            store_id=s_id,
            as_of_date=as_of_date,
            recent_window_days=recent_window_days,
            baseline_weeks=baseline_weeks,
            thresholds=thresholds
        )
        results.append(anom)

    return results

def get_sales_spikes(
    store_id: Optional[int] = None,
    as_of_date: Optional[str] = None,
    thresholds: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """
    Return all sales spike anomalies, sorted by percentage change descending.
    """
    all_anomalies = detect_all_sales_anomalies(store_id=store_id, as_of_date=as_of_date, thresholds=thresholds)
    filtered = [item for item in all_anomalies if item["classification"]["anomaly_type"] == "spike"]
    filtered.sort(key=lambda x: x["change"]["percentage_change"] if x["change"]["percentage_change"] is not None else -999999, reverse=True)
    return filtered

def get_sales_drops(
    store_id: Optional[int] = None,
    as_of_date: Optional[str] = None,
    thresholds: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """
    Return all sales drop anomalies, sorted by percentage change ascending (most negative first).
    """
    all_anomalies = detect_all_sales_anomalies(store_id=store_id, as_of_date=as_of_date, thresholds=thresholds)
    filtered = [item for item in all_anomalies if item["classification"]["anomaly_type"] == "drop"]
    filtered.sort(key=lambda x: x["change"]["percentage_change"] if x["change"]["percentage_change"] is not None else 999999)
    return filtered

def get_normal_sales_products(
    store_id: Optional[int] = None,
    as_of_date: Optional[str] = None,
    thresholds: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """
    Return all normal sales products.
    """
    all_anomalies = detect_all_sales_anomalies(store_id=store_id, as_of_date=as_of_date, thresholds=thresholds)
    return [item for item in all_anomalies if item["classification"]["anomaly_type"] == "normal"]
