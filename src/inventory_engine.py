from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from src.database import get_connection
from src.sales_engine import get_average_daily_sales, get_dataset_date_range

def get_current_inventory(product_id: int, store_id: int) -> Dict[str, Any]:
    """
    Retrieve current stock, reorder level, and last updated date for a specific store/product combination.
    Raises ValueError if record does not exist.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT current_stock, reorder_level, last_updated
        FROM inventory
        WHERE product_id = ? AND store_id = ?;
    """, (product_id, store_id))
    row = cursor.fetchone()
    conn.close()

    if not row:
        raise ValueError(f"No inventory record found for product_id {product_id} at store_id {store_id}.")

    return {
        "product_id": product_id,
        "store_id": store_id,
        "current_stock": row["current_stock"],
        "reorder_level": row["reorder_level"],
        "last_updated": row["last_updated"]
    }

def get_days_of_stock_remaining(
    product_id: int,
    store_id: int,
    sales_window_days: int = 30,
    as_of_date: Optional[str] = None
) -> Dict[str, Any]:
    """
    Calculate days of stock remaining: Current Stock / Average Daily Sales.
    Handles zero sales gracefully by returning days_of_stock_remaining=None.
    """
    inv = get_current_inventory(product_id, store_id)
    current_stock = inv["current_stock"]

    ads_info = get_average_daily_sales(
        product_id=product_id,
        store_id=store_id,
        window_days=sales_window_days,
        as_of_date=as_of_date
    )

    ads = ads_info["average_daily_sales"]
    units_sold = ads_info["units_sold"]

    # Zero sales case: ADS == 0.0
    if ads == 0.0:
        return {
            "product_id": product_id,
            "store_id": store_id,
            "current_stock": current_stock,
            "sales_window_days": sales_window_days,
            "units_sold_in_window": units_sold,
            "average_daily_sales": 0.0,
            "days_of_stock_remaining": None,
            "coverage_status": "no_recent_sales",
            "calculation": "Not calculable because average daily sales is 0."
        }

    # Zero stock case: current_stock == 0 and ads > 0
    if current_stock == 0:
        return {
            "product_id": product_id,
            "store_id": store_id,
            "current_stock": 0,
            "sales_window_days": sales_window_days,
            "units_sold_in_window": units_sold,
            "average_daily_sales": ads,
            "days_of_stock_remaining": 0.0,
            "coverage_status": "calculable",
            "calculation": f"0 / {ads:.4f} = 0.0"
        }

    # Normal calculation
    days_remaining = round(current_stock / ads, 2)
    return {
        "product_id": product_id,
        "store_id": store_id,
        "current_stock": current_stock,
        "sales_window_days": sales_window_days,
        "units_sold_in_window": units_sold,
        "average_daily_sales": ads,
        "days_of_stock_remaining": days_remaining,
        "coverage_status": "calculable",
        "calculation": f"{current_stock} / {ads:.4f} = {days_remaining:.2f}"
    }

def get_inventory_summary(
    product_id: int,
    store_id: int,
    as_of_date: Optional[str] = None
) -> Dict[str, Any]:
    """
    Get comprehensive inventory summary including stock level, reorder level, reorder gap,
    ADS 30d, and days of stock remaining.
    """
    inv = get_current_inventory(product_id, store_id)
    days_info = get_days_of_stock_remaining(product_id, store_id, sales_window_days=30, as_of_date=as_of_date)

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT product_name, category, selling_price FROM products WHERE product_id = ?;", (product_id,))
    p_row = cursor.fetchone()
    conn.close()

    reorder_gap = inv["current_stock"] - inv["reorder_level"]

    return {
        "product_id": product_id,
        "product_name": p_row["product_name"] if p_row else "",
        "category": p_row["category"] if p_row else "",
        "selling_price": p_row["selling_price"] if p_row else 0.0,
        "store_id": store_id,
        "current_stock": inv["current_stock"],
        "reorder_level": inv["reorder_level"],
        "reorder_gap": reorder_gap,
        "units_sold_30d": days_info["units_sold_in_window"],
        "average_daily_sales_30d": days_info["average_daily_sales"],
        "days_of_stock_remaining": days_info["days_of_stock_remaining"],
        "coverage_status": days_info["coverage_status"],
        "last_updated": inv["last_updated"]
    }

def get_all_inventory_metrics(
    store_id: Optional[int] = None,
    as_of_date: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Bulk calculation returning a list of dictionaries for all store/product combinations
    with joined inventory levels, product details, and 30-day sales metrics.
    """
    if as_of_date is None:
        as_of_date = get_dataset_date_range()["end_date"]

    end_dt = datetime.strptime(as_of_date, "%Y-%m-%d")
    start_dt = end_dt - timedelta(days=29)
    start_date_str = start_dt.strftime("%Y-%m-%d")

    conn = get_connection()

    query = """
        SELECT
            i.store_id,
            s.store_name,
            i.product_id,
            p.product_name,
            p.category,
            p.selling_price,
            i.current_stock,
            i.reorder_level,
            i.last_updated,
            COALESCE(sales_30d.units_sold_30d, 0) AS units_sold_30d
        FROM inventory i
        JOIN products p ON i.product_id = p.product_id
        JOIN stores s ON i.store_id = s.store_id
        LEFT JOIN (
            SELECT store_id, product_id, SUM(quantity_sold) AS units_sold_30d
            FROM sales
            WHERE date >= ? AND date <= ?
            GROUP BY store_id, product_id
        ) sales_30d ON i.store_id = sales_30d.store_id AND i.product_id = sales_30d.product_id
    """
    params = [start_date_str, as_of_date]

    if store_id is not None:
        query += " WHERE i.store_id = ?"
        params.append(store_id)

    query += " ORDER BY i.store_id, i.product_id;"

    cursor = conn.cursor()
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    results = []
    for r in rows:
        units_30d = int(r["units_sold_30d"] or 0)
        ads_30d = round(units_30d / 30.0, 4)
        current_stock = int(r["current_stock"])
        reorder_level = int(r["reorder_level"])
        reorder_gap = current_stock - reorder_level

        if ads_30d == 0.0:
            days_remaining = None
            coverage_status = "no_recent_sales"
        else:
            days_remaining = round(current_stock / ads_30d, 2)
            coverage_status = "calculable"

        results.append({
            "store_id": r["store_id"],
            "store_name": r["store_name"],
            "product_id": r["product_id"],
            "product_name": r["product_name"],
            "category": r["category"],
            "selling_price": float(r["selling_price"]),
            "current_stock": current_stock,
            "reorder_level": reorder_level,
            "reorder_gap": reorder_gap,
            "units_sold_30d": units_30d,
            "avg_daily_sales_30d": ads_30d,
            "days_of_stock_remaining": days_remaining,
            "coverage_status": coverage_status,
            "last_updated": r["last_updated"]
        })

    return results
