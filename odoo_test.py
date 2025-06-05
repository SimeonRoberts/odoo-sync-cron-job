import xmlrpc.client
import os
from dotenv import load_dotenv

load_dotenv()  # Ensure .env values are loaded

ODOO_URL = os.getenv("ODOO_URL")
ODOO_DB = os.getenv("ODOO_DB")
ODOO_USER = os.getenv("ODOO_USER")
ODOO_PASSWORD = os.getenv("ODOO_PASSWORD")

try:
    common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common")
    uid = common.authenticate(ODOO_DB, ODOO_USER, ODOO_PASSWORD, {})

    if uid:
        print(f"✅ Successfully connected to Odoo! UID: {uid}")
    else:
        print("❌ Authentication failed. Check your URL, DB, username, or password.")

except Exception as e:
    print(f"❌ Error connecting to Odoo: {e}")