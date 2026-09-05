"""
StockSage AI - Query Router & Entity Resolution Layer (Phase 8, 9 & 10)

Translates natural-language user questions into validated structured business intents.
Implements an allowlist of supported intents, deterministic product & store entity resolution
against SQLite (with ambiguity detection and closed failure for unknown items), limit extraction,
scenario parameter extraction, and grounding policy hooks.
"""

import re
import json
from typing import Optional, Dict, Any, List, Tuple
from difflib import SequenceMatcher

from src.database import get_connection

# Explicit Allowlist of Supported Business Intents (Phase 10 Expanded)
SUPPORTED_INTENTS = {
    "top_attention": "High-priority items needing immediate manager attention today",
    "stockout_risks": "Products facing critical or high stock-out risk",
    "overstock": "Products with inventory coverage above target levels",
    "slow_moving": "Products showing very low sales velocity relative to stock",
    "non_moving": "Products with zero sales in the last 30 days while inventory remains",
    "sales_spikes": "Products experiencing recent sales spikes above historical baseline",
    "sales_drops": "Products experiencing recent sales drops below historical baseline",
    "product_status": "Comprehensive status profile for a specific product",
    "product_evidence": "Detailed calculation evidence and inspector payload for a product",
    "priority_explanation": "Breakdown of why a product received a high priority score",
    "revenue_at_risk": "Estimated gross revenue at risk from stock-outs",
    "business_impact_summary": "Summary of financial impact metrics across all issues",
    "store_risk_summary": "Comparison of inventory risk and priorities across retail stores",
    "recommendation_summary": "Summary of actionable evidence-backed recommendations",
    "latest_sales_summary": "Total sales revenue and units sold on the latest dataset day",
    "what_if": "Simulates before/after inventory coverage under assumed demand or stock changes",
    "what_if_critical_products": "Identifies products that transition into critical stock-out risk under demand growth",
    "root_cause": "Cross-checks retail signals for possible contributing factors to sales or risk issues",
    "basket_pairs": "Products commonly bought together (co-purchased)",
    "related_products": "Specific products usually bought with a given item",
    "top_opportunities": "Top deterministic growth, high performer, or cross-sell opportunities",
    "product_opportunities": "Specific growth or cross-sell opportunities for a single product",
    "decision_history": "History of manager actions (Accept/Dismiss/Review) on recommendations",
    "unsupported_question": "Questions requiring missing metrics like cost, profit, suppliers, or employees"
}


def get_all_products_cache() -> List[Dict[str, Any]]:
    """Fetch product catalog from SQLite database."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT product_id, product_name, category FROM products;")
    products = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return products


def get_all_stores_cache() -> List[Dict[str, Any]]:
    """Fetch store list from SQLite database."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT store_id, store_name, location FROM stores;")
    stores = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return stores


def resolve_product(text: str) -> Dict[str, Any]:
    """
    Deterministically resolve product mentions in natural language against SQLite catalog.
    Uses exact, normalized, substring, ambiguity detection, and conservative fuzzy matching with strict threshold.
    Returns matched status dictionary. Fails closed for unknown products like 'iPhone'.
    """
    if not text or len(text.strip()) == 0:
        return {"matched": False, "reason": "Empty product query."}

    query = text.lower().strip()
    products = get_all_products_cache()

    # 1. Exact case-insensitive match
    for p in products:
        p_name = p["product_name"].lower()
        if query == p_name:
            return {
                "matched": True,
                "product_id": p["product_id"],
                "product_name": p["product_name"],
                "category": p["category"],
                "match_type": "exact"
            }

    # 2. Ambiguous Check: Generic terms matching multiple catalog products (e.g., "bread")
    sub_matches = [p for p in products if query in p["product_name"].lower() or any(w == query for w in p["product_name"].lower().split())]
    if len(sub_matches) > 1:
        return {
            "matched": False,
            "status": "ambiguous",
            "reason": f"Found multiple products matching '{text}'.",
            "candidates": sub_matches
        }

    # 3. Substring / Word boundaries match (single match)
    best_sub = None
    best_sub_len = 0
    for p in products:
        p_name = p["product_name"].lower()
        if p_name in query or (len(query) >= 3 and query in p_name):
            if len(p_name) > best_sub_len:
                best_sub_len = len(p_name)
                best_sub = p

    if best_sub:
        return {
            "matched": True,
            "product_id": best_sub["product_id"],
            "product_name": best_sub["product_name"],
            "category": best_sub["category"],
            "match_type": "normalized_exact"
        }

    # 4. Conservative Fuzzy Matching (minimum 0.75 similarity threshold)
    best_ratio = 0.0
    best_fuzzy = None
    for p in products:
        p_name = p["product_name"].lower()
        ratio = SequenceMatcher(None, query, p_name).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_fuzzy = p

    if best_ratio >= 0.75 and best_fuzzy:
        return {
            "matched": True,
            "product_id": best_fuzzy["product_id"],
            "product_name": best_fuzzy["product_name"],
            "category": best_fuzzy["category"],
            "match_type": "fuzzy",
            "similarity": round(best_ratio, 2)
        }

    # Fails closed if query is an unknown product like 'iPhone'
    return {
        "matched": False,
        "reason": f"No matching product found for '{text}' in current catalog."
    }


def resolve_store(text: str) -> Dict[str, Any]:
    """
    Resolve store mentions in text against SQLite store table.
    """
    if not text:
        return {"matched": False, "reason": "No store specified."}

    query = text.lower().strip()
    stores = get_all_stores_cache()

    # Exact or Substring Match
    matches = [s for s in stores if query == s["store_name"].lower() or s["store_name"].lower() in query or query in s["store_name"].lower()]
    if len(matches) == 1:
        s = matches[0]
        return {
            "matched": True,
            "store_id": s["store_id"],
            "store_name": s["store_name"],
            "match_type": "exact"
        }
    elif len(matches) > 1:
        return {
            "matched": False,
            "status": "ambiguous",
            "reason": f"Found multiple stores matching '{text}'.",
            "candidates": matches
        }

    # Common branch/alias mappings
    if "branch #104" in query or "104" in query:
        return {"matched": True, "store_id": 1, "store_name": "Central Market", "match_type": "alias"}
    elif "branch #108" in query or "108" in query:
        return {"matched": True, "store_id": 2, "store_name": "City Square Mart", "match_type": "alias"}

    return {"matched": False, "reason": f"No matching store found for '{text}' in database."}


def extract_limit(text: str) -> Optional[int]:
    """
    Extract integer bounds from query like 'top 3 issues' -> limit = 3.
    Caps limits between 1 and 20.
    """
    match = re.search(r'\btop\s+(\d+)\b', text.lower())
    if not match:
        match = re.search(r'\b(\d+)\s+items?\b', text.lower())
    if not match:
        match = re.search(r'\b(\d+)\s+issues?\b', text.lower())

    if match:
        val = int(match.group(1))
        return max(1, min(val, 20))

    return None


def extract_scenario_params(question: str) -> Dict[str, Any]:
    """
    Deterministic regex extraction of scenario parameters:
    - demand_change_percent (e.g., +30%, -20%, 50% increase)
    - stock_change_units (e.g., add 50 units, reduce 20 units)
    """
    q = question.lower().strip()
    demand_pct = 0.0
    stock_units = 0

    # 1. Match percentage scenario params
    p_match = re.search(r'(\+|-)?(\d+(\.\d+)?)\s*(%|percent)', q)
    if p_match:
        val = float(p_match.group(2))
        sign = p_match.group(1)
        if sign == "-":
            val = -abs(val)
        elif sign == "+":
            val = abs(val)
        elif any(w in q for w in ["drop", "drops", "fall", "falls", "decline", "declines", "down", "reduce demand", "decrease"]):
            val = -abs(val)
        demand_pct = val

    # 2. Match stock unit adjustments
    s_match = re.search(r'(add|increase|reduce|decrease|remove|plus|minus)?\s*(stock\s+)?(by\s+)?(\+|-)?(\d+)\s*units?', q)
    if s_match:
        num_val = int(s_match.group(5))
        prefix = s_match.group(1) or ""
        sign = s_match.group(4) or ""
        if sign == "-" or any(w in prefix for w in ["reduce", "decrease", "remove", "minus"]):
            num_val = -abs(num_val)
        stock_units = num_val

    return {
        "demand_change_percent": demand_pct,
        "stock_change_units": stock_units,
        "has_explicit_params": (demand_pct != 0.0 or stock_units != 0)
    }


def match_deterministic_intent(question: str) -> Optional[str]:
    """
    Deterministic rule & keyword matching for fast, 100% reliable intent classification.
    """
    q = question.lower().strip()

    # Unsupported Questions Rules (Profit, Supplier, Employee, Cost, Margin, Forecast)
    if any(k in q for k in ["profit", "margin", "net profit", "gross profit", "cost price", "unit cost"]):
        return "unsupported_question"
    if any(k in q for k in ["supplier", "vendor", "distributor", "employee", "staff"]):
        return "unsupported_question"
    if any(k in q for k in ["next month", "future sales", "sales forecast", "predict sales"]):
        return "unsupported_question"

    # Specific Evidence & Priority Queries
    if "why" in q and ("priority" in q or "ranked" in q or "score" in q):
        return "priority_explanation"
    if "evidence" in q or "why this recommendation" in q or "inspector" in q:
        return "product_evidence"

    # What-If Critical Products Query
    if "become critical" in q or "turn critical" in q or "become high risk" in q:
        return "what_if_critical_products"

    # What-If Scenario Queries
    if "what if" in q or "if demand" in q or "if sales rise" in q or "if sales drop" in q or "if i add" in q or "if stock" in q or "simulate" in q:
        return "what_if"

    # Root Cause Queries ("why did sales drop", "why is stockout risk high", "possible reason")
    if "why" in q or "possible reason" in q or "what may explain" in q or "explain drop" in q or "explain spike" in q:
        return "root_cause"

    # Financial Impact & Revenue at Risk
    if "revenue at risk" in q or "rev at risk" in q or "potential loss" in q:
        return "revenue_at_risk"
    if "business impact" in q or "financial impact" in q or "impact summary" in q:
        return "business_impact_summary"

    # Stock-out Risks
    if any(k in q for k in ["running out", "stockout", "stock-out", "out of stock", "critical stock", "stock shortage"]):
        return "stockout_risks"

    # Overstock
    if any(k in q for k in ["overstock", "overstocked", "too much stock", "excess stock", "surplus"]):
        return "overstock"

    # Non-Moving & Slow-Moving
    if any(k in q for k in ["non moving", "non-moving", "not selling", "isn't selling", "isnt selling", "zero sales", "no sales"]):
        return "non_moving"
    if any(k in q for k in ["slow moving", "slow-moving", "slow sales", "sluggish"]):
        return "slow_moving"

    # Sales Anomalies
    if any(k in q for k in ["spike", "spikes", "selling fast", "demand surge", "sales increase", "unusually fast"]):
        return "sales_spikes"
    if any(k in q for k in ["drop", "drops", "selling less", "drop in sales", "sales decline", "sales fell"]):
        return "sales_drops"

    # Store Risk Summary
    if "which store" in q or "store risk" in q or "compare stores" in q:
        return "store_risk_summary"

    # Latest Sales Summary
    if any(k in q for k in ["today's sales", "latest sales", "yesterday's sales", "sales today"]):
        return "latest_sales_summary"

    # Top Attention / Priorities
    if any(k in q for k in ["focus", "attention", "top issues", "top priorities", "what to do today", "needs attention"]):
        return "top_attention"

    # Product Performance Status ("How is X performing?", "Milk 1L status")
    if any(k in q for k in ["performing", "doing", "status of", "how is", "check"]):
        return "product_status"

    return None


def route_query(question: str) -> Dict[str, Any]:
    """
    Main Query Router entry point.
    Processes user natural-language question, detects intent, resolves product & store entities,
    extracts scenario parameters, and returns normalized routing dictionary.
    """
    if not question or not question.strip():
        return {
            "intent": "unsupported_question",
            "reason": "Empty question provided.",
            "product_info": {"matched": False},
            "store_info": {"matched": False},
            "scenario_params": {"demand_change_percent": 0.0, "stock_change_units": 0, "has_explicit_params": False},
            "limit": None
        }

    q_clean = question.strip()
    limit = extract_limit(q_clean)

    # 1. First run deterministic keyword matcher
    intent = match_deterministic_intent(q_clean)

    # 2. Extract Scenario Parameters if What-If intent
    scenario_params = extract_scenario_params(q_clean)

    # 3. Extract potential product entity
    product_info = {"matched": False}
    products = get_all_products_cache()
    for p in products:
        p_name = p["product_name"].lower()
        if p_name in q_clean.lower() or (len(p_name.split()) > 1 and p_name.split()[0] in q_clean.lower()):
            resolved = resolve_product(p["product_name"])
            if resolved.get("matched") or resolved.get("status") == "ambiguous":
                product_info = resolved
                break

    # If query contains ambiguous product keyword like 'bread'
    if not product_info.get("matched") and product_info.get("status") != "ambiguous":
        for token in q_clean.lower().split():
            if len(token) >= 3:
                res = resolve_product(token)
                if res.get("status") == "ambiguous":
                    product_info = res
                    break

    # If question mentions an unknown product like 'iPhone'
    if not product_info.get("matched") and product_info.get("status") != "ambiguous":
        for word in ["iphone", "laptop", "macbook", "television", "car", "shoes", "clothes"]:
            if word in q_clean.lower():
                product_info = resolve_product(word)  # Will fail closed
                break

    # 4. Extract potential store entity
    store_info = {"matched": False}
    stores = get_all_stores_cache()
    for s in stores:
        s_name = s["store_name"].lower()
        if s_name in q_clean.lower():
            resolved = resolve_store(s["store_name"])
            if resolved.get("matched") or resolved.get("status") == "ambiguous":
                store_info = resolved
                break

    # If question mentions an unknown store (e.g. 'Paris Store')
    if not store_info.get("matched") and store_info.get("status") != "ambiguous":
        if "store" in q_clean.lower() or "branch" in q_clean.lower():
            store_tokens = [w for w in q_clean.lower().split() if w not in ["the", "which", "how", "is", "store", "doing", "in", "at", "show", "me", "risk", "status"]]
            if store_tokens:
                store_info = resolve_store(" ".join(store_tokens))

    # If product_info matched and no intent was matched yet, default to product_status
    if intent is None and (product_info.get("matched") or product_info.get("status") == "ambiguous"):
        intent = "product_status"

    # Fallback default intent if still unknown
    if intent is None:
        intent = "top_attention"

    # Ensure intent is in allowlist
    if intent not in SUPPORTED_INTENTS:
        intent = "unsupported_question"

    return {
        "question": q_clean,
        "intent": intent,
        "intent_description": SUPPORTED_INTENTS.get(intent, ""),
        "product_info": product_info,
        "store_info": store_info,
        "scenario_params": scenario_params,
        "limit": limit or 5
    }
