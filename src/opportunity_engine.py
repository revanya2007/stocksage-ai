"""
StockSage AI - Opportunity Detector (Phase 11)

Detects positive retail signals using deterministic rules:
- sustained_growth
- high_performer
- strong_new_activity
- demand_growth_with_low_stock
- cross_sell_opportunity
"""

from typing import Optional, Dict, Any, List
from src.database import get_connection
from src.inventory_engine import get_all_inventory_metrics, get_inventory_summary
from src.basket_engine import get_top_product_pairs

OPPORTUNITY_CONFIG = {
    "sustained_growth_min_pct": 20.0,
    "high_performer_top_n": 10,
    "new_activity_min_sales": 5,
    "low_stock_days_threshold": 7.0
}

def get_weekly_sales(product_id: int, store_id: int, max_date: str) -> List[float]:
    """Returns sales for the last 3 complete weeks (Week -3, Week -2, Week -1)."""
    conn = get_connection()
    cursor = conn.cursor()
    
    weeks_sales = []
    for week_offset in range(3, 0, -1):
        start_days = week_offset * 7
        end_days = (week_offset - 1) * 7
        query = f"""
            SELECT SUM(quantity_sold) as total_qty 
            FROM sales 
            WHERE product_id = ? AND store_id = ? 
            AND date > date(?, '-{start_days} days') 
            AND date <= date(?, '-{end_days} days')
        """
        res = cursor.execute(query, (product_id, store_id, max_date, max_date)).fetchone()
        qty = res["total_qty"] if res and res["total_qty"] else 0
        weeks_sales.append(float(qty))
        
    conn.close()
    return weeks_sales

def detect_sustained_growth(product_id: int, store_id: int, max_date: str) -> Optional[Dict[str, Any]]:
    weeks = get_weekly_sales(product_id, store_id, max_date)
    if not weeks or len(weeks) != 3:
        return None
        
    w1, w2, w3 = weeks
    if w1 == 0:
        return None
        
    # Non-declining trajectory
    if w2 >= w1 and w3 >= w2:
        growth_pct = ((w3 - w1) / w1) * 100
        if growth_pct >= OPPORTUNITY_CONFIG["sustained_growth_min_pct"]:
            return {
                "opportunity_type": "sustained_growth",
                "opportunity_label": "Sustained Growth",
                "score": 85.0,
                "evidence": {
                    "week_minus_3": w1,
                    "week_minus_2": w2,
                    "week_minus_1": w3,
                    "growth_pct": round(growth_pct, 1)
                },
                "business_context": f"Sales grew from {w1} to {w3} units over the last 3 weeks.",
                "suggested_action": "Consider maintaining product availability and reviewing replenishment.",
                "confidence": "High"
            }
    return None

def get_high_performers(store_id: Optional[int] = None, as_of_date: Optional[str] = None) -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    
    if as_of_date:
        max_d = as_of_date
    else:
        cursor.execute("SELECT MAX(date) as md FROM sales")
        res = cursor.fetchone()
        max_d = res["md"] if res and res["md"] else None
        
    if not max_d:
        conn.close()
        return []
        
    query = """
        SELECT s.product_id, s.store_id, p.product_name, p.category, st.store_name, SUM(s.sales_amount) as revenue_30d
        FROM sales s
        JOIN products p ON s.product_id = p.product_id
        JOIN stores st ON s.store_id = st.store_id
        WHERE s.date > date(?, '-30 days') AND s.date <= ?
    """
    params = [max_d, max_d]
    if store_id:
        query += " AND s.store_id = ?"
        params.append(store_id)
        
    query += " GROUP BY s.product_id, s.store_id ORDER BY revenue_30d DESC LIMIT ?"
    params.append(OPPORTUNITY_CONFIG["high_performer_top_n"])
    
    rows = cursor.execute(query, params).fetchall()
    conn.close()
    
    results = []
    for r in rows:
        results.append({
            "opportunity_type": "high_performer",
            "store_id": r["store_id"],
            "store_name": r["store_name"],
            "product_id": r["product_id"],
            "product_name": r["product_name"],
            "category": r["category"],
            "score": 90.0,
            "opportunity_label": "High Performer",
            "evidence": {
                "30d_revenue": round(r["revenue_30d"], 2)
            },
            "business_context": f"Top performing product with ₹{r['revenue_30d']:.2f} revenue in the last 30 days.",
            "suggested_action": "Consider protecting stock availability and monitoring store-level demand.",
            "confidence": "High"
        })
    return results

def get_strong_new_activity(store_id: Optional[int] = None, as_of_date: Optional[str] = None) -> List[Dict[str, Any]]:
    items = get_all_inventory_metrics(store_id=store_id, as_of_date=as_of_date)
    results = []
    for item in items:
        # Pseudo new-activity check: 0 earlier, active recently
        # Phase 5 already handles new activity, but we will do a simpler deterministic check here based on sales vs inventory.
        # Let's say if 30d units > min_sales and it's flagged or assumed new.
        # Actually, Phase 3 metrics has total historical items. Let's use get_inventory_summary.
        
        summ = get_inventory_summary(item["product_id"], item["store_id"], as_of_date=as_of_date)
        if summ["units_sold_30d"] >= OPPORTUNITY_CONFIG["new_activity_min_sales"]:
            # Check if older sales exist
            conn = get_connection()
            cursor = conn.cursor()
            max_d = as_of_date or item.get("as_of_date") or '2023-12-31'
            res = cursor.execute("SELECT SUM(quantity_sold) as old_qty FROM sales WHERE product_id=? AND store_id=? AND date <= date(?, '-30 days')", (item["product_id"], item["store_id"], max_d)).fetchone()
            conn.close()
            old_qty = res["old_qty"] if res and res["old_qty"] else 0
            if old_qty == 0:
                results.append({
                    "opportunity_type": "strong_new_activity",
                    "store_id": item["store_id"],
                    "store_name": item["store_name"],
                    "product_id": item["product_id"],
                    "product_name": item["product_name"],
                    "category": item["category"],
                    "score": 75.0,
                    "opportunity_label": "Strong New Activity",
                    "evidence": {
                        "recent_30d_units": summ["units_sold_30d"],
                        "prior_sales": 0
                    },
                    "business_context": f"Strong new activity with {summ['units_sold_30d']} units sold from a zero baseline.",
                    "suggested_action": "Monitor whether the new sales activity continues before making a major inventory change.",
                    "confidence": "Medium"
                })
    return results

def get_growth_low_stock_opportunities(store_id: Optional[int] = None, as_of_date: Optional[str] = None) -> List[Dict[str, Any]]:
    # Combines sustained growth with low stock
    items = get_all_inventory_metrics(store_id=store_id, as_of_date=as_of_date)
    conn = get_connection()
    cursor = conn.cursor()
    if as_of_date:
        max_d = as_of_date
    else:
        cursor.execute("SELECT MAX(date) as md FROM sales")
        res = cursor.fetchone()
        max_d = res["md"] if res and res["md"] else '2023-12-31'
    conn.close()
    
    results = []
    for item in items:
        days_rem = item["days_of_stock_remaining"]
        if days_rem is not None and days_rem < OPPORTUNITY_CONFIG["low_stock_days_threshold"]:
            sg = detect_sustained_growth(item["product_id"], item["store_id"], max_d)
            if sg:
                results.append({
                    "opportunity_type": "demand_growth_with_low_stock",
                    "store_id": item["store_id"],
                    "store_name": item["store_name"],
                    "product_id": item["product_id"],
                    "product_name": item["product_name"],
                    "category": item["category"],
                    "score": 95.0,
                    "opportunity_label": "Demand Growth + Low Stock",
                    "evidence": {
                        "growth_evidence": sg["evidence"],
                        "days_remaining": round(days_rem, 1)
                    },
                    "business_context": f"Sales are accelerating, but only {days_rem:.1f} days of stock remain.",
                    "suggested_action": "Consider reviewing replenishment because demand is strengthening while stock coverage is limited.",
                    "confidence": "High"
                })
    return results

def get_cross_sell_opportunities(store_id: Optional[int] = None, as_of_date: Optional[str] = None) -> List[Dict[str, Any]]:
    pairs = get_top_product_pairs(store_id=store_id, limit=20, as_of_date=as_of_date)
    results = []
    for p in pairs:
        results.append({
            "opportunity_type": "cross_sell_opportunity",
            "store_id": store_id or 1,
            "store_name": "Multiple Stores" if not store_id else f"Store #{store_id}",
            "product_id": p["product_a_id"],
            "product_name": p["product_a_name"],
            "category": "Cross-Sell",
            "score": 70.0 + (p["lift"] * 5),
            "opportunity_label": "Cross-Sell Opportunity",
            "evidence": {
                "product_b_id": p["product_b_id"],
                "product_b_name": p["product_b_name"],
                "pair_transaction_count": p["pair_transaction_count"],
                "confidence": p["confidence_a_to_b"],
                "lift": p["lift"]
            },
            "business_context": f"{p['product_a_name']} and {p['product_b_name']} were bought together in {p['pair_transaction_count']} transactions.",
            "suggested_action": "Consider testing bundle placement or cross-merchandising.",
            "confidence": "Medium"
        })
    # normalize scores
    for r in results:
        r["score"] = min(100.0, r["score"])
    return results

def get_all_opportunities(store_id: Optional[int] = None, as_of_date: Optional[str] = None, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    if as_of_date:
        max_d = as_of_date
    else:
        cursor.execute("SELECT MAX(date) as md FROM sales")
        res = cursor.fetchone()
        max_d = res["md"] if res and res["md"] else '2023-12-31'
    conn.close()
    
    all_opps = []
    all_opps.extend(get_high_performers(store_id, max_d))
    all_opps.extend(get_strong_new_activity(store_id, max_d))
    all_opps.extend(get_growth_low_stock_opportunities(store_id, max_d))
    all_opps.extend(get_cross_sell_opportunities(store_id, max_d))
    
    # Also add sustained growth directly
    items = get_all_inventory_metrics(store_id=store_id, as_of_date=max_d)
    for item in items:
        sg = detect_sustained_growth(item["product_id"], item["store_id"], max_d)
        if sg:
            sg["store_id"] = item["store_id"]
            sg["store_name"] = item["store_name"]
            sg["product_id"] = item["product_id"]
            sg["product_name"] = item["product_name"]
            sg["category"] = item["category"]
            all_opps.append(sg)
            
    # Remove duplicates based on product and opportunity type
    unique_opps = []
    seen = set()
    for o in all_opps:
        key = (o["store_id"], o["product_id"], o["opportunity_type"])
        if key not in seen:
            seen.add(key)
            unique_opps.append(o)
            
    # Consolidation by product_id could happen here, but we will return individual opportunities
    # Sort by score DESC
    unique_opps.sort(key=lambda x: (-x["score"], x["product_id"]))
    
    if limit:
        unique_opps = unique_opps[:limit]
    return unique_opps

def get_top_opportunities(store_id: Optional[int] = None, as_of_date: Optional[str] = None, limit: int = 5) -> List[Dict[str, Any]]:
    return get_all_opportunities(store_id=store_id, as_of_date=as_of_date, limit=limit)
