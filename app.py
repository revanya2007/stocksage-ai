"""
StockSage AI - Flask Application Controller (Phase 7)
"""

from flask import Flask, render_template, jsonify, request
from src.database import get_connection
from src.decision_engine import (
    get_all_issue_candidates,
    get_ranked_issues,
    get_top_attention_items,
    get_business_impact_summary,
    get_issue_counts,
    ISSUE_LABEL_MAP
)
from src.recommendation_engine import (
    generate_top_recommendations,
    generate_recommendation,
    get_saved_recommendations,
    sync_current_recommendations,
    update_manager_action
)
from src.basket_engine import get_top_product_pairs
from src.opportunity_engine import get_top_opportunities
from datetime import datetime

app = Flask(__name__)


def get_dashboard_data():
    """Fetch all real dashboard metrics and recommendations from SQLite & decision pipeline."""
    conn = get_connection()
    cursor = conn.cursor()

    # 1. Latest Dataset-Day Sales
    cursor.execute("SELECT MAX(date) FROM sales;")
    max_date_row = cursor.fetchone()
    max_date = max_date_row[0] if max_date_row else None

    latest_sales_amount = 0.0
    if max_date:
        cursor.execute("SELECT SUM(sales_amount) FROM sales WHERE date = ?;", (max_date,))
        res = cursor.fetchone()
        if res and res[0] is not None:
            latest_sales_amount = float(res[0])

    # 2. 30-Day Sales Trend Summary
    cursor.execute("SELECT SUM(sales_amount), SUM(quantity_sold) FROM sales;")
    total_sales_row = cursor.fetchone()
    total_sales_30d = float(total_sales_row[0]) if total_sales_row and total_sales_row[0] else 0.0
    total_units_30d = int(total_sales_row[1]) if total_sales_row and total_sales_row[1] else 0

    # 3. Top 5 Performing Products by 30-day Revenue
    cursor.execute("""
    SELECT p.product_name, p.category, SUM(s.quantity_sold) as total_units, SUM(s.sales_amount) as total_revenue
    FROM sales s
    JOIN products p ON s.product_id = p.product_id
    GROUP BY p.product_id
    ORDER BY total_revenue DESC
    LIMIT 5;
    """)
    top_products = [dict(r) for r in cursor.fetchall()]
    conn.close()

    # 4. Phase 6C Candidates & Decision Summaries
    candidates = get_all_issue_candidates(as_of_date=max_date)
    impact_summary = get_business_impact_summary(as_of_date=max_date, candidates=candidates)
    issue_counts_data = get_issue_counts(as_of_date=max_date, candidates=candidates)
    cand_counts = issue_counts_data.get("candidate_issue_counts", {})

    products_at_risk = cand_counts.get("stockout_risk", 0)
    slow_non_moving = cand_counts.get("slow_moving", 0) + cand_counts.get("non_moving", 0)
    sales_anomalies = cand_counts.get("sales_spike", 0) + cand_counts.get("sales_drop", 0)
    revenue_at_risk = impact_summary.get("estimated_revenue_at_risk", 0.0)

    # 5. Top 5 Actionable Recommendations
    top_recommendations = generate_top_recommendations(as_of_date=max_date, limit=5, candidates=candidates)

    # 6. Inventory Status Counts (Total store-product pairs = 150)
    total_inventory_items = 150
    at_risk_cnt = products_at_risk
    overstock_cnt = cand_counts.get("overstock", 0)
    slow_cnt = cand_counts.get("slow_moving", 0)
    non_moving_cnt = cand_counts.get("non_moving", 0)
    healthy_cnt = max(total_inventory_items - (at_risk_cnt + overstock_cnt + slow_cnt + non_moving_cnt), 0)

    inventory_status = {
        "total": total_inventory_items,
        "at_risk": at_risk_cnt,
        "overstock": overstock_cnt,
        "slow_moving": slow_cnt,
        "non_moving": non_moving_cnt,
        "healthy": healthy_cnt
    }

    return {
        "max_date": max_date,
        "latest_sales": latest_sales_amount,
        "products_at_risk": products_at_risk,
        "slow_non_moving": slow_non_moving,
        "sales_anomalies": sales_anomalies,
        "revenue_at_risk": revenue_at_risk,
        "top_recommendations": top_recommendations,
        "total_sales_30d": total_sales_30d,
        "total_units_30d": total_units_30d,
        "top_products": top_products,
        "inventory_status": inventory_status
    }


@app.route("/")
def dashboard():
    data = get_dashboard_data()
    return render_template("index.html", active_page="dashboard", d=data)


@app.route("/inventory")
def inventory():
    conn = get_connection()
    cursor = conn.cursor()

    # Fetch all store inventory items enriched with product and store metadata
    cursor.execute("""
    SELECT i.store_id, st.store_name, i.product_id, p.product_name, p.category,
           i.current_stock, i.reorder_level
    FROM inventory i
    JOIN stores st ON i.store_id = st.store_id
    JOIN products p ON i.product_id = p.product_id
    ORDER BY i.store_id, i.product_id;
    """)
    inv_rows = [dict(r) for r in cursor.fetchall()]

    # Fetch 30-day sales velocity per store-product
    cursor.execute("""
    SELECT store_id, product_id, SUM(quantity_sold) as units_30d
    FROM sales
    GROUP BY store_id, product_id;
    """)
    sales_map = {(r["store_id"], r["product_id"]): r["units_30d"] for r in cursor.fetchall()}
    conn.close()

    candidates = get_all_issue_candidates()
    cand_map = {}
    for c in candidates:
        key = (c["store_id"], c["product_id"])
        if key not in cand_map or c["priority"]["score"] > cand_map[key]["priority"]["score"]:
            cand_map[key] = c

    inventory_items = []
    at_risk_count = 0
    overstock_count = 0
    slow_count = 0
    healthy_count = 0

    for row in inv_rows:
        st_id = row["store_id"]
        pr_id = row["product_id"]
        stock = row["current_stock"]
        units_30d = sales_map.get((st_id, pr_id), 0)
        ads = units_30d / 30.0

        if stock == 0:
            days_rem_display = "0 days (Out of Stock)"
            days_rem_val = 0.0
        elif ads > 0:
            days_rem_val = round(stock / ads, 1)
            days_rem_display = f"{days_rem_val} days"
        else:
            days_rem_val = None
            days_rem_display = "Not calculable — no recent sales"

        cand = cand_map.get((st_id, pr_id))
        if cand:
            rec_obj = generate_recommendation(cand)
            status_label = cand.get("issue_label", cand["issue_type"])
            badge_class = "badge-critical" if cand["issue_type"] == "stockout_risk" else (
                "badge-high" if cand["issue_type"] == "overstock" else "badge-warning"
            )
            priority_score = cand["priority"]["score"]
            priority_label = cand["priority"]["label"]
            evidence_json = rec_obj
        else:
            status_label = "Healthy"
            badge_class = "badge-healthy"
            priority_score = 0
            priority_label = "Healthy"
            evidence_json = {
                "product_name": row["product_name"],
                "store_name": row["store_name"],
                "category": row["category"],
                "issue_label": "Healthy",
                "priority_score": 0,
                "recommendation": f"Inventory for {row['product_name']} is within healthy operational parameters.",
                "evidence": {
                    "metrics": [
                        {"label": "Current Stock", "value": stock, "unit": "units"},
                        {"label": "30-Day Units Sold", "value": units_30d, "unit": "units"}
                    ],
                    "calculation": {"label": "Stock Status", "formula": "Normal inventory coverage"},
                    "confidence": "High",
                    "assumptions": ["Stock levels match expected demand."]
                }
            }

        if cand and cand["issue_type"] == "stockout_risk":
            at_risk_count += 1
        elif cand and cand["issue_type"] == "overstock":
            overstock_count += 1
        elif cand and cand["issue_type"] in ["slow_moving", "non_moving"]:
            slow_count += 1
        else:
            healthy_count += 1

        inventory_items.append({
            "store_id": st_id,
            "store_name": row["store_name"],
            "product_id": pr_id,
            "product_name": row["product_name"],
            "category": row["category"],
            "current_stock": stock,
            "reorder_level": row["reorder_level"],
            "units_30d": units_30d,
            "ads": round(ads, 2),
            "days_remaining_display": days_rem_display,
            "days_remaining_val": days_rem_val,
            "status_label": status_label,
            "badge_class": badge_class,
            "priority_score": priority_score,
            "priority_label": priority_label,
            "evidence_json": evidence_json
        })

    kpis = {
        "total_skus": len(inventory_items),
        "at_risk": at_risk_count,
        "overstock": overstock_count,
        "slow_moving": slow_count,
        "healthy": healthy_count
    }

    return render_template("inventory.html", active_page="inventory", items=inventory_items, kpis=kpis)


@app.route("/copilot")
def copilot():
    return render_template("copilot.html", active_page="copilot")


@app.route("/sales")
def sales():
    baskets = get_top_product_pairs(limit=10)
    opportunities = get_top_opportunities(limit=10)
    return render_template("sales.html", active_page="sales", baskets=baskets, opportunities=opportunities)

@app.route("/api/recommendations/<int:rec_id>/action", methods=["POST"])
def api_recommendation_action(rec_id):
    data = request.get_json(silent=True) or {}
    action = data.get("action")
    note = data.get("note")
    if not action:
        return jsonify({"success": False, "message": "Action is required."}), 400
    try:
        update_manager_action(rec_id, action, note)
        return jsonify({
            "success": True,
            "recommendation_id": rec_id,
            "manager_action": action,
            "action_timestamp": datetime.now().isoformat()
        })
    except ValueError as ve:
        return jsonify({"success": False, "message": str(ve)}), 400
    except Exception as e:
        return jsonify({"success": False, "message": f"Action error: {str(e)}"}), 500


from src.scenario_engine import simulate_product_scenario


@app.route("/simulator")
def simulator():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT store_id, store_name FROM stores ORDER BY store_id;")
    stores = [dict(r) for r in cursor.fetchall()]
    cursor.execute("SELECT product_id, product_name, category FROM products ORDER BY product_id;")
    products = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return render_template("simulator.html", active_page="simulator", stores=stores, products=products)


@app.route("/api/simulate", methods=["POST"])
def api_simulate():
    data = request.get_json(silent=True) or {}
    product_id = data.get("product_id")
    store_id = data.get("store_id")
    try:
        demand_change_percent = float(data.get("demand_change_percent", 0.0))
        stock_change_units = int(data.get("stock_change_units", 0))
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "Invalid input numbers."}), 400

    if not product_id:
        return jsonify({"success": False, "message": "Please select a product for the simulation."}), 400

    try:
        sim_res = simulate_product_scenario(
            product_id=int(product_id),
            store_id=int(store_id) if store_id and str(store_id).isdigit() else None,
            demand_change_percent=demand_change_percent,
            stock_change_units=stock_change_units
        )
        return jsonify({
            "success": True,
            "simulation": sim_res
        })
    except ValueError as ve:
        return jsonify({"success": False, "message": str(ve)}), 400
    except Exception as e:
        return jsonify({"success": False, "message": f"Simulation error: {str(e)}"}), 500


@app.route("/history")
def history():
    saved_recs = get_saved_recommendations(limit=20)
    return render_template("history.html", active_page="history", recs=saved_recs)


from src.copilot_service import answer_question

# LOCAL API ENDPOINTS (OPTIONAL / INTEGRATION)
@app.route("/api/dashboard", methods=["GET"])
def api_dashboard():
    return jsonify(get_dashboard_data())


@app.route("/api/recommendations/top", methods=["GET"])
def api_top_recommendations():
    limit = request.args.get("limit", 5, type=int)
    store_id = request.args.get("store_id", None, type=int)
    return jsonify(generate_top_recommendations(store_id=store_id, limit=limit))


@app.route("/api/copilot", methods=["POST"])
def api_copilot():
    data = request.get_json(silent=True) or {}
    question = data.get("question", "").strip()

    if not question:
        return jsonify({
            "success": False,
            "error_type": "empty_question",
            "message": "Please enter a valid retail sales or inventory question.",
            "answer": "Please enter a question.",
            "evidence": [],
            "generated_by_ai": False,
            "response_source": "validation_error"
        }), 400

    result = answer_question(question)
    return jsonify(result)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
