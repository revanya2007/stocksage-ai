"""
StockSage AI - Phase 10 Real Cases Validation Script
Validates 12 representative What-If scenario and Root-Cause questions.
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from src.copilot_service import answer_question
from src.scenario_engine import simulate_product_scenario, get_products_becoming_critical
from src.root_cause_engine import analyze_possible_causes

TEST_QUESTIONS = [
    # Scenario Simulations
    ("1. What if demand for Milk 1L increases by 20%?", "what_if"),
    ("2. What if sales for Basmati Rice 5kg drop by 30%?", "what_if"),
    ("3. What if demand for Olive Oil 500ml increases by 50%?", "what_if"),
    ("4. Which products would become critical stock-out risk if overall demand increases by 25%?", "what_if_critical_products"),
    ("5. What if demand for Organic Eggs 12pk increases by 200%?", "what_if"),
    ("6. What if demand for Whole Wheat Bread increases by 400%?", "bounds_error_high"),
    ("7. What if stock for Milk 1L decreases by 1000 units?", "bounds_error_negative"),
    
    # Root Cause Diagnostics
    ("8. Why are Milk 1L sales dropping at Central Market?", "root_cause"),
    ("9. What is the root cause for Basmati Rice 5kg stock-out risk?", "root_cause"),
    ("10. Why is Olive Oil 500ml flagged as a priority item?", "root_cause"),
    ("11. Why is Sunflower Oil 1L non-moving?", "root_cause"),
    
    # ML Forecast Refusal Check
    ("12. What will sales for Milk 1L be next month?", "unsupported_forecast_refusal")
]


def run_validation():
    print("================================================================")
    print("       STOCKSAGE AI - PHASE 10 REAL CASES VALIDATION            ")
    print("================================================================\n")
    
    success_count = 0
    total_count = len(TEST_QUESTIONS)

    for q_text, expected_mode in TEST_QUESTIONS:
        print(f"----------------------------------------------------------------")
        print(f"QUERY: {q_text}")
        
        if expected_mode == "bounds_error_high":
            try:
                res = simulate_product_scenario(product_id=1, demand_change_percent=400.0)
                print(f"FAILED: Expected ValueError for > +300% demand change, but succeeded.")
            except ValueError as ve:
                print(f"PASSED: Bounded error caught successfully -> '{ve}'")
                success_count += 1
            continue

        if expected_mode == "bounds_error_negative":
            try:
                res = simulate_product_scenario(product_id=1, store_id=1, stock_change_units=-1000)
                print(f"FAILED: Expected ValueError for negative resulting stock, but succeeded.")
            except ValueError as ve:
                print(f"PASSED: Bounded error caught successfully -> '{ve}'")
                success_count += 1
            continue

        res = answer_question(q_text, use_gemini=False)
        print(f"Grounded Status: {res.get('status')}")
        print(f"Intent: {res.get('intent')}")
        print(f"Answer Output:\n{res.get('answer')}")
        
        if expected_mode == "unsupported_forecast_refusal":
            if res.get("status") == "missing_data" and "sales_forecast_model" in res.get("missing_fields", []):
                print("PASSED: ML Forecast refusal properly grounded!")
                success_count += 1
            else:
                print("FAILED: Did not trigger expected sales_forecast_model refusal!")
        else:
            if res.get("success"):
                print("PASSED: Success grounded response!")
                success_count += 1
            else:
                print(f"FAILED: Grounding refusal or error -> {res.get('answer')}")
        print()

    print("================================================================")
    print(f"VALIDATION SUMMARY: {success_count}/{total_count} Passed ({success_count/total_count*100:.1f}%)")
    print("================================================================")


if __name__ == "__main__":
    run_validation()
