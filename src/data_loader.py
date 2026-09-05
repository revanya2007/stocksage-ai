import csv
import sqlite3
import random
from datetime import datetime, timedelta
from pathlib import Path
from src.database import get_db_path, get_connection, initialize_database, reset_database

RANDOM_SEED = 42
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

# Scenario Registry for deterministic test cases
SCENARIO_PRODUCTS = {
    "stockout": [1, 9, 17],       # Milk 1L, Bread White 400g, Coca-Cola 750ml
    "overstock": [31, 37, 26],     # Shampoo 180ml, Detergent Powder 1kg, Premium Chocolate Box
    "non_moving": [34, 38],        # Herbal Hair Oil 200ml, Specialty Cleaner 500ml
    "slow_moving": [20, 44],       # Green Tea 100g, Olive Oil 500ml
    "sales_spike": [15, 10],       # Mango Juice 1L, Bread Wheat 400g
    "sales_drop": [16, 32]         # Orange Juice 1L, Soap Bar Pack
}

def set_seed(seed=RANDOM_SEED):
    """Set random seed for reproducibility."""
    random.seed(seed)

def generate_stores() -> list[dict]:
    """Generate exactly 3 retail stores."""
    return [
        {"store_id": 1, "store_name": "Central Market", "location": "Downtown"},
        {"store_id": 2, "store_name": "Riverside Store", "location": "Riverside"},
        {"store_id": 3, "store_name": "City Square Mart", "location": "City Centre"}
    ]

def generate_products() -> list[dict]:
    """Generate 60 realistic retail products across 8 categories with INR prices."""
    products_raw = [
        # Dairy (IDs 1-7)
        (1, "Milk 1L", "Dairy", 64.0),
        (2, "Curd 500g", "Dairy", 35.0),
        (3, "Butter 200g", "Dairy", 115.0),
        (4, "Cheese Slices 200g", "Dairy", 140.0),
        (5, "Paneer 200g", "Dairy", 95.0),
        (6, "Flavored Milk 200ml", "Dairy", 30.0),
        (7, "Condensed Milk 400g", "Dairy", 130.0),

        # Bakery (IDs 8-14)
        (8, "Eggs (12 pack)", "Bakery", 84.0),
        (9, "Bread White 400g", "Bakery", 40.0),
        (10, "Bread Wheat 400g", "Bakery", 45.0),
        (11, "Burger Buns (4 pack)", "Bakery", 35.0),
        (12, "Fruit Cake 250g", "Bakery", 90.0),
        (13, "Garlic Bread 200g", "Bakery", 60.0),
        (14, "Croissant (2 pack)", "Bakery", 80.0),

        # Beverages (IDs 15-21)
        (15, "Mango Juice 1L", "Beverages", 110.0),
        (16, "Orange Juice 1L", "Beverages", 120.0),
        (17, "Coca-Cola 750ml", "Beverages", 45.0),
        (18, "Mineral Water 1L", "Beverages", 20.0),
        (19, "Energy Drink 250ml", "Beverages", 110.0),
        (20, "Green Tea 100g", "Beverages", 220.0),
        (21, "Instant Coffee 100g", "Beverages", 310.0),

        # Snacks (IDs 22-28)
        (22, "Potato Chips 100g", "Snacks", 30.0),
        (23, "Cream Biscuits 120g", "Snacks", 25.0),
        (24, "Salted Peanuts 150g", "Snacks", 50.0),
        (25, "Roasted Almonds 200g", "Snacks", 280.0),
        (26, "Premium Chocolate Box", "Snacks", 450.0),
        (27, "Popcorn Pack 100g", "Snacks", 40.0),
        (28, "Wafer Roll 150g", "Snacks", 75.0),

        # Personal Care (IDs 29-35)
        (29, "Toothpaste 150g", "Personal Care", 95.0),
        (30, "Toothbrush Soft", "Personal Care", 40.0),
        (31, "Shampoo 180ml", "Personal Care", 175.0),
        (32, "Soap Bar Pack (3x100g)", "Personal Care", 120.0),
        (33, "Hand Wash 250ml", "Personal Care", 85.0),
        (34, "Herbal Hair Oil 200ml", "Personal Care", 190.0),
        (35, "Face Wash 100ml", "Personal Care", 145.0),

        # Household (IDs 36-41)
        (36, "Dishwash Liquid 500ml", "Household", 105.0),
        (37, "Detergent Powder 1kg", "Household", 160.0),
        (38, "Specialty Cleaner 500ml", "Household", 210.0),
        (39, "Floor Cleaner 1L", "Household", 140.0),
        (40, "Tissue Paper Box", "Household", 65.0),
        (41, "Garbage Bags 30s", "Household", 90.0),

        # Grocery (IDs 42-50)
        (42, "Basmati Rice 5kg", "Grocery", 620.0),
        (43, "Wheat Flour 5kg", "Grocery", 240.0),
        (44, "Olive Oil 500ml", "Grocery", 580.0),
        (45, "Refined Oil 1L", "Grocery", 135.0),
        (46, "Sugar 1kg", "Grocery", 48.0),
        (47, "Toor Dal 1kg", "Grocery", 165.0),
        (48, "Salt 1kg", "Grocery", 24.0),
        (49, "Spices Mix Pack", "Grocery", 85.0),
        (50, "Tea Powder 500g", "Grocery", 260.0),

        # Fresh Produce (IDs 51-60)
        (51, "Apples 1kg", "Fresh Produce", 180.0),
        (52, "Bananas 1kg", "Fresh Produce", 50.0),
        (53, "Tomatoes 1kg", "Fresh Produce", 40.0),
        (54, "Onions 1kg", "Fresh Produce", 35.0),
        (55, "Potatoes 1kg", "Fresh Produce", 30.0),
        (56, "Oranges 1kg", "Fresh Produce", 120.0),
        (57, "Grapes 500g", "Fresh Produce", 90.0),
        (58, "Spinach Pack 250g", "Fresh Produce", 25.0),
        (59, "Carrots 500g", "Fresh Produce", 35.0),
        (60, "Cucumber 1kg", "Fresh Produce", 40.0),
    ]

    return [
        {
            "product_id": p[0],
            "product_name": p[1],
            "category": p[2],
            "selling_price": p[3]
        }
        for p in products_raw
    ]

def generate_sales(stores: list[dict], products: list[dict]) -> list[dict]:
    """
    Generate 120 days of sales history with multi-product transactions and injected scenarios.
    Start date: 2026-05-08
    End date: 2026-09-04
    """
    set_seed(RANDOM_SEED)

    start_date = datetime(2026, 5, 8)
    end_date = datetime(2026, 9, 4)
    total_days = (end_date - start_date).days + 1  # 120 days

    prices_dict = {p["product_id"]: p["selling_price"] for p in products}
    product_ids = [p["product_id"] for p in products]

    # Assign base popularity
    base_popularity = {}
    for p_id in product_ids:
        if p_id in SCENARIO_PRODUCTS["stockout"]:
            base_popularity[p_id] = 2.5
        elif p_id in SCENARIO_PRODUCTS["overstock"]:
            base_popularity[p_id] = 0.4
        elif p_id in SCENARIO_PRODUCTS["non_moving"]:
            base_popularity[p_id] = 0.2
        elif p_id in SCENARIO_PRODUCTS["slow_moving"]:
            base_popularity[p_id] = 0.3
        elif p_id in SCENARIO_PRODUCTS["sales_spike"]:
            base_popularity[p_id] = 1.2
        elif p_id in SCENARIO_PRODUCTS["sales_drop"]:
            base_popularity[p_id] = 1.4
        else:
            base_popularity[p_id] = round(random.uniform(0.6, 1.8), 2)

    store_multipliers = {1: 1.2, 2: 1.0, 3: 0.85}
    sales_lines = []
    transaction_counter = 1

    for day_offset in range(total_days):
        current_date = start_date + timedelta(days=day_offset)
        date_str = current_date.strftime("%Y-%m-%d")
        is_weekend = current_date.weekday() in [5, 6]
        weekend_mult = 1.20 if is_weekend else 1.0

        for store in stores:
            store_id = store["store_id"]
            store_mult = store_multipliers[store_id]

            num_txns = int(random.randint(25, 40) * store_mult * weekend_mult)

            for _ in range(num_txns):
                txn_id = f"TXN{transaction_counter:06d}"
                transaction_counter += 1

                basket_size = random.randint(1, 5)
                basket_products = random.sample(product_ids, basket_size)

                for p_id in basket_products:
                    # Non-Moving Scenario C: Final 30 days (day_offset >= 90) must have 0 sales
                    if p_id in SCENARIO_PRODUCTS["non_moving"] and day_offset >= 90:
                        continue

                    # Slow-Moving Scenario D: Final 30 days (day_offset >= 90) very low sales probability
                    if p_id in SCENARIO_PRODUCTS["slow_moving"] and day_offset >= 90:
                        if random.random() > 0.015:  # ~1.5% chance to sell
                            continue

                    pop = base_popularity[p_id]
                    mult = store_mult * weekend_mult

                    # Injected Scenario E: Sales Spike in latest 7 days (day_offset >= 113)
                    if p_id in SCENARIO_PRODUCTS["sales_spike"] and day_offset >= 113:
                        mult *= 2.5  # Spike boost

                    # Injected Scenario F: Sales Drop in latest 7 days (day_offset >= 113)
                    if p_id in SCENARIO_PRODUCTS["sales_drop"] and day_offset >= 113:
                        mult *= 0.20 # Drop reduction

                    # Quantity calculation
                    qty_mean = pop * mult * 0.8
                    if qty_mean < 0.5:
                        qty = 1 if random.random() < qty_mean else 0
                    else:
                        qty = max(0, int(round(random.gauss(qty_mean, 0.6))))

                    if qty > 0:
                        price = prices_dict[p_id]
                        sales_amount = round(qty * price, 2)
                        sales_lines.append({
                            "transaction_id": txn_id,
                            "date": date_str,
                            "store_id": store_id,
                            "product_id": p_id,
                            "quantity_sold": qty,
                            "sales_amount": sales_amount
                        })

    return sales_lines

def generate_inventory(stores: list[dict], products: list[dict]) -> list[dict]:
    """Generate inventory records (1 per store x product) aligned with test scenarios."""
    last_updated_date = "2026-09-04"
    inventory_rows = []

    for store in stores:
        store_id = store["store_id"]
        for p in products:
            p_id = p["product_id"]

            # Scenario A: Stock-out Risk -> low current stock (10 to 25 units)
            if p_id in SCENARIO_PRODUCTS["stockout"]:
                current_stock = random.randint(10, 25)
                reorder_level = 35

            # Scenario B: Overstock -> high stock (120 to 240 units)
            elif p_id in SCENARIO_PRODUCTS["overstock"]:
                current_stock = random.randint(140, 240)
                reorder_level = 20

            # Scenario C: Non-Moving -> substantial inventory (45 to 80 units)
            elif p_id in SCENARIO_PRODUCTS["non_moving"]:
                current_stock = random.randint(45, 80)
                reorder_level = 15

            # Scenario D: Slow-Moving -> substantial inventory (60 to 95 units)
            elif p_id in SCENARIO_PRODUCTS["slow_moving"]:
                current_stock = random.randint(60, 95)
                reorder_level = 15

            # Scenario E: Sales Spike -> moderate stock
            elif p_id in SCENARIO_PRODUCTS["sales_spike"]:
                current_stock = random.randint(30, 50)
                reorder_level = 40

            # Scenario F: Sales Drop -> moderate/high inventory
            elif p_id in SCENARIO_PRODUCTS["sales_drop"]:
                current_stock = random.randint(70, 110)
                reorder_level = 25

            # Normal Products
            else:
                current_stock = random.randint(30, 90)
                reorder_level = random.randint(15, 30)

            inventory_rows.append({
                "store_id": store_id,
                "product_id": p_id,
                "current_stock": current_stock,
                "reorder_level": reorder_level,
                "last_updated": last_updated_date
            })

    return inventory_rows

def validate_data(stores: list[dict], products: list[dict], sales: list[dict], inventory: list[dict]):
    """Perform rigorous data quality and sanity checks before database load."""

    # 1. Unique Store IDs
    store_ids = [s["store_id"] for s in stores]
    if len(set(store_ids)) != len(stores):
        raise ValueError("Validation Failed: Duplicate store_id found.")

    # 2. Unique Product IDs
    product_ids = [p["product_id"] for p in products]
    if len(set(product_ids)) != len(products):
        raise ValueError("Validation Failed: Duplicate product_id found.")

    # 3. Unique Inventory Composite Key (store_id + product_id)
    inv_keys = [(i["store_id"], i["product_id"]) for i in inventory]
    if len(set(inv_keys)) != len(inventory):
        raise ValueError("Validation Failed: Duplicate (store_id, product_id) found in inventory.")

    # 4. Store count check
    if len(stores) != 3:
        raise ValueError(f"Validation Failed: Expected exactly 3 stores, found {len(stores)}.")

    # 5. Inventory count check = stores * products
    expected_inv_count = len(stores) * len(products)
    if len(inventory) != expected_inv_count:
        raise ValueError(f"Validation Failed: Inventory count mismatch ({len(inventory)} vs expected {expected_inv_count}).")

    # 6. Foreign Key Validity
    valid_stores = set(store_ids)
    valid_products = set(product_ids)
    prices_dict = {p["product_id"]: p["selling_price"] for p in products}

    for line in sales:
        if line["store_id"] not in valid_stores:
            raise ValueError("Validation Failed: Unknown store_id in sales.")
        if line["product_id"] not in valid_products:
            raise ValueError("Validation Failed: Unknown product_id in sales.")
        if line["quantity_sold"] < 0:
            raise ValueError("Validation Failed: Negative quantity_sold in sales.")
        if line["sales_amount"] < 0:
            raise ValueError("Validation Failed: Negative sales_amount in sales.")

        expected_amount = round(line["quantity_sold"] * prices_dict[line["product_id"]], 2)
        if abs(line["sales_amount"] - expected_amount) > 0.01:
            raise ValueError(f"Validation Failed: Sales amount mismatch ({line['sales_amount']} vs {expected_amount}).")

    for inv in inventory:
        if inv["store_id"] not in valid_stores or inv["product_id"] not in valid_products:
            raise ValueError("Validation Failed: Unknown store_id or product_id in inventory.")
        if inv["current_stock"] < 0 or inv["reorder_level"] < 0:
            raise ValueError("Validation Failed: Negative stock/reorder in inventory.")

    # 7. Non-moving Scenario Validation: Final 30 days must have 0 sales
    cutoff_30d = (datetime(2026, 9, 4) - timedelta(days=30)).strftime("%Y-%m-%d")
    for p_id in SCENARIO_PRODUCTS["non_moving"]:
        recent_sales = [s for s in sales if s["product_id"] == p_id and s["date"] > cutoff_30d]
        if sum(s["quantity_sold"] for s in recent_sales) > 0:
            raise ValueError(f"Validation Failed: Non-moving product ID {p_id} has sales in final 30 days.")

    # 8. Sales Spike / Drop Sanity Check
    cutoff_7d = (datetime(2026, 9, 4) - timedelta(days=7)).strftime("%Y-%m-%d")
    for p_id in SCENARIO_PRODUCTS["sales_spike"]:
        hist_sales = [s["quantity_sold"] for s in sales if s["product_id"] == p_id and s["date"] <= cutoff_7d]
        rec_sales = [s["quantity_sold"] for s in sales if s["product_id"] == p_id and s["date"] > cutoff_7d]
        hist_7d_avg = (sum(hist_sales) / 113.0) * 7.0 if hist_sales else 0
        rec_7d_total = sum(rec_sales)
        if rec_7d_total <= hist_7d_avg:
            raise ValueError(f"Validation Failed: Spike product {p_id} recent sales ({rec_7d_total}) <= baseline ({hist_7d_avg}).")

    for p_id in SCENARIO_PRODUCTS["sales_drop"]:
        hist_sales = [s["quantity_sold"] for s in sales if s["product_id"] == p_id and s["date"] <= cutoff_7d]
        rec_sales = [s["quantity_sold"] for s in sales if s["product_id"] == p_id and s["date"] > cutoff_7d]
        hist_7d_avg = (sum(hist_sales) / 113.0) * 7.0 if hist_sales else 0
        rec_7d_total = sum(rec_sales)
        if rec_7d_total >= hist_7d_avg:
            raise ValueError(f"Validation Failed: Drop product {p_id} recent sales ({rec_7d_total}) >= baseline ({hist_7d_avg}).")

def save_csvs(stores: list[dict], products: list[dict], sales: list[dict], inventory: list[dict]):
    """Save clean CSV files without index columns to data/ directory."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    def _write(filepath, fieldnames, rows):
        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    _write(DATA_DIR / "stores.csv", ["store_id", "store_name", "location"], stores)
    _write(DATA_DIR / "products.csv", ["product_id", "product_name", "category", "selling_price"], products)
    _write(DATA_DIR / "sales.csv", ["transaction_id", "date", "store_id", "product_id", "quantity_sold", "sales_amount"], sales)
    _write(DATA_DIR / "inventory.csv", ["store_id", "product_id", "current_stock", "reorder_level", "last_updated"], inventory)

def load_to_sqlite(stores: list[dict], products: list[dict], sales: list[dict], inventory: list[dict]):
    """Reset SQLite database and load validated data into corresponding tables."""
    reset_database()
    conn = get_connection()
    cursor = conn.cursor()

    cursor.executemany("INSERT INTO stores (store_id, store_name, location) VALUES (:store_id, :store_name, :location);", stores)
    cursor.executemany("INSERT INTO products (product_id, product_name, category, selling_price) VALUES (:product_id, :product_name, :category, :selling_price);", products)
    cursor.executemany("INSERT INTO sales (transaction_id, date, store_id, product_id, quantity_sold, sales_amount) VALUES (:transaction_id, :date, :store_id, :product_id, :quantity_sold, :sales_amount);", sales)
    cursor.executemany("INSERT INTO inventory (store_id, product_id, current_stock, reorder_level, last_updated) VALUES (:store_id, :product_id, :current_stock, :reorder_level, :last_updated);", inventory)

    cursor.execute("PRAGMA foreign_key_check;")
    fk_errors = cursor.fetchall()
    if fk_errors:
        conn.close()
        raise ValueError(f"SQLite Foreign Key Check Failed: {fk_errors}")

    conn.commit()
    conn.close()

def generate_all_data():
    """Main execution function to generate, validate, save, and load synthetic retail data."""
    set_seed(RANDOM_SEED)

    stores = generate_stores()
    products = generate_products()
    sales = generate_sales(stores, products)
    inventory = generate_inventory(stores, products)

    validate_data(stores, products, sales, inventory)
    save_csvs(stores, products, sales, inventory)
    load_to_sqlite(stores, products, sales, inventory)

    return stores, products, sales, inventory
