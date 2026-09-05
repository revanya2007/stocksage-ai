"""
StockSage AI - Formal Grounding & Failure Handling Layer (Phase 9)

Centralized intent policies, dataset capability registry, required field validation,
prompt injection defense, SQL request defense, entity completeness evaluation,
and deterministic cannot-answer response builder.

Core Principle: StockSage prefers "I cannot calculate this from the available data."
over inventing a plausible answer.
"""

import re
from typing import Optional, Dict, Any, List, Set

# Controlled Set of Grounding Statuses
GROUNDING_STATUSES = {
    "grounded": "Request is fully valid, grounded, and executable",
    "unsupported_intent": "Question domain is outside StockSage retail scope or represents prompt injection / SQL request",
    "missing_entity": "Question requires a specific entity (e.g. product) that was not provided",
    "unknown_entity": "Requested entity does not exist in the retail database catalog",
    "ambiguous": "Entity resolution returned multiple equally plausible candidates",
    "missing_data": "Requested metric relies on missing database fields (cost, margin, supplier, employee, forecast)",
    "insufficient_history": "Dataset lacks sufficient historical dates to calculate metric",
    "uncalculable": "Mathematical operation cannot be calculated (e.g. coverage when velocity = 0)",
    "backend_error": "Deterministic backend calculation failed"
}

# Centralized Intent Policy Registry
INTENT_POLICIES: Dict[str, Dict[str, Any]] = {
    "top_attention": {
        "description": "High-priority items needing immediate manager attention today",
        "required_entities": [],
        "optional_entities": ["store"],
        "required_fields": [
            "products.product_id", "products.product_name",
            "inventory.current_stock", "sales.quantity_sold"
        ],
        "required_backend": "decision_engine.get_top_attention_items",
        "estimate_allowed": True,
        "gemini_allowed": True,
        "fallback_category": "top_priorities",
        "alternatives": ["stock-out risks", "overstock items", "business impact summary"]
    },
    "stockout_risks": {
        "description": "Products facing critical or high stock-out risk",
        "required_entities": [],
        "optional_entities": ["store"],
        "required_fields": [
            "products.product_id", "products.product_name",
            "inventory.current_stock", "sales.quantity_sold"
        ],
        "required_backend": "decision_engine.get_all_issue_candidates",
        "estimate_allowed": True,
        "gemini_allowed": True,
        "fallback_category": "stockout_risks",
        "alternatives": ["top attention items", "revenue at risk", "overstock items"]
    },
    "overstock": {
        "description": "Products with inventory coverage above target levels",
        "required_entities": [],
        "optional_entities": ["store"],
        "required_fields": [
            "products.product_id", "products.product_name",
            "inventory.current_stock", "inventory.reorder_level"
        ],
        "required_backend": "decision_engine.get_all_issue_candidates",
        "estimate_allowed": True,
        "gemini_allowed": True,
        "fallback_category": "overstock",
        "alternatives": ["slow moving stock", "non moving stock", "top attention items"]
    },
    "slow_moving": {
        "description": "Products showing very low sales velocity relative to stock",
        "required_entities": [],
        "optional_entities": ["store"],
        "required_fields": [
            "products.product_id", "products.product_name",
            "inventory.current_stock", "sales.quantity_sold"
        ],
        "required_backend": "decision_engine.get_all_issue_candidates",
        "estimate_allowed": True,
        "gemini_allowed": True,
        "fallback_category": "slow_moving",
        "alternatives": ["non moving stock", "overstock items", "top attention items"]
    },
    "non_moving": {
        "description": "Products with zero sales in the last 30 days while inventory remains",
        "required_entities": [],
        "optional_entities": ["store"],
        "required_fields": [
            "products.product_id", "products.product_name",
            "inventory.current_stock", "sales.quantity_sold"
        ],
        "required_backend": "decision_engine.get_all_issue_candidates",
        "estimate_allowed": True,
        "gemini_allowed": True,
        "fallback_category": "non_moving",
        "alternatives": ["slow moving stock", "excess retail value", "top attention items"]
    },
    "sales_spikes": {
        "description": "Products experiencing recent sales spikes above historical baseline",
        "required_entities": [],
        "optional_entities": ["store"],
        "required_fields": [
            "sales.quantity_sold", "sales.date", "products.product_id"
        ],
        "required_backend": "anomaly_detector.detect_sales_anomalies",
        "estimate_allowed": True,
        "gemini_allowed": True,
        "fallback_category": "sales_spikes",
        "alternatives": ["sales drops", "latest sales summary", "top attention items"]
    },
    "sales_drops": {
        "description": "Products experiencing recent sales drops below historical baseline",
        "required_entities": [],
        "optional_entities": ["store"],
        "required_fields": [
            "sales.quantity_sold", "sales.date", "products.product_id"
        ],
        "required_backend": "anomaly_detector.detect_sales_anomalies",
        "estimate_allowed": True,
        "gemini_allowed": True,
        "fallback_category": "sales_drops",
        "alternatives": ["sales spikes", "latest sales summary", "top attention items"]
    },
    "product_status": {
        "description": "Comprehensive status profile for a specific product",
        "required_entities": ["product"],
        "optional_entities": ["store"],
        "required_fields": [
            "products.product_id", "products.product_name",
            "inventory.current_stock", "sales.quantity_sold"
        ],
        "required_backend": "copilot_service.get_product_status",
        "estimate_allowed": True,
        "gemini_allowed": True,
        "fallback_category": "product_status",
        "alternatives": ["top attention items", "stock-out risk summary"]
    },
    "product_evidence": {
        "description": "Detailed calculation evidence and inspector payload for a product",
        "required_entities": ["product"],
        "optional_entities": ["store"],
        "required_fields": [
            "products.product_id", "products.product_name",
            "inventory.current_stock", "sales.quantity_sold"
        ],
        "required_backend": "recommendation_engine.build_recommendation_evidence",
        "estimate_allowed": True,
        "gemini_allowed": True,
        "fallback_category": "product_evidence",
        "alternatives": ["product status", "top attention items"]
    },
    "priority_explanation": {
        "description": "Breakdown of why a product received a high priority score",
        "required_entities": ["product"],
        "optional_entities": ["store"],
        "required_fields": [
            "products.product_id", "priority_score"
        ],
        "required_backend": "priority_engine.calculate_priority_score",
        "estimate_allowed": True,
        "gemini_allowed": True,
        "fallback_category": "priority_explanation",
        "alternatives": ["product status", "product evidence"]
    },
    "revenue_at_risk": {
        "description": "Estimated gross revenue at risk from stock-outs",
        "required_entities": [],
        "optional_entities": ["store"],
        "required_fields": [
            "products.selling_price", "sales.quantity_sold", "inventory.current_stock"
        ],
        "required_backend": "impact_engine.calculate_revenue_at_risk",
        "estimate_allowed": True,
        "gemini_allowed": True,
        "fallback_category": "revenue_at_risk",
        "alternatives": ["stock-out risks", "business impact summary", "latest sales summary"]
    },
    "business_impact_summary": {
        "description": "Summary of financial impact metrics across all issues",
        "required_entities": [],
        "optional_entities": ["store"],
        "required_fields": [
            "products.selling_price", "inventory.current_stock"
        ],
        "required_backend": "impact_engine.get_business_impact_summary",
        "estimate_allowed": True,
        "gemini_allowed": True,
        "fallback_category": "business_impact_summary",
        "alternatives": ["revenue at risk", "top attention items", "latest sales summary"]
    },
    "store_risk_summary": {
        "description": "Comparison of inventory risk and priorities across retail stores",
        "required_entities": [],
        "optional_entities": ["store"],
        "required_fields": [
            "stores.store_id", "stores.store_name"
        ],
        "required_backend": "decision_engine.get_all_issue_candidates",
        "estimate_allowed": True,
        "gemini_allowed": True,
        "fallback_category": "store_risk_summary",
        "alternatives": ["top attention items", "business impact summary"]
    },
    "recommendation_summary": {
        "description": "Summary of actionable evidence-backed recommendations",
        "required_entities": [],
        "optional_entities": ["store"],
        "required_fields": [
            "recommendations.recommendation_id"
        ],
        "required_backend": "recommendation_engine.generate_top_recommendations",
        "estimate_allowed": True,
        "gemini_allowed": True,
        "fallback_category": "recommendation_summary",
        "alternatives": ["top attention items", "business impact summary"]
    },
    "latest_sales_summary": {
        "description": "Total sales revenue and units sold on the latest dataset day",
        "required_entities": [],
        "optional_entities": ["store"],
        "required_fields": [
            "sales.sales_amount", "sales.date"
        ],
        "required_backend": "database.sales",
        "estimate_allowed": False,
        "gemini_allowed": True,
        "fallback_category": "latest_sales_summary",
        "alternatives": ["business impact summary", "top attention items"]
    },
    "what_if": {
        "description": "Deterministic scenario simulation for a product given demand % change or stock change",
        "required_entities": ["product"],
        "optional_entities": ["store"],
        "required_fields": [
            "products.product_id", "products.product_name",
            "inventory.current_stock", "sales.quantity_sold"
        ],
        "required_backend": "scenario_engine.simulate_product_scenario",
        "estimate_allowed": True,
        "gemini_allowed": True,
        "fallback_category": "what_if",
        "alternatives": ["critical scenario transitions", "product status", "top attention items"]
    },
    "what_if_critical_products": {
        "description": "Batch simulation identifying products becoming critical under a demand increase scenario",
        "required_entities": [],
        "optional_entities": ["store"],
        "required_fields": [
            "products.product_id", "products.product_name",
            "inventory.current_stock"
        ],
        "required_backend": "scenario_engine.get_products_becoming_critical",
        "estimate_allowed": True,
        "gemini_allowed": True,
        "fallback_category": "what_if_critical",
        "alternatives": ["stock-out risks", "top attention items"]
    },
    "root_cause": {
        "description": "Cross-checks retail signals for possible contributing factors to sales or risk issues",
        "required_entities": ["product"],
        "optional_entities": ["store"],
        "required_fields": [
            "products.product_id", "inventory.current_stock",
            "sales.quantity_sold"
        ],
        "required_backend": "scenario_engine.get_possible_root_causes",
        "estimate_allowed": True,
        "gemini_allowed": True,
        "fallback_category": "root_cause",
        "alternatives": ["product status", "sales drops", "sales spikes"]
    },
    "basket_pairs": {
        "description": "Products commonly bought together (co-purchased)",
        "required_entities": [],
        "optional_entities": ["store"],
        "required_fields": ["sales.transaction_id", "sales.product_id"],
        "required_backend": "basket_engine.get_top_product_pairs",
        "estimate_allowed": False,
        "gemini_allowed": True,
        "fallback_category": "baskets",
        "alternatives": ["top opportunities"]
    },
    "related_products": {
        "description": "Specific products usually bought with a given item",
        "required_entities": ["product"],
        "optional_entities": ["store"],
        "required_fields": ["sales.transaction_id", "sales.product_id"],
        "required_backend": "basket_engine.get_related_products",
        "estimate_allowed": False,
        "gemini_allowed": True,
        "fallback_category": "baskets",
        "alternatives": ["basket pairs"]
    },
    "top_opportunities": {
        "description": "Top deterministic growth, high performer, or cross-sell opportunities",
        "required_entities": [],
        "optional_entities": ["store"],
        "required_fields": ["sales.transaction_id", "sales.product_id", "sales.quantity_sold"],
        "required_backend": "opportunity_engine.get_top_opportunities",
        "estimate_allowed": False,
        "gemini_allowed": True,
        "fallback_category": "opportunities",
        "alternatives": ["top attention items"]
    },
    "product_opportunities": {
        "description": "Specific growth or cross-sell opportunities for a single product",
        "required_entities": ["product"],
        "optional_entities": ["store"],
        "required_fields": ["sales.transaction_id", "sales.product_id", "sales.quantity_sold"],
        "required_backend": "opportunity_engine.get_all_opportunities",
        "estimate_allowed": False,
        "gemini_allowed": True,
        "fallback_category": "opportunities",
        "alternatives": ["related products", "product status"]
    },
    "decision_history": {
        "description": "History of manager actions (Accept/Dismiss/Review) on recommendations",
        "required_entities": [],
        "optional_entities": ["store"],
        "required_fields": ["recommendations.manager_action"],
        "required_backend": "recommendation_engine.get_saved_recommendations",
        "estimate_allowed": False,
        "gemini_allowed": True,
        "fallback_category": "recommendations",
        "alternatives": ["recommendation summary"]
    },
    "unsupported_question": {
        "description": "Questions requiring missing metrics like cost, profit, suppliers, or employees",
        "required_entities": [],
        "optional_entities": [],
        "required_fields": [],
        "required_backend": "grounding.build_cannot_answer_response",
        "estimate_allowed": False,
        "gemini_allowed": False,
        "fallback_category": "cannot_answer",
        "alternatives": ["sales revenue", "top attention items", "stock-out risk summary"]
    }
}

# Database Capability Registry
DATASET_CAPABILITY: Dict[str, List[str]] = {
    "stores": ["store_id", "store_name", "location"],
    "products": ["product_id", "product_name", "category", "selling_price"],
    "sales": ["sale_line_id", "transaction_id", "date", "store_id", "product_id", "quantity_sold", "sales_amount"],
    "inventory": ["store_id", "product_id", "current_stock", "reorder_level", "last_updated"],
    "recommendations": ["recommendation_id", "timestamp", "store_id", "product_id", "issue_type", "priority_score", "evidence", "recommendation", "confidence", "manager_action"]
}

# Explicit Unavailable Fields and Explanations
UNAVAILABLE_FIELDS: Dict[str, Dict[str, Any]] = {
    "cost_price": {
        "missing_fields": ["cost_price", "gross_margin"],
        "reason": "Profit cannot be calculated from the available data because product cost or margin information is not available.",
        "alternatives": ["sales revenue", "units sold", "estimated revenue at risk"]
    },
    "gross_margin": {
        "missing_fields": ["cost_price", "gross_margin"],
        "reason": "Profit margin cannot be calculated from the available data because product cost or margin information is not available.",
        "alternatives": ["sales revenue", "units sold", "selling price"]
    },
    "profit": {
        "missing_fields": ["cost_price", "gross_margin"],
        "reason": "Profit cannot be calculated from the available data because product cost or margin information is not available. I can show sales revenue instead.",
        "alternatives": ["sales revenue", "sales trends", "estimated revenue at risk"]
    },
    "supplier": {
        "missing_fields": ["supplier", "supplier_lead_time"],
        "reason": "Supplier details are unavailable because supplier and procurement data are not part of the current store database.",
        "alternatives": ["products at stock-out risk", "inventory stock levels"]
    },
    "sales_forecast_model": {
        "missing_fields": ["sales_forecast_model"],
        "reason": "StockSage does not currently implement a future-sales forecasting model. I can show recent sales trends and current demand velocity.",
        "alternatives": ["recent sales trends", "30-day daily velocity", "sales anomalies"]
    },
    "root_cause_causal_engine": {
        "missing_fields": ["root_cause_causal_engine"],
        "reason": "Sales are below/above historical baseline, but StockSage does not yet have enough evidence to determine a confirmed cause.",
        "alternatives": ["recent sales velocity", "historical baseline comparison", "current inventory stock"]
    },
    "employee_count": {
        "missing_fields": ["employee_count", "staffing"],
        "reason": "Employee and store staffing information is not tracked in the store database.",
        "alternatives": ["store risk summaries", "sales performance by store"]
    },
    "customer_demographics": {
        "missing_fields": ["customer_demographics"],
        "reason": "Customer demographic data is not available in the store database.",
        "alternatives": ["top selling products", "sales volume"]
    },
    "competitor_price": {
        "missing_fields": ["competitor_price"],
        "reason": "Competitor pricing data is not available in the store database.",
        "alternatives": ["product selling price", "sales revenue"]
    },
    "direct_sql_execution": {
        "missing_fields": ["sql_engine"],
        "reason": "Direct SQL execution is not supported by the retail Copilot.",
        "alternatives": ["top attention items", "stock-out risk summary", "product status"]
    },
    "prompt_injection": {
        "missing_fields": ["security_compliance"],
        "reason": "Prompt override attempts are rejected. StockSage Copilot only provides answers strictly grounded in store database evidence.",
        "alternatives": ["top attention items", "stock-out risks", "sales anomalies"]
    }
}


def detect_prompt_injection(question: str) -> bool:
    """Detect if a user prompt attempts to bypass grounding rules or force hallucination."""
    q_lower = question.lower().strip()
    injection_patterns = [
        r"ignore\s+(the\s+)?database",
        r"ignore\s+(previous\s+)?instructions",
        r"make\s+up\s+an?\s+answer",
        r"invent\s+(a\s+|our\s+)?(profit|number|data)",
        r"use\s+your\s+own\s+knowledge",
        r"pretend\s+you\s+know",
        r"disregard\s+rules",
        r"bypass\s+grounding"
    ]
    for pattern in injection_patterns:
        if re.search(pattern, q_lower):
            return True
    return False


def detect_sql_request(question: str) -> bool:
    """Detect direct SQL query execution requests."""
    q_lower = question.lower().strip()
    sql_patterns = [
        r"select\s+.*\s+from",
        r"run\s+select",
        r"execute\s+sql",
        r"drop\s+table",
        r"show\s+me\s+every\s+database\s+row",
        r"dump\s+(the\s+)?database"
    ]
    for pattern in sql_patterns:
        if re.search(pattern, q_lower):
            return True
    return False


def check_required_fields(intent: str, entity_context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate whether the requested intent's required DB fields and entity requirements are satisfied.
    Returns status dictionary.
    """
    policy = INTENT_POLICIES.get(intent)
    if not policy:
        return {
            "supported": False,
            "status": "unsupported_intent",
            "missing_fields": [],
            "reason": f"Intent '{intent}' is not registered in the grounding policy registry."
        }

    # Check entity requirements
    req_entities = policy.get("required_entities", [])
    missing_entities = []
    if "product" in req_entities:
        prod_info = entity_context.get("product_info", {})
        if not prod_info.get("matched"):
            missing_entities.append("product")

    if missing_entities:
        return {
            "supported": False,
            "status": "missing_entity",
            "missing_entities": missing_entities,
            "missing_fields": [],
            "reason": "Which product would you like evidence for?"
        }

    return {
        "supported": True,
        "status": "grounded",
        "missing_entities": [],
        "missing_fields": [],
        "reason": None
    }


def evaluate_grounding(
    question: str,
    routed_query: Dict[str, Any],
    dataset_info: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Evaluates strict grounding rules for a user question and routed query.
    Returns a Grounding Decision Object determining whether execution is allowed,
    the exact grounding status, missing fields/entities, and whether Gemini API calls are permitted.
    """
    if not question or not question.strip():
        return {
            "allowed": False,
            "status": "unsupported_intent",
            "intent": "unsupported_question",
            "missing_entities": [],
            "missing_fields": [],
            "reason": "Please enter a valid question.",
            "can_call_gemini": False,
            "alternatives": ["top attention items", "stock-out risks"]
        }

    # 1. Check Prompt Injection
    if detect_prompt_injection(question):
        unavail = UNAVAILABLE_FIELDS["prompt_injection"]
        return {
            "allowed": False,
            "status": "unsupported_intent",
            "intent": "unsupported_question",
            "missing_entities": [],
            "missing_fields": unavail["missing_fields"],
            "reason": unavail["reason"],
            "can_call_gemini": False,
            "alternatives": unavail["alternatives"]
        }

    # 2. Check Direct SQL Request
    if detect_sql_request(question):
        unavail = UNAVAILABLE_FIELDS["direct_sql_execution"]
        return {
            "allowed": False,
            "status": "unsupported_intent",
            "intent": "unsupported_question",
            "missing_entities": [],
            "missing_fields": unavail["missing_fields"],
            "reason": unavail["reason"],
            "can_call_gemini": False,
            "alternatives": unavail["alternatives"]
        }

    intent = routed_query.get("intent", "unsupported_question")
    product_info = routed_query.get("product_info", {})
    store_info = routed_query.get("store_info", {})
    q_lower = question.lower().strip()

    # 3. Handle Explicit Unavailable Business Metric Refusals
    # A. Profit / Cost / Margin
    if any(k in q_lower for k in ["profit", "margin", "gross profit", "net profit", "cost price", "unit cost"]):
        unavail = UNAVAILABLE_FIELDS["profit"]
        return {
            "allowed": False,
            "status": "missing_data",
            "intent": intent,
            "missing_entities": [],
            "missing_fields": unavail["missing_fields"],
            "reason": unavail["reason"],
            "can_call_gemini": False,
            "alternatives": unavail["alternatives"]
        }

    # B. Supplier / Procurement
    if any(k in q_lower for k in ["supplier", "vendor", "distributor", "reorder from", "lead time"]):
        unavail = UNAVAILABLE_FIELDS["supplier"]
        return {
            "allowed": False,
            "status": "missing_data",
            "intent": intent,
            "missing_entities": [],
            "missing_fields": unavail["missing_fields"],
            "reason": unavail["reason"],
            "can_call_gemini": False,
            "alternatives": unavail["alternatives"]
        }

    # C. Sales Forecast / Future Sales (except for deterministic What-If scenario simulations)
    if intent not in ["what_if", "what_if_critical_products"] and any(k in q_lower for k in ["next month", "future sales", "sales forecast", "predict sales", "will sales be"]):
        unavail = UNAVAILABLE_FIELDS["sales_forecast_model"]
        return {
            "allowed": False,
            "status": "missing_data",
            "intent": intent,
            "missing_entities": [],
            "missing_fields": unavail["missing_fields"],
            "reason": unavail["reason"],
            "can_call_gemini": False,
            "alternatives": unavail["alternatives"]
        }

    # D. Employee / Staffing
    if any(k in q_lower for k in ["employee", "staff", "headcount", "workers"]):
        unavail = UNAVAILABLE_FIELDS["employee_count"]
        return {
            "allowed": False,
            "status": "missing_data",
            "intent": intent,
            "missing_entities": [],
            "missing_fields": unavail["missing_fields"],
            "reason": unavail["reason"],
            "can_call_gemini": False,
            "alternatives": unavail["alternatives"]
        }

    # E. Weather / External Unrelated Intent
    if any(k in q_lower for k in ["weather", "temperature", "rain", "sports", "football", "president"]):
        return {
            "allowed": False,
            "status": "unsupported_intent",
            "intent": "unsupported_question",
            "missing_entities": [],
            "missing_fields": [],
            "reason": "That question cannot be answered from the current StockSage retail dataset.",
            "can_call_gemini": False,
            "alternatives": ["sales revenue", "inventory risk items", "top priority issues"]
        }

    # 4. Entity Ambiguity & Unknown Entity Evaluation
    # Check if entity resolution marked query as ambiguous
    if product_info.get("status") == "ambiguous":
        candidates = product_info.get("candidates", [])
        cand_names = [c["product_name"] for c in candidates]
        cand_str = " and ".join(cand_names) if len(cand_names) == 2 else ", ".join(cand_names)
        return {
            "allowed": False,
            "status": "ambiguous",
            "intent": intent,
            "missing_entities": [],
            "missing_fields": [],
            "reason": f"I found multiple matching products: {cand_str}. Please specify one.",
            "can_call_gemini": False,
            "candidates": candidates,
            "alternatives": cand_names
        }

    if store_info.get("status") == "ambiguous":
        candidates = store_info.get("candidates", [])
        cand_names = [c["store_name"] for c in candidates]
        cand_str = " and ".join(cand_names) if len(cand_names) == 2 else ", ".join(cand_names)
        return {
            "allowed": False,
            "status": "ambiguous",
            "intent": intent,
            "missing_entities": [],
            "missing_fields": [],
            "reason": f"I found multiple matching stores: {cand_str}. Please specify one.",
            "can_call_gemini": False,
            "candidates": candidates,
            "alternatives": cand_names
        }

    # Check for unknown store (e.g., "Paris Store")
    if any(k in q_lower for k in ["store", "branch"]) and not store_info.get("matched") and store_info.get("reason"):
        if "No matching store found" in store_info.get("reason", ""):
            return {
                "allowed": False,
                "status": "unknown_entity",
                "intent": intent,
                "missing_entities": [],
                "missing_fields": [],
                "reason": store_info.get("reason"),
                "can_call_gemini": False,
                "alternatives": ["Central Market", "City Square Mart", "Riverside Store"]
            }

    # Check for unknown product (e.g., "iPhone") if product_info was explicitly attempted with reason
    if not product_info.get("matched") and product_info.get("reason") and "No matching product found" in product_info.get("reason", ""):
        return {
            "allowed": False,
            "status": "unknown_entity",
            "intent": intent,
            "missing_entities": [],
            "missing_fields": [],
            "reason": product_info.get("reason"),
            "can_call_gemini": False,
            "alternatives": ["Basmati Rice 5kg", "Milk 1L", "Olive Oil 500ml"]
        }

    # 5. Check Missing Entity Requirements (e.g., "Show evidence" without product)
    policy = INTENT_POLICIES.get(intent, {})
    req_entities = policy.get("required_entities", [])
    if "product" in req_entities and not product_info.get("matched"):
        entity_reason = "Which product would you like evidence for?"
        if intent == "what_if":
            entity_reason = "Which product would you like to simulate?"
        elif intent == "root_cause":
            entity_reason = "Which product would you like to investigate for root causes?"
        return {
            "allowed": False,
            "status": "missing_entity",
            "intent": intent,
            "missing_entities": ["product"],
            "missing_fields": [],
            "reason": entity_reason,
            "can_call_gemini": False,
            "alternatives": ["Milk 1L", "Basmati Rice 5kg", "Olive Oil 500ml"]
        }

    # Scenario Parameter Check for What-If Queries
    if intent == "what_if":
        scenario_params = routed_query.get("scenario_params", {})
        if scenario_params.get("demand_change_percent") is None and scenario_params.get("stock_change_units") is None:
            return {
                "allowed": False,
                "status": "missing_entity",
                "intent": intent,
                "missing_entities": ["scenario_parameters"],
                "missing_fields": [],
                "reason": "What demand change percentage would you like to simulate? For example, +20% or -10%.",
                "can_call_gemini": False,
                "alternatives": ["simulate +20% demand", "simulate -10% demand", "simulate +50 stock units"]
            }

    # 6. Default Grounded Status
    return {
        "allowed": True,
        "status": "grounded",
        "intent": intent,
        "missing_entities": [],
        "missing_fields": [],
        "reason": None,
        "can_call_gemini": policy.get("gemini_allowed", True),
        "alternatives": policy.get("alternatives", [])
    }


def build_cannot_answer_response(
    grounding_result: Dict[str, Any],
    question: str
) -> Dict[str, Any]:
    """
    Constructs a structured cannot-answer / refusal response payload.
    Guarantees deterministic output without calling Gemini.
    Note: success = False indicates refusal / missing data, but is NOT a system error.
    """
    status = grounding_result.get("status", "unsupported_intent")
    reason = grounding_result.get("reason", "Question cannot be answered from current store data.")
    missing_fields = grounding_result.get("missing_fields", [])
    alternatives = grounding_result.get("alternatives", ["top attention items", "sales summary"])
    intent = grounding_result.get("intent", "unsupported_question")

    return {
        "success": False,
        "grounded": True,
        "status": status,
        "intent": intent,
        "question": question,
        "answer": reason,
        "missing_fields": missing_fields,
        "available_alternatives": alternatives,
        "evidence": [],
        "assumptions": ["Answer was generated by StockSage Grounding Policy."],
        "data_source": "StockSage deterministic grounding rules",
        "generated_by_ai": False,
        "response_source": "grounding_policy"
    }
