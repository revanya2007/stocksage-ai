import sys
import os
from pathlib import Path

# Add project root to Python path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# Force UTF-8 output for Windows console
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from src.data_loader import generate_all_data, SCENARIO_PRODUCTS
from src.database import get_table_counts, get_connection

def main():
    print("============================================================")
    print("       StockSage AI — Phase 2 Data Initialization           ")
    print("============================================================")

    try:
        stores, products, sales, inventory = generate_all_data()

        print(f"✓ Generated {len(stores)} stores")
        print(f"✓ Generated {len(products)} products")
        print(f"✓ Generated {len(inventory)} inventory records")
        print(f"✓ Generated {len(sales):,} sales transaction lines")
        print("✓ Data validation passed (math, keys, non-negativity & scenario rules)")
        print("✓ CSV files saved in data/")
        print("✓ SQLite database initialized: data/stocksage.db")

        # Foreign Key Verification
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("PRAGMA foreign_key_check;")
        fk_errors = cursor.fetchall()
        conn.close()

        if fk_errors:
            print(f"❌ Foreign Key Violations: {fk_errors}")
            sys.exit(1)
        else:
            print("✓ SQLite Foreign Key Check passed (0 violations)")

        print("\nTable Row Counts:")
        counts = get_table_counts()
        for table, count in counts.items():
            print(f"  - {table:<16} : {count:,}")

        print("\nInjected Scenario Products Registry:")
        for scenario, p_ids in SCENARIO_PRODUCTS.items():
            print(f"  - {scenario:<16} : Product IDs {p_ids}")

        print("\n============================================================")
        print("✓ Phase 2 Data Initialization Complete Successfully!")
        print("============================================================")

    except Exception as e:
        print(f"\n❌ Data Initialization Failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
