"""
StockSage AI - Basket Intelligence Engine (Phase 11)

Detects frequent co-purchases from historical transaction data.
Analyzes transactions (not total item quantities) to calculate Support, 
Confidence, and Lift for product pairs.
"""

import json
from collections import defaultdict
from itertools import combinations
from typing import Optional, Dict, Any, List

from src.database import get_connection

BASKET_CONFIG = {
    "window_days": 30,
    "min_pair_transactions": 2,
    "min_support": 0.005
}

def get_transaction_baskets(store_id: Optional[int] = None, start_date: Optional[str] = None, end_date: Optional[str] = None) -> List[List[int]]:
    conn = get_connection()
    cursor = conn.cursor()
    
    # Base query for transaction mapping
    query = "SELECT transaction_id, product_id FROM sales WHERE 1=1"
    params = []
    
    if store_id is not None:
        query += " AND store_id = ?"
        params.append(store_id)
        
    if start_date is not None:
        query += " AND date >= ?"
        params.append(start_date)
        
    if end_date is not None:
        query += " AND date <= ?"
        params.append(end_date)
        
    rows = cursor.execute(query, params).fetchall()
    conn.close()
    
    # Group by transaction_id
    transactions = defaultdict(set)
    for r in rows:
        transactions[r["transaction_id"]].add(r["product_id"])
        
    # Return list of product lists
    return [list(t) for t in transactions.values() if len(t) > 0]


def calculate_product_pairs(store_id: Optional[int] = None, as_of_date: Optional[str] = None) -> List[Dict[str, Any]]:
    # 1. Determine date range
    conn = get_connection()
    cursor = conn.cursor()
    if as_of_date:
        max_d = as_of_date
    else:
        cursor.execute("SELECT MAX(date) as md FROM sales")
        res = cursor.fetchone()
        max_d = res["md"] if res and res["md"] else None
        
    start_date = None
    if max_d:
        cursor.execute("SELECT date(?, '-{} days') as sd".format(BASKET_CONFIG["window_days"]), (max_d,))
        res = cursor.fetchone()
        start_date = res["sd"] if res else None
        
    # 2. Fetch all product details for fast lookup
    cursor.execute("SELECT product_id, product_name FROM products")
    products = {r["product_id"]: r["product_name"] for r in cursor.fetchall()}
    conn.close()
    
    # 3. Get transactions
    baskets = get_transaction_baskets(store_id=store_id, start_date=start_date, end_date=max_d)
    
    total_transactions = len(baskets)
    if total_transactions == 0:
        return []
        
    # 4. Count items and pairs
    item_counts = defaultdict(int)
    pair_counts = defaultdict(int)
    
    for b in baskets:
        # unique items in the transaction
        items = sorted(list(set(b)))
        for item in items:
            item_counts[item] += 1
            
        for a, b_item in combinations(items, 2):
            pair_counts[(a, b_item)] += 1
            
    # 5. Calculate metrics
    results = []
    for (a, b_item), count in pair_counts.items():
        if count < BASKET_CONFIG["min_pair_transactions"]:
            continue
            
        support = count / total_transactions
        if support < BASKET_CONFIG["min_support"]:
            continue
            
        conf_a_b = count / item_counts[a]
        conf_b_a = count / item_counts[b_item]
        lift = support / ((item_counts[a] / total_transactions) * (item_counts[b_item] / total_transactions))
        
        results.append({
            "product_a_id": a,
            "product_a_name": products.get(a, f"Unknown {a}"),
            "product_b_id": b_item,
            "product_b_name": products.get(b_item, f"Unknown {b_item}"),
            "pair_transaction_count": count,
            "product_a_transaction_count": item_counts[a],
            "product_b_transaction_count": item_counts[b_item],
            "total_transactions": total_transactions,
            "support": round(support, 4),
            "confidence_a_to_b": round(conf_a_b, 4),
            "confidence_b_to_a": round(conf_b_a, 4),
            "lift": round(lift, 4),
            "store_id": store_id,
            "window_days": BASKET_CONFIG["window_days"]
        })
        
    # Default sorting: descending count, then product IDs for determinism
    results.sort(key=lambda x: (-x["pair_transaction_count"], -x["lift"], x["product_a_id"], x["product_b_id"]))
    return results

def get_top_product_pairs(store_id: Optional[int] = None, limit: int = 10, as_of_date: Optional[str] = None) -> List[Dict[str, Any]]:
    pairs = calculate_product_pairs(store_id=store_id, as_of_date=as_of_date)
    return pairs[:limit]

def get_related_products(product_id: int, store_id: Optional[int] = None, limit: int = 5, as_of_date: Optional[str] = None) -> List[Dict[str, Any]]:
    pairs = calculate_product_pairs(store_id=store_id, as_of_date=as_of_date)
    related = []
    for p in pairs:
        if p["product_a_id"] == product_id:
            related.append({
                "related_product_id": p["product_b_id"],
                "related_product_name": p["product_b_name"],
                "pair_transaction_count": p["pair_transaction_count"],
                "confidence": p["confidence_a_to_b"],
                "lift": p["lift"]
            })
        elif p["product_b_id"] == product_id:
            related.append({
                "related_product_id": p["product_a_id"],
                "related_product_name": p["product_a_name"],
                "pair_transaction_count": p["pair_transaction_count"],
                "confidence": p["confidence_b_to_a"],
                "lift": p["lift"]
            })
            
    # Sort highest confidence and count
    related.sort(key=lambda x: (-x["confidence"], -x["pair_transaction_count"], x["related_product_id"]))
    return related[:limit]
