import math
import statistics
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from src.database import get_connection

def get_dataset_date_range(db_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Determine dataset start date, end date, and total calendar days from sales table.
    """
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT MIN(date), MAX(date) FROM sales;")
    row = cursor.fetchone()
    conn.close()

    if not row or not row[0] or not row[1]:
        raise ValueError("Sales database is empty. Cannot determine dataset date range.")

    start_date_str = row[0]
    end_date_str = row[1]
    start_dt = datetime.strptime(start_date_str, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date_str, "%Y-%m-%d")
    total_days = (end_dt - start_dt).days + 1

    return {
        "start_date": start_date_str,
        "end_date": end_date_str,
        "total_days": total_days
    }

def _validate_product_and_store(conn, product_id: int, store_id: Optional[int] = None):
    """
    Internal helper to validate that product_id and store_id exist in database.
    Raises ValueError if invalid.
    """
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM products WHERE product_id = ?;", (product_id,))
    if not cursor.fetchone():
        raise ValueError(f"Invalid product_id: {product_id}. Product does not exist.")

    if store_id is not None:
        cursor.execute("SELECT 1 FROM stores WHERE store_id = ?;", (store_id,))
        if not cursor.fetchone():
            raise ValueError(f"Invalid store_id: {store_id}. Store does not exist.")

def get_units_sold(
    product_id: int,
    store_id: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db_path: Optional[str] = None
) -> int:
    """
    Calculate total units sold for a product across optional store and date bounds.
    Returns 0 if no sales records exist.
    """
    conn = get_connection(db_path)
    _validate_product_and_store(conn, product_id, store_id)

    query = "SELECT COALESCE(SUM(quantity_sold), 0) FROM sales WHERE product_id = ?"
    params: List[Any] = [product_id]

    if store_id is not None:
        query += " AND store_id = ?"
        params.append(store_id)

    if start_date is not None:
        query += " AND date >= ?"
        params.append(start_date)

    if end_date is not None:
        query += " AND date <= ?"
        params.append(end_date)

    cursor = conn.cursor()
    cursor.execute(query, params)
    units = cursor.fetchone()[0]
    conn.close()

    return int(units or 0)

def get_sales_revenue(
    product_id: int,
    store_id: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db_path: Optional[str] = None
) -> float:
    """
    Calculate total sales revenue for a product across optional store and date bounds.
    Returns 0.0 if no sales records exist.
    """
    conn = get_connection(db_path)
    _validate_product_and_store(conn, product_id, store_id)

    query = "SELECT COALESCE(SUM(sales_amount), 0.0) FROM sales WHERE product_id = ?"
    params: List[Any] = [product_id]

    if store_id is not None:
        query += " AND store_id = ?"
        params.append(store_id)

    if start_date is not None:
        query += " AND date >= ?"
        params.append(start_date)

    if end_date is not None:
        query += " AND date <= ?"
        params.append(end_date)

    cursor = conn.cursor()
    cursor.execute(query, params)
    revenue = cursor.fetchone()[0]
    conn.close()

    return round(float(revenue or 0.0), 2)

def get_average_daily_sales(
    product_id: int,
    store_id: Optional[int] = None,
    window_days: int = 30,
    as_of_date: Optional[str] = None,
    db_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Calculate Average Daily Sales (ADS) over a fixed calendar-day window.
    ADS = Total Units Sold in Window / window_days.
    """
    if window_days <= 0:
        raise ValueError(f"Invalid window_days: {window_days}. Must be greater than 0.")

    if as_of_date is None:
        as_of_date = get_dataset_date_range(db_path=db_path)["end_date"]

    end_dt = datetime.strptime(as_of_date, "%Y-%m-%d")
    start_dt = end_dt - timedelta(days=window_days - 1)
    start_date_str = start_dt.strftime("%Y-%m-%d")

    units = get_units_sold(product_id, store_id=store_id, start_date=start_date_str, end_date=as_of_date, db_path=db_path)
    ads = units / float(window_days)

    return {
        "product_id": product_id,
        "store_id": store_id,
        "window_days": window_days,
        "as_of_date": as_of_date,
        "start_date": start_date_str,
        "end_date": as_of_date,
        "units_sold": units,
        "average_daily_sales": round(ads, 4)
    }

def get_recent_sales_summary(
    product_id: int,
    store_id: Optional[int] = None,
    days: int = 7,
    as_of_date: Optional[str] = None
) -> Dict[str, Any]:
    """
    Get units sold, revenue, and daily average for recent calendar days.
    """
    if days <= 0:
        raise ValueError(f"Invalid days: {days}. Must be greater than 0.")

    if as_of_date is None:
        as_of_date = get_dataset_date_range()["end_date"]

    end_dt = datetime.strptime(as_of_date, "%Y-%m-%d")
    start_dt = end_dt - timedelta(days=days - 1)
    start_date_str = start_dt.strftime("%Y-%m-%d")

    units = get_units_sold(product_id, store_id=store_id, start_date=start_date_str, end_date=as_of_date)
    revenue = get_sales_revenue(product_id, store_id=store_id, start_date=start_date_str, end_date=as_of_date)
    avg_units = units / float(days)

    return {
        "product_id": product_id,
        "store_id": store_id,
        "period_days": days,
        "as_of_date": as_of_date,
        "start_date": start_date_str,
        "end_date": as_of_date,
        "units_sold": units,
        "revenue": revenue,
        "average_daily_units": round(avg_units, 4)
    }

def get_weekly_sales_totals(
    product_id: int,
    store_id: Optional[int] = None,
    weeks: int = 8,
    as_of_date: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Calculate weekly sales totals for fixed 7-day windows in chronological order.
    """
    if weeks <= 0:
        raise ValueError(f"Invalid weeks: {weeks}. Must be greater than 0.")

    if as_of_date is None:
        as_of_date = get_dataset_date_range()["end_date"]

    end_dt = datetime.strptime(as_of_date, "%Y-%m-%d")

    weekly_results = []
    for i in range(weeks - 1, -1, -1):
        w_end = end_dt - timedelta(days=i * 7)
        w_start = w_end - timedelta(days=6)

        w_start_str = w_start.strftime("%Y-%m-%d")
        w_end_str = w_end.strftime("%Y-%m-%d")

        units = get_units_sold(product_id, store_id=store_id, start_date=w_start_str, end_date=w_end_str)
        revenue = get_sales_revenue(product_id, store_id=store_id, start_date=w_start_str, end_date=w_end_str)

        weekly_results.append({
            "week_start": w_start_str,
            "week_end": w_end_str,
            "units_sold": units,
            "revenue": revenue
        })

    return weekly_results

def get_historical_weekly_baseline(
    product_id: int,
    store_id: Optional[int] = None,
    baseline_weeks: int = 6,
    exclude_recent_days: int = 7,
    as_of_date: Optional[str] = None
) -> Dict[str, Any]:
    """
    Calculate historical weekly sales baseline stats excluding the most recent days.
    """
    if baseline_weeks <= 0 or exclude_recent_days < 0:
        raise ValueError("Invalid parameters: baseline_weeks must be > 0 and exclude_recent_days >= 0.")

    if as_of_date is None:
        as_of_date = get_dataset_date_range()["end_date"]

    end_dt = datetime.strptime(as_of_date, "%Y-%m-%d")
    baseline_end_dt = end_dt - timedelta(days=exclude_recent_days)
    baseline_end_str = baseline_end_dt.strftime("%Y-%m-%d")

    weekly_totals = get_weekly_sales_totals(
        product_id=product_id,
        store_id=store_id,
        weeks=baseline_weeks,
        as_of_date=baseline_end_str
    )

    weekly_units = [w["units_sold"] for w in weekly_totals]

    mean_units = statistics.mean(weekly_units) if weekly_units else 0.0
    median_units = statistics.median(weekly_units) if weekly_units else 0.0
    min_units = min(weekly_units) if weekly_units else 0
    max_units = max(weekly_units) if weekly_units else 0
    std_units = statistics.stdev(weekly_units) if len(weekly_units) > 1 else 0.0

    return {
        "product_id": product_id,
        "store_id": store_id,
        "baseline_weeks": baseline_weeks,
        "exclude_recent_days": exclude_recent_days,
        "as_of_date": as_of_date,
        "baseline_end_date": baseline_end_str,
        "weekly_units": weekly_units,
        "mean_weekly_units": round(mean_units, 2),
        "median_weekly_units": round(median_units, 2),
        "min_weekly_units": min_units,
        "max_weekly_units": max_units,
        "std_weekly_units": round(std_units, 2)
    }

def get_product_sales_summary(
    product_id: int,
    store_id: Optional[int] = None,
    as_of_date: Optional[str] = None
) -> Dict[str, Any]:
    """
    Convenience summary combining recent sales, 30-day ADS, and historical weekly baseline.
    """
    recent_7d = get_recent_sales_summary(product_id, store_id=store_id, days=7, as_of_date=as_of_date)
    recent_30d = get_recent_sales_summary(product_id, store_id=store_id, days=30, as_of_date=as_of_date)
    ads_30d = get_average_daily_sales(product_id, store_id=store_id, window_days=30, as_of_date=as_of_date)
    baseline = get_historical_weekly_baseline(product_id, store_id=store_id, baseline_weeks=6, exclude_recent_days=7, as_of_date=as_of_date)

    return {
        "product_id": product_id,
        "store_id": store_id,
        "as_of_date": ads_30d["as_of_date"],
        "last_7_days": recent_7d,
        "last_30_days": recent_30d,
        "average_daily_sales_30d": ads_30d,
        "historical_weekly_baseline": baseline
    }
