import copy
from typing import Optional, Dict, Any, List
from src.inventory_engine import (
    get_current_inventory,
    get_days_of_stock_remaining,
    get_inventory_summary,
    get_all_inventory_metrics
)
from src.database import get_connection

# Centralized Default Risk Thresholds
DEFAULT_THRESHOLDS = {
    "stockout": {
        "critical_days": 3.0,
        "high_days": 5.0,
        "medium_days": 7.0
    },
    "overstock": {
        "coverage_days": 30.0
    },
    "slow_moving": {
        "lookback_days": 30,
        "max_units_sold": 5
    },
    "non_moving": {
        "lookback_days": 30,
        "max_units_sold": 0
    }
}

def validate_thresholds(thresholds: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Validate and merge user thresholds with default risk thresholds.
    Raises ValueError if thresholds violate logical constraints.
    """
    merged = copy.deepcopy(DEFAULT_THRESHOLDS)
    if thresholds:
        for cat, vals in thresholds.items():
            if cat in merged and isinstance(vals, dict):
                merged[cat].update(vals)

    so = merged["stockout"]
    c_days = float(so["critical_days"])
    h_days = float(so["high_days"])
    m_days = float(so["medium_days"])
    ov_days = float(merged["overstock"]["coverage_days"])
    sl_lookback = int(merged["slow_moving"]["lookback_days"])
    sl_max = int(merged["slow_moving"]["max_units_sold"])

    if c_days <= 0:
        raise ValueError("Critical stock-out threshold days must be greater than 0.")
    if h_days <= c_days:
        raise ValueError("High stock-out threshold days must be greater than critical days.")
    if m_days <= h_days:
        raise ValueError("Medium stock-out threshold days must be greater than high days.")
    if ov_days <= m_days:
        raise ValueError("Overstock threshold days must be greater than medium stock-out days.")
    if sl_lookback <= 0:
        raise ValueError("Movement lookback days must be greater than 0.")
    if sl_max < 1:
        raise ValueError("Slow-moving max units sold must be at least 1.")

    return merged

# Pure Classification Helper Functions
def classify_stockout_days(
    days_remaining: Optional[float],
    thresholds: Optional[Dict[str, Any]] = None
) -> Dict[str, str]:
    """
    Pure helper function to classify stock-out risk based on days remaining.
    Boundary rules:
      days < critical  -> critical
      critical <= days < high -> high
      high <= days < medium -> medium
      days >= medium -> safe
      days is None -> not_applicable
    """
    cfg = validate_thresholds(thresholds)["stockout"]
    c_days = cfg["critical_days"]
    h_days = cfg["high_days"]
    m_days = cfg["medium_days"]

    if days_remaining is None:
        return {"status": "not_applicable", "severity": "none"}

    if days_remaining < c_days:
        return {"status": "risk", "severity": "critical"}
    elif c_days <= days_remaining < h_days:
        return {"status": "risk", "severity": "high"}
    elif h_days <= days_remaining < m_days:
        return {"status": "risk", "severity": "medium"}
    else:
        return {"status": "safe", "severity": "safe"}

def is_overstock_coverage(
    days_remaining: Optional[float],
    threshold_days: float = 30.0
) -> bool:
    """
    Pure helper to evaluate overstock condition based on stock coverage days.
    Returns False if days_remaining is None (zero sales case).
    """
    if days_remaining is None:
        return False
    return days_remaining >= threshold_days

def is_non_moving(units_sold_30d: int, current_stock: int) -> bool:
    """
    Pure helper to evaluate non-moving condition (0 sales in 30 days and current_stock > 0).
    """
    return units_sold_30d == 0 and current_stock > 0

def is_slow_moving(units_sold_30d: int, current_stock: int, max_units: int = 5) -> bool:
    """
    Pure helper to evaluate slow-moving condition (1 to max_units sold in 30 days and current_stock > 0).
    """
    return 1 <= units_sold_30d <= max_units and current_stock > 0

# Single Product Risk Evaluation Functions
def classify_stockout_risk(
    product_id: int,
    store_id: int,
    as_of_date: Optional[str] = None,
    thresholds: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Classify stock-out risk for a specific product and store with structured evidence.
    """
    cfg = validate_thresholds(thresholds)
    summary = get_inventory_summary(product_id, store_id, as_of_date=as_of_date)
    days_rem = summary["days_of_stock_remaining"]

    result = classify_stockout_days(days_rem, cfg)
    status = result["status"]
    severity = result["severity"]

    if status == "not_applicable":
        reason = "No recent sales, therefore stock coverage cannot be estimated."
    elif severity == "safe":
        reason = f"Stock covers approximately {days_rem:.2f} days at current sales velocity (>= {cfg['stockout']['medium_days']}d safe threshold)."
    else:
        reason = f"Stock covers approximately {days_rem:.2f} days at current sales velocity (< {cfg['stockout'][severity + '_days']}d threshold)."

    return {
        "issue_type": "stockout_risk",
        "product_id": product_id,
        "product_name": summary["product_name"],
        "store_id": store_id,
        "current_stock": summary["current_stock"],
        "reorder_level": summary["reorder_level"],
        "reorder_gap": summary["reorder_gap"],
        "average_daily_sales": summary["average_daily_sales_30d"],
        "days_of_stock_remaining": days_rem,
        "status": status,
        "severity": severity,
        "thresholds": cfg["stockout"],
        "reason": reason
    }

def classify_overstock(
    product_id: int,
    store_id: int,
    as_of_date: Optional[str] = None,
    thresholds: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Classify overstock condition for a specific product and store.
    """
    cfg = validate_thresholds(thresholds)
    summary = get_inventory_summary(product_id, store_id, as_of_date=as_of_date)
    days_rem = summary["days_of_stock_remaining"]
    threshold_days = cfg["overstock"]["coverage_days"]

    overstock_flag = is_overstock_coverage(days_rem, threshold_days)

    if days_rem is None:
        reason = "No recent sales; product is evaluated under non-moving logic."
    elif overstock_flag:
        reason = f"Stock coverage of {days_rem:.2f} days exceeds the overstock threshold of {threshold_days} days."
    else:
        reason = f"Stock coverage of {days_rem:.2f} days is within normal operating limits (< {threshold_days} days)."

    return {
        "issue_type": "overstock",
        "product_id": product_id,
        "product_name": summary["product_name"],
        "store_id": store_id,
        "current_stock": summary["current_stock"],
        "average_daily_sales": summary["average_daily_sales_30d"],
        "days_of_stock_remaining": days_rem,
        "is_overstock": overstock_flag,
        "threshold_days": threshold_days,
        "reason": reason
    }

def classify_non_moving(
    product_id: int,
    store_id: int,
    lookback_days: int = 30,
    as_of_date: Optional[str] = None
) -> Dict[str, Any]:
    """
    Classify non-moving condition (0 sales in lookback period with current_stock > 0).
    """
    summary = get_inventory_summary(product_id, store_id, as_of_date=as_of_date)
    units_sold = summary["units_sold_30d"]
    stock = summary["current_stock"]

    non_moving_flag = is_non_moving(units_sold, stock)

    if non_moving_flag:
        reason = f"0 units sold in the last {lookback_days} days while {stock} units remain in stock."
    elif stock == 0:
        reason = "Current stock is 0; not classified as non-moving inventory."
    else:
        reason = f"{units_sold} units sold in the last {lookback_days} days."

    return {
        "issue_type": "non_moving",
        "product_id": product_id,
        "product_name": summary["product_name"],
        "store_id": store_id,
        "lookback_days": lookback_days,
        "units_sold": units_sold,
        "current_stock": stock,
        "is_non_moving": non_moving_flag,
        "reason": reason
    }

def classify_slow_moving(
    product_id: int,
    store_id: int,
    lookback_days: int = 30,
    max_units_sold: int = 5,
    as_of_date: Optional[str] = None
) -> Dict[str, Any]:
    """
    Classify slow-moving condition (1 to max_units_sold in lookback period with current_stock > 0).
    """
    summary = get_inventory_summary(product_id, store_id, as_of_date=as_of_date)
    units_sold = summary["units_sold_30d"]
    stock = summary["current_stock"]

    slow_moving_flag = is_slow_moving(units_sold, stock, max_units_sold)

    if slow_moving_flag:
        reason = f"Only {units_sold} units sold in the last {lookback_days} days while {stock} units remain in stock."
    elif units_sold == 0:
        reason = "0 units sold; classified under non-moving logic rather than slow-moving."
    else:
        reason = f"{units_sold} units sold exceeds the slow-moving threshold of {max_units_sold} units."

    return {
        "issue_type": "slow_moving",
        "product_id": product_id,
        "product_name": summary["product_name"],
        "store_id": store_id,
        "lookback_days": lookback_days,
        "units_sold": units_sold,
        "current_stock": stock,
        "is_slow_moving": slow_moving_flag,
        "threshold_units": max_units_sold,
        "reason": reason
    }

def analyze_inventory_product(
    product_id: int,
    store_id: int,
    as_of_date: Optional[str] = None,
    thresholds: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Combine all risk evaluations for a single product at a store and determine primary_issue label.
    """
    cfg = validate_thresholds(thresholds)
    summary = get_inventory_summary(product_id, store_id, as_of_date=as_of_date)

    so_eval = classify_stockout_risk(product_id, store_id, as_of_date=as_of_date, thresholds=cfg)
    ov_eval = classify_overstock(product_id, store_id, as_of_date=as_of_date, thresholds=cfg)
    nm_eval = classify_non_moving(product_id, store_id, lookback_days=cfg["non_moving"]["lookback_days"], as_of_date=as_of_date)
    sm_eval = classify_slow_moving(product_id, store_id, lookback_days=cfg["slow_moving"]["lookback_days"], max_units_sold=cfg["slow_moving"]["max_units_sold"], as_of_date=as_of_date)

    # Primary Issue Precedence Hierarchy
    if nm_eval["is_non_moving"]:
        primary_issue = "non_moving"
    elif so_eval["severity"] in ["critical", "high", "medium"]:
        primary_issue = "stockout_risk"
    elif ov_eval["is_overstock"]:
        primary_issue = "overstock"
    elif sm_eval["is_slow_moving"]:
        primary_issue = "slow_moving"
    else:
        primary_issue = "healthy"

    return {
        "product": {
            "product_id": product_id,
            "product_name": summary["product_name"],
            "category": summary["category"]
        },
        "store": {
            "store_id": store_id
        },
        "metrics": {
            "current_stock": summary["current_stock"],
            "reorder_level": summary["reorder_level"],
            "reorder_gap": summary["reorder_gap"],
            "units_sold_30d": summary["units_sold_30d"],
            "average_daily_sales_30d": summary["average_daily_sales_30d"],
            "days_of_stock_remaining": summary["days_of_stock_remaining"],
            "coverage_status": summary["coverage_status"]
        },
        "classifications": {
            "stockout_risk": so_eval,
            "overstock": ov_eval,
            "non_moving": nm_eval,
            "slow_moving": sm_eval
        },
        "primary_issue": primary_issue
    }

# Batch Analysis and Filter Functions
def analyze_all_inventory_risks(
    store_id: Optional[int] = None,
    as_of_date: Optional[str] = None,
    thresholds: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """
    Bulk calculation returning risk metrics and classifications for all store/product inventory combinations.
    """
    cfg = validate_thresholds(thresholds)
    all_metrics = get_all_inventory_metrics(store_id=store_id, as_of_date=as_of_date)

    results = []
    for item in all_metrics:
        days_rem = item["days_of_stock_remaining"]
        units_30d = item["units_sold_30d"]
        stock = item["current_stock"]

        so_res = classify_stockout_days(days_rem, cfg)
        is_ov = is_overstock_coverage(days_rem, cfg["overstock"]["coverage_days"])
        is_nm = is_non_moving(units_30d, stock)
        is_sm = is_slow_moving(units_30d, stock, cfg["slow_moving"]["max_units_sold"])

        # Primary issue hierarchy
        if is_nm:
            primary_issue = "non_moving"
        elif so_res["severity"] in ["critical", "high", "medium"]:
            primary_issue = "stockout_risk"
        elif is_ov:
            primary_issue = "overstock"
        elif is_sm:
            primary_issue = "slow_moving"
        else:
            primary_issue = "healthy"

        entry = copy.deepcopy(item)
        entry.update({
            "stockout_status": so_res["status"],
            "stockout_severity": so_res["severity"],
            "is_overstock": is_ov,
            "is_slow_moving": is_sm,
            "is_non_moving": is_nm,
            "primary_issue": primary_issue
        })
        results.append(entry)

    return results

def get_stockout_risks(
    severity: Optional[str] = None,
    store_id: Optional[int] = None,
    as_of_date: Optional[str] = None,
    thresholds: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """
    Return all stock-out risk items, optionally filtered by severity, sorted by days remaining ascending.
    """
    all_risks = analyze_all_inventory_risks(store_id=store_id, as_of_date=as_of_date, thresholds=thresholds)

    filtered = [
        item for item in all_risks
        if item["stockout_status"] == "risk"
        and (severity is None or item["stockout_severity"] == severity)
    ]

    # Sort lowest days_of_stock_remaining first
    filtered.sort(key=lambda x: x["days_of_stock_remaining"] if x["days_of_stock_remaining"] is not None else 999999)
    return filtered

def get_overstock_products(
    store_id: Optional[int] = None,
    as_of_date: Optional[str] = None,
    thresholds: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """
    Return all overstocked products, sorted by days remaining descending.
    """
    all_risks = analyze_all_inventory_risks(store_id=store_id, as_of_date=as_of_date, thresholds=thresholds)
    filtered = [item for item in all_risks if item["is_overstock"]]

    # Sort highest days_of_stock_remaining first
    filtered.sort(key=lambda x: x["days_of_stock_remaining"] if x["days_of_stock_remaining"] is not None else -1, reverse=True)
    return filtered

def get_slow_moving_products(
    store_id: Optional[int] = None,
    as_of_date: Optional[str] = None,
    thresholds: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """
    Return all slow-moving products, sorted by units sold ascending, then stock descending.
    """
    all_risks = analyze_all_inventory_risks(store_id=store_id, as_of_date=as_of_date, thresholds=thresholds)
    filtered = [item for item in all_risks if item["is_slow_moving"]]

    filtered.sort(key=lambda x: (x["units_sold_30d"], -x["current_stock"]))
    return filtered

def get_non_moving_products(
    store_id: Optional[int] = None,
    as_of_date: Optional[str] = None,
    thresholds: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """
    Return all non-moving products, sorted by current stock descending.
    """
    all_risks = analyze_all_inventory_risks(store_id=store_id, as_of_date=as_of_date, thresholds=thresholds)
    filtered = [item for item in all_risks if item["is_non_moving"]]

    filtered.sort(key=lambda x: x["current_stock"], reverse=True)
    return filtered
