import sqlite3
import os

# Check both root directory and instance folder for the database
db_path = 'instance/crowdfund.db' if os.path.exists('instance/crowdfund.db') else 'crowdfund.db'

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

for column in [("receipt_no", "VARCHAR(20)"), ("txn_hash", "VARCHAR(64)")]:
    try:
        cursor.execute(f"ALTER TABLE donation ADD COLUMN {column[0]} {column[1]};")
        print(f"Added column: {column[0]}")
    except sqlite3.OperationalError:
        print(f"Column {column[0]} already exists.")

conn.commit()
conn.close()
print("Database schema successfully patched.")