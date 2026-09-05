"""
StockSage AI - Retail Copilot Orchestrator (Phase 8 & 9)

Orchestrates natural-language question handling: routing intents, grounding evaluation,
entity resolution, calling verified Phase 3-7 backend analytics, constructing structured context,
gating Gemini API execution, and returning standardized grounded responses.
"""

import json
from typing import Optional, Dict, Any, List

from src.database import get_connection
from src.query_router import route_query, SUPPORTED_INTENTS
from src.grounding import (
    evaluate_grounding,
    build_cannot_answer_response,
    GROUNDING_STATUSES
)
from src.decision_engine import (
    get_all_issue_candidates,
    get_top_attention_items,
    get_business_impact_summary,
    get_issue_counts,
    ISSUE_LABEL_MAP
)
from src.recommendation_engine import (
    generate_top_recommendations,
    generate_recommendation,
    build_recommendation_evidence
)
from src.gemini_client import (
    is_gemini_configured,
    generate_grounded_response
)
from src.scenario_engine import (
    simulate_product_scenario,
    get_products_becoming_critical
)
from src.root_cause_engine import (
    analyze_possible_causes,
    CAUSALITY_DISCLAIMER
)
from src.basket_engine import get_top_product_pairs, get_related_products
from src.opportunity_engine import get_top_opportunities, get_all_opportunities


def build_fallback_answer(intent: str, context: Dict[str, Any]) -> str:
    """
    Generate a deterministic, verified natural-language response template when Gemini API is unconfigured or unavailable.
    Guarantees 100% working Copilot responses without external network calls.
    """
    results = context.get("results", [])

    if intent == "unsupported_question":
        reason = context.get("unsupported_reason")
        if reason:
            return reason
        return "I can answer questions regarding sales trends, inventory stock levels, risk alerts, anomalies, priority scores, and business impact."

    if not results and intent not in ["revenue_at_risk", "business_impact_summary", "latest_sales_summary", "store_risk_summary"]:
        return "No high-priority retail issues or risk items were found matching your criteria in the current store data."

    if intent == "top_attention":
        count = len(results)
        lines = [f"StockSage AI identified {count} high-priority item(s) needing your attention today:"]
        for idx, r in enumerate(results, start=1):
            pr = r.get("product_name")
            st = r.get("store_name")
            itype = r.get("issue_label", r.get("issue_type"))
            score = r.get("priority_score", 0)
            imp = r.get("impact", {}).get("value")
            imp_str = f" (Impact: ₹{imp:,.2f})" if imp else ""
            lines.append(f"{idx}. {pr} at {st} — {itype} [Priority: {score}/100]{imp_str}")
        return "\n".join(lines)

    elif intent in ["stockout_risks", "overstock", "slow_moving", "non_moving", "sales_spikes", "sales_drops"]:
        label = ISSUE_LABEL_MAP.get(intent, intent.replace("_", " ").title())
        count = len(results)
        lines = [f"Found {count} product(s) flagged for {label}:"]
        for idx, r in enumerate(results, start=1):
            pr = r.get("product_name")
            st = r.get("store_name")
            score = r.get("priority_score", 0)
            rec = r.get("recommendation", "")
            lines.append(f"{idx}. {pr} ({st}) — Priority: {score}/100. {rec}")
        return "\n".join(lines)

    elif intent in ["product_status", "product_evidence", "priority_explanation"]:
        item = results[0] if results else {}
        pr = item.get("product_name", "Product")
        st = item.get("store_name", "All Stores")
        stock = item.get("current_stock")
        ads = item.get("average_daily_sales")
        days = item.get("days_of_stock_remaining")
        itype = item.get("issue_label", "Healthy")
        rec = item.get("recommendation", "")

        stock_str = f"{stock} units" if stock is not None else "N/A"
        ads_str = f"{ads:.2f} units/day" if ads is not None else "0 units/day"
        days_str = f"{days:.2f} days" if days is not None else "N/A"

        return (
            f"{pr} at {st}:\n"
            f"• Current Stock: {stock_str}\n"
            f"• 30-Day Sales Velocity: {ads_str}\n"
            f"• Stock Coverage: {days_str}\n"
            f"• Current Status: {itype}\n"
            f"• Advisory: {rec}"
        )

    elif intent == "revenue_at_risk":
        val = context.get("estimated_revenue_at_risk", 0.0)
        cnt = context.get("stockout_risk_count", 0)
        return (
            f"The total estimated revenue at risk across all critical stock-out risk items is ₹{val:,.2f} "
            f"affecting {cnt} product(s). This represents top-line estimated unrealized gross revenue over a 7-day horizon."
        )

    elif intent == "business_impact_summary":
        imp = context.get("impact_summary", {})
        rev_risk = imp.get("estimated_revenue_at_risk", 0.0)
        excess_val = imp.get("estimated_excess_retail_value", 0.0)
        non_mov_val = imp.get("non_moving_retail_value", 0.0)
        return (
            "Business Impact Summary:\n"
            f"• Estimated Revenue at Risk (Stock-outs): ₹{rev_risk:,.2f}\n"
            f"• Estimated Retail Value of Excess Stock: ₹{excess_val:,.2f}\n"
            f"• Retail Value of Non-Moving Stock: ₹{non_mov_val:,.2f}"
        )

    elif intent == "latest_sales_summary":
        tot_sales = context.get("latest_sales_amount", 0.0)
        max_dt = context.get("latest_date", "N/A")
        return f"Latest available dataset sales total on {max_dt} is ₹{tot_sales:,.2f}."

    elif intent == "store_risk_summary":
        stores_data = context.get("store_summaries", [])
        lines = ["Store Risk Summary:"]
        for s in stores_data:
            lines.append(f"• {s['store_name']}: {s['stockout_risks']} Stock-out Risk(s), {s['overstock_items']} Overstock Item(s)")
        return "\n".join(lines)

    elif intent == "what_if":
        sim = context.get("scenario_result", {})
        if not sim:
            return "No scenario simulation result was generated."
        pr = sim.get("product_name", "Product")
        st = sim.get("store_name", "Store")
        b = sim.get("before", {})
        a = sim.get("after", {})
        c = sim.get("change", {})
        pct = sim.get("demand_change_percent", 0.0)
        st_adj = sim.get("stock_change_units", 0)

        b_days = f"{b.get('days_remaining'):.1f}d" if b.get('days_remaining') is not None else "N/A"
        a_days = f"{a.get('days_remaining'):.1f}d" if a.get('days_remaining') is not None else "N/A"

        return (
            f"What-If Simulation for {pr} ({st}):\n"
            f"• Scenario Parameters: Demand Change = {pct:+.1f}%, Stock Adjustment = {st_adj:+d} units\n"
            f"• Inventory Stock: {b.get('stock')} → {a.get('stock')} units\n"
            f"• Stock Coverage: {b_days} → {a_days}\n"
            f"• Risk Classification: {b.get('risk_status', '').upper()} → {a.get('risk_status', '').upper()}\n"
            f"• Estimated Revenue at Risk: ₹{b.get('revenue_at_risk', 0.0):,.2f} → ₹{a.get('revenue_at_risk', 0.0):,.2f} (Change: ₹{c.get('revenue_at_risk_change', 0.0):+,.2f})\n"
            f"• Disclaimer: {sim.get('disclaimer', 'Scenario simulation only — not a forecast.')}"
        )

    elif intent == "what_if_critical_products":
        crit_items = context.get("critical_transitions", [])
        pct = context.get("demand_change_percent", 25.0)
        cnt = len(crit_items)
        if not crit_items:
            return f"Under a {pct:+.1f}% demand increase scenario, no additional products transition into critical stock-out risk."
        lines = [f"What-If Critical Scenario ({pct:+.1f}% Demand Increase): {cnt} product(s) transition to critical stock-out risk:"]
        for idx, item in enumerate(crit_items, start=1):
            pr = item.get("product_name")
            st = item.get("store_name")
            b_days = f"{item.get('before_days_remaining'):.1f}d" if item.get('before_days_remaining') is not None else "N/A"
            a_days = f"{item.get('after_days_remaining'):.1f}d" if item.get('after_days_remaining') is not None else "N/A"
            lines.append(f"{idx}. {pr} at {st} — Coverage drops from {b_days} to {a_days} ({item.get('before_risk_status')} → {item.get('after_risk_status')})")
        lines.append("• Note: Scenario simulation only — not a forecast.")
        return "\n".join(lines)

    elif intent == "root_cause":
        rc = context.get("root_cause_analysis", {})
        if not rc:
            return "No root-cause evidence analysis could be performed."
        pr = rc.get("product_name", "Product")
        st = rc.get("store_name", "Store")
        causes = rc.get("possible_causes", [])
        rating = rc.get("confidence_rating", "Low")

        lines = [
            f"Root-Cause Diagnostic for {pr} ({st}):",
            f"• Confidence Rating: {rating}"
        ]
        for idx, c_item in enumerate(causes, start=1):
            lines.append(f"• Hypothesis {idx}: {c_item.get('hypothesis')}")
            for ev in c_item.get("evidence_supporting", []):
                lines.append(f"  - Evidence: {ev}")
        lines.append(f"• Disclaimer: {rc.get('disclaimer', CAUSALITY_DISCLAIMER)}")
        return "\n".join(lines)

    elif intent == "basket_pairs":
        baskets = context.get("basket_pairs", [])
        if not baskets:
            return "No frequently bought together products detected."
        lines = ["Top Frequently Bought Together Products:"]
        for b in baskets[:5]:
            lines.append(f"• {b['product_a_name']} and {b['product_b_name']} ({b['pair_transaction_count']} transactions, Lift: {b['lift']:.2f})")
        return "\n".join(lines)
        
    elif intent == "related_products":
        related = context.get("related_products", [])
        pr = context.get("product_name", "Product")
        if not related:
            return f"No related products found for {pr}."
        lines = [f"Products frequently bought with {pr}:"]
        for r in related[:5]:
            lines.append(f"• {r['related_product_name']} ({r['pair_transaction_count']} transactions)")
        return "\n".join(lines)
        
    elif intent in ["top_opportunities", "product_opportunities"]:
        opps = context.get("opportunities", [])
        if not opps:
            return "No growth or cross-sell opportunities detected."
        lines = ["Detected Opportunities:"]
        for o in opps[:5]:
            lines.append(f"• {o['product_name']}: {o['opportunity_label']} (Score: {o['score']:.0f})")
        return "\n".join(lines)
        
    elif intent == "decision_history":
        recs = context.get("decision_history", [])
        if not recs:
            return "No recommendation history available."
        lines = ["Recent Decision History:"]
        for r in recs[:5]:
            lines.append(f"• Product {r['product_id']}: {r['manager_action']} on {r['timestamp'][:10]}")
        return "\n".join(lines)

    return "Refer to the verified metrics and recommendation evidence below for full operational details."


def answer_question(question: str, use_gemini: bool = True, candidates: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """
    Main entry point for Copilot conversational queries.
    Enforces Phase 9 Grounding Policy:
    Route -> Evaluate Grounding -> Refuse if allowed=False -> Execute Backend -> Format Context -> Call Gemini/Fallback.
    """
    # 1. Sanity check & input validation
    if not question or not question.strip():
        grounding = {
            "allowed": False,
            "status": "unsupported_intent",
            "intent": "unsupported_question",
            "reason": "Please enter a valid retail sales or inventory question.",
            "missing_fields": [],
            "alternatives": ["top attention items", "stock-out risks"]
        }
        return build_cannot_answer_response(grounding, question)

    if len(question) > 1000:
        grounding = {
            "allowed": False,
            "status": "unsupported_intent",
            "intent": "unsupported_question",
            "reason": "Question exceeds maximum limit of 1000 characters.",
            "missing_fields": [],
            "alternatives": ["top attention items"]
        }
        return build_cannot_answer_response(grounding, question)

    # 2. Route Query & Resolve Entities
    routing = route_query(question)
    intent = routing["intent"]
    product_info = routing["product_info"]
    store_info = routing["store_info"]
    limit = routing["limit"]

    store_id = store_info.get("store_id") if store_info.get("matched") else None

    # 3. Evaluate Grounding Rules (Gating Engine)
    grounding = evaluate_grounding(question, routing)

    # IF Grounding is not allowed, return Cannot-Answer Response WITHOUT calling Gemini!
    if not grounding.get("allowed"):
        return build_cannot_answer_response(grounding, question)

    # 4. Deterministic Backend Execution & Verified Context Construction
    verified_context: Dict[str, Any] = {
        "question": question,
        "intent": intent,
        "results": [],
        "assumptions": []
    }
    evidence_payload: List[Dict[str, Any]] = []

    # A. Top Attention Items
    if intent == "top_attention":
        top_recs = generate_top_recommendations(store_id=store_id, limit=limit, candidates=candidates)
        verified_context["results"] = top_recs
        evidence_payload = top_recs

    # B. Issue Category Filtered Recommendations
    elif intent in ["stockout_risks", "overstock", "slow_moving", "non_moving", "sales_spikes", "sales_drops"]:
        all_cands = candidates if candidates is not None else get_all_issue_candidates(store_id=store_id)
        filtered_cands = [c for c in all_cands if c["issue_type"] == intent]
        filtered_recs = [generate_recommendation(c) for c in filtered_cands[:limit]]

        verified_context["results"] = filtered_recs
        evidence_payload = filtered_recs

    # C. Product Specific Status / Evidence / Priority Explanation
    elif intent in ["product_status", "product_evidence", "priority_explanation"]:
        pr_id = product_info.get("product_id")
        all_cands = candidates if candidates is not None else get_all_issue_candidates(store_id=store_id)
        matched_cands = [c for c in all_cands if c.get("product_id") == pr_id]

        if matched_cands:
            for c in matched_cands:
                rec_obj = generate_recommendation(c)
                verified_context["results"].append(rec_obj)
            evidence_payload = verified_context["results"]
        else:
            # Query SQLite for healthy product info if no candidate risk issue exists
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("""
            SELECT i.store_id, st.store_name, i.product_id, p.product_name, p.category, i.current_stock
            FROM inventory i
            JOIN stores st ON i.store_id = st.store_id
            JOIN products p ON i.product_id = p.product_id
            WHERE i.product_id = ?;
            """, (pr_id,))
            inv_rows = cursor.fetchall()

            for row in inv_rows:
                st_id = row["store_id"]
                cursor.execute("SELECT SUM(quantity_sold) FROM sales WHERE store_id = ? AND product_id = ?;", (st_id, pr_id))
                u_res = cursor.fetchone()
                units_30d = u_res[0] if u_res and u_res[0] is not None else 0
                ads = units_30d / 30.0
                stock = row["current_stock"]
                days_rem = round(stock / ads, 2) if ads > 0 else None

                healthy_rec = {
                    "store_id": st_id,
                    "store_name": row["store_name"],
                    "product_id": pr_id,
                    "product_name": row["product_name"],
                    "category": row["category"],
                    "issue_type": "healthy",
                    "issue_label": "Healthy Inventory",
                    "priority_score": 0,
                    "priority_label": "Healthy",
                    "recommendation": f"{row['product_name']} inventory is within healthy operational parameters.",
                    "evidence": {
                        "metrics": [
                            {"label": "Current Stock", "value": stock, "unit": "units"},
                            {"label": "30-Day Units Sold", "value": units_30d, "unit": "units"},
                            {"label": "Average Daily Sales", "value": round(ads, 2), "unit": "units/day"},
                            {"label": "Days Remaining", "value": days_rem, "unit": "days"}
                        ],
                        "calculation": {"label": "Coverage", "formula": "Stock ÷ Average Daily Sales"},
                        "confidence": "High"
                    },
                    "impact": {"label": "Financial Impact", "value": 0.0},
                    "assumptions": ["Stock matches normal sales velocity."]
                }
                verified_context["results"].append(healthy_rec)
            conn.close()
            evidence_payload = verified_context["results"]

    # D. Revenue at Risk & Impact Summaries
    elif intent in ["revenue_at_risk", "business_impact_summary"]:
        impact_summary = get_business_impact_summary(store_id=store_id)
        counts_info = get_issue_counts(store_id=store_id)
        stockout_cnt = counts_info.get("candidate_issue_counts", {}).get("stockout_risk", 0)

        verified_context["estimated_revenue_at_risk"] = impact_summary.get("estimated_revenue_at_risk", 0.0)
        verified_context["stockout_risk_count"] = stockout_cnt
        verified_context["impact_summary"] = impact_summary
        verified_context["assumptions"] = [
            "Estimated Revenue at Risk horizon is set to 7 calendar days.",
            "Uses 30-day average daily sales velocity."
        ]

    # E. Store Risk Summary
    elif intent == "store_risk_summary":
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT store_id, store_name FROM stores;")
        all_stores = cursor.fetchall()
        conn.close()

        store_summaries = []
        for s in all_stores:
            st_id = s["store_id"]
            st_cands = get_all_issue_candidates(store_id=st_id)
            st_counts = {c["issue_type"]: 0 for c in st_cands}
            for c in st_cands:
                st_counts[c["issue_type"]] = st_counts.get(c["issue_type"], 0) + 1

            store_summaries.append({
                "store_id": st_id,
                "store_name": s["store_name"],
                "stockout_risks": st_counts.get("stockout_risk", 0),
                "overstock_items": st_counts.get("overstock", 0),
                "anomalies": st_counts.get("sales_spike", 0) + st_counts.get("sales_drop", 0)
            })

        verified_context["store_summaries"] = store_summaries

    # F. Latest Sales Summary
    elif intent == "latest_sales_summary":
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT MAX(date) FROM sales;")
        max_dt = cursor.fetchone()[0]
        cursor.execute("SELECT SUM(sales_amount) FROM sales WHERE date = ?;", (max_dt,))
        s_res = cursor.fetchone()
        tot_sales = float(s_res[0]) if s_res and s_res[0] else 0.0
        conn.close()

        verified_context["latest_date"] = max_dt
        verified_context["latest_sales_amount"] = tot_sales

    # G. Phase 10 What-If Scenario Simulation for a Product
    elif intent == "what_if":
        pr_id = product_info.get("product_id")
        scen_params = routing.get("scenario_params", {})
        demand_pct = scen_params.get("demand_change_percent", 0.0)
        stock_change = scen_params.get("stock_change_units", 0)

        sim_res = simulate_product_scenario(
            product_id=pr_id,
            store_id=store_id,
            demand_change_percent=demand_pct,
            stock_change_units=stock_change
        )
        verified_context["scenario_result"] = sim_res
        verified_context["results"] = [sim_res]
        evidence_payload = [sim_res]
        verified_context["assumptions"] = [sim_res.get("disclaimer", "Scenario simulation only — not a forecast.")]

    # H. Phase 10 Batch Critical Transition Simulation
    elif intent == "what_if_critical_products":
        scen_params = routing.get("scenario_params", {})
        demand_pct = scen_params.get("demand_change_percent", 25.0)

        crit_res = get_products_becoming_critical(
            demand_change_percent=demand_pct,
            store_id=store_id
        )
        verified_context["critical_transitions"] = crit_res
        verified_context["demand_change_percent"] = demand_pct
        verified_context["results"] = crit_res
        evidence_payload = crit_res
        verified_context["assumptions"] = ["Scenario simulation under assumed demand change. Not a sales forecast."]

    # I. Phase 10 Cautious Root-Cause Diagnostic
    elif intent == "root_cause":
        pr_id = product_info.get("product_id")
        rc_res = analyze_possible_causes(
            product_id=pr_id,
            store_id=store_id
        )
        verified_context["root_cause_analysis"] = rc_res
        verified_context["results"] = [rc_res]
        evidence_payload = [rc_res]
        verified_context["assumptions"] = [rc_res.get("disclaimer", CAUSALITY_DISCLAIMER)]
        
    # J. Phase 11 Basket Intelligence & Opportunities
    elif intent == "basket_pairs":
        baskets = get_top_product_pairs(store_id=store_id, limit=20)
        verified_context["basket_pairs"] = baskets
        verified_context["results"] = baskets
        evidence_payload = baskets
        
    elif intent == "related_products":
        pr_id = product_info.get("product_id")
        pr_name = product_info.get("product_name", "Product")
        related = get_related_products(product_id=pr_id, store_id=store_id, limit=10)
        verified_context["related_products"] = related
        verified_context["product_name"] = pr_name
        verified_context["results"] = related
        evidence_payload = related
        
    elif intent == "top_opportunities":
        opps = get_top_opportunities(store_id=store_id, limit=10)
        verified_context["opportunities"] = opps
        verified_context["results"] = opps
        evidence_payload = opps
        
    elif intent == "product_opportunities":
        pr_id = product_info.get("product_id")
        all_opps = get_all_opportunities(store_id=store_id)
        pr_opps = [o for o in all_opps if o["product_id"] == pr_id]
        verified_context["opportunities"] = pr_opps
        verified_context["results"] = pr_opps
        evidence_payload = pr_opps
        
    elif intent == "decision_history":
        recs = get_saved_recommendations(store_id=store_id, limit=20)
        verified_context["decision_history"] = recs
        verified_context["results"] = recs
        evidence_payload = recs

    # 5. Phrasing Response via Gemini API or Fallback
    ai_answer = None
    if use_gemini and is_gemini_configured() and grounding.get("can_call_gemini", True):
        ai_answer = generate_grounded_response(question, verified_context, intent=intent)

    if ai_answer:
        final_answer = ai_answer
        generated_by_ai = True
        response_source = "gemini_grounded"
    else:
        final_answer = build_fallback_answer(intent, verified_context)
        generated_by_ai = False
        response_source = "deterministic_fallback"

    # Extract assumptions if present
    assumptions_list = verified_context.get("assumptions", [])
    if not assumptions_list and evidence_payload:
        first_ev = evidence_payload[0].get("evidence", {})
        assumptions_list = first_ev.get("assumptions", [])

    return {
        "success": True,
        "grounded": True,
        "status": grounding.get("status", "grounded"),
        "intent": intent,
        "question": question,
        "answer": final_answer,
        "evidence": evidence_payload,
        "assumptions": assumptions_list,
        "missing_fields": [],
        "available_alternatives": grounding.get("alternatives", []),
        "data_source": "StockSage deterministic analytics",
        "generated_by_ai": generated_by_ai,
        "response_source": response_source
    }
