"""
StockSage AI - Deterministic What-If Scenario Engine (Phase 10)

Calculates before/after inventory metrics, stock-out risk reclassification,
and Estimated Revenue at Risk under assumed demand changes (-90% to +300%)
and inventory adjustments.

Core Principle: All calculations are deterministic Python math.
This engine provides scenario simulation based on user assumptions, NOT predictive ML forecasts.
"""

from typing import Optional, Dict, Any, List
from src.database import get_connection
from src.inventory_engine import get_inventory_summary, get_all_inventory_metrics
from src.risk_engine import classify_stockout_days, validate_thresholds

SCENARIO_CONFIG = {
    "min_demand_change_percent": -90.0,
    "max_demand_change_percent": 300.0
}


def validate_scenario_inputs(
    demand_change_percent: float,
    stock_change_units: int,
    current_stock: int
) -> None:
    """
    Validate scenario inputs against logical boundaries.
    Raises ValueError if demand_change_percent is outside [-90, +300] or if
    resulting inventory becomes negative.
    """
    min_d = SCENARIO_CONFIG["min_demand_change_percent"]
    max_d = SCENARIO_CONFIG["max_demand_change_percent"]

    if demand_change_percent < min_d or demand_change_percent > max_d:
        raise ValueError(
            f"Demand change percentage {demand_change_percent}% is outside the valid scenario range "
            f"[{min_d}%, +{max_d}%]."
        )

    projected_stock = current_stock + stock_change_units
    if projected_stock < 0:
        raise ValueError(
            f"Stock adjustment of {stock_change_units} units on current stock of {current_stock} units "
            f"results in negative inventory ({projected_stock} units), which is invalid."
        )


def simulate_product_scenario(
    product_id: int,
    store_id: Optional[int] = None,
    demand_change_percent: float = 0.0,
    stock_change_units: int = 0,
    as_of_date: Optional[str] = None
) -> Dict[str, Any]:
    """
    Simulates the operational impact of assumed demand change % and/or stock unit adjustment
    for a specific product at a store.
    """
    if store_id is None:
        store_id = 1

    summary = get_inventory_summary(product_id, store_id, as_of_date=as_of_date)
    current_stock = summary["current_stock"]
    baseline_ads = summary["average_daily_sales_30d"]
    baseline_days = summary["days_of_stock_remaining"]
    selling_price = summary.get("selling_price", 0.0)

    # Fetch selling price from database if missing
    conn = get_connection()
    cursor = conn.cursor()
    if selling_price == 0.0:
        cursor.execute("SELECT selling_price FROM products WHERE product_id = ?;", (product_id,))
        p_row = cursor.fetchone()
        if p_row:
            selling_price = float(p_row["selling_price"])

    cursor.execute("SELECT store_name FROM stores WHERE store_id = ?;", (store_id,))
    st_row = cursor.fetchone()
    store_name = st_row["store_name"] if st_row else f"Store #{store_id}"
    conn.close()

    # 1. Input Validation
    validate_scenario_inputs(demand_change_percent, stock_change_units, current_stock)

    # 2. Before Risk Classification & Revenue at Risk
    before_risk_res = classify_stockout_days(baseline_days)
    before_severity = before_risk_res["severity"]

    # Phase 6A Revenue at Risk Formula: max(0, 7 * ADS - Stock) * Price (if days < 7)
    before_rev_at_risk = 0.0
    if baseline_days is not None and baseline_days < 7.0:
        unmet_7d = max(0.0, (7.0 * baseline_ads) - current_stock)
        before_rev_at_risk = unmet_7d * selling_price

    # 3. Assumed Demand Velocity & Days Coverage After Scenario
    assumed_ads = round(baseline_ads * (1.0 + (demand_change_percent / 100.0)), 4)
    projected_stock = current_stock + stock_change_units

    if assumed_ads == 0.0:
        days_remaining_after = None
    else:
        days_remaining_after = round(projected_stock / assumed_ads, 2)

    # 4. After Risk Classification & Revenue at Risk
    after_risk_res = classify_stockout_days(days_remaining_after)
    after_severity = after_risk_res["severity"]

    after_rev_at_risk = 0.0
    if days_remaining_after is not None and days_remaining_after < 7.0:
        unmet_7d = max(0.0, (7.0 * assumed_ads) - projected_stock)
        after_rev_at_risk = unmet_7d * selling_price

    rev_at_risk_change = after_rev_at_risk - before_rev_at_risk

    # Interpretation text
    demand_str = f"{demand_change_percent:+.1f}%"
    stock_action_str = f"stock adjusted by {stock_change_units:+d} units" if stock_change_units != 0 else "stock unchanged"
    
    if days_remaining_after is not None and baseline_days is not None:
        coverage_change_str = f"change from {baseline_days:.1f} days to {days_remaining_after:.1f} days"
    elif days_remaining_after is not None:
        coverage_change_str = f"become {days_remaining_after:.1f} days"
    else:
        coverage_change_str = "be not calculable (assumed demand = 0)"

    interpretation = (
        f"With demand assumed to change by {demand_str} and {stock_action_str}, "
        f"average daily sales would be assumed to change from {baseline_ads:.2f} to {assumed_ads:.2f} units/day. "
        f"Stock coverage would {coverage_change_str}, changing the stock-out risk status from "
        f"{before_severity.title()} to {after_severity.title()}."
    )

    days_change_val = None
    if days_remaining_after is not None and baseline_days is not None:
        days_change_val = round(days_remaining_after - baseline_days, 2)

    NON_FORECAST_DISCLAIMER = "Scenario simulation only — not a forecast. StockSage uses deterministic baseline calculations and does not generate unverified ML predictions."

    return {
        "product_id": product_id,
        "product_name": summary["product_name"],
        "store_id": store_id,
        "store_name": store_name,
        "category": summary["category"],
        "selling_price": selling_price,
        "demand_change_percent": demand_change_percent,
        "stock_change_units": stock_change_units,
        "disclaimer": NON_FORECAST_DISCLAIMER,
        "scenario": {
            "demand_change_percent": demand_change_percent,
            "stock_change_units": stock_change_units
        },
        "before": {
            "stock": current_stock,
            "current_stock": current_stock,
            "daily_sales_velocity": round(baseline_ads, 2),
            "average_daily_sales": round(baseline_ads, 2),
            "days_remaining": baseline_days,
            "risk_status": before_severity,
            "stockout_risk": before_severity,
            "revenue_at_risk": round(before_rev_at_risk, 2),
            "estimated_revenue_at_risk": round(before_rev_at_risk, 2)
        },
        "after": {
            "stock": projected_stock,
            "current_stock": projected_stock,
            "projected_stock_for_scenario": projected_stock,
            "daily_sales_velocity": round(assumed_ads, 2),
            "average_daily_sales": round(assumed_ads, 2),
            "assumed_average_daily_sales": round(assumed_ads, 2),
            "days_remaining": days_remaining_after,
            "risk_status": after_severity,
            "stockout_risk": after_severity,
            "revenue_at_risk": round(after_rev_at_risk, 2),
            "estimated_revenue_at_risk": round(after_rev_at_risk, 2)
        },
        "change": {
            "stock_change": stock_change_units,
            "velocity_change": round(assumed_ads - baseline_ads, 2),
            "ads_change": round(assumed_ads - baseline_ads, 2),
            "days_remaining_change": days_change_val,
            "risk_change": f"{before_severity.title()} -> {after_severity.title()}",
            "stockout_risk_change": f"{before_severity.title()} -> {after_severity.title()}",
            "revenue_at_risk_change": round(rev_at_risk_change, 2)
        },
        "interpretation": interpretation,
        "assumptions": [
            "30-day average daily sales is used as the baseline.",
            "Demand change is a user-defined scenario assumption, NOT a sales forecast.",
            "Product selling price is assumed unchanged.",
            "No unmodeled supplier lead times or purchase orders are included."
        ]
    }


def simulate_demand_change_for_all(
    demand_change_percent: float,
    store_id: Optional[int] = None,
    as_of_date: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Run demand change simulation across all store-product items.
    Returns list of simulated results.
    """
    all_items = get_all_inventory_metrics(store_id=store_id, as_of_date=as_of_date)
    results = []
    for item in all_items:
        sim = simulate_product_scenario(
            product_id=item["product_id"],
            store_id=item["store_id"],
            demand_change_percent=demand_change_percent,
            stock_change_units=0,
            as_of_date=as_of_date
        )
        results.append(sim)
    return results


def get_products_becoming_critical(
    demand_change_percent: float,
    store_id: Optional[int] = None,
    as_of_date: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Filter store-product items that transition into 'critical' stockout risk status
    under the assumed demand change (where before.stockout_risk != 'critical').
    """
    all_sims = simulate_demand_change_for_all(demand_change_percent, store_id=store_id, as_of_date=as_of_date)
    critical_transitions = [
        s for s in all_sims
        if s["before"]["stockout_risk"] != "critical" and s["after"]["stockout_risk"] == "critical"
    ]
    # Sort lowest resulting days_remaining first
    critical_transitions.sort(
        key=lambda x: (
            x["after"]["days_remaining"] if x["after"]["days_remaining"] is not None else 999,
            x["product_id"],
            x["store_id"]
        )
    )
    return critical_transitions
