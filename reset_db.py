"""Delete the database and start fresh. Uploaded files are kept.

Usage:  python reset_db.py
"""
import os

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE, "instance", "database.db")

if input("This deletes all users, products and orders. Type YES to continue: ").strip() != "YES":
    raise SystemExit("Cancelled. Nothing was changed.")

# Remove the file before the app opens it, so an old schema can never get in the way.
if os.path.exists(DB_PATH):
    os.remove(DB_PATH)

from farmbasket import create_app  # noqa: E402  (imported after the file is removed)

create_app()
print("Database reset. Starter areas were added.")
print("Register buyer and farmer accounts on the site, then run: python seed_admin.py")
